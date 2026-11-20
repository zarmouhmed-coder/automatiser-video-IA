"""Décors 2.5D procéduraux en couches (lointain / milieu / premier plan) pour la parallaxe.

Chaque couche est plus grande que l'image (marge pour les mouvements de caméra).
Un décor importé dans la Bibliothèque (clé `bg.<lieu>`) remplace la couche lointaine.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

MARGIN = 1.3
_library_bgs: dict[str, Path] = {}


def set_library_backgrounds(mapping: dict[str, Path]) -> None:
    _library_bgs.clear()
    _library_bgs.update(mapping)
    layers.cache_clear()


def _grad(w, h, top, bottom, mid=None) -> Image.Image:
    t = np.linspace(0, 1, h)[:, None]
    top, bottom = np.array(top, float), np.array(bottom, float)
    if mid is not None:
        mid = np.array(mid, float)
        col = np.where(t < 0.5, top + (mid - top) * (t * 2), mid + (bottom - mid) * ((t - 0.5) * 2))
    else:
        col = top + (bottom - top) * t
    arr = np.repeat(col[:, None, :], w, axis=1)
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB").convert("RGBA")


def _glow(img: Image.Image, xy, r, color, alpha=180, blur=None):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((xy[0] - r, xy[1] - r, xy[0] + r, xy[1] + r), fill=tuple(color) + (alpha,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur or r * 0.6)))


def _fog(w, h, y0, y1, color=(200, 210, 225), alpha=90, seed=1):
    rng = random.Random(seed)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(18):
        x = rng.uniform(-0.2, 1.0) * w
        y = rng.uniform(y0, y1) * h
        d.ellipse((x, y, x + rng.uniform(0.3, 0.7) * w, y + rng.uniform(0.04, 0.1) * h), fill=color + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(w * 0.03))


def _empty(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


# ------------------------------------------------------------------- HORREUR

def _exterior_sanatorium(w, h, rng):
    far = _grad(w, h, (6, 9, 18), (24, 30, 44))
    _glow(far, (w * 0.72, h * 0.18), w * 0.07, (200, 215, 235), 255, w * 0.01)
    _glow(far, (w * 0.72, h * 0.18), w * 0.2, (120, 140, 170), 70)
    d = ImageDraw.Draw(far)
    for _ in range(8):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.35)
        d.ellipse((x, y, x + w * 0.4, y + h * 0.03), fill=(10, 14, 24, 200))
    far = far.filter(ImageFilter.GaussianBlur(2))
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    bx0, bx1, by0, by1 = w * 0.08, w * 0.92, h * 0.33, h * 0.72
    d.rectangle((bx0, by0, bx1, by1), fill=(16, 19, 26, 255))
    d.polygon([(bx0 - 20, by0), (w * 0.5, by0 - h * 0.08), (bx1 + 20, by0)], fill=(12, 14, 20, 255))
    d.rectangle((w * 0.62, by0 - h * 0.12, w * 0.67, by0), fill=(12, 14, 20, 255))
    for row in range(3):
        for col in range(9):
            x = bx0 + (col + 0.5) * (bx1 - bx0) / 9
            y = by0 + (row + 0.6) * (by1 - by0) / 4
            lit = rng.random() < 0.08
            c = (190, 150, 80, 255) if lit else (28, 34, 44, 255)
            d.rectangle((x - w * 0.018, y - h * 0.025, x + w * 0.018, y + h * 0.025), fill=c)
            if lit:
                _glow(mid, (x, y), w * 0.04, (220, 160, 80), 120)
    d.rectangle((0, by1, w, h), fill=(10, 12, 16, 255))
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    for x in (w * 0.05, w * 0.92):
        d.polygon([(x - 25, h), (x - 8, h * 0.35), (x + 8, h * 0.35), (x + 25, h)], fill=(4, 5, 8, 255))
        for k in range(5):
            ang = rng.uniform(-2.6, -0.5)
            y = h * (0.4 + k * 0.06)
            d.line([(x, y), (x + math.cos(ang) * w * 0.18 * (1 if x < w / 2 else -1), y + math.sin(ang) * h * 0.08)],
                   fill=(4, 5, 8, 255), width=10)
    for i in range(30):
        x = i * w / 29
        d.line([(x, h * 0.78), (x, h * 0.88)], fill=(6, 7, 10, 255), width=8)
    d.line([(0, h * 0.8), (w, h * 0.8)], fill=(6, 7, 10, 255), width=6)
    near.alpha_composite(_fog(w, h, 0.78, 0.95, alpha=55, seed=rng.randint(0, 99)))
    return far, mid, near


def _corridor(w, h, rng):
    far = _grad(w, h, (14, 18, 22), (6, 8, 10))
    d = ImageDraw.Draw(far)
    vx, vy = w * 0.5, h * 0.47
    d.polygon([(0, 0), (w, 0), (vx + w * 0.08, vy - h * 0.06), (vx - w * 0.08, vy - h * 0.06)], fill=(20, 24, 26))
    d.polygon([(0, h), (w, h), (vx + w * 0.08, vy + h * 0.06), (vx - w * 0.08, vy + h * 0.06)], fill=(26, 28, 27))
    d.polygon([(0, 0), (vx - w * 0.08, vy - h * 0.06), (vx - w * 0.08, vy + h * 0.06), (0, h)], fill=(34, 40, 40))
    d.polygon([(w, 0), (vx + w * 0.08, vy - h * 0.06), (vx + w * 0.08, vy + h * 0.06), (w, h)], fill=(30, 36, 36))
    d.rectangle((vx - w * 0.08, vy - h * 0.06, vx + w * 0.08, vy + h * 0.06), fill=(4, 5, 6))
    d.rectangle((vx - w * 0.03, vy - h * 0.045, vx + w * 0.03, vy + h * 0.06), fill=(60, 18, 22))
    for k in range(1, 12):
        t = (k / 12) ** 1.6
        yb = h - (h - vy - h * 0.06) * t
        xl = vx - w * 0.08 - (vx - w * 0.08) * (1 - t)
        d.line([(xl, yb), (w - xl, yb)], fill=(18, 20, 20), width=3)
    for side in (-1, 1):
        for k, t in enumerate((0.25, 0.5, 0.68, 0.8)):
            x = vx + side * (w * 0.08 + (w * 0.5 - w * 0.08) * (1 - t))
            hh = h * 0.06 + (h * 0.42) * (1 - t)
            ww = w * 0.12 * (1 - t) + w * 0.02
            d.polygon([(x, vy + hh * 0.9), (x, vy - hh * 0.6), (x + side * ww, vy - hh * 0.75),
                       (x + side * ww, vy + hh * 1.05)], fill=(48, 52, 50), outline=(12, 14, 14))
    for t in (0.3, 0.6, 0.8):
        y = vy - h * 0.06 - (vy - h * 0.06) * (1 - t)
        ww = w * 0.04 + w * 0.2 * (1 - t)
        d.rectangle((vx - ww, y - 6, vx + ww, y + 6), fill=(190, 220, 210))
        _glow(far, (vx, y), ww * 1.4, (140, 200, 190), 90)
    far.alpha_composite(_fog(w, h, 0.4, 0.7, (90, 110, 110), 50, seed=3))
    mid = _empty(w, h)
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    d.rectangle((0, 0, w * 0.06, h), fill=(8, 9, 10, 255))
    d.rectangle((w * 0.94, 0, w, h), fill=(8, 9, 10, 255))
    return far, mid, near


def _archive_room(w, h, rng):
    far = _grad(w, h, (22, 18, 16), (10, 9, 8))
    d = ImageDraw.Draw(far)
    for col in range(5):
        x0 = w * (0.02 + col * 0.2)
        for row in range(7):
            y = h * (0.12 + row * 0.1)
            d.rectangle((x0, y + h * 0.085, x0 + w * 0.18, y + h * 0.095), fill=(50, 36, 26))
            x = x0
            while x < x0 + w * 0.17:
                bw = rng.uniform(0.02, 0.045) * w
                c = rng.choice([(90, 70, 50), (70, 60, 52), (110, 90, 60), (60, 50, 44)])
                d.rectangle((x, y + h * rng.uniform(0.01, 0.03), x + bw - 4, y + h * 0.085), fill=c)
                x += bw
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    d.rectangle((0, h * 0.78, w, h), fill=(40, 28, 20, 255))
    _glow(mid, (w * 0.8, h * 0.68), w * 0.25, (255, 190, 110), 110)
    d.polygon([(w * 0.74, h * 0.63), (w * 0.86, h * 0.63), (w * 0.82, h * 0.6), (w * 0.78, h * 0.6)], fill=(30, 60, 40, 255))
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    for _ in range(140):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(1, 4)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 220, 170, rng.randint(30, 110)))
    return far, mid, near.filter(ImageFilter.GaussianBlur(1))


def _bedroom(w, h, rng):
    far = _grad(w, h, (12, 16, 30), (8, 10, 16))
    d = ImageDraw.Draw(far)
    wx0, wy0, wx1, wy1 = w * 0.3, h * 0.18, w * 0.7, h * 0.5
    d.rectangle((wx0, wy0, wx1, wy1), fill=(40, 60, 100))
    _glow(far, (w * 0.6, h * 0.26), w * 0.05, (230, 235, 255), 255, 4)
    d.line([(w * 0.5, wy0), (w * 0.5, wy1)], fill=(10, 12, 18), width=14)
    d.line([(wx0, h * 0.34), (wx1, h * 0.34)], fill=(10, 12, 18), width=14)
    beam = _empty(w, h)
    ImageDraw.Draw(beam).polygon([(wx0, wy1), (wx1, wy1), (w * 0.95, h), (w * 0.1, h)], fill=(140, 160, 220, 50))
    far.alpha_composite(beam.filter(ImageFilter.GaussianBlur(20)))
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    d.rectangle((w * 0.15, wy0 - 20, w * 0.3, h * 0.62), fill=(50, 20, 30, 255))
    d.rectangle((w * 0.7, wy0 - 20, w * 0.85, h * 0.62), fill=(50, 20, 30, 255))
    d.rounded_rectangle((w * 0.05, h * 0.68, w * 0.7, h * 0.85), 30, fill=(30, 34, 50, 255))
    near = _empty(w, h)
    return far, mid, near


def _forest_night(w, h, rng):
    far = _grad(w, h, (5, 8, 14), (16, 22, 28))
    _glow(far, (w * 0.3, h * 0.15), w * 0.05, (210, 220, 240), 255, 5)
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    for _ in range(14):
        x = rng.uniform(0, w)
        tw = rng.uniform(0.02, 0.05) * w
        d.rectangle((x, h * 0.1, x + tw, h), fill=(14, 18, 22, 255))
    mid.alpha_composite(_fog(w, h, 0.5, 0.85, (120, 140, 150), 70, seed=5))
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    for x in (w * 0.02, w * 0.85):
        d.rectangle((x, 0, x + w * 0.12, h), fill=(3, 4, 5, 255))
    return far, mid, near


# ------------------------------------------------------------------- FOOTBALL

def _crowd(d, w, y0, y1, rng, colors, density=0.0025):
    for _ in range(int(w * (y1 - y0) * density)):
        x, y = rng.uniform(0, w), rng.uniform(y0, y1)
        r = rng.uniform(4, 9)
        d.ellipse((x - r, y - r, x + r, y + r), fill=rng.choice(colors))


def _stadium_night(w, h, rng):
    far = _grad(w, h, (6, 10, 24), (18, 28, 46))
    d = ImageDraw.Draw(far)
    for x in (w * 0.12, w * 0.88):
        d.rectangle((x - 10, h * 0.06, x + 10, h * 0.4), fill=(30, 34, 40))
        d.rectangle((x - 70, h * 0.05, x + 70, h * 0.09), fill=(230, 240, 255))
        _glow(far, (x, h * 0.07), w * 0.18, (210, 225, 255), 120)
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    d.polygon([(0, h * 0.22), (w, h * 0.22), (w, h * 0.5), (0, h * 0.5)], fill=(26, 30, 40, 255))
    _crowd(d, w, h * 0.24, h * 0.48, rng,
           [(245, 166, 35), (245, 166, 35), (220, 220, 220), (40, 40, 50), (122, 60, 255), (30, 21, 48)])
    d.rectangle((0, h * 0.47, w, h * 0.5), fill=(20, 22, 30, 255))
    for i in range(6):
        x = w * (0.05 + i * 0.16)
        d.rectangle((x, h * 0.475, x + w * 0.12, h * 0.495), fill=(245, 166, 35, 255) if i % 2 else (230, 230, 230, 255))
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    for i in range(10):
        y0 = h * 0.5 + (h * 0.5) * (i / 10) ** 1.3
        y1 = h * 0.5 + (h * 0.5) * ((i + 1) / 10) ** 1.3
        d.rectangle((0, y0, w, y1), fill=(34, 120, 60, 255) if i % 2 else (40, 136, 70, 255))
    d.line([(w * 0.5, h * 0.5), (w * 0.5, h)], fill=(235, 245, 235, 255), width=8)
    d.ellipse((w * 0.2, h * 0.62, w * 0.8, h * 0.82), outline=(235, 245, 235, 255), width=8)
    d.line([(0, h * 0.53), (w, h * 0.53)], fill=(235, 245, 235, 255), width=6)
    return far, mid, near


def _training_field(w, h, rng):
    far = _grad(w, h, (110, 170, 230), (210, 230, 245))
    d = ImageDraw.Draw(far)
    for _ in range(6):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.3)
        d.ellipse((x, y, x + w * 0.3, y + h * 0.04), fill=(255, 255, 255, 200))
    far = far.filter(ImageFilter.GaussianBlur(3))
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    for _ in range(12):
        x = rng.uniform(0, w)
        d.ellipse((x - w * 0.08, h * 0.32, x + w * 0.08, h * 0.48), fill=(50, 110, 60, 255))
    d.rectangle((0, h * 0.44, w, h * 0.47), fill=(120, 120, 120, 255))
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    d.rectangle((0, h * 0.47, w, h), fill=(70, 160, 80, 255))
    for i in range(5):
        x = w * (0.15 + i * 0.18)
        y = h * (0.7 + (i % 2) * 0.08)
        d.polygon([(x - 18, y), (x + 18, y), (x, y - 40)], fill=(255, 120, 20, 255))
    return far, mid, near


def _locker_room(w, h, rng):
    far = _grad(w, h, (40, 46, 56), (20, 24, 30))
    d = ImageDraw.Draw(far)
    for i in range(9):
        x = i * w / 8.5
        d.rectangle((x, h * 0.15, x + w / 9, h * 0.7), fill=(60, 70, 86), outline=(25, 30, 38), width=6)
        d.rectangle((x + 20, h * 0.25, x + w / 9 - 20, h * 0.27), fill=(30, 36, 44))
        if i % 3 == 1:
            d.rectangle((x + 25, h * 0.32, x + w / 9 - 25, h * 0.5), fill=(245, 166, 35))
    _glow(far, (w * 0.5, 0), w * 0.5, (255, 250, 230), 80)
    mid = _empty(w, h)
    ImageDraw.Draw(mid).rectangle((0, h * 0.72, w, h * 0.76), fill=(110, 80, 50, 255))
    near = _empty(w, h)
    ImageDraw.Draw(near).rectangle((0, h * 0.85, w, h), fill=(30, 34, 40, 255))
    return far, mid, near


# --------------------------------------------------------------------- ISEKAI

def _mountains(d, w, h, base, amp, color, rng, step=0.08):
    pts = [(0, h)]
    x = 0.0
    while x <= w + w * step:
        pts.append((x, base - rng.uniform(0.2, 1.0) * amp))
        x += w * step
    pts.append((w, h))
    d.polygon(pts, fill=color)


def _plains(w, h, rng):
    far = _grad(w, h, (40, 30, 90), (255, 190, 130), mid=(170, 110, 170))
    _glow(far, (w * 0.25, h * 0.12), w * 0.04, (255, 250, 240), 255, 3)
    _glow(far, (w * 0.4, h * 0.08), w * 0.025, (190, 230, 255), 255, 3)
    d = ImageDraw.Draw(far)
    _mountains(d, w, h, h * 0.45, h * 0.15, (120, 90, 150, 255), rng)
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    _mountains(d, w, h, h * 0.52, h * 0.09, (70, 60, 110, 255), rng, 0.12)
    cx = w * 0.7
    d.rectangle((cx - 60, h * 0.36, cx + 60, h * 0.47), fill=(40, 34, 70, 255))
    for k, (x, hh) in enumerate([(cx - 80, 0.3), (cx, 0.27), (cx + 80, 0.31)]):
        d.rectangle((x - 18, h * hh, x + 18, h * 0.47), fill=(40, 34, 70, 255))
        d.polygon([(x - 26, h * hh), (x + 26, h * hh), (x, h * (hh - 0.04))], fill=(60, 40, 90, 255))
        _glow(mid, (x, h * (hh + 0.03)), 14, (255, 220, 120), 230, 6)
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    _mountains(d, w, h, h * 0.66, h * 0.04, (40, 70, 60, 255), rng, 0.15)
    d.rectangle((0, h * 0.7, w, h), fill=(34, 60, 52, 255))
    for _ in range(160):
        x, y = rng.uniform(0, w), rng.uniform(h * 0.68, h)
        d.line([(x, y), (x + rng.uniform(-6, 6), y - rng.uniform(15, 40))], fill=(60, 110, 80, 255), width=4)
        if rng.random() < 0.15:
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=rng.choice([(255, 210, 120, 255), (180, 140, 255, 255)]))
    return far, mid, near


def _magic_forest(w, h, rng):
    far = _grad(w, h, (10, 12, 30), (20, 40, 50))
    for _ in range(10):
        _glow(far, (rng.uniform(0, w), rng.uniform(h * 0.2, h * 0.8)), w * 0.08,
              rng.choice([(120, 220, 255), (180, 140, 255)]), 70)
    mid = _empty(w, h)
    d = ImageDraw.Draw(mid)
    for _ in range(9):
        x = rng.uniform(0, w)
        d.rectangle((x, h * 0.15, x + w * 0.05, h * 0.8), fill=(20, 30, 40, 255))
        d.ellipse((x - w * 0.12, h * 0.05, x + w * 0.17, h * 0.3), fill=(24, 50, 60, 255))
    for _ in range(12):
        x, y = rng.uniform(0, w), rng.uniform(h * 0.72, h * 0.82)
        d.ellipse((x - 25, y - 15, x + 25, y + 10), fill=(120, 220, 255, 255))
        _glow(mid, (x, y), 40, (120, 220, 255), 120)
    d.rectangle((0, h * 0.8, w, h), fill=(14, 24, 30, 255))
    near = _empty(w, h)
    return far, mid, near


def _dungeon(w, h, rng):
    far = _grad(w, h, (30, 26, 34), (12, 10, 14))
    d = ImageDraw.Draw(far)
    bh, bw = h * 0.035, w * 0.12
    for r in range(int(h / bh) + 1):
        off = (r % 2) * bw / 2
        for c in range(-1, int(w / bw) + 2):
            x, y = c * bw + off, r * bh
            g = rng.randint(38, 58)
            d.rectangle((x + 3, y + 3, x + bw - 3, y + bh - 3), fill=(g, g - 4, g + 6))
    d.ellipse((w * 0.3, h * 0.25, w * 0.7, h * 0.55), fill=(6, 5, 8))
    d.rectangle((w * 0.3, h * 0.4, w * 0.7, h * 0.85), fill=(6, 5, 8))
    mid = _empty(w, h)
    for x in (w * 0.18, w * 0.82):
        _glow(mid, (x, h * 0.4), w * 0.16, (255, 150, 60), 140)
        dd = ImageDraw.Draw(mid)
        dd.rectangle((x - 10, h * 0.41, x + 10, h * 0.5), fill=(60, 40, 30, 255))
        dd.ellipse((x - 18, h * 0.37, x + 18, h * 0.42), fill=(255, 200, 90, 255))
    near = _empty(w, h)
    ImageDraw.Draw(near).rectangle((0, h * 0.85, w, h), fill=(20, 18, 24, 255))
    return far, mid, near


def _town(w, h, rng):
    far = _grad(w, h, (30, 30, 70), (200, 120, 110))
    d = ImageDraw.Draw(far)
    for i in range(8):
        x = i * w / 7 - w * 0.05
        hh = rng.uniform(0.3, 0.42) * h
        d.rectangle((x, hh, x + w * 0.15, h * 0.75), fill=(50, 40, 60))
        d.polygon([(x - 10, hh), (x + w * 0.075, hh - h * 0.06), (x + w * 0.16, hh)], fill=(70, 40, 50))
        for _ in range(3):
            wx, wy = x + rng.uniform(0.02, 0.11) * w, rng.uniform(hh + 30, h * 0.65)
            d.rectangle((wx, wy, wx + 24, wy + 32), fill=(255, 200, 110))
    mid = _empty(w, h)
    for x in (w * 0.25, w * 0.75):
        dd = ImageDraw.Draw(mid)
        dd.rectangle((x - 6, h * 0.5, x + 6, h * 0.8), fill=(30, 26, 30, 255))
        _glow(mid, (x, h * 0.5), 60, (255, 210, 120), 200)
    near = _empty(w, h)
    d = ImageDraw.Draw(near)
    d.rectangle((0, h * 0.78, w, h), fill=(60, 54, 60, 255))
    for _ in range(80):
        x, y = rng.uniform(0, w), rng.uniform(h * 0.79, h)
        d.ellipse((x - 20, y - 10, x + 20, y + 10), outline=(40, 36, 40, 255), width=3)
    return far, mid, near


BUILDERS = {
    "exterior_sanatorium": _exterior_sanatorium, "corridor": _corridor, "archive_room": _archive_room,
    "bedroom": _bedroom, "forest_night": _forest_night, "stadium_night": _stadium_night,
    "training_field": _training_field, "locker_room": _locker_room, "plains": _plains,
    "magic_forest": _magic_forest, "dungeon": _dungeon, "town": _town,
}


NEAR_KEEP = {"exterior_sanatorium", "corridor", "archive_room", "forest_night"}


@lru_cache(maxsize=24)
def layers(location: str, width: int, height: int) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Renvoie (lointain, milieu, premier plan) en RGBA, taille = image × MARGIN."""
    w, h = int(width * MARGIN), int(height * MARGIN)
    # Dessin à une résolution de référence puis mise à l'échelle (rendu identique quelle que soit la sortie).
    ref_w, ref_h = int(1080 * MARGIN), int(1920 * MARGIN)
    rng = random.Random(location)
    builder = BUILDERS.get(location, _corridor)
    far, mid, near = builder(ref_w, ref_h, rng)
    if location not in NEAR_KEEP:  # les sols passent derrière les personnages
        mid.alpha_composite(near)
        near = _empty(ref_w, ref_h)
    lib = _library_bgs.get(f"bg.{location}")
    if lib and lib.exists():
        img = Image.open(lib).convert("RGBA")
        scale = max(ref_w / img.width, ref_h / img.height)
        img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
        far = img.crop(((img.width - ref_w) // 2, (img.height - ref_h) // 2,
                        (img.width - ref_w) // 2 + ref_w, (img.height - ref_h) // 2 + ref_h))
        mid, near = _empty(ref_w, ref_h), _empty(ref_w, ref_h)
    if (w, h) != (ref_w, ref_h):
        far, mid, near = (im.resize((w, h), Image.LANCZOS) for im in (far, mid, near))
    return far.convert("RGBA"), mid, near
