"""Rapport de validation d'un épisode : tout ce qu'il faut pour décider en une seule fois."""
from __future__ import annotations

from typing import Any

from .. import bible, db, inspiration
from ..agents.translate import localize
from ..render import pipeline, voices

MUSIC_WHY = {
    "tension": "nappe grave et pulsations pour faire monter la pression",
    "mystery": "bourdon et cloches éparses pour l'étrangeté",
    "calm": "accords doux pour poser l'émotion",
    "epic": "cordes et percussions pour l'ampleur",
    "action": "batterie rapide pour l'énergie",
    "sad": "accords mineurs lents pour la mélancolie",
    "silence": "quasi-silence intentionnel pour isoler la scène",
}
CAMERA_WHY = {
    "push_in": "travelling avant (rapproche, intensifie)", "pull_out": "travelling arrière (isole, révèle l'espace)",
    "pan_left": "panoramique (suit l'action)", "pan_right": "panoramique (suit l'action)",
    "shake": "caméra secouée (choc, panique)", "tilt_up": "contre-plongée progressive (révèle, impressionne)",
    "static": "plan posé (laisse jouer les personnages)",
}
ENDING_WHY = {
    "vote": "Fin sur un vote : le public choisit la suite. L'épisode suivant restera BLOQUÉ tant que vous n'aurez "
            "pas saisi puis validé le résultat officiel (page Communauté).",
    "cliffhanger": "Fin en suspens : pas de vote, l'épisode suivant pourra être écrit dès validation.",
    "reveal": "Fin sur une révélation : pas de vote, l'épisode suivant pourra être écrit dès validation.",
    "resolution": "Fin résolue : pas de vote.",
}


def build(ep: dict, script: dict, storyboard: dict, renders: list[dict], critique: dict | None) -> dict[str, Any]:
    cmap = bible.character_map(ep["series_id"])
    plan = storyboard["content"]
    thumbs = {s["shot_id"]: s.get("thumb") for s in plan["shots"]}
    en = localize(script, "en") if (script.get("i18n") or {}).get("en") else None
    scenes = []
    for i, sc in enumerate(script["scenes"]):
        who = sorted({c["id"] for sh in sc["shots"] for c in sh["characters"]})
        cams = sorted({sh["camera"] for sh in sc["shots"]})
        strong = [sh["caption"] for sh in sc["shots"] if sh["caption"]]
        dur = sum(sh["duration"] for sh in sc["shots"])
        why = [f"Lieu : {sc['location']} — ambiance « {sc.get('mood') or '—'} ».",
               f"Musique « {sc['music']} » : {MUSIC_WHY.get(sc['music'], '')}.",
               "Caméra : " + " ; ".join(CAMERA_WHY.get(c, c) for c in cams) + "."]
        if strong:
            why.append("Temps forts à l'écran : " + " · ".join(strong) + ".")
        lines = [{"shot": sh["id"], "speaker": cmap.get(sh["speaker"], {}).get("name", "Voix off") if sh["speaker"] else
                  ("Voix off" if sh["narration"] else ""), "fr": sh["text"] or sh["narration"],
                  "en": (next(x for s2 in en["scenes"] for x in s2["shots"] if x["id"] == sh["id"])["text"] or
                         next(x for s2 in en["scenes"] for x in s2["shots"] if x["id"] == sh["id"])["narration"])
                  if en else ""}
                 for sh in sc["shots"] if sh["text"] or sh["narration"]]
        scenes.append({"index": i, "id": sc["id"], "summary": sc.get("summary", ""), "duration_s": round(dur, 1),
                       "characters": [cmap.get(c, {}).get("name", c) for c in who], "why": why, "lines": lines,
                       "thumb": thumbs.get(sc["shots"][0]["id"]) if sc["shots"] else None})
    end = script.get("ending", {})
    manifest = pipeline.load_manifest(ep["id"])
    style = inspiration.style_for(ep)
    insp = inspiration.get(ep.get("inspiration_id"))
    crit = (critique or {}).get("content", {}) if critique else {}
    used = sorted({sh["speaker"] for sc in script["scenes"] for sh in sc["shots"] if sh["speaker"]})
    return {
        "title": {"fr": script.get("title", ""), "en": en.get("title", "") if en else ""},
        "logline": {"fr": script.get("logline", ""), "en": en.get("logline", "") if en else ""},
        "hook": script.get("hook", ""),
        "duration_s": round(plan["total"], 1),
        "shots": len(plan["shots"]),
        "scenes": scenes,
        "ending": {"type": end.get("type"), "why": ENDING_WHY.get(end.get("type"), ""),
                   "question": {"fr": end.get("vote_question", ""), "en": (en or {}).get("ending", {}).get("vote_question", "")},
                   "options": {"fr": end.get("vote_options", []), "en": (en or {}).get("ending", {}).get("vote_options", [])}},
        "canon_proposals": script.get("canon_proposals", []),
        "new_characters": script.get("new_characters", []),
        "critique": {"summary": crit.get("summary", ""), "scores": crit.get("scores", {}),
                     "issues": crit.get("issues", []), "source": crit.get("source", "")},
        "voices": {"provider": manifest.get("tts_provider"), "requested": manifest.get("requested_provider"),
                   "warnings": manifest.get("warnings", []),
                   "langs": {k: {"status": v.get("voice_status"), "warnings": v.get("warnings", [])}
                             for k, v in manifest.get("langs", {}).items()},
                   "cast": [r for r in voices.voice_table([cmap[c] for c in used if c in cmap])]},
        "translation": script.get("i18n_meta", {}),
        "inspiration": {"title": insp["title"] if insp else None, "url": insp["url"] if insp else None,
                        "description": style.get("description", ""), "applied": inspiration.applied_summary(style)}
        if insp else None,
        "renders": [{"lang": r["lang"], "path": r["path"], "duration_s": r["duration_s"], "size_bytes": r["size_bytes"],
                     "width": r["width"], "height": r["height"]} for r in renders],
        "on_approve": ["Les propositions de canon cochées entrent dans la bible ; les autres sont rejetées (historisé).",
                       "Les packs de publication FR et EN sont générés (MP4, miniature, textes, sondage).",
                       "Rien n'est publié automatiquement."] + ([ENDING_WHY["vote"]] if end.get("type") == "vote" else []),
        "costs_usd": round(sum(c["cost_usd"] for c in db.rows("SELECT cost_usd FROM cost_ledger WHERE episode_id=?",
                                                              (ep["id"],))), 4),
    }
