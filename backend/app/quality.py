"""Contrôle d'originalité (idée TrendForge) : on copie la recette, jamais la vidéo.

Compare des empreintes perceptuelles (dHash 64 bits, 2 images/s) du rendu et de la vidéo de
référence. Une distance de Hamming ≤ 6 signale une image quasi identique.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from . import config

FPS = 2
SEUIL = 6


def dhashes(video: Path) -> np.ndarray:
    ff = config.ffmpeg_exe()
    p = subprocess.run([ff, "-v", "error", "-i", str(video), "-vf", f"fps={FPS},scale=9:8,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=600)
    raw = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(raw) // 72
    if n == 0:
        return np.zeros(0, dtype=np.uint64)
    px = raw[: n * 72].reshape(n, 8, 9).astype(np.int16)
    bits = (px[:, :, 1:] > px[:, :, :-1]).reshape(n, 64)
    return np.packbits(bits, axis=1).view(">u8").reshape(n).astype(np.uint64)


def _popcount(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.uint64)
    c = np.zeros(x.shape, dtype=np.uint64)
    for _ in range(64):
        c += x & np.uint64(1)
        x = x >> np.uint64(1)
    return c


def originality(render: Path, reference: Path) -> dict[str, Any]:
    a, b = dhashes(render), dhashes(reference)
    if not len(a) or not len(b):
        return {"checked": False, "reason": "empreintes illisibles"}
    # on ignore les images quasi unies (fonds noirs, fondus) qui donnent des faux positifs
    a = a[(a != 0) & (a != np.uint64(0xFFFFFFFFFFFFFFFF))]
    b = b[(b != 0) & (b != np.uint64(0xFFFFFFFFFFFFFFFF))]
    if not len(a) or not len(b):
        return {"checked": True, "matches": 0, "frames": 0, "ok": True}
    dist = _popcount(a[:, None] ^ b[None, :])
    matches = int((dist.min(axis=1) <= SEUIL).sum())
    return {"checked": True, "frames": int(len(a)), "matches": matches, "ok": matches == 0,
            "verdict": "Aucune image de la référence n'a été reprise." if matches == 0 else
            f"{matches} image(s) trop proches de la référence : vérifiez avant de publier."}
