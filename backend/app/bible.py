"""Bibles persistantes : lecture, mémoire des agents, import sans écrasement, instantanés."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from . import config, db
from .core import StudioError, log, record_choice


def get_series(series_id: str) -> dict[str, Any]:
    s = db.row("SELECT * FROM series WHERE id=?", (series_id,))
    if not s:
        raise StudioError(f"Série inconnue : {series_id}", status_code=404)
    s["bible"] = db.jloads(s["bible"], {})
    s["features"] = db.jloads(s["features"], {})
    return s


def list_series() -> list[dict[str, Any]]:
    out = []
    for s in db.rows("SELECT * FROM series ORDER BY code"):
        s["bible"] = db.jloads(s["bible"], {})
        s["features"] = db.jloads(s["features"], {})
        out.append(s)
    return out


def characters(series_id: str, include_proposed: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM characters WHERE series_id=?"
    if not include_proposed:
        sql += " AND status='canon'"
    out = []
    for c in db.rows(sql + " ORDER BY created_at, id", (series_id,)):
        for k in ("appearance", "stats", "voice"):
            c[k] = db.jloads(c[k], {})
        out.append(c)
    return out


def character_map(series_id: str) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in characters(series_id)}


def full_bible(series_id: str) -> dict[str, Any]:
    s = get_series(series_id)
    entries = db.rows("SELECT * FROM bible_entries WHERE series_id=? ORDER BY kind, name", (series_id,))
    for e in entries:
        e["data"] = db.jloads(e["data"], {})
    return {
        **s,
        "characters": characters(series_id),
        "relations": db.rows("SELECT * FROM relations WHERE series_id=? ORDER BY id", (series_id,)),
        "entries": entries,
        "facts": db.rows("SELECT * FROM canon_facts WHERE series_id=? ORDER BY id", (series_id,)),
        "timeline": db.rows("SELECT * FROM timeline WHERE series_id=? ORDER BY id", (series_id,)),
        "choices": db.rows("SELECT * FROM choices WHERE series_id=? ORDER BY id DESC", (series_id,)),
    }


def writer_memory(series_id: str, max_episodes: int = 6) -> dict[str, Any]:
    """Contexte transmis à l'agent scénariste : uniquement du canon validé + inspirations choisies."""
    s = get_series(series_id)
    chars = [
        {"id": c["id"], "name": c["name"], "role": c["role"], "description": c["description"],
         "personality": c["personality"], "stats": c["stats"]}
        for c in characters(series_id, include_proposed=False)
    ]
    entries = [
        {"kind": e["kind"], "key": e["key"], "name": e["name"], "data": db.jloads(e["data"], {})}
        for e in db.rows("SELECT * FROM bible_entries WHERE series_id=? AND kind != 'agent_memory'", (series_id,))
    ]
    facts = [f["text"] for f in db.rows(
        "SELECT text FROM canon_facts WHERE series_id=? AND status='canon' ORDER BY id", (series_id,))]
    timeline = [f"{t['label']} — {t['text']}" for t in db.rows(
        "SELECT * FROM timeline WHERE series_id=? ORDER BY id DESC LIMIT ?", (series_id, max_episodes))][::-1]
    votes = [
        {"question": v["question"], "winner": v["winner"], "platform": v["platform"]}
        for v in db.rows("SELECT * FROM votes WHERE series_id=? AND status='validated' ORDER BY id", (series_id,))
    ]
    notes = [e["name"] for e in db.rows(
        "SELECT name FROM bible_entries WHERE series_id=? AND kind='agent_memory' ORDER BY id DESC LIMIT 12",
        (series_id,))]
    inspirations = [c["text"] for c in db.rows(
        "SELECT text FROM comments WHERE series_id=? AND use_as_inspiration=1 ORDER BY id DESC LIMIT 10",
        (series_id,))]
    observers = [o["final_text"] for o in db.rows(
        "SELECT final_text FROM observer_proposals WHERE series_id=? AND status IN ('accepted','adapted')"
        " ORDER BY id", (series_id,))]
    return {
        "series": {"id": s["id"], "name": s["name"], "genre": s["genre"]},
        "bible": s["bible"],
        "characters": chars,
        "entries": entries,
        "canon_facts": facts,
        "recent_timeline": timeline,
        "validated_votes": votes,
        "director_notes": notes,
        "viewer_inspirations": inspirations,
        "accepted_observer_gifts": observers,
    }


def add_agent_memory(series_id: str, note: str) -> None:
    key = f"note-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    db.execute("INSERT INTO bible_entries(series_id, kind, key, name, data, source, created_at) VALUES(?,?,?,?,?,?,?)",
               (series_id, "agent_memory", key, note[:500], "{}", "user", db.now()))


# ------------------------------------------------------------------- import

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "entree"


def import_bible(series_id: str, payload: dict[str, Any] | None = None, *, text: str | None = None,
                 filename: str = "import") -> dict[str, Any]:
    """Fusionne une bible existante SANS écraser : les éléments déjà présents sont signalés, jamais remplacés."""
    get_series(series_id)
    ts = db.now()
    report: dict[str, list] = {"added": [], "skipped_existing": [], "errors": []}
    if text is not None:
        key = _slug(filename)
        if db.row("SELECT id FROM bible_entries WHERE series_id=? AND kind='document' AND key=?", (series_id, key)):
            key = f"{key}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        db.execute("INSERT INTO bible_entries(series_id, kind, key, name, data, source, created_at) VALUES(?,?,?,?,?,?,?)",
                   (series_id, "document", key, filename, db.jdumps({"text": text}), "import", ts))
        report["added"].append(f"document:{key}")
    payload = payload or {}
    with db.transaction() as c:
        prefix = {"horror": "hor", "football": "fb", "isekai": "isk"}.get(series_id, series_id)
        for ch in payload.get("characters", []) or []:
            name = (ch.get("name") or "").strip()
            if not name:
                report["errors"].append("personnage sans nom ignoré")
                continue
            cid = ch.get("id") or f"{prefix}.{_slug(name)}"
            if c.execute("SELECT id FROM characters WHERE id=?", (cid,)).fetchone():
                report["skipped_existing"].append(f"personnage:{cid}")
                continue
            c.execute(
                "INSERT INTO characters(id, series_id, name, role, description, personality, appearance, stats, voice,"
                " status, version, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, series_id, name, ch.get("role", ""), ch.get("description", ""), ch.get("personality", ""),
                 db.jdumps(ch.get("appearance", {"archetype": "human"})), db.jdumps(ch.get("stats", {})),
                 db.jdumps(ch.get("voice", {})), "canon", 1, ts, ts))
            report["added"].append(f"personnage:{cid}")
        for e in payload.get("entries", []) or []:
            kind = _slug(e.get("kind", "note"))
            name = e.get("name") or e.get("key") or "Sans nom"
            key = e.get("key") or _slug(name)
            if c.execute("SELECT id FROM bible_entries WHERE series_id=? AND kind=? AND key=?",
                         (series_id, kind, key)).fetchone():
                report["skipped_existing"].append(f"{kind}:{key}")
                continue
            c.execute("INSERT INTO bible_entries(series_id, kind, key, name, data, source, created_at) VALUES(?,?,?,?,?,?,?)",
                      (series_id, kind, key, name, db.jdumps(e.get("data", {})), "import", ts))
            report["added"].append(f"{kind}:{key}")
        existing_facts = {r[0] for r in c.execute("SELECT text FROM canon_facts WHERE series_id=?", (series_id,))}
        for f in payload.get("facts", []) or []:
            txt = f if isinstance(f, str) else f.get("text", "")
            if not txt:
                continue
            if txt in existing_facts:
                report["skipped_existing"].append(f"fait:{txt[:40]}")
                continue
            c.execute("INSERT INTO canon_facts(series_id, text, category, status, source, created_at, decided_at)"
                      " VALUES(?,?,?,?,?,?,?)", (series_id, txt, "fait", "canon", "import", ts, ts))
            report["added"].append(f"fait:{txt[:40]}")
        rules = payload.get("rules") or []
        if rules:
            row = c.execute("SELECT bible FROM series WHERE id=?", (series_id,)).fetchone()
            bible = db.jloads(row[0], {})
            current = bible.get("rules", [])
            for r in rules:
                if r in current:
                    report["skipped_existing"].append(f"règle:{r[:40]}")
                else:
                    current.append(r)
                    report["added"].append(f"règle:{r[:40]}")
            bible["rules"] = current
            c.execute("UPDATE series SET bible=? WHERE id=?", (db.jdumps(bible), series_id))
    log("bible.import", f"Import de bible : {len(report['added'])} ajout(s), "
        f"{len(report['skipped_existing'])} élément(s) existant(s) conservé(s)", series_id=series_id, data=report)
    record_choice(series_id, "import", f"Import « {filename} »", data=report)
    snapshot(series_id, "after-import")
    return report


def snapshot(series_id: str, reason: str = "manual") -> str:
    config.BIBLES_DIR.mkdir(parents=True, exist_ok=True)
    data = full_bible(series_id)
    path = config.BIBLES_DIR / f"{series_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{reason}.json"
    path.write_text(db.jdumps(data), encoding="utf-8")
    return str(path)
