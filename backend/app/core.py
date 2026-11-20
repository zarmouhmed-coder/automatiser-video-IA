"""Services transverses : réglages, journal d'événements, historique des choix, erreurs métier."""
from __future__ import annotations

import json
from typing import Any

from . import config, db


class StudioError(Exception):
    """Erreur métier lisible renvoyée à l'interface."""

    status_code = 400

    def __init__(self, message: str, code: str = "error", status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        if status_code:
            self.status_code = status_code


class LockedError(StudioError):
    status_code = 423


class ConfigRequired(StudioError):
    status_code = 409

    def __init__(self, message: str):
        super().__init__(message, code="configuration_requise", status_code=409)


# ------------------------------------------------------------------- settings

def get_settings() -> dict[str, Any]:
    out = dict(config.DEFAULT_SETTINGS)
    for r in db.rows("SELECT key, value FROM settings"):
        try:
            out[r["key"]] = json.loads(r["value"])
        except ValueError:
            pass
    return out


def get_setting(key: str) -> Any:
    return get_settings().get(key, config.DEFAULT_SETTINGS.get(key))


def update_settings(values: dict[str, Any]) -> dict[str, Any]:
    allowed = set(config.DEFAULT_SETTINGS)
    with db.transaction() as c:
        for k, v in values.items():
            if k not in allowed:
                raise StudioError(f"Paramètre inconnu : {k}")
            default = config.DEFAULT_SETTINGS[k]
            if isinstance(default, bool):
                v = bool(v)
            elif isinstance(default, int) and not isinstance(default, bool):
                v = int(v)
            elif isinstance(default, float):
                v = float(v)
            else:
                v = str(v)
            if k == "max_parallel_workflows":
                v = max(1, min(3, v))
            c.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, json.dumps(v)),
            )
    return get_settings()


# --------------------------------------------------------------------- events

def log(kind: str, message: str, *, level: str = "info", series_id: str | None = None,
        episode_id: int | None = None, job_id: int | None = None, data: dict | None = None) -> None:
    db.execute(
        "INSERT INTO events(ts, level, series_id, episode_id, job_id, kind, message, data) VALUES(?,?,?,?,?,?,?,?)",
        (db.now(), level, series_id, episode_id, job_id, kind, message, db.jdumps(data or {})),
    )


def record_choice(series_id: str, kind: str, summary: str, *, episode_id: int | None = None,
                  data: dict | None = None) -> None:
    db.execute(
        "INSERT INTO choices(series_id, episode_id, kind, summary, data, created_at) VALUES(?,?,?,?,?,?)",
        (series_id, episode_id, kind, summary, db.jdumps(data or {}), db.now()),
    )
