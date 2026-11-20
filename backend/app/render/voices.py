"""Voix neuronales Piper (gratuites, hors ligne après téléchargement) en français et en anglais.

Les modèles (licences libres, voir https://huggingface.co/rhasspy/piper-voices) sont téléchargés une
seule fois dans data/models/piper. Chaque personnage reçoit une voix stable, choisie selon son genre,
puis personnalisée par sa hauteur (pitch) ; l'entité de l'horreur reçoit un traitement spectral.
"""
from __future__ import annotations

import json
import threading
import wave
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from .. import config

HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# (modèle, chemin HF, speaker_id) — classés par genre
CATALOG: dict[str, dict[str, list[tuple[str, str, int | None]]]] = {
    "fr": {
        "F": [("fr_FR-siwis-medium", "fr/fr_FR/siwis/medium", None), ("fr_FR-upmc-medium", "fr/fr_FR/upmc/medium", 0)],
        "M": [("fr_FR-tom-medium", "fr/fr_FR/tom/medium", None), ("fr_FR-upmc-medium", "fr/fr_FR/upmc/medium", 1)],
    },
    "en": {
        "F": [("en_US-amy-medium", "en/en_US/amy/medium", None), ("en_US-lessac-medium", "en/en_US/lessac/medium", None)],
        "M": [("en_US-ryan-medium", "en/en_US/ryan/medium", None), ("en_US-joe-medium", "en/en_US/joe/medium", None)],
    },
}
NARRATOR = {"fr": ("fr_FR-tom-medium", "fr/fr_FR/tom/medium", None), "en": ("en_US-ryan-medium", "en/en_US/ryan/medium", None)}

_lock = threading.Lock()
_loaded: dict[str, Any] = {}


def models_dir() -> Path:
    d = config.MODELS_DIR / "piper"
    d.mkdir(parents=True, exist_ok=True)
    return d


def all_models() -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for lang in CATALOG.values():
        for lst in lang.values():
            for name, path, _ in lst:
                seen[name] = path
    for name, path, _ in NARRATOR.values():
        seen[name] = path
    return sorted(seen.items())


def installed(name: str) -> bool:
    d = models_dir()
    return (d / f"{name}.onnx").exists() and (d / f"{name}.onnx.json").exists()


def status() -> dict[str, Any]:
    try:
        import piper  # noqa: F401
        lib = True
    except Exception:
        lib = False
    models = [{"name": n, "installed": installed(n)} for n, _ in all_models()]
    return {"library": lib, "models": models, "ready": lib and all(m["installed"] for m in models),
            "missing": [m["name"] for m in models if not m["installed"]]}


def download(names: list[str] | None = None, progress=None) -> list[str]:
    """Télécharge les modèles manquants (≈ 60-75 Mo chacun). Renvoie les modèles téléchargés."""
    import httpx

    done = []
    todo = [(n, p) for n, p in all_models() if (names is None or n in names) and not installed(n)]
    for i, (name, path) in enumerate(todo):
        for ext in ("onnx.json", "onnx"):
            dest = models_dir() / f"{name}.{ext}"
            tmp = dest.with_suffix(dest.suffix + ".part")
            if progress:
                progress(i / max(1, len(todo)), f"Téléchargement de la voix {name} ({i + 1}/{len(todo)})")
            with httpx.stream("GET", f"{HF}/{path}/{name}.{ext}", follow_redirects=True, timeout=600) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"Téléchargement impossible ({r.status_code}) : {name}.{ext}")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            tmp.replace(dest)
        done.append(name)
    return done


def _voice(name: str):
    with _lock:
        if name not in _loaded:
            from piper import PiperVoice

            _loaded[name] = PiperVoice.load(str(models_dir() / f"{name}.onnx"))
        return _loaded[name]


def gender_of(character: dict) -> str:
    g = (character.get("voice") or {}).get("gender")
    if g in ("F", "M"):
        return g
    return "M"


def assign(character: dict, lang: str) -> tuple[str, int | None]:
    """Voix stable pour un personnage (même personnage → même voix, d'un épisode à l'autre)."""
    v = character.get("voice") or {}
    override = v.get(f"piper_{lang}")
    if override:
        return override, v.get(f"piper_{lang}_speaker")
    if not character.get("id"):
        name, _, spk = NARRATOR[lang]
        return name, spk
    options = CATALOG[lang][gender_of(character)]
    name, _, spk = options[zlib.crc32(character["id"].encode()) % len(options)]
    return name, spk


def synthesize(text: str, character: dict, lang: str, out: Path) -> Path:
    from piper import SynthesisConfig

    name, spk = assign(character, lang)
    if not installed(name):
        raise FileNotFoundError(name)
    v = character.get("voice") or {}
    pitch = float(v.get("pitch", 1.0))
    speed = float(v.get("speed", 1.0))
    voice = _voice(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".raw.wav")
    # Débit naturel ; la hauteur est appliquée ensuite par rééchantillonnage (durée compensée ici).
    cfg = SynthesisConfig(speaker_id=spk, length_scale=pitch / speed, noise_scale=0.6, noise_w_scale=0.8)
    with _lock:
        with wave.open(str(raw), "wb") as w:
            voice.synthesize_wav(text, w, syn_config=cfg)
    from .audio import SR, read_wav, write_wav

    x = read_wav(raw)
    raw.unlink(missing_ok=True)
    if abs(pitch - 1.0) > 0.01:
        n = int(len(x) / pitch)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    if (character.get("appearance") or {}).get("archetype") == "entity":
        # voix spectrale : doublure grave + écho
        low = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 1.25)), np.arange(len(x)), x)[: len(x)]
        x = 0.7 * x + 0.5 * low
        d = int(0.09 * SR)
        echo = np.zeros(len(x) + d * 3)
        for k, g in enumerate((1.0, 0.45, 0.25, 0.12)):
            echo[k * d:k * d + len(x)] += x * g
        x = echo
    x = x / (np.abs(x).max() + 1e-9) * 0.92
    write_wav(out, x)
    return out


def voice_table(characters: list[dict]) -> list[dict]:
    rows = []
    for c in characters:
        rows.append({"id": c["id"], "name": c["name"], "gender": gender_of(c),
                     "fr": assign(c, "fr")[0], "en": assign(c, "en")[0],
                     "pitch": (c.get("voice") or {}).get("pitch", 1.0)})
    return rows


def describe() -> str:
    return json.dumps(status(), ensure_ascii=False)
