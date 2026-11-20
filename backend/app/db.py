"""Accès SQLite : connexions, migrations versionnées et sauvegardes sans perte."""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_write_lock = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=30000")
    return c


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    c = _connect()
    try:
        yield c
    finally:
        c.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Transaction exclusive sérialisée (écritures atomiques)."""
    with _write_lock:
        c = _connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()


def rows(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with connection() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def row(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    with connection() as c:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql: str, params: tuple | list = ()) -> int:
    with transaction() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def jloads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def jdumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# --------------------------------------------------------------------- backups

def backup(reason: str = "manual") -> Path | None:
    """Copie cohérente de la base (API de sauvegarde SQLite, compatible WAL)."""
    if not config.DB_PATH.exists():
        return None
    config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = config.BACKUPS_DIR / f"studio-{stamp}-{reason}.db"
    src = sqlite3.connect(config.DB_PATH)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    _prune_backups()
    return dest


def _prune_backups() -> None:
    keep = 10
    try:
        r = row("SELECT value FROM settings WHERE key='backups_keep'")
        if r:
            keep = max(1, int(json.loads(r["value"])))
    except Exception:
        pass
    files = sorted(config.BACKUPS_DIR.glob("studio-*.db"))
    # On ne supprime jamais les sauvegardes faites avant une migration.
    prunable = [f for f in files if "pre-migration" not in f.name]
    for f in prunable[:-keep]:
        f.unlink(missing_ok=True)


def list_backups() -> list[dict[str, Any]]:
    out = []
    for f in sorted(config.BACKUPS_DIR.glob("studio-*.db"), reverse=True):
        out.append({"name": f.name, "size": f.stat().st_size, "path": str(f)})
    return out


# ------------------------------------------------------------------ migrations

def migrate() -> list[str]:
    """Applique les migrations manquantes, après sauvegarde de la base existante."""
    config.ensure_dirs()
    existed = config.DB_PATH.exists()
    with connection() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {r[0] for r in c.execute("SELECT name FROM schema_migrations")}
    pending = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.name not in done)
    if not pending:
        return []
    if existed and done:
        backup("pre-migration")
    applied = []
    for p in pending:
        sql = p.read_text(encoding="utf-8")
        with _write_lock:
            c = _connect()
            try:
                name_sql = p.name.replace("'", "''")
                c.executescript(
                    "BEGIN;\n" + sql + f"\nINSERT INTO schema_migrations(name, applied_at) VALUES('{name_sql}', '{now()}');\nCOMMIT;"
                )
            except Exception:
                try:
                    c.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            finally:
                c.close()
        applied.append(p.name)
    return applied


def restore_backup_copy(name: str) -> Path:
    """Ne remplace pas la base active : prépare une copie restaurable (non destructif)."""
    src = config.BACKUPS_DIR / name
    if not src.exists() or src.parent != config.BACKUPS_DIR:
        raise FileNotFoundError(name)
    dest = config.DATA_DIR / f"restore-{name}"
    shutil.copy2(src, dest)
    return dest
