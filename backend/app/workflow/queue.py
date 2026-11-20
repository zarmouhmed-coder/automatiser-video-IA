"""File d'attente persistante (SQLite) avec un exécuteur en arrière-plan.

- jusqu'à 3 workflows (épisodes) en parallèle (réglable, max 3) ;
- un seul rendu lourd (prévisualisation / rendu final) à la fois ;
- reprise après redémarrage : les tâches « running » repassent en file ;
- annulation propre (coopérative), pause/reprise globale, aucune relance automatique en boucle.
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable

from .. import db
from ..core import StudioError, get_settings, log


class Cancelled(Exception):
    pass


class JobContext:
    def __init__(self, job: dict[str, Any]):
        self.job = job
        self.id = job["id"]
        self.params = db.jloads(job["params"], {})
        self._last_progress = 0.0
        self.started = time.monotonic()

    def cancelled(self) -> bool:
        r = db.row("SELECT cancel_requested FROM jobs WHERE id=?", (self.id,))
        return bool(r and r["cancel_requested"])

    def check(self, timeout_s: float | None = None) -> None:
        if self.cancelled():
            raise Cancelled()
        if timeout_s and time.monotonic() - self.started > timeout_s:
            raise StudioError(f"Temps maximal dépassé ({int(timeout_s)} s). Ajustez la limite dans Paramètres.",
                              code="timeout")

    def progress(self, value: float | None, message: str | None = None, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_progress < 0.7:
            return
        self._last_progress = now
        if message is None:
            db.execute("UPDATE jobs SET progress=? WHERE id=?", (value, self.id))
        else:
            db.execute("UPDATE jobs SET progress=?, message=? WHERE id=?", (value, message, self.id))


Handler = Callable[[JobContext], None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return deco


def recover_on_startup() -> int:
    """Remet en file les tâches interrompues par une fermeture brutale."""
    running = db.rows("SELECT id FROM jobs WHERE status='running'")
    for r in running:
        db.execute("UPDATE jobs SET status='queued', progress=NULL, message=? WHERE id=?",
                   ("Reprise après redémarrage de l'application", r["id"]))
        log("job.recovered", "Tâche reprise après redémarrage", job_id=r["id"])
    return len(running)


def cancel(job_id: int) -> dict[str, Any]:
    j = db.row("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not j:
        raise StudioError("Tâche introuvable.", status_code=404)
    if j["status"] == "queued":
        db.execute("UPDATE jobs SET status='cancelled', finished_at=?, message='Annulée avant démarrage' WHERE id=?",
                   (db.now(), job_id))
    elif j["status"] == "running":
        db.execute("UPDATE jobs SET cancel_requested=1, message='Annulation demandée…' WHERE id=?", (job_id,))
    else:
        raise StudioError("Cette tâche est déjà terminée.")
    log("job.cancel", "Annulation demandée", job_id=job_id, episode_id=j["episode_id"], series_id=j["series_id"])
    return db.row("SELECT * FROM jobs WHERE id=?", (job_id,))


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="mvs-scheduler", daemon=True)
        self._thread.start()

    def stop(self, wait: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(wait)

    def active(self) -> list[int]:
        with self._lock:
            return list(self._running)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # le planificateur ne doit jamais mourir
                traceback.print_exc()
            self._stop.wait(0.5)

    def _tick(self) -> None:
        with self._lock:
            for jid in [j for j, t in self._running.items() if not t.is_alive()]:
                del self._running[jid]
        s = get_settings()
        if s.get("queue_paused"):
            return
        max_wf = max(1, min(3, int(s.get("max_parallel_workflows", 3))))
        running = db.rows("SELECT * FROM jobs WHERE status='running'")
        heavy_busy = any(r["heavy"] for r in running)
        busy_eps = {r["episode_id"] for r in running}
        for job in db.rows("SELECT * FROM jobs WHERE status='queued' ORDER BY id"):
            if len(busy_eps) >= max_wf:
                break
            if job["episode_id"] in busy_eps:
                continue
            if job["heavy"] and heavy_busy:
                continue
            db.execute("UPDATE jobs SET status='running', started_at=?, attempts=attempts+1, cancel_requested=0,"
                       " message='En cours' WHERE id=? AND status='queued'", (db.now(), job["id"]))
            job = db.row("SELECT * FROM jobs WHERE id=?", (job["id"],))
            t = threading.Thread(target=self._run, args=(job,), name=f"mvs-job-{job['id']}", daemon=True)
            with self._lock:
                self._running[job["id"]] = t
            t.start()
            busy_eps.add(job["episode_id"])
            heavy_busy = heavy_busy or bool(job["heavy"])

    def _run(self, job: dict[str, Any]) -> None:
        ctx = JobContext(job)
        kw = dict(series_id=job["series_id"], episode_id=job["episode_id"], job_id=job["id"])
        log("job.start", f"Démarrage : {job['kind']}", **kw)
        try:
            fn = HANDLERS.get(job["kind"])
            if not fn:
                raise StudioError(f"Type de tâche inconnu : {job['kind']}")
            fn(ctx)
            if ctx.cancelled():
                raise Cancelled()
            db.execute("UPDATE jobs SET status='done', finished_at=?, message=COALESCE(NULLIF(message,'En cours'),'Terminé')"
                       " WHERE id=?", (db.now(), job["id"]))
            log("job.done", f"Terminé : {job['kind']}", **kw)
        except Cancelled:
            db.execute("UPDATE jobs SET status='cancelled', finished_at=?, message='Annulée proprement' WHERE id=?",
                       (db.now(), job["id"]))
            log("job.cancelled", f"Annulée : {job['kind']}", level="warning", **kw)
        except StudioError as e:
            db.execute("UPDATE jobs SET status='failed', finished_at=?, error=?, message=? WHERE id=?",
                       (db.now(), e.message, "Échec", job["id"]))
            log("job.failed", f"Échec de « {job['kind']} » : {e.message}", level="error", **kw)
        except Exception as e:  # erreur inattendue : message lisible + trace dans le journal
            tb = traceback.format_exc(limit=6)
            db.execute("UPDATE jobs SET status='failed', finished_at=?, error=?, message=? WHERE id=?",
                       (db.now(), f"{type(e).__name__}: {e}", "Échec", job["id"]))
            log("job.failed", f"Erreur inattendue dans « {job['kind']} » : {e}", level="error",
                data={"trace": tb}, **kw)


worker = Worker()


def wait_idle(timeout: float = 120.0) -> bool:
    """Utilitaire (tests / scripts) : attend que la file soit vide."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not db.row("SELECT id FROM jobs WHERE status IN ('queued','running') LIMIT 1"):
            time.sleep(0.2)
            if not db.row("SELECT id FROM jobs WHERE status IN ('queued','running') LIMIT 1"):
                return True
        time.sleep(0.2)
    return False
