"""Audio procédural (aucune musique ni son sous licence tierce) + synthèse vocale optionnelle.

- Ambiances par série (vent, bourdon, foule, nature), nappes musicales par humeur,
  effets sonores synthétisés (impact, souffle, stinger, sifflet, cloche du Système…).
- Voix : « none » (sous-titres seuls), « espeak » (espeak-ng local, gratuit) ou
  « elevenlabs » (clé API requise). Le mixage atténue la musique sous les voix (ducking).
Tous les sons générés ici sont des créations originales du projet (libres d'utilisation).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import wave
import zlib
from pathlib import Path

import numpy as np

from .. import config

SR = 44100


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _env(n: int, a: float = 0.01, r: float = 0.2) -> np.ndarray:
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, min(na, n))[: min(na, n)]
    if nr < n:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _smooth_noise(n: int, rng: np.random.Generator, k: int = 64) -> np.ndarray:
    """Bruit filtré (moyenne glissante par FFT) : rapide et sans dépendance."""
    x = rng.standard_normal(n + k)
    c = np.cumsum(x)
    y = (c[k:] - c[:-k]) / k
    return y[:n] / (np.abs(y).max() + 1e-9)


# ------------------------------------------------------------------- effets

def sfx(name: str, rng: np.random.Generator | None = None) -> np.ndarray:
    rng = rng or np.random.default_rng(zlib.crc32(name.encode()))
    if name == "impact":
        t = _t(0.7)
        x = np.sin(2 * np.pi * (90 * np.exp(-t * 6) + 40) * t) * np.exp(-t * 6)
        x += _smooth_noise(len(t), rng, 8) * np.exp(-t * 18) * 0.6
    elif name == "whoosh":
        t = _t(0.8)
        x = _smooth_noise(len(t), rng, 12) * np.sin(np.pi * t / 0.8) ** 2
    elif name == "stinger":
        t = _t(2.2)
        x = sum(np.sin(2 * np.pi * f * t) for f in (220, 233.1, 311.1, 466.2)) / 4
        x *= np.exp(-t * 1.6) * _env(len(t), 0.005, 0.5)
        x += _smooth_noise(len(t), rng, 4) * np.exp(-t * 9) * 0.4
    elif name == "heartbeat":
        t = _t(1.6)
        x = np.zeros_like(t)
        for off in (0.0, 0.28, 0.8, 1.08):
            tt = t - off
            m = tt >= 0
            x[m] += np.sin(2 * np.pi * 55 * tt[m]) * np.exp(-tt[m] * 22)
    elif name == "creak":
        t = _t(1.4)
        f = 180 + 60 * np.sin(2 * np.pi * 1.3 * t)
        x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * 0.3 * _env(len(t), 0.1, 0.4)
        x = np.convolve(x, np.ones(6) / 6, mode="same")
    elif name == "footsteps":
        t = _t(2.0)
        x = np.zeros_like(t)
        for off in (0.0, 0.55, 1.1, 1.65):
            tt = t - off
            m = (tt >= 0) & (tt < 0.15)
            x[m] += _smooth_noise(int(m.sum()), rng, 20) * np.exp(-tt[m] * 30)
    elif name == "whistle":
        t = _t(1.0)
        x = np.sin(2 * np.pi * 2900 * t + 3 * np.sin(2 * np.pi * 30 * t)) * _env(len(t), 0.02, 0.1) * 0.5
    elif name == "kick":
        t = _t(0.35)
        x = np.sin(2 * np.pi * (140 * np.exp(-t * 20) + 60) * t) * np.exp(-t * 14)
        x += _smooth_noise(len(t), rng, 3) * np.exp(-t * 60) * 0.5
    elif name == "crowd_roar":
        t = _t(2.5)
        x = _smooth_noise(len(t), rng, 30) * np.sin(np.pi * t / 2.5) * 0.9
    elif name in ("chime", "system_ping"):
        t = _t(1.5)
        base = 1320 if name == "chime" else 1760
        x = (np.sin(2 * np.pi * base * t) + 0.5 * np.sin(2 * np.pi * base * 1.5 * t)) * np.exp(-t * 4) * 0.5
    elif name == "glitch":
        t = _t(0.6)
        x = np.sign(np.sin(2 * np.pi * rng.uniform(80, 400) * t)) * (rng.random(len(t)) > 0.5) * 0.4
        x *= _env(len(t), 0.001, 0.05)
    elif name == "wind":
        t = _t(3.0)
        x = _smooth_noise(len(t), rng, 200) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.4 * t)) * _env(len(t), 0.8, 0.8)
    elif name == "door_slam":
        t = _t(1.0)
        x = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 8) + _smooth_noise(len(t), rng, 5) * np.exp(-t * 25) * 0.7
    elif name == "breath":
        t = _t(1.6)
        x = _smooth_noise(len(t), rng, 40) * np.sin(np.pi * t / 1.6) ** 3 * 0.5
    elif name == "magic_cast":
        t = _t(1.4)
        f = 400 + 900 * t
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.05, 0.6) * 0.4
        x += _smooth_noise(len(t), rng, 6) * np.sin(np.pi * t / 1.4) * 0.3
    elif name == "sword":
        t = _t(0.8)
        x = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 5) * 0.3 + _smooth_noise(len(t), rng, 4) * np.exp(-t * 20) * 0.4
    else:
        x = np.zeros(int(0.2 * SR))
    x = np.asarray(x, dtype=np.float64)
    return x / (np.abs(x).max() + 1e-9) * 0.8


# ------------------------------------------------------------------- musique

def _note(f: float, dur: float, decay: float = 2.0, harm=(1, 0.5, 0.25)) -> np.ndarray:
    t = _t(dur)
    x = sum(a * np.sin(2 * np.pi * f * (k + 1) * t) for k, a in enumerate(harm))
    return x * np.exp(-t * decay)


def music_bed(cue: str, dur: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    if cue == "silence":
        return _smooth_noise(n, rng, 400) * 0.02
    if cue in ("tension", "mystery"):
        base = 55.0 if cue == "tension" else 73.4
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.08 * t)
        out += (np.sin(2 * np.pi * base * t) + 0.6 * np.sin(2 * np.pi * base * 1.006 * t)
                + 0.3 * np.sin(2 * np.pi * base * 1.5 * t)) * (0.35 + 0.3 * lfo)
        if cue == "tension":
            out += np.sin(2 * np.pi * base * 16 * 1.059 * t) * 0.04 * lfo
        else:
            for k in range(int(dur / 2.7)):
                f = rng.choice([587.3, 659.3, 698.5, 880.0])
                s = int((k * 2.7 + rng.uniform(0, 1)) * SR)
                nn = _note(f, 2.5, 2.5)[: max(0, n - s)]
                out[s:s + len(nn)] += nn * 0.12
    elif cue in ("calm", "sad"):
        chords = [[261.6, 329.6, 392.0], [220.0, 261.6, 329.6], [174.6, 220.0, 261.6], [196.0, 246.9, 293.7]]
        if cue == "sad":
            chords = [[220.0, 261.6, 329.6], [174.6, 220.0, 261.6], [196.0, 233.1, 293.7], [164.8, 207.7, 246.9]]
        seg = 3.0
        for k in range(int(dur / seg) + 1):
            s = int(k * seg * SR)
            nn = min(int(seg * SR), n - s)
            if nn <= 0:
                break
            tt = np.arange(nn) / SR
            ch = chords[k % 4]
            pad = sum(np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2 * tt) for f in ch) / 3
            out[s:s + nn] += pad * _env(nn, 0.6, 0.6) * 0.3
            for j in range(4 if cue == "calm" else 2):
                ns = s + int(j * seg / (4 if cue == "calm" else 2) * SR)
                note = _note(ch[j % 3] * 2, 1.2, 3.0)[: max(0, n - ns)]
                out[ns:ns + len(note)] += note * 0.12
    elif cue in ("epic", "action"):
        bpm = 128 if cue == "action" else 92
        beat = 60 / bpm
        roots = [110.0, 87.3, 130.8, 98.0]
        for k in range(int(dur / beat) + 1):
            s = int(k * beat * SR)
            if s >= n:
                break
            kk = sfx("kick", rng) * (0.9 if k % 2 == 0 else 0.5)
            out[s:s + len(kk)] += kk[: n - s] * (0.7 if cue == "action" else 0.9)
            if cue == "action" and k % 2 == 1:
                sn = _smooth_noise(int(0.15 * SR), rng, 3) * np.exp(-np.arange(int(0.15 * SR)) / SR * 30)
                out[s:s + len(sn)] += sn[: n - s] * 0.35
            if cue == "action":
                hs = s + int(beat / 2 * SR)
                if hs < n:
                    hh = rng.standard_normal(int(0.04 * SR)) * np.exp(-np.arange(int(0.04 * SR)) / SR * 120)
                    out[hs:hs + len(hh)] += hh[: n - hs] * 0.12
            r = roots[(k // 4) % 4]
            bl = _note(r, beat, 3.0, harm=(1, 0.6, 0.4, 0.3))[: n - s]
            out[s:s + len(bl)] += bl * 0.35
        if cue == "epic":
            str_ = sum(np.sin(2 * np.pi * f * t + np.sin(2 * np.pi * 5 * t) * 0.02) for f in (220, 277.2, 329.6)) / 3
            out += str_ * 0.18 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t))
    m = np.abs(out).max()
    return out / m * 0.6 if m > 0 else out


def ambience(series_id: str, dur: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed + 7)
    n = int(dur * SR)
    t = np.arange(n) / SR
    if series_id == "horror":
        x = _smooth_noise(n, rng, 300) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * t)) * 0.5
        x += np.sin(2 * np.pi * 50 * t) * 0.05  # bourdonnement électrique
    elif series_id == "football":
        x = _smooth_noise(n, rng, 25) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t)) * 0.45
    else:
        x = _smooth_noise(n, rng, 150) * 0.3
        for k in range(int(dur / 3)):
            s = int((k * 3 + rng.uniform(0, 2)) * SR)
            ch = np.sin(2 * np.pi * (2400 + 800 * np.sin(np.linspace(0, 6, int(0.12 * SR)))) *
                        np.arange(int(0.12 * SR)) / SR) * 0.05
            out_len = min(len(ch), max(0, n - s))
            x[s:s + out_len] += ch[:out_len]
    return x


# ------------------------------------------------------------------- voix

def tts_status() -> dict:
    from ..core import get_settings
    from . import voices

    prov = get_settings()["tts_provider"]
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    pst = voices.status()
    return {
        "active": prov,
        "piper": {"ready": pst["ready"], "label": "Piper — voix neuronales FR/EN (gratuit, hors ligne)",
                  "note": None if pst["ready"] else (
                      "Les voix seront téléchargées automatiquement au premier épisode (≈ 500 Mo), "
                      "ou via le bouton « Télécharger les voix »." if pst["library"]
                      else "Configuration requise : paquet piper-tts non installé.")},
        "espeak": {"ready": bool(espeak), "label": "espeak-ng (local, gratuit, voix robotique)",
                   "note": None if espeak else "Configuration requise : sudo apt install espeak-ng"},
        "elevenlabs": {"ready": bool(os.environ.get("ELEVENLABS_API_KEY")), "label": "ElevenLabs (payant, clé API)",
                       "note": "Renseignez un voice_id par personnage dans la bible."},
        "none": {"ready": True, "label": "Aucune voix (sous-titres seuls)"},
        "piper_models": pst,
    }


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16 if sw == 2 else np.uint8).astype(np.float64)
    if sw == 1:
        data = (data - 128) / 128
    else:
        data /= 32768
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        idx = np.linspace(0, len(data) - 1, int(len(data) * SR / sr))
        data = np.interp(idx, np.arange(len(data)), data)
    return data


def write_wav(path: Path, x: np.ndarray) -> None:
    """x : mono (n,) ou stéréo (n, 2), valeurs en [-1, 1]."""
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def synthesize_voice(text: str, character: dict, out: Path, provider: str, lang: str = "fr") -> Path | None:
    """Produit un WAV pour une réplique. Renvoie None si aucune voix n'est configurée."""
    if provider == "none" or not text.strip():
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    pitch = float(character.get("voice", {}).get("pitch", 1.0))
    if provider == "piper":
        from . import voices

        return voices.synthesize(text, character, lang, out)
    if provider == "espeak":
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            from ..core import ConfigRequired
            raise ConfigRequired("Configuration requise : espeak-ng n'est pas installé.")
        p = int(max(0, min(99, 50 * pitch)))
        subprocess.run([exe, "-v", "fr" if lang == "fr" else "en-us", "-s", "160", "-p", str(p), "-w", str(out), text],
                       check=True, capture_output=True, timeout=60)
        return out
    if provider == "elevenlabs":
        import httpx

        from ..core import ConfigRequired, get_settings
        key = os.environ.get("ELEVENLABS_API_KEY")
        voice_id = character.get("voice", {}).get("voice_id")
        if not key:
            raise ConfigRequired("Configuration requise : clé ELEVENLABS_API_KEY absente.")
        if not voice_id:
            raise ConfigRequired(f"Configuration requise : aucun voice_id ElevenLabs pour {character['name']}.")
        r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                       headers={"xi-api-key": key}, timeout=120,
                       json={"text": text, "model_id": get_settings()["elevenlabs_model"]})
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs a répondu {r.status_code} : {r.text[:200]}")
        mp3 = out.with_suffix(".mp3")
        mp3.write_bytes(r.content)
        subprocess.run([config.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(mp3), "-ar", str(SR), str(out)],
                       check=True, timeout=120)
        return out
    return None


def envelope(x: np.ndarray, fps: int) -> np.ndarray:
    hop = SR // fps
    n = len(x) // hop
    if n == 0:
        return np.zeros(0)
    e = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    return e / (e.max() + 1e-9)


# ------------------------------------------------------------------- mixage

def mix_episode(plan: dict, series_id: str, voices: dict[str, dict], out: Path,
                music_db: float | None = None) -> Path:
    total = plan["total"]
    n = int(total * SR) + SR
    music = np.zeros(n)
    amb = ambience(series_id, total + 1)
    fx = np.zeros(n)
    vox = np.zeros(n)
    # musique par scène avec fondus
    for sc in plan["scenes"]:
        s, d = int(sc["start"] * SR), sc["duration"]
        bed = music_bed(sc["music"], d + 0.6, seed=zlib.crc32(sc["scene_id"].encode()) % 1000)
        bed *= _env(len(bed), 0.4, 0.6)
        e = min(n, s + len(bed))
        music[s:e] += bed[: e - s]
    rng = np.random.default_rng(1)
    for sh in plan["shots"]:
        s = int(sh["start"] * SR)
        for k, name in enumerate(sh.get("sfx", [])):
            x = sfx(name, rng) * (0.9 if name in ("impact", "stinger", "door_slam") else 0.6)
            st = s + int(k * 0.15 * SR)
            e = min(n, st + len(x))
            fx[st:e] += x[: e - st]
        v = voices.get(sh["shot_id"])
        if v and v.get("path"):
            x = read_wav(Path(v["path"]))
            st = s + int(0.15 * SR)
            e = min(n, st + len(x))
            vox[st:e] += x[: e - st] * 0.95
    # ducking : la musique baisse sous les voix
    duck = np.convolve((np.abs(vox) > 0.02).astype(float), np.ones(SR // 10) / (SR // 10), mode="same")
    music *= 1 - 0.55 * np.clip(duck * 3, 0, 1)
    mlev = 0.45 if music_db is None else float(np.clip(0.45 * 10 ** ((music_db + 20) / 20), 0.12, 0.7))
    mono = music * mlev + amb * 0.35 + fx * 0.7 + vox
    # légère stéréo : ambiance décorrélée
    left = mono + amb * 0.08
    right = mono - amb * 0.08
    st = np.stack([left, right], axis=1)
    st = np.tanh(st * 1.2) / np.tanh(1.2)
    peak = np.abs(st).max()
    if peak > 0:
        st = st / peak * 0.89
    fade = int(0.4 * SR)
    st[-fade:] *= np.linspace(1, 0, fade)[:, None]
    st = st[: int(total * SR)]
    write_wav(out, st)
    return out
