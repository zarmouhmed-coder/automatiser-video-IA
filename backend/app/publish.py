"""Pack de publication MANUELLE (aucune publication automatique).

Produit dans data/exports/<série>/ep<n>/ : la vidéo MP4, la miniature, un JSON et un fichier
texte prêt à copier depuis le téléphone (titre, description par plateforme, hashtags,
commentaire à épingler, options de sondage courtes, mention de contenu de synthèse).
"""
from __future__ import annotations

import json
import shutil
from typing import Any

from . import bible, config, db
from .render import pipeline

HASHTAGS = {
    "horror": ["#horreur", "#paranormal", "#creepypasta", "#histoiredhorreur", "#enquete", "#frisson"],
    "football": ["#football", "#animefoot", "#foot", "#animesport", "#tactique", "#blueprint"],
    "isekai": ["#isekai", "#fantasy", "#anime", "#reincarnation", "#rpg", "#aventure"],
}
PLATFORMS = {
    "tiktok": {"label": "TikTok", "title_max": 90, "desc_max": 2200, "poll_option_max": 25},
    "youtube_shorts": {"label": "YouTube Shorts", "title_max": 100, "desc_max": 5000, "poll_option_max": 65},
    "instagram_reels": {"label": "Instagram Reels", "title_max": 90, "desc_max": 2200, "poll_option_max": 25},
}
DISCLOSURE = ("Œuvre de fiction. Images, voix et sons créés par ordinateur (contenu de synthèse). "
              "Toute ressemblance avec des personnes réelles serait fortuite.")


def _short(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def build_pack(ep: dict, script: dict, render: dict) -> dict[str, Any]:
    s = bible.get_series(ep["series_id"])
    title = script.get("title", "")
    hook = script.get("hook", "")
    end = script.get("ending", {})
    vote = end.get("type") == "vote"
    import re as _re
    import unicodedata
    plain = unicodedata.normalize("NFKD", s["name"]).encode("ascii", "ignore").decode().lower()
    tags = HASHTAGS[ep["series_id"]] + ["#" + _re.sub(r"[^a-z0-9]", "", plain)]
    out: dict[str, Any] = {"episode": {"series": s["name"], "number": ep["number"], "title": title},
                           "disclosure": DISCLOSURE, "platforms": {}}
    for key, p in PLATFORMS.items():
        t = _short(f"{s['name']} — Ép.{ep['number']} : {title}", p["title_max"])
        desc_lines = [hook, "", script.get("logline", "")]
        if vote:
            desc_lines += ["", f"🗳️ {end.get('vote_question')}"]
            desc_lines += [f"{chr(65 + i)}. {o}" for i, o in enumerate(end.get("vote_options", []))]
            desc_lines += ["Le résultat décidera de l'épisode suivant."]
        desc_lines += ["", DISCLOSURE, "", " ".join(tags[:5] if key != "youtube_shorts" else tags[:3] + ["#shorts"])]
        out["platforms"][key] = {
            "label": p["label"],
            "title": t,
            "description": _short("\n".join(l for l in desc_lines if l is not None), p["desc_max"]),
            "hashtags": tags if key != "youtube_shorts" else tags[:3] + ["#shorts"],
            "pinned_comment": (f"🗳️ {end.get('vote_question')} Répondez {' ou '.join(chr(65 + i) for i in range(len(end.get('vote_options', []))))} !"
                               if vote else "Qu'avez-vous remarqué dans cet épisode ? 👀"),
            "poll": {"question": _short(end.get("vote_question", ""), 100),
                     "options": [_short(o, p["poll_option_max"]) for o in end.get("vote_options", [])]} if vote else None,
            "ai_label_recommended": True,
        }
    folder = config.EXPORTS_DIR / ep["series_id"] / f"ep{ep['number']:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    video_src = config.DATA_DIR / render["path"]
    video_dst = folder / f"{ep['series_id']}_ep{ep['number']:03d}.mp4"
    shutil.copy2(video_src, video_dst)
    thumb = pipeline.thumbnail(ep, script, folder / "miniature.jpg")
    out["files"] = {"video": pipeline.rel(video_dst), "thumbnail": pipeline.rel(thumb)}
    (folder / "pack.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    txt = [f"PACK DE PUBLICATION — {s['name']} — Épisode {ep['number']} : {title}",
           "Publication MANUELLE uniquement. Rien n'est publié automatiquement.", ""]
    for key, p in out["platforms"].items():
        txt += [f"===== {p['label']} =====", f"TITRE : {p['title']}", "DESCRIPTION :", p["description"],
                f"HASHTAGS : {' '.join(p['hashtags'])}", f"COMMENTAIRE À ÉPINGLER : {p['pinned_comment']}"]
        if p["poll"]:
            txt += [f"SONDAGE : {p['poll']['question']}"] + [f"  - {o}" for o in p["poll"]["options"]]
        txt += ["Pensez à activer l'étiquette « contenu généré par IA » si la plateforme la propose.", ""]
    (folder / "pack.txt").write_text("\n".join(txt), encoding="utf-8")
    out["files"]["json"] = pipeline.rel(folder / "pack.json")
    out["files"]["txt"] = pipeline.rel(folder / "pack.txt")
    out["folder"] = str(folder)
    return out


def save_pack(ep: dict, render_id: int, pack: dict) -> int:
    return db.execute("INSERT INTO publication_packs(episode_id, render_id, content, folder, created_at) VALUES(?,?,?,?,?)",
                      (ep["id"], render_id, db.jdumps(pack), pack["folder"], db.now()))
