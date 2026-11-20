"""Recettes de style (idée et 6 préréglages repris de TrendForge, projet de @wesh622).

Une recette décrit COMMENT une vidéo marche, jamais son contenu :
- bloc « contenu » : accroche (hook), structure en parties, ton, rythme de parole ;
- bloc « visuel »  : rythme des changements de plan, punch de caméra, style des sous-titres,
  ambiance, musique, vitesse de la voix.
On l'obtient depuis un préréglage, une vidéo de référence (mesures + transcription) ou un lien
TikTok (téléchargement par yt-dlp si la plateforme le permet, sinon import du fichier).
Elle est ensuite appliquée au montage, aux sous-titres, au son et aux consignes des scénaristes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config, db
from .core import get_settings, log

PRESETS_DIR = Path(__file__).parent / "recipes"

MOOD_TO_CUE = [
    (r"dark|ambient|horror|creepy|eerie", "mystery"), (r"suspense|tension|thriller", "tension"),
    (r"energetic|electronic|upbeat|hype|trap|epic", "action"), (r"piano|calm|soft|nature|lo-?fi|chill", "calm"),
    (r"sad|melanchol", "sad"),
]


def _cue(mood: str) -> str:
    for rx, cue in MOOD_TO_CUE:
        if re.search(rx, mood or "", re.I):
            return cue
    return "tension"


def profile_from_recipe(r: dict[str, Any]) -> dict[str, Any]:
    """Traduit une recette (format TrendForge v3) en profil de style utilisable par le moteur."""
    v, c = r.get("visuel", {}), r.get("contenu", {})
    rythme = v.get("rythme", {})
    st = v.get("sous_titres", {})
    audio = v.get("audio", {})
    voix = v.get("voix", {})
    struct = c.get("structure", [])
    hook = next((p for p in struct if p.get("part") == "hook"), {})
    return {
        "avg_shot_s": float(rythme.get("changement_s", 3.5)),
        "zoom_punch": bool(rythme.get("zoom_punch", False)),
        "motion": 0.6 if rythme.get("zoom_punch") else 0.3,
        "caption_style": "word_by_word" if st.get("style", "word_by_word") == "word_by_word" else "phrase",
        "words_on_screen": int(st.get("words_on_screen", 3) or 3),
        "caption_position": st.get("position", "center"),
        "music_cue": _cue(audio.get("music_mood", "")),
        "music_db": float(audio.get("music_db", -22)),
        "voice_speed": float(voix.get("speed", 1.0) or 1.0),
        "wpm": float(c.get("script_style", {}).get("wpm", 0) or 0) or None,
        "hook_pattern": hook.get("pattern", ""),
        "hook_example": hook.get("example", ""),
        "structure": [{"part": p.get("part"), "seconds": p.get("seconds"), "pattern": p.get("pattern", "")}
                      for p in struct],
        "tone": c.get("script_style", {}).get("tone", ""),
        "ambiance": v.get("ambiance", ""),
        "why_it_works": r.get("why_it_works", ""),
    }


def describe_recipe(p: dict[str, Any]) -> str:
    out = []
    if p.get("avg_shot_s"):
        out.append(f"un changement visuel toutes les ~{p['avg_shot_s']:.1f} s")
    if p.get("zoom_punch"):
        out.append("zooms « punch » sur les mots forts")
    if p.get("caption_style") == "word_by_word":
        out.append(f"sous-titres mot par mot ({p.get('words_on_screen', 3)} à l'écran)")
    if p.get("music_cue"):
        out.append(f"musique « {p['music_cue']} »")
    if p.get("tone"):
        out.append(f"ton {p['tone']}")
    if p.get("hook_pattern"):
        out.append(f"accroche : {p['hook_pattern']}")
    return ", ".join(out)


TITLES = {
    "top-5": "Top 5 énergique", "mystere-non-resolu": "Mystère non résolu",
    "histoire-premiere-personne": "Histoire à la première personne", "faits-etonnants": "Faits étonnants",
    "numbered-news-facts-verdict-explainer": "Actu chiffrée + verdict",
    "calm-nature-psychology-fact-two-line-reveal": "Révélation douce en deux lignes",
}


def seed_presets() -> int:
    """Ajoute les recettes préréglées comme inspirations (une seule fois, jamais écrasées)."""
    n = 0
    for f in sorted(PRESETS_DIR.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        key = f"recette:{r.get('recipe_id', f.stem)}"
        title = TITLES.get(r.get("recipe_id", f.stem), r.get("recipe_id", f.stem).replace("-", " ").capitalize())
        if db.row("SELECT id FROM inspirations WHERE url=?", (key,)):
            db.execute("UPDATE inspirations SET title=? WHERE url=?", (title, key))
            continue
        prof = profile_from_recipe(r)
        prof["description"] = describe_recipe(prof)
        prof["recipe"] = r
        db.execute("INSERT INTO inspirations(series_id, kind, url, title, author, profile, notes, status, created_at)"
                   " VALUES(?,?,?,?,?,?,?,?,?)", (None, "recette", key, title, "TrendForge",
                                                  db.jdumps(prof), r.get("why_it_works", ""), "ready", db.now()))
        n += 1
    return n


# ------------------------------------------------------------------ téléchargement

class DownloadError(Exception):
    pass


def download(url: str, dest_dir: Path) -> dict[str, Any]:
    """Télécharge la vidéo publique avec yt-dlp (sans contournement de protection).

    Si la plateforme refuse, on lève DownloadError avec la marche à suivre : utiliser le bouton
    « Enregistrer la vidéo » de TikTok (quand le créateur l'autorise) puis importer le fichier.
    """
    try:
        import yt_dlp
    except Exception as e:
        raise DownloadError("yt-dlp n'est pas installé (relancez start.sh).") from e
    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "overwrites": True, "noplaylist": True,
            "outtmpl": str(dest_dir / "reference.%(ext)s"), "format": "best[ext=mp4]/best",
            "socket_timeout": 15, "retries": 1, "max_filesize": 300 * 1024 * 1024}
    ff = config.ffmpeg_exe()
    if ff:
        opts["ffmpeg_location"] = ff
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        msg = str(e).replace("ERROR: ", "")[:200]
        raise DownloadError(
            "Téléchargement refusé par la plateforme. Ouvrez la vidéo dans TikTok, utilisez « Partager → "
            "Enregistrer la vidéo » (si le créateur l'autorise), puis importez le fichier ici. "
            f"(détail : {msg})") from None
    files = sorted(dest_dir.glob("reference.*"))
    if not files:
        raise DownloadError("Aucun fichier reçu.")
    return {"file": files[0], "title": info.get("title") or "", "author": info.get("uploader") or "",
            "duration": info.get("duration"), "views": info.get("view_count"),
            "caption": (info.get("description") or "")[:500]}


# ------------------------------------------------------------------ transcription

def transcribe(video: Path) -> dict[str, Any] | None:
    """Transcription mot à mot (faster-whisper, modèle « base », CPU). None si indisponible."""
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return None
    try:
        model = WhisperModel("base", device="cpu", compute_type="int8",
                             download_root=str(config.MODELS_DIR / "whisper"))
        segs, info = model.transcribe(str(video), word_timestamps=True, vad_filter=True, beam_size=1)
        words = [{"w": w.word.strip(), "d": round(w.start, 2), "f": round(w.end, 2)}
                 for s in segs for w in (s.words or []) if w.word.strip()]
    except Exception as e:
        log("recipe.transcribe", f"Transcription impossible : {e}", level="warning")
        return None
    if not words:
        return {"language": info.language, "words": [], "text": "", "wpm": 0, "hook_text": "", "has_voice": False}
    span = max(1.0, words[-1]["f"] - words[0]["d"])
    return {"language": info.language, "words": words[:600], "text": " ".join(w["w"] for w in words)[:4000],
            "wpm": round(len(words) / span * 60), "has_voice": True,
            "hook_text": " ".join(w["w"] for w in words if w["d"] < 3.2)}


# ------------------------------------------------------------------ synthèse

def heuristic_recipe(profile: dict[str, Any], tr: dict[str, Any] | None) -> dict[str, Any]:
    out = {
        "caption_style": "word_by_word",
        "words_on_screen": 2 if (profile.get("avg_shot_s") or 3) < 1.8 else 3,
        "caption_position": "center",
        "zoom_punch": (profile.get("motion") or 0) > 0.45 or (profile.get("cuts_per_min") or 0) > 30,
        "music_cue": "action" if (profile.get("motion") or 0) > 0.5 else
                     ("mystery" if (profile.get("brightness") or 0.5) < 0.3 else "tension"),
    }
    if tr and tr.get("has_voice"):
        out["wpm"] = tr["wpm"]
        out["voice_speed"] = round(min(1.25, max(0.85, tr["wpm"] / 165)), 2)
        out["hook_example"] = tr.get("hook_text", "")
        first = tr["hook_text"]
        out["hook_pattern"] = ("question directe au spectateur" if "?" in first else
                               "chiffre ou date précise" if re.search(r"\d", first) else
                               "phrase choc dès la première seconde")
    return out


def llm_recipe(profile: dict[str, Any], tr: dict[str, Any] | None, meta: dict[str, Any]) -> dict[str, Any] | None:
    s = get_settings()
    if s["llm_provider"] == "demo":
        return None
    from .llm import providers

    schema = {"type": "object", "additionalProperties": False,
              "required": ["hook_pattern", "structure", "tone", "why_it_works", "caption_style", "zoom_punch"],
              "properties": {
                  "hook_pattern": {"type": "string"}, "tone": {"type": "string"}, "why_it_works": {"type": "string"},
                  "caption_style": {"type": "string", "enum": ["word_by_word", "phrase"]},
                  "zoom_punch": {"type": "boolean"},
                  "structure": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                "required": ["part", "pattern"],
                                "properties": {"part": {"type": "string"}, "pattern": {"type": "string"}}}}}}
    prompt = (f"Mesures de la vidéo de référence : {json.dumps({k: v for k, v in profile.items() if k != 'palette'}, ensure_ascii=False)}\n"
              f"Métadonnées : {json.dumps(meta, ensure_ascii=False)}\n"
              f"Transcription (extrait) : {(tr or {}).get('text', '')[:2500]}\n\n"
              "Décris la RECETTE de cette vidéo (pas son contenu) : le motif de l'accroche des 3 premières "
              "secondes, la structure en parties, le ton, pourquoi elle marche, et le style de sous-titres. "
              "Ne recopie aucune phrase de la transcription.")
    try:
        data, _ = providers.generate_json("Tu es analyste de formats vidéo courts (TikTok, Shorts). Réponds en français.",
                                          prompt, schema, purpose="recipe")
        return data
    except Exception as e:
        log("recipe.llm", f"Synthèse IA de la recette impossible : {e}", level="warning")
        return None


def enrich(profile: dict[str, Any], video: Path, meta: dict[str, Any], progress=lambda m: None) -> dict[str, Any]:
    """Ajoute transcription + recette (heuristique, puis IA si configurée) à un profil mesuré."""
    progress("Transcription de la référence…")
    tr = transcribe(video)
    rec = heuristic_recipe(profile, tr)
    progress("Synthèse de la recette…")
    ai = llm_recipe(profile, tr, meta)
    if ai:
        rec.update({k: v for k, v in ai.items() if v not in (None, "", [])})
        rec["recipe_source"] = "IA + mesures"
    else:
        rec["recipe_source"] = "mesures locales" + (" + transcription" if tr and tr.get("has_voice") else "")
    out = {**profile, **rec}
    if tr:
        out["transcript"] = {k: tr[k] for k in ("language", "wpm", "has_voice", "hook_text")}
    out["recipe_summary"] = describe_recipe(out)
    return out
