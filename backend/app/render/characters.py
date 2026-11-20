"""Personnages 2D procéduraux expressifs (face / trois-quarts gauche-droite).

Chaque personnage est dessiné en vectoriel à partir de sa fiche `appearance` (identifiant stable),
avec suréchantillonnage ×2 pour l'anticrénelage. Les sprites sont mis en cache par
(personnage, expression, orientation, bouche, clignement, atténuation) : le rendu reste rapide.
Si la Bibliothèque contient un sprite importé `char.<id>.<expression>` (PNG), il est utilisé à la place.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .. import config

BASE_W, BASE_H = 720, 1000  # gabarit pour une vidéo 1080×1920
SS = 2  # suréchantillonnage


def hex_rgb(h: str, default=(128, 128, 128)) -> tuple[int, int, int]:
    try:
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except Exception:
        return default


def shade(c, k: float):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def mix(a, b, t: float):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


@lru_cache(maxsize=16)
def font(size: int, bold: bool = True, serif: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSerif-Bold.ttf" if serif else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return ImageFont.truetype(str(config.FONTS_DIR / name), size)


class _Pen:
    """Dessin en coordonnées du gabarit, mis à l'échelle ×SS, avec contour automatique."""

    def __init__(self, img: Image.Image):
        self.img = img
        self.d = ImageDraw.Draw(img)

    @staticmethod
    def s(v):
        return [int(x * SS) for x in v]

    def ellipse(self, box, fill, outline=None, width=5):
        self.d.ellipse(self.s(box), fill=fill, outline=outline, width=width * SS if outline else 0)

    def poly(self, pts, fill, outline=None, width=5):
        p = [(int(x * SS), int(y * SS)) for x, y in pts]
        self.d.polygon(p, fill=fill)
        if outline:
            self.d.line(p + [p[0]], fill=outline, width=width * SS, joint="curve")

    def rrect(self, box, r, fill, outline=None, width=5):
        self.d.rounded_rectangle(self.s(box), radius=r * SS, fill=fill, outline=outline,
                                 width=width * SS if outline else 0)

    def line(self, pts, fill, width=6):
        self.d.line([(int(x * SS), int(y * SS)) for x, y in pts], fill=fill, width=width * SS, joint="curve")

    def arc(self, box, start, end, fill, width=6):
        self.d.arc(self.s(box), start, end, fill=fill, width=width * SS)

    def chord(self, box, start, end, fill):
        self.d.chord(self.s(box), start, end, fill=fill)


# ------------------------------------------------------------------ parties du corps

def _torso(p: _Pen, a: dict, out_c, out2_c, skin):
    ol = shade(out_c, 0.45)
    style = a.get("outfit_style", "shirt")
    # cou
    p.rrect((318, 500, 402, 650), 20, skin, shade(skin, 0.55), 4)
    p.poly([(318, 560), (402, 560), (402, 600), (318, 610)], shade(skin, 0.8))
    # épaules / buste
    p.poly([(110, 1000), (140, 700), (220, 630), (500, 630), (580, 700), (610, 1000)], out_c, ol, 5)
    p.poly([(470, 640), (575, 705), (605, 1000), (520, 1000)], shade(out_c, 0.82))
    if style == "jersey":
        p.poly([(300, 630), (360, 720), (420, 630)], out2_c, shade(out2_c, 0.5), 4)
        p.poly([(140, 700), (220, 630), (250, 640), (175, 760)], out2_c)
        p.poly([(580, 700), (500, 630), (470, 640), (545, 760)], out2_c)
    elif style == "hoodie":
        p.ellipse((230, 580, 490, 700), shade(out_c, 0.8), ol, 4)
        p.line([(330, 690), (325, 800)], out2_c, 6)
        p.line([(390, 690), (395, 800)], out2_c, 6)
        p.rrect((250, 850, 470, 960), 30, shade(out_c, 0.9), ol, 3)
    elif style == "coat":
        p.poly([(260, 632), (360, 780), (330, 1000), (230, 1000), (250, 700)], out2_c, ol, 3)
        p.poly([(460, 632), (360, 780), (390, 1000), (490, 1000), (470, 700)], out2_c, ol, 3)
        p.poly([(300, 630), (360, 700), (420, 630)], (235, 235, 230))
    elif style == "robe":
        p.poly([(270, 632), (360, 760), (450, 632)], shade(out_c, 0.7), ol, 3)
        p.line([(270, 632), (360, 760), (450, 632)], out2_c, 9)
        p.line([(360, 760), (360, 1000)], out2_c, 7)
        p.ellipse((340, 790, 380, 830), out2_c, ol, 2)
    elif style == "armor":
        p.ellipse((95, 640, 285, 780), out2_c, shade(out2_c, 0.45), 5)
        p.ellipse((435, 640, 625, 780), out2_c, shade(out2_c, 0.45), 5)
        p.rrect((250, 680, 470, 900), 40, shade(out_c, 1.15), ol, 4)
        p.line([(260, 790), (460, 790)], out2_c, 6)
    else:
        p.poly([(300, 630), (360, 700), (420, 630)], shade(out_c, 0.7))


def _accessory_neck(p: _Pen, a: dict, out2_c):
    if a.get("accessory") == "scarf":
        p.rrect((250, 585, 470, 660), 30, out2_c, shade(out2_c, 0.5), 4)
        p.poly([(400, 640), (450, 640), (470, 820), (420, 830)], out2_c, shade(out2_c, 0.5), 4)


def _back_hair(p: _Pen, a: dict, hair, hl):
    st = a.get("hair_style", "short")
    if st == "long":
        p.rrect((175, 220, 545, 800), 150, hair, hl, 5)
    elif st == "bob":
        p.rrect((170, 220, 550, 560), 140, hair, hl, 5)
    elif st == "ponytail":
        p.ellipse((470, 300, 610, 640), hair, hl, 5)
    elif st == "hood":
        p.ellipse((150, 150, 570, 640), hair, hl, 5)


def _front_hair(p: _Pen, a: dict, hair, hl):
    st = a.get("hair_style", "short")
    if st == "bald":
        return
    if st == "hood":
        p.chord((170, 160, 550, 520), 180, 360, hair)
        p.arc((170, 160, 550, 520), 180, 360, hl, 5)
        return
    p.chord((182, 150, 538, 470), 180, 360, hair)
    p.arc((182, 150, 538, 470), 185, 355, hl, 5)
    hi = shade(hair, 1.35)
    p.arc((230, 175, 470, 330), 210, 260, hi, 7)
    if st in ("short", "bob", "long", "ponytail"):
        p.poly([(190, 310), (230, 230), (300, 250), (270, 345)], hair)
        p.poly([(300, 250), (380, 235), (360, 340)], hair)
        p.poly([(380, 235), (480, 240), (530, 320), (450, 330)], hair)
        if st in ("bob", "long"):
            p.poly([(185, 300), (215, 300), (220, 520), (180, 480)], hair, hl, 4)
            p.poly([(535, 300), (505, 300), (500, 520), (540, 480)], hair, hl, 4)
    elif st == "spiky":
        for x0, x1, tip in [(180, 260, (150, 160)), (240, 340, (250, 70)), (320, 420, (380, 50)),
                            (400, 500, (500, 90)), (470, 545, (590, 190))]:
            p.poly([(x0, 290), tip, (x1, 250)], hair, hl, 4)
        p.poly([(220, 300), (300, 250), (290, 360)], hair)
        p.poly([(400, 250), (500, 300), (430, 350)], hair)
    elif st == "messy":
        for pts in ([(185, 320), (200, 200), (280, 250)], [(260, 230), (330, 130), (370, 240)],
                    [(350, 240), (440, 140), (450, 250)], [(430, 240), (540, 210), (535, 330)],
                    [(250, 260), (300, 360), (340, 260)], [(380, 260), (420, 350), (460, 270)]):
            p.poly(pts, hair, hl, 4)
    if a.get("accessory") == "headband":
        p.arc((185, 170, 535, 470), 200, 340, (245, 245, 245), 20)


def _ears(p: _Pen, a: dict, skin, hair):
    sl = shade(skin, 0.55)
    kind = a.get("ears", "none")
    if kind == "elf":
        p.poly([(195, 360), (95, 270), (205, 420)], skin, sl, 4)
        p.poly([(525, 360), (625, 270), (515, 420)], skin, sl, 4)
    else:
        p.ellipse((172, 350, 222, 430), skin, sl, 4)
        p.ellipse((498, 350, 548, 430), skin, sl, 4)
    if kind == "cat":
        p.poly([(200, 230), (215, 90), (300, 185)], hair, shade(hair, 0.5), 4)
        p.poly([(520, 230), (505, 90), (420, 185)], hair, shade(hair, 0.5), 4)
        p.poly([(220, 205), (225, 125), (275, 185)], (240, 170, 180))
        p.poly([(500, 205), (495, 125), (445, 185)], (240, 170, 180))
    if a.get("horns"):
        p.poly([(250, 190), (200, 60), (175, 80), (225, 215)], (60, 50, 60), (20, 20, 25), 4)
        p.poly([(470, 190), (520, 60), (545, 80), (495, 215)], (60, 50, 60), (20, 20, 25), 4)
    if a.get("accessory") == "headphones":
        p.arc((170, 140, 550, 520), 190, 350, (40, 40, 45), 22)
        p.rrect((150, 330, 215, 450), 25, (50, 50, 55), (20, 20, 20), 4)
        p.rrect((505, 330, 570, 450), 25, (50, 50, 55), (20, 20, 20), 4)


EYE_Y = 400


def _eye(p: _Pen, cx, cy, sc, iris, expr, blink, side, skin, lid):
    """side : -1 œil gauche à l'écran, +1 œil droit."""
    rx, ry = 46 * sc, 52 * sc
    if blink or expr == "happy":
        if expr == "happy":
            p.arc((cx - rx, cy - ry * 0.6, cx + rx, cy + ry * 0.9), 200, 340, lid, 8)
        else:
            p.arc((cx - rx, cy - ry, cx + rx, cy + ry * 0.4), 20, 160, lid, 8)
        return
    if expr == "surprised":
        rx, ry = rx * 1.12, ry * 1.15
    p.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), (250, 250, 250), lid, 5)
    ir = 31 * sc * (0.75 if expr in ("surprised", "scared") else 1.0)
    look = 0 if expr != "smirk" else 6 * side
    p.ellipse((cx - ir + look, cy - ir + 4, cx + ir + look, cy + ir + 4), iris, shade(iris, 0.5), 3)
    pr = ir * 0.45
    p.ellipse((cx - pr + look, cy - pr + 4, cx + pr + look, cy + pr + 4), (15, 15, 20))
    p.ellipse((cx - ir * 0.55 + look, cy - ir * 0.6, cx - ir * 0.05 + look, cy - ir * 0.1), (255, 255, 255))
    # paupières selon l'expression
    if expr == "angry":
        p.poly([(cx - rx - 6, cy - ry - 8), (cx + rx + 6, cy - ry - 8),
                (cx + rx + 6, cy - ry * (0.1 if side < 0 else 0.6)),
                (cx - rx - 6, cy - ry * (0.6 if side < 0 else 0.1))], skin)
    elif expr == "sad":
        p.poly([(cx - rx - 6, cy - ry - 8), (cx + rx + 6, cy - ry - 8),
                (cx + rx + 6, cy - ry * (0.55 if side < 0 else 0.15)),
                (cx - rx - 6, cy - ry * (0.15 if side < 0 else 0.55))], skin)
    elif expr == "determined":
        p.poly([(cx - rx - 6, cy - ry - 8), (cx + rx + 6, cy - ry - 8), (cx + rx + 6, cy - ry * 0.35),
                (cx - rx - 6, cy - ry * 0.35)], skin)
    elif expr == "smirk" and side > 0:
        p.poly([(cx - rx - 6, cy - ry - 8), (cx + rx + 6, cy - ry - 8), (cx + rx + 6, cy - ry * 0.1),
                (cx - rx - 6, cy - ry * 0.1)], skin)
    p.arc((cx - rx, cy - ry, cx + rx, cy + ry), 200, 340, lid, 7)


def _brows(p: _Pen, lx, rx_, expr, color, k_far=1.0):
    y = EYE_Y - 74
    tilt = {"angry": (18, -6), "sad": (-14, 10), "scared": (-16, 14), "surprised": (-10, -16),
            "determined": (12, -2), "happy": (0, -8), "smirk": (0, 10)}.get(expr, (0, 0))
    # (inclinaison intérieure, hauteur)
    for cx, side in ((lx, -1), (rx_, 1)):
        inner = (cx - side * 38, y + tilt[0] + tilt[1])
        outer = (cx + side * 42, y - tilt[0] * 0.2 + tilt[1])
        if expr == "smirk" and side > 0:
            inner, outer = (inner[0], inner[1] - 12), (outer[0], outer[1] - 22)
        p.line([inner, outer], color, 11)


def _mouth(p: _Pen, cx, cy, expr, mouth, skin):
    dark, lip, tongue = (70, 20, 30), shade(skin, 0.5), (200, 90, 100)
    if mouth > 0 and expr not in ("happy",):
        h = 18 if mouth == 1 else 36
        w = 30 if expr != "surprised" else 26
        p.ellipse((cx - w, cy - h * 0.4, cx + w, cy + h), dark, lip, 4)
        p.chord((cx - w * 0.7, cy + h * 0.3, cx + w * 0.7, cy + h * 1.0), 0, 180, tongue)
        if expr == "angry":
            p.rrect((cx - w * 0.8, cy - h * 0.35, cx + w * 0.8, cy - h * 0.05), 3, (245, 245, 240))
        return
    if expr == "happy":
        op = 26 if mouth else 16
        p.chord((cx - 42, cy - 22, cx + 42, cy + op + 16), 0, 180, dark)
        p.arc((cx - 42, cy - 22, cx + 42, cy + op + 16), 0, 180, lip, 4)
    elif expr == "sad":
        p.arc((cx - 30, cy, cx + 30, cy + 34), 200, 340, lip, 7)
    elif expr == "surprised":
        p.ellipse((cx - 16, cy - 8, cx + 16, cy + 30), dark, lip, 4)
    elif expr == "scared":
        p.line([(cx - 30, cy + 10), (cx - 15, cy + 2), (cx, cy + 10), (cx + 15, cy + 2), (cx + 30, cy + 10)], lip, 6)
    elif expr == "angry":
        p.line([(cx - 32, cy + 12), (cx + 32, cy + 6)], lip, 8)
    elif expr == "smirk":
        p.line([(cx - 28, cy + 12), (cx + 10, cy + 10), (cx + 34, cy - 4)], lip, 7)
    elif expr == "determined":
        p.line([(cx - 30, cy + 8), (cx + 30, cy + 8)], lip, 8)
    else:
        p.arc((cx - 28, cy - 10, cx + 28, cy + 16), 20, 160, lip, 7)


def _face(p: _Pen, a: dict, expr: str, mouth: int, blink: bool, three_quarter: bool, skin, hair, iris):
    sl = shade(skin, 0.55)
    p.ellipse((190, 190, 530, 590), skin, sl, 5)
    p.poly([(215, 450), (360, 600), (505, 450)], skin)
    p.arc((206, 300, 514, 605), 25, 155, sl, 5)
    # ombre portée de la frange
    shadow = Image.new("RGBA", p.img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).chord([int(v * SS) for v in (200, 200, 520, 380)], 180, 360,
                                 fill=shade(skin, 0.78) + (255,))
    p.img.alpha_composite(shadow)
    dx = 38 if three_quarter else 0
    lx, rx_ = 292 + dx, 428 + dx
    far = 0.82 if three_quarter else 1.0
    lid = shade(hair, 0.6) if sum(hair) > 120 else (25, 20, 20)
    _eye(p, lx, EYE_Y, far, iris, expr, blink, -1, skin, lid)
    _eye(p, rx_, EYE_Y, 1.0, iris, expr, blink, 1, skin, lid)
    if three_quarter:
        p.line([(392 + dx, 455), (410 + dx, 482), (390 + dx, 488)], sl, 5)
    else:
        p.line([(360, 450), (352, 478), (366, 482)], sl, 5)
    if expr in ("happy", "smirk"):
        blush = Image.new("RGBA", p.img.size, (0, 0, 0, 0))
        bp = _Pen(blush)
        bp.ellipse((222 + dx, 462, 292 + dx, 492), (240, 120, 130, 110))
        bp.ellipse((428 + dx, 462, 498 + dx, 492), (240, 120, 130, 110))
        p.img.alpha_composite(blush.filter(ImageFilter.GaussianBlur(4 * SS)))
    if expr == "scared":
        p.poly([(480 + dx, 280), (465 + dx, 320), (480 + dx, 335), (495 + dx, 320)], (170, 220, 255), (90, 140, 200), 3)
    _mouth(p, 360 + dx * 0.9, 530, expr, mouth, skin)
    if a.get("tusks"):
        p.poly([(318 + dx, 548), (330 + dx, 505), (342 + dx, 550)], (245, 240, 220), (120, 110, 90), 3)
        p.poly([(378 + dx, 550), (390 + dx, 505), (402 + dx, 548)], (245, 240, 220), (120, 110, 90), 3)
    if a.get("accessory") == "glasses":
        frame = (40, 40, 48)
        p.rrect((lx - 52, EYE_Y - 46, lx + 52, EYE_Y + 44), 18, None, frame, 6)
        p.rrect((rx_ - 52, EYE_Y - 46, rx_ + 52, EYE_Y + 44), 18, None, frame, 6)
        p.line([(lx + 52, EYE_Y - 10), (rx_ - 52, EYE_Y - 10)], frame, 6)
    return lx, rx_


def _entity(img: Image.Image, a: dict, mouth: int, blink: bool):
    """Silhouette du Locataire : trop grande, floue, yeux luminescents."""
    p = _Pen(img)
    body = hex_rgb(a.get("outfit", "#050608"))
    p.poly([(180, 1000), (250, 520), (300, 470), (420, 470), (470, 520), (540, 1000)], body + (235,))
    p.ellipse((255, 80, 465, 500), body + (240,))
    p.poly([(250, 560), (120, 1000), (190, 1000)], body + (200,))
    p.poly([(470, 560), (600, 1000), (530, 1000)], body + (200,))
    blurred = img.filter(ImageFilter.GaussianBlur(6 * SS))
    img.paste(blurred)
    if not blink:
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        g = _Pen(glow)
        gc = hex_rgb(a.get("glow", "#9fd3ff"))
        g.ellipse((300, 250, 340, 275), gc + (255,))
        g.ellipse((385, 250, 425, 275), gc + (255,))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * SS)))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3 * SS)))
        p.ellipse((308, 256, 332, 270), hex_rgb(a.get("eyes", "#e8f1ff")) + (255,))
        p.ellipse((393, 256, 417, 270), hex_rgb(a.get("eyes", "#e8f1ff")) + (255,))
    if mouth:
        p.ellipse((340, 360, 380, 360 + 14 * mouth), (0, 0, 0, 255))


def draw_character(appearance: dict, expression: str = "neutral", facing: str = "front", mouth: int = 0,
                   blink: bool = False) -> Image.Image:
    a = appearance or {}
    img = Image.new("RGBA", (BASE_W * SS, BASE_H * SS), (0, 0, 0, 0))
    if a.get("archetype") == "entity":
        _entity(img, a, mouth, blink)
    else:
        skin = hex_rgb(a.get("skin", "#e8c4a8"))
        hair = hex_rgb(a.get("hair", "#2a1d17"))
        iris = hex_rgb(a.get("eyes", "#5b7f6a"))
        out_c = hex_rgb(a.get("outfit", "#3a4652"))
        out2_c = hex_rgb(a.get("outfit2", "#1c232b"))
        if a.get("hair_style") == "hood":
            hair = out_c
        hl = shade(hair, 0.45)
        p = _Pen(img)
        _back_hair(p, a, hair, hl)
        _torso(p, a, out_c, out2_c, skin)
        _accessory_neck(p, a, out2_c)
        _ears(p, a, skin, hair)
        lx, rx_ = _face(p, a, expression, mouth, blink, facing != "front", skin, hair, iris)
        _front_hair(p, a, hair, hl)
        _brows(p, lx, rx_, expression, shade(hair, 0.55) if sum(hair) > 200 else shade(hair, 0.8))
        if a.get("accessory") == "headphones":
            _Pen(img).arc((170, 140, 550, 520), 190, 350, (40, 40, 45), 22)
    if facing == "left":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if a.get("outfit_style") == "jersey" and a.get("number") is not None:
        d = ImageDraw.Draw(img)
        f = font(110 * SS)
        txt = str(a["number"])
        out2 = hex_rgb(a.get("outfit2", "#1b1b1b"))
        bw = d.textlength(txt, font=f)
        d.text(((BASE_W * SS - bw) / 2, 790 * SS), txt, font=f, fill=out2,
               stroke_width=4 * SS, stroke_fill=(255, 255, 255))
    return img


_library_sprites: dict[str, Path] = {}


def set_library_sprites(mapping: dict[str, Path]) -> None:
    """mapping « char.<id>.<expression> » → fichier PNG importé dans la Bibliothèque."""
    _library_sprites.clear()
    _library_sprites.update(mapping)
    sprite.cache_clear()


@lru_cache(maxsize=512)
def sprite(char_id: str, appearance_key: str, expression: str, facing: str, mouth: int, blink: bool,
           height: int, dim: bool) -> Image.Image:
    import json

    lib = _library_sprites.get(f"char.{char_id}.{expression}") or _library_sprites.get(f"char.{char_id}.neutral")
    if lib and lib.exists():
        img = Image.open(lib).convert("RGBA")
        if facing == "left":
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
    else:
        img = draw_character(json.loads(appearance_key), expression, facing, mouth, blink)
    w = int(img.width * height / img.height)
    img = img.resize((w, height), Image.LANCZOS)
    if dim:
        rgb = ImageEnhance.Brightness(img.convert("RGB")).enhance(0.72)
        rgb.putalpha(img.getchannel("A"))
        img = rgb
    return img


def expression_sheet(appearance: dict, name: str) -> Image.Image:
    """Planche de référence (expressions × orientations) pour la Bibliothèque."""
    exprs = ["neutral", "happy", "sad", "angry", "scared", "surprised", "determined", "smirk"]
    cell_w, cell_h = 240, 333
    sheet = Image.new("RGBA", (cell_w * 4, cell_h * 2 + 60 + cell_h), (14, 18, 26, 255))
    d = ImageDraw.Draw(sheet)
    d.text((16, 14), name, font=font(30), fill=(230, 240, 255))
    for i, e in enumerate(exprs):
        img = draw_character(appearance, e, "front").resize((cell_w, cell_h), Image.LANCZOS)
        x, y = (i % 4) * cell_w, 60 + (i // 4) * cell_h
        sheet.alpha_composite(img, (x, y))
        d.text((x + 8, y + cell_h - 30), e, font=font(20, bold=False), fill=(150, 220, 255))
    for i, (f, m) in enumerate([("left", 0), ("front", 2), ("right", 0), ("front", 1)]):
        img = draw_character(appearance, "neutral", f, m).resize((cell_w, cell_h), Image.LANCZOS)
        sheet.alpha_composite(img, (i * cell_w, 60 + 2 * cell_h))
    return sheet
