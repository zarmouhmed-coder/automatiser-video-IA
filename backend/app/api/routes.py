"""API REST de MULTIVERSE STUDIO."""
from __future__ import annotations

import json
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from .. import bible, config, db, inspiration, library
from ..agents import agents
from ..core import StudioError, get_settings, log, record_choice, update_settings
from ..llm import providers
from ..render import audio
from ..workflow import engine, queue

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------- statut

@router.get("/status")
def status() -> dict[str, Any]:
    s = get_settings()
    import os
    return {
        "app": "MULTIVERSE STUDIO",
        "demo_mode": s["llm_provider"] == "demo",
        "llm": providers.provider_status(),
        "tts": audio.tts_status(),
        "ffmpeg": config.ffmpeg_exe(),
        "queue_paused": s["queue_paused"],
        "active_jobs": queue.worker.active(),
        "data_dir": str(config.DATA_DIR),
        "system": {"os": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
                   "cpu_count": os.cpu_count(), "disk_free_gb": round(shutil.disk_usage(config.DATA_DIR).free / 1e9, 1)},
        "secrets": config.secret_status(),
    }


@router.get("/dashboard")
def dashboard() -> dict[str, Any]:
    series = []
    for s in bible.list_series():
        eps = db.rows("SELECT id, number, title, stage, status, ends_with_vote, updated_at FROM episodes"
                      " WHERE series_id=? ORDER BY number DESC", (s["id"],))
        counts: dict[str, int] = {}
        for e in eps:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
        current = next((e for e in eps if e["status"] not in ("published", "rejected")), None)
        if current:
            full = engine.get_episode(current["id"])
            current.update(engine.stage_progress(full))
        pending = db.row("SELECT COUNT(*) AS n FROM gates g JOIN episodes e ON e.id=g.episode_id WHERE e.series_id=?"
                         " AND g.status='pending'", (s["id"],))["n"]
        cover = db.row("SELECT sb.content FROM storyboards sb JOIN episodes e ON e.id=sb.episode_id WHERE e.series_id=?"
                       " ORDER BY sb.id DESC LIMIT 1", (s["id"],))
        cover_path = None
        if cover:
            shots = db.jloads(cover["content"], {}).get("shots", [])
            cand = ([x for x in shots if x.get("thumb") and not x.get("characters") and x.get("kind") != "endcard"]
                    or [x for x in shots if x.get("thumb")])
            cover_path = cand[0]["thumb"] if cand else None
        if not cover_path:
            loc = {"horror": "corridor", "football": "stadium_night", "isekai": "plains"}[s["id"]]
            a = db.row("SELECT path FROM assets WHERE asset_key=? ORDER BY version DESC LIMIT 1", (f"bg.{loc}.procedural",))
            cover_path = a["path"] if a else None
        series.append({"id": s["id"], "code": s["code"], "name": s["name"], "genre": s["genre"], "accent": s["accent"],
                       "cover": cover_path, "pitch": s["bible"].get("pitch", ""),
                       "episodes_total": len(eps), "counts": counts, "current": current,
                       "published": counts.get("published", 0), "pending_gates": pending,
                       "lock": engine.vote_lock_status(s["id"])})
    jobs = db.rows("SELECT j.*, e.number AS episode_number FROM jobs j LEFT JOIN episodes e ON e.id=j.episode_id"
                   " WHERE j.status IN ('queued','running') ORDER BY j.id")
    return {"series": series, "jobs": jobs, "validations_pending": len(_validations()),
            "month_spend_usd": round(providers.month_spend(), 4), "settings": get_settings(),
            "recent_events": db.rows("SELECT * FROM events ORDER BY id DESC LIMIT 12")}


# --------------------------------------------------------------------- séries

@router.get("/series")
def series_list():
    return bible.list_series()


@router.get("/series/{series_id}/bible")
def series_bible(series_id: str):
    data = bible.full_bible(series_id)
    data["lock"] = engine.vote_lock_status(series_id)
    return data


class ImportBody(BaseModel):
    characters: list[dict] = []
    entries: list[dict] = []
    facts: list[Any] = []
    rules: list[str] = []


@router.post("/series/{series_id}/import")
def series_import(series_id: str, body: ImportBody):
    return bible.import_bible(series_id, body.model_dump(), filename="import JSON")


@router.post("/series/{series_id}/import-file")
async def series_import_file(series_id: str, file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8", errors="replace")
    if file.filename and file.filename.lower().endswith(".json"):
        try:
            payload = json.loads(raw)
        except ValueError as e:
            raise StudioError(f"JSON invalide : {e}")
        return bible.import_bible(series_id, payload, filename=file.filename)
    return bible.import_bible(series_id, None, text=raw, filename=file.filename or "document")


@router.post("/series/{series_id}/snapshot")
def series_snapshot(series_id: str):
    return {"path": bible.snapshot(series_id)}


class FactBody(BaseModel):
    text: str
    category: str = "fait"


@router.post("/series/{series_id}/facts")
def add_fact(series_id: str, body: FactBody):
    bible.get_series(series_id)
    fid = db.execute("INSERT INTO canon_facts(series_id, text, category, status, source, created_at, decided_at)"
                     " VALUES(?,?,?,?,?,?,?)", (series_id, body.text.strip(), body.category, "canon", "user",
                                                 db.now(), db.now()))
    record_choice(series_id, "canon", f"Fait ajouté : {body.text[:80]}")
    return db.row("SELECT * FROM canon_facts WHERE id=?", (fid,))


class DecideBody(BaseModel):
    action: str
    note: str = ""
    scene_index: int | None = None
    final_text: str | None = None
    accept_canon: list[int] | None = None
    accept_characters: list[int] | None = None
    target: str | None = None


@router.post("/facts/{fact_id}/decide")
def decide_fact(fact_id: int, body: DecideBody):
    f = db.row("SELECT * FROM canon_facts WHERE id=?", (fact_id,))
    if not f:
        raise StudioError("Fait introuvable.", status_code=404)
    if f["status"] != "proposed":
        raise StudioError("Déjà traité.", status_code=409)
    status = {"accept": "canon", "reject": "rejected"}.get(body.action)
    if not status:
        raise StudioError("Action invalide.")
    text = (body.final_text or f["text"]).strip()
    db.execute("UPDATE canon_facts SET status=?, text=?, decided_at=? WHERE id=?", (status, text, db.now(), fact_id))
    record_choice(f["series_id"], "canon", f"Proposition {'acceptée' if status == 'canon' else 'rejetée'} : {text[:80]}",
                  episode_id=f["episode_id"])
    return db.row("SELECT * FROM canon_facts WHERE id=?", (fact_id,))


class CharacterPatch(BaseModel):
    status: str | None = None
    name: str | None = None
    role: str | None = None
    description: str | None = None
    personality: str | None = None
    appearance: dict | None = None
    voice: dict | None = None
    stats: dict | None = None


@router.patch("/characters/{char_id}")
def patch_character(char_id: str, body: CharacterPatch):
    c = db.row("SELECT * FROM characters WHERE id=?", (char_id,))
    if not c:
        raise StudioError("Personnage introuvable.", status_code=404)
    sets, params = [], []
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "status" and v not in ("canon", "rejected", "proposed"):
            raise StudioError("Statut invalide.")
        sets.append(f"{k}=?")
        params.append(json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v)
    if not sets:
        return c
    sets += ["version=version+1", "updated_at=?"]
    params.append(db.now())
    db.execute(f"UPDATE characters SET {', '.join(sets)} WHERE id=?", (*params, char_id))
    record_choice(c["series_id"], "canon", f"Personnage {c['name']} modifié ({', '.join(body.model_dump(exclude_none=True))})")
    return db.row("SELECT * FROM characters WHERE id=?", (char_id,))


@router.get("/agents")
def agents_list():
    return agents.all_agents()


# ------------------------------------------------------------------- épisodes

class EpisodeCreate(BaseModel):
    series_id: str
    intent: str
    duration_s: int = 45
    style: str = ""
    allow_vote: int = Field(1, description="0 jamais, 1 auto, 2 obligatoire")
    inspiration_id: int | None = None
    inspiration_url: str = ""


@router.post("/episodes")
def create_episode(body: EpisodeCreate):
    iid = body.inspiration_id
    if body.inspiration_url.strip() and not iid:
        insp = inspiration.add_tiktok(body.inspiration_url, body.series_id)
        iid = insp["id"]
    return engine.create_episode(body.series_id, body.intent, body.duration_s, body.style, body.allow_vote, iid)


# ------------------------------------------------------------------ inspirations

@router.get("/inspirations")
def inspirations_list(series_id: str | None = None):
    return inspiration.list_all(series_id)


class InspirationLink(BaseModel):
    url: str
    series_id: str | None = None
    notes: str = ""


@router.post("/inspirations/link")
def inspiration_link(body: InspirationLink):
    return inspiration.add_tiktok(body.url, body.series_id or None, body.notes)


@router.post("/inspirations/upload")
async def inspiration_upload(file: UploadFile = File(...), series_id: str = Form(""), notes: str = Form(""),
                             url: str = Form("")):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "upload"
        p.write_bytes(await file.read())
        return inspiration.add_file(p, file.filename or "reference.mp4", series_id or None, notes, url)


@router.delete("/inspirations/{iid}")
def inspiration_delete(iid: int):
    if db.row("SELECT id FROM episodes WHERE inspiration_id=? AND status NOT IN ('published','rejected')", (iid,)):
        raise StudioError("Cette inspiration est utilisée par un épisode en cours.")
    db.execute("DELETE FROM inspirations WHERE id=?", (iid,))
    shutil.rmtree(config.INSPIRATIONS_DIR / str(iid), ignore_errors=True)
    return {"deleted": iid}


# ------------------------------------------------------------------ idées du moment

@router.get("/ideas/{series_id}")
def ideas(series_id: str, lang: str = "fr"):
    from .. import trends
    s = bible.get_series(series_id)
    out = trends.ideas(series_id, lang)
    for it in out["items"]:
        it["intent"] = trends.intent_from(it["title"], s["name"])
    return out


# ------------------------------------------------------------------ voix

@router.get("/voices")
def voices_status():
    from ..render import voices
    out = voices.status()
    out["cast"] = {s["id"]: voices.voice_table(bible.characters(s["id"])) for s in bible.list_series()}
    return out


@router.post("/voices/download")
def voices_download():
    jid = engine.enqueue("models_download", None)
    return {"job_id": jid}


@router.get("/episodes")
def episodes(series_id: str | None = None):
    sql = "SELECT * FROM episodes"
    params: list[Any] = []
    if series_id:
        sql += " WHERE series_id=?"
        params.append(series_id)
    out = db.rows(sql + " ORDER BY updated_at DESC", params)
    for e in out:
        e.update(engine.stage_progress(e))
    return out


@router.get("/episodes/{episode_id}")
def episode_detail(episode_id: int):
    ep = engine.get_episode(episode_id)
    ep.update(engine.stage_progress(ep))
    ep["inspiration"] = inspiration.get(ep.get("inspiration_id"))
    scripts = db.rows("SELECT * FROM script_versions WHERE episode_id=? ORDER BY version DESC", (episode_id,))
    for s in scripts:
        s["content"] = db.jloads(s["content"], {})
    crits = db.rows("SELECT * FROM critiques WHERE episode_id=? ORDER BY id DESC", (episode_id,))
    for c in crits:
        c["content"] = db.jloads(c["content"], {})
    sbs = db.rows("SELECT * FROM storyboards WHERE episode_id=? ORDER BY version DESC", (episode_id,))
    for s in sbs:
        s["content"] = db.jloads(s["content"], {})
    renders = db.rows("SELECT * FROM renders WHERE episode_id=? ORDER BY id DESC", (episode_id,))
    for r in renders:
        r["meta"] = db.jloads(r["meta"], {})
    packs = db.rows("SELECT * FROM publication_packs WHERE episode_id=? ORDER BY id DESC", (episode_id,))
    for p in packs:
        p["content"] = db.jloads(p["content"], {})
    from ..render import pipeline
    return {
        "episode": ep, "scripts": scripts, "critiques": crits, "storyboards": sbs, "renders": renders,
        "packs": packs, "gates": [dict(g, report=db.jloads(g["report"], {})) for g in
                                   db.rows("SELECT * FROM gates WHERE episode_id=? ORDER BY id DESC", (episode_id,))],
        "jobs": db.rows("SELECT * FROM jobs WHERE episode_id=? ORDER BY id DESC LIMIT 30", (episode_id,)),
        "events": db.rows("SELECT * FROM events WHERE episode_id=? ORDER BY id DESC LIMIT 80", (episode_id,)),
        "votes": db.rows("SELECT * FROM votes WHERE episode_id=? ORDER BY id DESC", (episode_id,)),
        "assets_manifest": pipeline.load_manifest(episode_id),
        "stages": [{"key": k, "label": v} for k, v in engine.STAGE_LABELS.items() if k not in ("rejected",)],
        "costs": db.rows("SELECT * FROM cost_ledger WHERE episode_id=? ORDER BY id", (episode_id,)),
    }


class ScriptEdit(BaseModel):
    content: dict
    note: str = ""


@router.put("/episodes/{episode_id}/script")
def edit_script(episode_id: int, body: ScriptEdit):
    return engine.edit_script(episode_id, body.content, body.note)


class SceneRegen(BaseModel):
    note: str = ""


@router.post("/episodes/{episode_id}/scenes/{scene_index}/regenerate")
def regen_scene(episode_id: int, scene_index: int, body: SceneRegen):
    ep = engine.get_episode(episode_id)
    engine.assert_unlocked(ep)
    g = db.row("SELECT * FROM gates WHERE episode_id=? AND stage IN ('script','episode') AND status='pending'",
               (episode_id,))
    if not g:
        raise StudioError("La réécriture d'une scène se fait pendant la validation de l'épisode.")
    return engine.decide_gate(g["id"], "changes", body.note or f"Réécrire la scène {scene_index + 1}", scene_index)


@router.patch("/episodes/{episode_id}/storyboard/shots/{shot_id}")
def edit_shot(episode_id: int, shot_id: str, changes: dict):
    return engine.edit_storyboard_shot(episode_id, shot_id, changes)


@router.post("/episodes/{episode_id}/retry")
def retry(episode_id: int):
    return engine.retry_stage(episode_id)


class PublishedBody(BaseModel):
    platform: str
    url: str = ""
    published_at: str = ""


@router.post("/episodes/{episode_id}/published")
def published(episode_id: int, body: PublishedBody):
    return engine.mark_published(episode_id, body.platform, body.url, body.published_at)


# ---------------------------------------------------------------- validations

@router.post("/gates/{gate_id}/decide")
def decide(gate_id: int, body: DecideBody):
    return engine.decide_gate(gate_id, body.action, body.note, body.scene_index, body.accept_canon,
                              body.accept_characters, body.target)


def _validations() -> list[dict]:
    items: list[dict] = []
    for g in db.rows("SELECT g.*, e.series_id, e.number, e.title FROM gates g JOIN episodes e ON e.id=g.episode_id"
                     " WHERE g.status='pending' ORDER BY g.id"):
        items.append({"type": "gate", "id": g["id"], "series_id": g["series_id"], "episode_id": g["episode_id"],
                      "title": f"Ép.{g['number']} {g['title']} — {engine.STAGE_LABELS['validation_' + g['stage']]}",
                      "stage": g["stage"], "created_at": g["created_at"],
                      "report": db.jloads(g["report"], {}) if g["stage"] == "episode" else None})
    for f in db.rows("SELECT * FROM canon_facts WHERE status='proposed' ORDER BY id"):
        items.append({"type": "canon", "id": f["id"], "series_id": f["series_id"], "episode_id": f["episode_id"],
                      "title": f["text"], "category": f["category"], "created_at": f["created_at"]})
    for c in db.rows("SELECT * FROM characters WHERE status='proposed' ORDER BY created_at"):
        items.append({"type": "character", "id": c["id"], "series_id": c["series_id"],
                      "title": f"Nouveau personnage : {c['name']} ({c['role']})", "created_at": c["created_at"]})
    for v in db.rows("SELECT * FROM votes WHERE status IN ('open','result_entered') ORDER BY id"):
        items.append({"type": "vote", "id": v["id"], "series_id": v["series_id"], "episode_id": v["episode_id"],
                      "title": v["question"], "status": v["status"], "created_at": v["created_at"]})
    for o in db.rows("SELECT * FROM observer_proposals WHERE status IN ('pending','analyzed') ORDER BY id"):
        items.append({"type": "observer", "id": o["id"], "series_id": o["series_id"],
                      "title": f"{o['pseudo']} : {o['content'][:80]}", "status": o["status"],
                      "created_at": o["created_at"]})
    return items


@router.get("/validations")
def validations():
    return _validations()


# ---------------------------------------------------------------------- file

@router.get("/jobs")
def jobs(limit: int = 60):
    return db.rows("SELECT j.*, e.number AS episode_number FROM jobs j LEFT JOIN episodes e ON e.id=j.episode_id"
                   " ORDER BY j.id DESC LIMIT ?", (limit,))


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: int):
    return queue.cancel(job_id)


@router.post("/queue/{action}")
def queue_action(action: str):
    if action not in ("pause", "resume"):
        raise StudioError("Action invalide.")
    update_settings({"queue_paused": action == "pause"})
    log("queue." + action, "File d'attente " + ("en pause" if action == "pause" else "reprise"))
    return {"queue_paused": action == "pause"}


@router.get("/events")
def events(limit: int = 200, series_id: str | None = None, level: str | None = None):
    sql, params = "SELECT * FROM events WHERE 1=1", []
    if series_id:
        sql += " AND series_id=?"
        params.append(series_id)
    if level:
        sql += " AND level=?"
        params.append(level)
    return db.rows(sql + " ORDER BY id DESC LIMIT ?", (*params, min(limit, 1000)))


# ---------------------------------------------------------------------- votes

@router.get("/votes")
def votes(series_id: str | None = None):
    sql, params = "SELECT v.*, e.number AS episode_number FROM votes v JOIN episodes e ON e.id=v.episode_id", []
    if series_id:
        sql += " WHERE v.series_id=?"
        params.append(series_id)
    out = db.rows(sql + " ORDER BY v.id DESC", params)
    for v in out:
        v["options"] = db.jloads(v["options"], [])
        v["counts"] = db.jloads(v["counts"], {})
    return out


class VoteResult(BaseModel):
    platform: str
    result_at: str
    winner: str
    counts: dict[str, int] = {}
    note: str = ""


@router.post("/votes/{vote_id}/result")
def vote_result(vote_id: int, body: VoteResult):
    return engine.enter_vote_result(vote_id, body.platform, body.result_at, body.winner, body.counts, body.note)


@router.post("/votes/{vote_id}/validate")
def vote_validate(vote_id: int):
    return engine.validate_vote(vote_id)


@router.get("/choices")
def choices(series_id: str | None = None):
    sql, params = "SELECT * FROM choices", []
    if series_id:
        sql += " WHERE series_id=?"
        params.append(series_id)
    return db.rows(sql + " ORDER BY id DESC LIMIT 300", params)


# ------------------------------------------------------------------ communauté

class CommentBody(BaseModel):
    series_id: str
    text: str
    author: str = ""
    platform: str = ""
    episode_id: int | None = None
    use_as_inspiration: bool = False


@router.get("/comments")
def comments(series_id: str | None = None):
    sql, params = "SELECT * FROM comments", []
    if series_id:
        sql += " WHERE series_id=?"
        params.append(series_id)
    return db.rows(sql + " ORDER BY id DESC", params)


@router.post("/comments")
def add_comment(body: CommentBody):
    bible.get_series(body.series_id)
    if not body.text.strip():
        raise StudioError("Commentaire vide.")
    cid = db.execute("INSERT INTO comments(series_id, episode_id, author, platform, text, use_as_inspiration, created_at)"
                     " VALUES(?,?,?,?,?,?,?)", (body.series_id, body.episode_id, body.author, body.platform,
                                                 body.text.strip(), int(body.use_as_inspiration), db.now()))
    return db.row("SELECT * FROM comments WHERE id=?", (cid,))


@router.patch("/comments/{comment_id}")
def patch_comment(comment_id: int, body: dict):
    if "use_as_inspiration" in body:
        db.execute("UPDATE comments SET use_as_inspiration=? WHERE id=?", (int(bool(body["use_as_inspiration"])), comment_id))
    return db.row("SELECT * FROM comments WHERE id=?", (comment_id,))


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int):
    db.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    return {"deleted": comment_id}


class ObserverBody(BaseModel):
    pseudo: str
    pseudo_kind: str = "fictif"
    kind: str = "capacite"
    content: str
    target_character: str | None = None


def _observers_series() -> str:
    s = next((s for s in bible.list_series() if s["features"].get("observers")), None)
    if not s:
        raise StudioError("Aucune série n'a le système des Observateurs.")
    return s["id"]


def _add_observer(body: ObserverBody) -> dict:
    sid = _observers_series()
    if body.pseudo_kind not in ("fictif", "consenti"):
        raise StudioError("Le pseudo doit être fictif ou consenti.")
    if body.kind not in ("capacite", "cadeau", "commentaire"):
        raise StudioError("Type invalide (capacite, cadeau, commentaire).")
    if not body.pseudo.strip() or not body.content.strip():
        raise StudioError("Pseudo et contenu obligatoires.")
    oid = db.execute("INSERT INTO observer_proposals(series_id, pseudo, pseudo_kind, kind, content, target_character,"
                     " status, created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (sid, body.pseudo.strip(), body.pseudo_kind, body.kind, body.content.strip(),
                      body.target_character or None, "pending", db.now()))
    return db.row("SELECT * FROM observer_proposals WHERE id=?", (oid,))


@router.get("/observers")
def observers():
    out = db.rows("SELECT * FROM observer_proposals ORDER BY id DESC")
    for o in out:
        o["analysis"] = db.jloads(o["analysis"], {})
    return out


@router.post("/observers")
def add_observer(body: ObserverBody):
    return _add_observer(body)


class ObserverImport(BaseModel):
    text: str
    pseudo_kind: str = "fictif"


@router.post("/observers/import")
def import_observers(body: ObserverImport):
    """Une proposition par ligne : « pseudo | type | contenu » (type : capacite, cadeau, commentaire)."""
    added, errors = [], []
    for i, line in enumerate(body.text.splitlines(), 1):
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 2:
            parts = [parts[0], "commentaire", parts[1]]
        if len(parts) < 3:
            errors.append(f"Ligne {i} ignorée (format : pseudo | type | contenu)")
            continue
        try:
            added.append(_add_observer(ObserverBody(pseudo=parts[0], kind=parts[1].lower(), content="|".join(parts[2:]),
                                                    pseudo_kind=body.pseudo_kind))["id"])
        except StudioError as e:
            errors.append(f"Ligne {i} : {e.message}")
    return {"added": added, "errors": errors}


@router.post("/observers/{obs_id}/analyze")
def analyze_observer(obs_id: int):
    o = db.row("SELECT * FROM observer_proposals WHERE id=?", (obs_id,))
    if not o:
        raise StudioError("Proposition introuvable.", status_code=404)
    if o["status"] not in ("pending", "analyzed"):
        raise StudioError("Déjà décidée.", status_code=409)
    analysis = agents.analyze_observer(o["series_id"], o)
    db.execute("UPDATE observer_proposals SET analysis=?, status='analyzed' WHERE id=?", (db.jdumps(analysis), obs_id))
    return {**db.row("SELECT * FROM observer_proposals WHERE id=?", (obs_id,)), "analysis": analysis}


@router.post("/observers/{obs_id}/decide")
def decide_observer(obs_id: int, body: DecideBody):
    o = db.row("SELECT * FROM observer_proposals WHERE id=?", (obs_id,))
    if not o:
        raise StudioError("Proposition introuvable.", status_code=404)
    if o["status"] != "analyzed":
        raise StudioError("Faites d'abord analyser la proposition par l'agent.")
    analysis = db.jloads(o["analysis"], {})
    status = {"accept": "accepted", "adapt": "adapted", "reject": "rejected"}.get(body.action)
    if not status:
        raise StudioError("Action invalide (accept, adapt, reject).")
    if status == "accepted" and analysis.get("verdict") == "incompatible":
        raise StudioError("Proposition incompatible avec les règles du monde : adaptez-la ou rejetez-la.")
    final = None
    if status == "adapted":
        final = (body.final_text or analysis.get("adaptation") or "").strip()
        if not final:
            raise StudioError("Texte adapté obligatoire.")
    elif status == "accepted":
        final = f"Don de l'Observateur « {o['pseudo']} » : {o['content']}"
    db.execute("UPDATE observer_proposals SET status=?, final_text=?, decided_at=? WHERE id=?",
               (status, final, db.now(), obs_id))
    if final:
        db.execute("INSERT INTO canon_facts(series_id, text, category, status, source, created_at, decided_at)"
                   " VALUES(?,?,?,?,?,?,?)", (o["series_id"], final, "observateur", "canon", "observer",
                                               db.now(), db.now()))
    record_choice(o["series_id"], "observer", f"Observateur {o['pseudo']} : {status}", data={"final": final})
    return db.row("SELECT * FROM observer_proposals WHERE id=?", (obs_id,))


# ------------------------------------------------------------------ bibliothèque

@router.get("/library")
def library_list(kind: str | None = None, series_id: str | None = None):
    return library.list_assets(kind, series_id)


@router.get("/library/{asset_key}/versions")
def library_versions(asset_key: str):
    return db.rows("SELECT * FROM assets WHERE asset_key=? ORDER BY version DESC", (asset_key,))


@router.post("/library/upload")
async def library_upload(file: UploadFile = File(...), asset_key: str = Form(...), kind: str = Form(...),
                         name: str = Form(...), license: str = Form(...), series_id: str = Form("")):
    suffix = Path(file.filename or "fichier").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3", ".ogg", ".json", ".txt", ".md", ".py", ".ts",
                      ".tsx", ".js", ".mp4", ".psd", ".kra", ".svg", ".zip"}:
        raise StudioError(f"Format non pris en charge : {suffix}")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / Path(file.filename or f"fichier{suffix}").name
        p.write_bytes(await file.read())
        a = library.register(asset_key, kind, p, name=name, license=license, source="import",
                             series_id=series_id or None)
    record_choice(series_id or "global", "import", f"Bibliothèque : {asset_key} v{a['version']}")
    return a


@router.post("/library/generate")
def library_generate():
    jid = engine.enqueue("library_seed", None)
    return {"job_id": jid}


# --------------------------------------------------------------------- archives

@router.get("/archives")
def archives():
    eps = db.rows("SELECT * FROM episodes ORDER BY series_id, number DESC")
    for e in eps:
        e["stage_label"] = engine.STAGE_LABELS.get(e["stage"], e["stage"])
        e["renders"] = db.rows("SELECT * FROM renders WHERE episode_id=? ORDER BY id DESC", (e["id"],))
        e["script_versions"] = db.row("SELECT COUNT(*) AS n FROM script_versions WHERE episode_id=?", (e["id"],))["n"]
        e["storyboard_versions"] = db.row("SELECT COUNT(*) AS n FROM storyboards WHERE episode_id=?", (e["id"],))["n"]
        p = db.row("SELECT folder FROM publication_packs WHERE episode_id=? ORDER BY id DESC LIMIT 1", (e["id"],))
        e["pack_folder"] = p["folder"] if p else None
    return {"episodes": eps, "backups": db.list_backups(), "data_dir": str(config.DATA_DIR)}


@router.get("/publication")
def publication():
    out = []
    for e in db.rows("SELECT * FROM episodes WHERE status IN ('ready_to_publish','published') ORDER BY updated_at DESC"):
        p = db.row("SELECT * FROM publication_packs WHERE episode_id=? ORDER BY id DESC LIMIT 1", (e["id"],))
        if p:
            p["content"] = db.jloads(p["content"], {})
        e["published_info"] = db.jloads(e["published_info"], {})
        out.append({"episode": e, "pack": p})
    return out


# --------------------------------------------------------------------- paramètres

@router.get("/settings")
def settings_get():
    return {"settings": get_settings(), "secrets": config.secret_status(), "costs": costs()}


@router.put("/settings")
def settings_put(values: dict):
    s = update_settings(values)
    log("settings.updated", f"Paramètres modifiés : {', '.join(values)}")
    return {"settings": s}


class SecretBody(BaseModel):
    key: str
    value: str


@router.put("/secrets")
def secret_put(body: SecretBody):
    config.save_secret(body.key, body.value.strip())
    log("settings.secret", f"Clé {body.key} {'enregistrée' if body.value.strip() else 'supprimée'} dans .env (local)")
    return config.secret_status()


@router.get("/costs")
def costs():
    return {"month_usd": round(providers.month_spend(), 4),
            "by_provider": db.rows("SELECT provider, model, COUNT(*) AS calls, SUM(input_tokens) AS tin,"
                                   " SUM(output_tokens) AS tout, ROUND(SUM(cost_usd),4) AS usd FROM cost_ledger"
                                   " GROUP BY provider, model")}


@router.get("/backups")
def backups():
    return db.list_backups()


@router.post("/backups")
def backup_now():
    p = db.backup("manual")
    for s in bible.list_series():
        bible.snapshot(s["id"], "backup")
    log("backup", f"Sauvegarde créée : {p.name if p else '—'}")
    return {"path": str(p) if p else None}
