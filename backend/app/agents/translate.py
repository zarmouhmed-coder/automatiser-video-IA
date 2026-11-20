"""Traduction FR → EN des épisodes.

Ordre de préférence (réglage « translation_provider » = auto) :
1. textes des gabarits du mode démo : traductions écrites à la main (qualité relue) ;
2. modèle d'IA configuré (Claude / Ollama), qui reçoit tout le script d'un coup ;
3. modèle de traduction local hors ligne (OPUS/Argos fr→en, exécuté avec CTranslate2) téléchargé
   une fois dans data/models/translate (~80 Mo).
Si rien n'est disponible, le texte français est conservé et l'épisode signale « traduction requise ».
"""
from __future__ import annotations

import json
import re
import threading
import zipfile
from pathlib import Path
from typing import Any

from .. import config
from ..core import get_settings

ARGOS_URL = "https://argos-net.com/v1/translate-fr_en-1_9.argosmodel"

DEMO_EN = {
    "03:33 — AILE B": "3:33 AM — WING B",
    "NUIT 4 — AILE B": "NIGHT 4 — WING B",
    "Sur la bande… c'était la voix de Clara.": "On the tape… it was Clara's voice.",
    "Quelqu'un a dit mon nom. Avec sa voix à elle.": "Someone said my name. In her voice.",
    "Une interférence. Une radio de camionneur, rien d'autre.": "Interference. A trucker's radio, nothing more.",
    "Les vieux câbles captent n'importe quoi, Léa.": "Old cables pick up anything, Léa.",
    "Chambre 13. Personne n'y a jamais été admis. Et pourtant, regardez.":
        "Room 13. No one was ever admitted there. And yet, look.",
    "Ce registre liste un patient de trop. Chaque année.": "This register lists one patient too many. Every year.",
    "Le dernier nom… c'est l'écriture de ma sœur.": "The last name… that's my sister's handwriting.",
    "Je repasse l'enregistrement. Ralenti à 50 %.": "Playing the recording back. Slowed to 50%.",
    "RÉÉCOUTE — 00:47": "PLAYBACK — 00:47",
    "Il était derrière toi. Pendant tout l'enregistrement.": "It was behind you. The whole recording.",
    "La porte 13 est entrouverte. À vous de décider.": "Door 13 is ajar. You decide.",
    "Léa doit-elle ouvrir la porte 13 ?": "Should Léa open door 13?",
    "Ouvrir la porte": "Open the door",
    "Fuir avec Samir": "Run with Samir",
    "À SUIVRE": "TO BE CONTINUED",
    "La chambre 13": "Room 13",
    "Le patient de trop": "One Patient Too Many",
    "La voix des absents": "The Voice of the Absent",
    "Une voix disparue sur un enregistrement.": "A vanished voice on a recording.",
    "Pressing haut ! Coupez Kaito de ses milieux !": "High press! Cut Kaito off from his midfield!",
    "Marco, remonte la ligne. Maintenant !": "Marco, push the line up. Now!",
    "Noa, il te faut deux secondes. Je te les donne.": "Noa, you need two seconds. I'll give them to you.",
    "Deux secondes ? Je n'en laisse jamais une.": "Two seconds? I never give anyone one.",
    "DUEL GAGNÉ": "DUEL WON",
    "LIGNE D'HORIZON — ÉLAN -30": "HORIZON LINE — MOMENTUM -30",
    "Je l'ai ! Deuxième Pas Fantôme, tant pis pour les crampes !":
        "Got it! Second Phantom Step, cramps be damned!",
    "PAS FANTÔME — 2/2": "PHANTOM STEP — 2/2",
    "POTEAU !": "OFF THE POST!",
    "Ma jambe… elle ne répond plus.": "My leg… it won't respond.",
    "Il reste dix minutes. Et une seule décision.": "Ten minutes left. And one decision.",
    "On change tout. Ou on tient.": "We change everything. Or we hold on.",
    "Quel plan pour les 10 dernières minutes ?": "What's the plan for the last 10 minutes?",
    "Tout pour l'attaque": "All-out attack",
    "Bloc bas et contre": "Low block & counter",
    "Le coach attend votre choix.": "The coach is waiting for your call.",
    "Deux secondes": "Two Seconds",
    "Le prix de l'Élan": "The Price of Momentum",
    "Poteau rentrant": "In Off the Post",
    "[SYSTÈME] Indice du jour : la carte ment.": "[SYSTEM] Hint of the day: the map lies.",
    "Ma propre carte… me ment ?": "My own map… is lying to me?",
    "Un indice par jour, et il choisit celui-là.": "One hint a day, and it picks that one.",
    "Les réincarnés font trop confiance à leurs fenêtres bleues.":
        "The reincarnated trust their blue windows too much.",
    "Chaque carte que tu traces, je l'efface. C'est mon travail.": "Every map you draw, I erase. That's my job.",
    "CARTE VIVANTE — MANA -20": "LIVING MAP — MANA -20",
    "Recule, Elio. Ma lame a faim.": "Step back, Elio. My blade is hungry.",
    "L'auberge du Pont… tu es sûr qu'elle existait ?": "The Bridge Inn… are you sure it existed?",
    "[SYSTÈME] Niveau 8 atteint. Évolution au niveau 10.": "[SYSTEM] Level 8 reached. Evolution at level 10.",
    "Où Elio doit-il aller ?": "Where should Elio go?",
    "Ruines d'Ost": "Ruins of Ost",
    "Cité de Verre": "Glass City",
    "Deux routes. Une seule carte fiable.": "Two roads. Only one map you can trust.",
    "Le nom d'Elio s'efface de sa propre carte.": "Elio's name fades from his own map.",
    "La carte qui ment": "The Map That Lies",
    "Le Héraut Gris": "The Grey Herald",
    "Ce que le monde oublie": "What the World Forgets",
    "Le Système affirme que la carte d'Elio ment.": "The System claims Elio's map is lying.",
}
PATTERNS = [
    (re.compile(r"^(\d+)' — FC AUBE (\d)-(\d) CORBEAUX$"), lambda m: f"{m[1]}' — FC AUBE {m[2]}-{m[3]} RAVENS"),
    (re.compile(r"^(\d+)e minute, mené (\d)-(\d), maintien en jeu\.$"),
     lambda m: f"Minute {m[1]}, down {m[2]}-{m[3]}, survival on the line."),
]
_lock = threading.Lock()
_model: dict[str, Any] = {}


# ------------------------------------------------------------- modèle local

def local_dir() -> Path:
    return config.MODELS_DIR / "translate" / "fr_en"


def local_ready() -> bool:
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
    except Exception:
        return False
    return bool(list(local_dir().glob("*/model/model.bin")))


def download_local(progress=None) -> None:
    import httpx

    d = local_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "model.argosmodel.part"
    if progress:
        progress(None, "Téléchargement du modèle de traduction FR→EN (~80 Mo)…")
    with httpx.stream("GET", ARGOS_URL, follow_redirects=True, timeout=600) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Téléchargement du modèle de traduction impossible ({r.status_code}).")
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    with zipfile.ZipFile(tmp) as z:
        for n in z.namelist():
            if "/stanza/" in n or n.endswith("/"):
                continue
            dest = (d / n).resolve()
            if d.resolve() not in dest.parents:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(n))
    tmp.unlink(missing_ok=True)


def _local_model():
    with _lock:
        if "tr" not in _model:
            import ctranslate2
            import sentencepiece as spm

            base = next(local_dir().glob("*/model/model.bin")).parent.parent
            _model["sp"] = spm.SentencePieceProcessor(model_file=str(base / "sentencepiece.model"))
            _model["tr"] = ctranslate2.Translator(str(base / "model"), device="cpu", compute_type="int8")
        return _model["sp"], _model["tr"]


def _split(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p for p in parts if p]


def translate_local(texts: list[str]) -> list[str]:
    sp, tr = _local_model()
    out = []
    for t in texts:
        if not t.strip():
            out.append(t)
            continue
        sents = _split(t)
        with _lock:
            res = tr.translate_batch([sp.encode(s, out_type=str) for s in sents], beam_size=4)
        dec = ["".join(r.hypotheses[0]).replace("▁", " ").strip() for r in res]
        out.append(" ".join(dec))
    return out


# ------------------------------------------------------------- script

def _collect(script: dict) -> dict[str, str]:
    items: dict[str, str] = {}
    for k in ("title", "logline", "hook"):
        items[k] = script.get(k, "")
    end = script.get("ending", {})
    items["ending.vote_question"] = end.get("vote_question", "")
    for i, o in enumerate(end.get("vote_options", [])):
        items[f"ending.vote_options.{i}"] = o
    for sc in script["scenes"]:
        for sh in sc["shots"]:
            for k in ("text", "narration", "caption"):
                if sh.get(k):
                    items[f"shot.{sh['id']}.{k}"] = sh[k]
    return {k: v for k, v in items.items() if v}


def _demo(text: str) -> str | None:
    if text in DEMO_EN:
        return DEMO_EN[text]
    for rx, fn in PATTERNS:
        m = rx.match(text)
        if m:
            return fn(m)
    if text.startswith("[OBSERVATEUR] "):
        return None
    return None


def translate_script(script: dict, episode_id: int | None = None) -> dict[str, Any]:
    """Renvoie {"en": {...clé → texte}, "source": ..., "missing": [...]}."""
    items = _collect(script)
    done: dict[str, str] = {}
    sources: set[str] = set()
    for k, v in items.items():
        d = _demo(v)
        if d:
            done[k] = d
            sources.add("traductions relues (gabarits)")
    rest = {k: v for k, v in items.items() if k not in done}
    s = get_settings()
    pref = s.get("translation_provider", "auto")
    errors = []
    if rest and s["llm_provider"] != "demo" and pref in ("auto", "llm"):
        try:
            from ..llm import providers

            schema = {"type": "object", "properties": {"items": {"type": "array", "items": {
                "type": "object", "properties": {"key": {"type": "string"}, "en": {"type": "string"}},
                "required": ["key", "en"], "additionalProperties": False}}},
                "required": ["items"], "additionalProperties": False}
            data, meta = providers.generate_json(
                "Tu traduis des épisodes de séries courtes du français vers l'anglais naturel et percutant, "
                "adapté aux sous-titres mobiles (même longueur, même ton, noms propres conservés). "
                "Les captions en MAJUSCULES restent en majuscules. Les options de vote restent sous 25 caractères.",
                json.dumps(rest, ensure_ascii=False), schema, purpose="translation", episode_id=episode_id)
            for it in data.get("items", []):
                if it["key"] in rest and it["en"].strip():
                    done[it["key"]] = it["en"].strip()
            sources.add(meta["provider"])
        except Exception as e:  # on tente la suite
            errors.append(f"IA : {e}")
    rest = {k: v for k, v in items.items() if k not in done}
    if rest and pref in ("auto", "argos"):
        try:
            if not local_ready():
                download_local()
            keys = list(rest)
            for k, v in zip(keys, translate_local([rest[k] for k in keys])):
                done[k] = v
            sources.add("modèle local hors ligne")
        except Exception as e:
            errors.append(f"modèle local : {e}")
    missing = [k for k in items if k not in done]
    return {"en": done, "source": ", ".join(sorted(sources)) or "—", "missing": missing, "errors": errors}


def localize(script: dict, lang: str) -> dict:
    """Script avec les textes de la langue demandée (le français est la langue source)."""
    if lang == "fr":
        return script
    tr = (script.get("i18n") or {}).get(lang) or {}
    s = json.loads(json.dumps(script))
    for k in ("title", "logline", "hook"):
        if tr.get(k):
            s[k] = tr[k]
    end = s.get("ending", {})
    if tr.get("ending.vote_question"):
        end["vote_question"] = tr["ending.vote_question"]
    end["vote_options"] = [tr.get(f"ending.vote_options.{i}", o) for i, o in enumerate(end.get("vote_options", []))]
    for sc in s["scenes"]:
        for sh in sc["shots"]:
            for k in ("text", "narration", "caption"):
                if sh.get(k) and tr.get(f"shot.{sh['id']}.{k}"):
                    sh[k] = tr[f"shot.{sh['id']}.{k}"]
    return s
