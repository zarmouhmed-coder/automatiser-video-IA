"""Bibliothèque réutilisable et versionnée (sprites, expressions, décors, sons, modèles, code…).

Chaque élément a une clé stable (ex. `char.hor.lea.sheet`, `sfx.impact`, `bg.corridor`).
Un nouvel envoi avec la même clé crée une nouvelle version ; les anciennes restent conservées.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import bible, config, db
from .core import StudioError, log

KINDS = ["character", "expression", "pose", "rig", "animation", "background", "palette", "effect", "subtitle_template",
         "voice", "music", "sfx", "code", "source", "export"]
ORIGINAL = "Création originale du projet (procédurale) — libre d'utilisation dans le projet"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register(asset_key: str, kind: str, src: Path, *, name: str, license: str, source: str,
             series_id: str | None = None, meta: dict | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9_.\-]+", asset_key):
        raise StudioError("Clé invalide : lettres minuscules, chiffres, points, tirets et soulignés uniquement.")
    if kind not in KINDS:
        raise StudioError(f"Type d'élément inconnu : {kind}")
    if not license.strip():
        raise StudioError("La licence / les droits d'utilisation sont obligatoires.")
    sha = _sha(src)
    last = db.row("SELECT * FROM assets WHERE asset_key=? ORDER BY version DESC LIMIT 1", (asset_key,))
    if last and db.jloads(last["meta"], {}).get("sha256") == sha:
        return last  # contenu identique : pas de nouvelle version
    version = (last["version"] + 1) if last else 1
    dest_dir = config.LIBRARY_DIR / asset_key / f"v{version}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    m = dict(meta or {}, sha256=sha, size=dest.stat().st_size, filename=src.name)
    aid = db.execute("INSERT INTO assets(asset_key, kind, series_id, name, version, path, license, source, meta, created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?)", (asset_key, kind, series_id, name, version,
                                                       dest.relative_to(config.DATA_DIR).as_posix(), license, source,
                                                       json.dumps(m, ensure_ascii=False), db.now()))
    return db.row("SELECT * FROM assets WHERE id=?", (aid,))


def list_assets(kind: str | None = None, series_id: str | None = None, all_versions: bool = False) -> list[dict]:
    sql = "SELECT * FROM assets a WHERE 1=1"
    params: list[Any] = []
    if not all_versions:
        sql += " AND version = (SELECT MAX(version) FROM assets b WHERE b.asset_key=a.asset_key)"
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    if series_id:
        sql += " AND (series_id=? OR series_id IS NULL)"
        params.append(series_id)
    out = db.rows(sql + " ORDER BY kind, asset_key, version DESC", params)
    for a in out:
        a["meta"] = db.jloads(a["meta"], {})
        a["versions"] = db.row("SELECT COUNT(*) AS n FROM assets WHERE asset_key=?", (a["asset_key"],))["n"]
    return out


def generate_procedural(check=lambda: None) -> int:
    """Enregistre dans la Bibliothèque les ressources originales générées par le moteur."""
    from .render import audio, backgrounds
    from .render.characters import expression_sheet

    tmp = config.DATA_DIR / "tmp_library"
    tmp.mkdir(exist_ok=True)
    count = 0
    for s in bible.list_series():
        for c in bible.characters(s["id"]):
            check()
            p = tmp / f"{c['id']}_expressions.png"
            expression_sheet(c["appearance"], f"{c['name']} — {c['id']}").convert("RGB").save(p)
            register(f"char.{c['id']}.sheet", "expression", p, name=f"{c['name']} — planche d'expressions",
                     license=ORIGINAL, source="procedural", series_id=s["id"],
                     meta={"character_id": c["id"], "expressions": 8, "facings": ["front", "left", "right"]})
            count += 1
    for loc in backgrounds.BUILDERS:
        check()
        far, mid, near = backgrounds.layers(loc, 540, 960)
        img = far.copy()
        img.alpha_composite(mid)
        img.alpha_composite(near)
        p = tmp / f"bg_{loc}_preview.jpg"
        img.convert("RGB").save(p, quality=88)
        register(f"bg.{loc}.procedural", "background", p, name=f"Décor procédural « {loc} » (3 couches parallaxe)",
                 license=ORIGINAL, source="procedural", meta={"layers": ["far", "mid", "near"]})
        count += 1
    from .agents.schema import SFX, MUSIC
    for name in SFX:
        check()
        p = tmp / f"sfx_{name}.wav"
        audio.write_wav(p, audio.sfx(name))
        register(f"sfx.{name}", "sfx", p, name=f"Effet sonore « {name} »", license=ORIGINAL, source="procedural")
        count += 1
    for cue in MUSIC:
        check()
        p = tmp / f"music_{cue}.wav"
        audio.write_wav(p, audio.music_bed(cue, 12.0))
        register(f"music.{cue}", "music", p, name=f"Nappe musicale « {cue} » (12 s, boucle)", license=ORIGINAL,
                 source="procedural")
        count += 1
    for s in bible.list_series():
        p = tmp / f"palette_{s['id']}.json"
        p.write_text(json.dumps(s["bible"].get("art_direction", {}), ensure_ascii=False, indent=1), encoding="utf-8")
        register(f"palette.{s['id']}", "palette", p, name=f"Palette & direction artistique — {s['name']}",
                 license=ORIGINAL, source="procedural", series_id=s["id"])
        count += 1
    p = tmp / "subtitles_mobile.json"
    p.write_text(json.dumps({"position_y": 0.73, "font": "DejaVu Sans Bold", "size_1080p": 54, "max_lines": 3,
                             "box": "rgba(6,10,16,0.75)", "karaoke": True, "speaker_tag": True}, indent=1),
                 encoding="utf-8")
    register("subtitle.mobile_default", "subtitle_template", p, name="Sous-titres mobiles (karaoké)",
             license=ORIGINAL, source="procedural")
    count += 1
    code_dir = Path(__file__).parent / "render"
    for f in ("characters.py", "backgrounds.py", "compositor.py", "audio.py"):
        register(f"code.render.{f[:-3]}", "code", code_dir / f, name=f"Code du moteur 2D — {f}",
                 license="Code source du projet", source="procedural")
        count += 1
    shutil.rmtree(tmp, ignore_errors=True)
    log("library.generated", f"Bibliothèque procédurale à jour ({count} éléments vérifiés)")
    return count
