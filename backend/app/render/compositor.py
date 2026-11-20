"""Compositeur 2.5D : caméra virtuelle, parallaxe, personnages animés, effets et sous-titres."""
from __future__ import annotations

import json
import math
import random
import zlib
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import backgrounds
from .characters import font, hex_rgb, sprite

TEXTS = {
    "fr": {"vote_sub": "Votez dans le sondage ou en commentaire", "tbc": "À SUIVRE", "follow": "Abonnez-vous pour la suite",
           "fiction": "Fiction • images et sons de synthèse", "choose": "À vous de choisir", "ep": "ÉP.",
           "system": "◆ SYSTÈME"},
    "en": {"vote_sub": "Vote in the poll or in the comments", "tbc": "TO BE CONTINUED", "follow": "Follow for the next part",
           "fiction": "Fiction • synthetic images and sounds", "choose": "Your call", "ep": "EP.", "system": "◆ SYSTEM"},
}


def L(ctx, key: str) -> str:
    return TEXTS.get(ctx.lang, TEXTS["fr"])[key]


DEPTH = {"far": 0.35, "mid": 0.7, "chars": 0.85, "near": 1.15}


@dataclass
class RenderContext:
    width: int
    height: int
    fps: int
    series_id: str
    series_name: str
    accent: str
    episode_number: int
    characters: dict  # id -> fiche
    envelopes: dict = field(default_factory=dict)  # shot_id -> enveloppe voix (par image)
    shot_durations: dict = field(default_factory=dict)
    lang: str = "fr"
    style: dict = field(default_factory=dict)  # profil d'inspiration (palette, contraste, mouvement…)
    energy: float = 1.0
    voice_durs: dict = field(default_factory=dict)  # shot_id -> durée réelle de la voix
    caption_style: str = "word_by_word"           # word_by_word (TikTok) | phrase

    @property
    def k(self) -> float:
        return self.height / 1920


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def camera(shot: dict, t: float, frame: int, energy: float = 1.0) -> tuple[float, float, float]:
    """Renvoie (zoom, décalage x, décalage y) en fraction de l'image."""
    cam, e = shot.get("camera", "static"), ease(min(1.0, max(0.0, t)))
    z, x, y = 1.0 + 0.02 * e, 0.0, 0.0
    if cam == "push_in":
        z = 1.0 + 0.14 * energy * e
    elif cam == "pull_out":
        z = 1 + 0.14 * energy * (1 - e)
    elif cam == "pan_left":
        z, x = 1.06, (0.06 - 0.12 * e) * energy
    elif cam == "pan_right":
        z, x = 1.06, (-0.06 + 0.12 * e) * energy
    elif cam == "tilt_up":
        z, y = 1.06, (-0.05 + 0.1 * e) * energy
    elif cam == "shake":
        rng = random.Random(frame)
        amp = 0.012 * energy * (1 - 0.6 * t)
        z, x, y = 1.07, rng.uniform(-amp, amp), rng.uniform(-amp, amp)
    return z, x, y


def _place(layer: Image.Image, W: int, H: int, zoom: float, ox: float, oy: float, depth: float) -> Image.Image:
    """Projette une couche (plus grande que l'image) avec zoom/translation pondérés par la profondeur."""
    z = 1 + (zoom - 1) * depth
    lw, lh = layer.size
    a = 1 / z
    c = lw / 2 - (W / 2) * a - ox * depth * W
    f = lh / 2 - (H / 2) * a - oy * depth * H
    return layer.transform((W, H), Image.AFFINE, (a, 0, c, 0, a, f), resample=Image.BILINEAR)


# ------------------------------------------------------------------ effets (caches)

@lru_cache(maxsize=8)
def _vignette(W: int, H: int, strength: float) -> np.ndarray:
    y, x = np.ogrid[-1:1:H * 1j, -1:1:W * 1j]
    r = np.sqrt(x * x * 0.9 + y * y * 0.6)
    return (1 - strength * np.clip(r - 0.35, 0, 1) ** 1.4)[..., None].astype(np.float32)


@lru_cache(maxsize=4)
def _grain(W: int, H: int) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(3)
    return tuple(rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32).repeat(2, 0).repeat(2, 1)[:H, :W, None]
                 for _ in range(4))


@lru_cache(maxsize=4)
def _speed_lines(W: int, H: int, color: tuple) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = random.Random(9)
    cx, cy = W / 2, H * 0.45
    for _ in range(90):
        ang = rng.uniform(0, 2 * math.pi)
        r0 = rng.uniform(0.32, 0.5) * H
        r1 = r0 + rng.uniform(0.2, 0.5) * H
        d.line([(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0), (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)],
               fill=color + (rng.randint(90, 200),), width=rng.randint(2, 7))
    return img


def _particles(W: int, H: int, t_global: float, color: tuple) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = random.Random(42)
    for _ in range(40):
        x0, y0, sp, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.02, 0.06), rng.uniform(2, 6) * H / 1920
        y = (y0 - t_global * sp * H) % H
        x = x0 + math.sin(t_global * 0.8 + y0) * 12
        a = int(120 + 100 * math.sin(t_global * 2 + x0))
        d.ellipse((x - r, y - r, x + r, y + r), fill=color + (max(0, min(255, a)),))
    return img.filter(ImageFilter.GaussianBlur(1.5))


def _grade(arr: np.ndarray, st: dict) -> np.ndarray:
    """Étalonnage doux vers le style de l'inspiration (saturation, contraste, luminosité, teinte)."""
    gray = arr.mean(axis=2, keepdims=True)
    sat = float(np.clip(0.75 + st.get("saturation", 0.35) * 0.9, 0.7, 1.35))
    arr = gray + (arr - gray) * sat
    con = float(np.clip(0.85 + st.get("contrast", 0.4) * 0.45, 0.85, 1.25))
    arr = (arr - 128) * con + 128
    bri = float(np.clip(0.85 + st.get("brightness", 0.45) * 0.4, 0.85, 1.15))
    arr = arr * bri
    tint = np.array(hex_rgb(st.get("dominant", "#808080")), dtype=np.float32)
    t = tint / max(float(tint.mean()), 1.0)  # teinte normalisée (moyenne 1) : pas d'assombrissement global
    return arr * (0.85 + 0.15 * t)


def post(frame: Image.Image, ctx: RenderContext, shot: dict, t: float, n: int, t_global: float) -> Image.Image:
    W, H = frame.size
    arr = np.asarray(frame.convert("RGB")).astype(np.float32)
    sid = ctx.series_id
    if sid == "horror":
        gray = arr.mean(axis=2, keepdims=True)
        arr = arr * 0.55 + gray * 0.45
        arr *= np.array([0.9, 0.98, 1.08], dtype=np.float32)
        flick = 1 - 0.06 * (random.Random(n).random() > 0.93)
        arr *= flick
        arr += _grain(W, H)[n % 4] * 9
        arr *= _vignette(W, H, 0.95)
        if shot["kind"] == "reveal" and t < 0.5:
            shift = int(8 * ctx.k * (1 - t * 2)) + 1
            arr[..., 0] = np.roll(arr[..., 0], shift, axis=1)
            arr[..., 2] = np.roll(arr[..., 2], -shift, axis=1)
    elif sid == "football":
        arr = (arr - 128) * 1.08 + 128
        arr *= _vignette(W, H, 0.5)
    else:
        arr *= _vignette(W, H, 0.45)
    if ctx.style.get("palette"):
        arr = _grade(arr, ctx.style)
    # flash d'impact au début des plans d'action / révélation
    if shot["kind"] in ("technique", "reveal") or "impact" in shot.get("sfx", []):
        if t * shot["duration"] < 0.12:
            arr = arr * 0.4 + 255 * 0.6
    # fondu d'ouverture de scène
    if shot.get("transition") == "fade" and t * shot["duration"] < 0.3:
        arr *= (t * shot["duration"]) / 0.3
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# ------------------------------------------------------------------ texte

def _wrap(text: str, f, max_w: float, d: ImageDraw.ImageDraw) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if d.textlength(cand, font=f) <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def word_times(text: str, dur: float) -> list[tuple[str, float]]:
    """Heure de début estimée de chaque mot (poids = longueur + pauses de ponctuation)."""
    words = text.split()
    weights = [len(w.strip(".,!?…;:«»\"'")) + 2 + (4 if w[-1:] in ".!?…" else 2 if w[-1:] in ",;:" else 0)
               for w in words]
    total = max(1, sum(weights))
    out, acc = [], 0.0
    for w, wt in zip(words, weights):
        out.append((w, dur * acc / total))
        acc += wt
    return out


def draw_words(img: Image.Image, ctx: RenderContext, speaker: str, text: str, lt: float, dur: float,
               narration: bool = False) -> None:
    """Sous-titres mot par mot façon TikTok : petit groupe de mots, mot prononcé en couleur + « pop »."""
    W, H, k = img.width, img.height, ctx.k
    times = word_times(text, dur)
    if not times:
        return
    n = max(1, int(ctx.style.get("words_on_screen", 3) or 3))
    cur = max(0, sum(1 for _, t0 in times if t0 <= lt) - 1) if lt >= 0 else 0
    g = cur // n
    group = times[g * n:(g + 1) * n]
    accent = hex_rgb(ctx.accent)
    d = ImageDraw.Draw(img, "RGBA")
    base = int(86 * k)
    f = font(base)
    words = [w.upper() for w, _ in group]
    space = d.textlength(" ", font=f)
    widths = [d.textlength(w, font=f) for w in words]
    lines, line, lw = [], [], 0.0
    for i, w in enumerate(widths):
        if line and lw + space + w > W * 0.84:
            lines.append(line)
            line, lw = [], 0.0
        line.append(i)
        lw += (space if len(line) > 1 else 0) + w
    lines.append(line)
    y = H * (0.765 if ctx.style.get("caption_position", "center") != "bottom" else 0.8)
    if speaker:
        nf = font(int(32 * k))
        tw = d.textlength(speaker, font=nf)
        d.rounded_rectangle(((W - tw) / 2 - 18 * k, y - 52 * k, (W + tw) / 2 + 18 * k, y - 8 * k), radius=int(14 * k),
                            fill=accent + (235,))
        d.text(((W - tw) / 2, y - 47 * k), speaker, font=nf, fill=(8, 10, 14))
    for ln in lines:
        total_w = sum(widths[i] for i in ln) + space * (len(ln) - 1)
        x = (W - total_w) / 2
        for i in ln:
            idx = g * n + i
            active = idx == cur and lt >= 0
            since = lt - times[idx][1]
            col = accent if active else ((235, 225, 200) if narration else (255, 255, 255))
            if active and 0 <= since < 0.12:  # pop à l'apparition du mot
                pf = font(int(base * (1.12 - since)))
                dy = (pf.size - base) * 0.5
                d.text((x - (d.textlength(words[i], font=pf) - widths[i]) / 2, y - dy), words[i], font=pf, fill=col,
                       stroke_width=max(2, int(7 * k)), stroke_fill=(0, 0, 0))
            else:
                d.text((x, y), words[i], font=f, fill=col, stroke_width=max(2, int(7 * k)), stroke_fill=(0, 0, 0))
            x += widths[i] + space
        y += base * 1.12


def draw_subtitle(img: Image.Image, ctx: RenderContext, speaker: str, text: str, progress: float,
                  narration: bool = False) -> None:
    """Sous-titres mobiles : boîte arrondie, nom du personnage, mots déjà prononcés en surbrillance."""
    W, H, k = img.width, img.height, ctx.k
    d = ImageDraw.Draw(img, "RGBA")
    f = font(int(54 * k), serif=narration)
    max_w = W * 0.82
    lines = _wrap(text, f, max_w, d)[:3]
    lh = int(70 * k)
    box_h = lh * len(lines) + int(46 * k)
    y0 = int(H * 0.765)
    x0 = int(W * 0.06)
    d.rounded_rectangle((x0, y0, W - x0, y0 + box_h), radius=int(28 * k), fill=(6, 10, 16, 190))
    accent = hex_rgb(ctx.accent)
    if speaker:
        nf = font(int(34 * k))
        tw = d.textlength(speaker, font=nf)
        d.rounded_rectangle((x0 + 24 * k, y0 - 30 * k, x0 + 24 * k + tw + 36 * k, y0 + 22 * k), radius=int(16 * k),
                            fill=accent + (255,))
        d.text((x0 + 42 * k, y0 - 25 * k), speaker, font=nf, fill=(8, 10, 14))
    total_words = max(1, len(text.split()))
    spoken = int(progress * total_words * 1.15) + 1
    count = 0
    for i, line in enumerate(lines):
        y = y0 + int(26 * k) + i * lh
        lw = d.textlength(line, font=f)
        x = (W - lw) / 2
        for w in line.split():
            count += 1
            col = (255, 255, 255) if count <= spoken else (150, 160, 175)
            if narration:
                col = (225, 215, 190) if count <= spoken else (140, 135, 120)
            d.text((x, y), w, font=f, fill=col, stroke_width=max(1, int(3 * k)), stroke_fill=(0, 0, 0))
            x += d.textlength(w + " ", font=f)


def draw_caption(img: Image.Image, ctx: RenderContext, shot: dict, t: float) -> None:
    cap = shot.get("caption", "")
    if not cap:
        return
    W, H, k = img.width, img.height, ctx.k
    accent = hex_rgb(ctx.accent)
    kind = shot["kind"]
    appear = min(1.0, t * shot["duration"] / 0.25)
    if kind == "system" or cap.startswith("["):
        import re as _re
        cap = _re.sub(r"^\[(SYSTÈME|SYSTEME|SYSTEM)\]\s*", "", cap)
        d = ImageDraw.Draw(img, "RGBA")
        f = font(int(44 * k))
        lines = _wrap(cap, f, W * 0.72, d)[:4]
        bh = int(70 * k + 58 * k * len(lines))
        y0 = int(H * 0.16 + (1 - appear) * 40 * k)
        x0 = int(W * 0.08)
        d.rounded_rectangle((x0, y0, W - x0, y0 + bh), radius=int(14 * k), fill=(10, 30, 70, int(215 * appear)),
                            outline=(127, 224, 255, int(255 * appear)), width=max(2, int(4 * k)))
        d.text((x0 + 26 * k, y0 + 14 * k), L(ctx, "system"), font=font(int(30 * k)), fill=(127, 224, 255, int(255 * appear)))
        for i, line in enumerate(lines):
            d.text((x0 + 26 * k, y0 + 58 * k + i * 58 * k), line, font=f, fill=(235, 248, 255, int(255 * appear)))
        return
    big = kind in ("title", "technique", "reveal")
    size = int((92 if big else 54) * k)
    f = font(size)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = _wrap(cap, f, W * 0.86, d)[:3]
    y = H * (0.2 if kind != "reveal" else 0.12)
    fill = accent if kind in ("technique", "title") else ((255, 80, 100) if kind == "reveal" else (240, 240, 240))
    for line in lines:
        lw = d.textlength(line, font=f)
        d.text(((W - lw) / 2, y), line, font=f, fill=fill + (int(255 * appear),),
               stroke_width=max(2, int(8 * k)), stroke_fill=(0, 0, 0, int(230 * appear)))
        y += size * 1.15
    if kind == "technique":
        glow = layer.filter(ImageFilter.GaussianBlur(14 * k))
        img.paste(glow, (0, 0), glow)
        layer = layer.rotate(-5, resample=Image.BICUBIC, center=(W / 2, H * 0.24))
    if big and t < 0.3:
        s = 1 + (0.3 - t) * 0.6
        layer = layer.resize((int(W * s), int(H * s)), Image.BILINEAR).crop(
            (int((W * s - W) / 2), int((H * 0.22) * (s - 1)), int((W * s - W) / 2) + W, int((H * 0.22) * (s - 1)) + H))
    img.paste(layer, (0, 0), layer)


def draw_hud(img: Image.Image, ctx: RenderContext, t_global: float) -> None:
    if t_global > 4.0:
        return
    k = ctx.k
    d = ImageDraw.Draw(img, "RGBA")
    a = int(255 * min(1.0, (4.0 - t_global) / 0.8))
    f = font(int(30 * k))
    label = f"{ctx.series_name}  •  {L(ctx, 'ep')} {ctx.episode_number}"
    d.text((40 * k, 60 * k), label, font=f, fill=hex_rgb(ctx.accent) + (a,), stroke_width=max(1, int(3 * k)),
           stroke_fill=(0, 0, 0, a))


def draw_endcard(img: Image.Image, ctx: RenderContext, shot: dict, t: float) -> None:
    W, H, k = img.width, img.height, ctx.k
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle((0, 0, W, H), fill=(0, 0, 0, int(170 * min(1, t * 3))))
    accent = hex_rgb(ctx.accent)
    end = shot.get("endcard", {})
    y = H * 0.3
    if end.get("type") == "vote":
        f = font(int(64 * k))
        for line in _wrap(end.get("question") or L(ctx, "choose"), f, W * 0.84, d):
            lw = d.textlength(line, font=f)
            d.text(((W - lw) / 2, y), line, font=f, fill=(255, 255, 255), stroke_width=int(4 * k), stroke_fill=(0, 0, 0))
            y += 80 * k
        y += 40 * k
        of = font(int(52 * k))
        for i, opt in enumerate(end.get("options", [])):
            label = f"{chr(65 + i)}  {opt}"
            d.rounded_rectangle((W * 0.12, y, W * 0.88, y + 100 * k), radius=int(26 * k), fill=(10, 16, 24, 230),
                                outline=accent + (255,), width=max(2, int(5 * k)))
            d.text((W * 0.12 + 40 * k, y + 20 * k), label, font=of, fill=(255, 255, 255))
            y += 130 * k
        sub = L(ctx, "vote_sub")
    else:
        f = font(int(110 * k))
        txt = L(ctx, "tbc")
        lw = d.textlength(txt, font=f)
        d.text(((W - lw) / 2, H * 0.4), txt, font=f, fill=accent, stroke_width=int(6 * k), stroke_fill=(0, 0, 0))
        y = H * 0.55
        sub = L(ctx, "follow")
    sf = font(int(36 * k), bold=False)
    lw = d.textlength(sub, font=sf)
    d.text(((W - lw) / 2, y + 30 * k), sub, font=sf, fill=(220, 230, 240))
    tag = L(ctx, "fiction")
    lw = d.textlength(tag, font=font(int(26 * k), bold=False))
    d.text(((W - lw) / 2, H * 0.92), tag, font=font(int(26 * k), bold=False), fill=(150, 160, 170))


# ------------------------------------------------------------------ image complète

POS_X = {"left": 0.27, "center": 0.5, "right": 0.73}


def render_frame(ctx: RenderContext, shot: dict, t: float, frame_no: int, t_global: float) -> Image.Image:
    """t : avancement dans le plan (0→1)."""
    W, H = ctx.width, ctx.height
    zoom, ox, oy = camera(shot, t, frame_no, ctx.energy)
    if ctx.style.get("zoom_punch") and shot["kind"] in ("action", "technique", "reveal", "title", "system"):
        lt0 = t * shot["duration"]
        if lt0 < 0.3:
            zoom *= 1 + 0.1 * (1 - lt0 / 0.3) ** 2
    far, mid, near = backgrounds.layers(shot["location"], W, H)
    frame = _place(far, W, H, zoom, ox, oy, DEPTH["far"])
    frame.alpha_composite(_place(mid, W, H, zoom, ox, oy, DEPTH["mid"]))
    local_time = t * shot["duration"]
    chars = shot.get("characters", [])
    if chars:
        plate = Image.new("RGBA", (int(W * backgrounds.MARGIN), int(H * backgrounds.MARGIN)), (0, 0, 0, 0))
        pw, ph = plate.size
        sprite_h = int(H * (0.72 if len(chars) == 1 else 0.66))
        env = ctx.envelopes.get(shot["shot_id"])
        for i, c in enumerate(chars):
            info = ctx.characters.get(c["id"])
            if not info:
                continue
            app = info.get("appearance", {})
            speaking = shot.get("speaker") == c["id"] and bool(shot.get("text"))
            mouth = 0
            if speaking:
                if env is not None and len(env):
                    idx = int((local_time - 0.15) * ctx.fps)
                    v = env[idx] if 0 <= idx < len(env) else 0
                    mouth = 0 if v < 0.12 else (1 if v < 0.45 else 2)
                else:
                    talk_end = min(shot["duration"] - 0.2, 0.15 + len(shot["text"]) / 14)
                    if 0.15 < local_time < talk_end:
                        ch = shot["text"][int((local_time - 0.15) * 14) % len(shot["text"])].lower()
                        mouth = 2 if ch in "aeiouyéèàâêô" else (0 if ch in " ,.!?…" else 1)
            phase = (zlib.crc32(c["id"].encode()) % 100) / 10
            blink = ((t_global + phase) % 3.7) < 0.12
            dim = bool(shot.get("speaker")) and not speaking and len(chars) > 1
            h = int(sprite_h * float(app.get("height", 1.0)))
            spr = sprite(c["id"], json.dumps(app, sort_keys=True), c["expression"], c["facing"], mouth, blink, h, dim)
            bob = math.sin((t_global + phase) * 2 * math.pi / 3.4) * H * 0.004
            if speaking:
                bob += math.sin(local_time * 9) * H * 0.002
            px = POS_X.get(c["position"], 0.5)
            if len(chars) == 1:
                px = 0.5 + (px - 0.5) * 0.4  # personnage seul : rester dans le cadre mobile
            cx = (pw - W) / 2 + W * px
            if len(chars) == 2 and all(x["position"] == "center" for x in chars):
                cx = (pw - W) / 2 + W * (0.3 if i == 0 else 0.7)
            x = int(cx - spr.width / 2)
            y = int((ph - H) / 2 + H * 1.01 - spr.height + bob)
            if app.get("archetype") == "entity":
                spr = spr.copy()
                spr.putalpha(spr.getchannel("A").point(lambda v: int(v * (0.55 + 0.35 * random.Random(frame_no).random()))))
                x += int(random.Random(frame_no * 7).uniform(-6, 6) * ctx.k)
            plate.paste(spr, (x, y), spr)
        frame.alpha_composite(_place(plate, W, H, zoom, ox, oy, DEPTH["chars"]))
    frame.alpha_composite(_place(near, W, H, zoom, ox, oy, DEPTH["near"]))
    if ctx.series_id == "football" and shot["kind"] in ("technique", "action"):
        frame.alpha_composite(_speed_lines(W, H, (255, 255, 255)))
    if ctx.series_id == "isekai":
        frame.alpha_composite(_particles(W, H, t_global, (255, 220, 150) if shot["location"] != "magic_forest"
                                         else (130, 230, 255)))
    if ctx.series_id == "horror" and shot["location"] in ("forest_night", "exterior_sanatorium", "corridor"):
        frame.alpha_composite(_particles(W, H, t_global * 0.3, (200, 210, 220)))
    out = post(frame, ctx, shot, t, frame_no, t_global)  # RGB : les dessins RGBA se mélangent
    if shot["kind"] == "endcard":
        draw_endcard(out, ctx, shot, t)
    else:
        draw_caption(out, ctx, shot, t)
        txt = shot.get("text") or shot.get("narration")
        if txt:
            speak_dur = ctx.voice_durs.get(shot["shot_id"]) or max(0.8, min(shot["duration"] - 0.3, len(txt) / 14))
            name = shot.get("speaker_name", "") if shot.get("text") else ""
            if ctx.caption_style == "word_by_word":
                draw_words(out, ctx, name, txt, local_time - 0.15, speak_dur, narration=not shot.get("text"))
            else:
                prog = max(0.0, min(1.0, (local_time - 0.15) / speak_dur))
                draw_subtitle(out, ctx, name, txt, prog, narration=not shot.get("text"))
        draw_hud(out, ctx, t_global)
    return out
