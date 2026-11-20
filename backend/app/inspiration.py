"""Inspirations de style : lien TikTok, vidéo de référence ou capture d'écran.

On n'extrait que des MESURES de style (palette, luminosité, saturation, contraste, rythme de montage,
intensité du mouvement), jamais d'images ou de sons de la référence : rien n'est copié dans nos vidéos.

- Lien TikTok : métadonnées publiques via l'API oEmbed officielle (titre, auteur, miniature) et
  palette de la miniature. TikTok n'autorise pas le téléchargement de ses vidéos : pour mesurer le
  rythme et le mouvement, importez le fichier vidéo (par ex. une vidéo que vous avez enregistrée).
- Vidéo : analyse complète avec FFmpeg (coupes, durée moyenne des plans, mouvement, couleurs).
- Image : palette et ambiance lumineuse.
"""
from __future__ import annotations

import colorsys
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from . import config, db
from .core import StudioError, log

TIKTOK_RX = re.compile(r"^https?://([a-z0-9-]+\.)?tiktok\.com/", re.I)
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _dir(iid: int) -> Path:
    d = config.INSPIRATIONS_DIR / str(iid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(v) for v in c[:3])


# ------------------------------------------------------------------ analyses

def color_stats(pixels: np.ndarray) -> dict[str, Any]:
    """pixels : (N, 3) uint8."""
    px = pixels.reshape(-1, 3).astype(np.float32) / 255
    lum = px @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    mx, mn = px.max(axis=1), px.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    img = Image.fromarray(pixels.reshape(1, -1, 3).astype(np.uint8)[:, :40000], "RGB")
    q = img.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:18]
    counts = sorted(q.getcolors(), reverse=True)
    palette = [_hex(pal[i * 3:i * 3 + 3]) for _, i in counts if i < 6]
    accent = max(palette, key=lambda h: colorsys.rgb_to_hsv(*[int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])[1]
                 * (0.4 + colorsys.rgb_to_hsv(*[int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])[2]))
    return {"palette": palette, "dominant": palette[0] if palette else "#808080", "accent": accent,
            "brightness": round(float(lum.mean()), 3), "contrast": round(float(lum.std() * 2), 3),
            "saturation": round(float(sat.mean()), 3)}


def analyze_image(path: Path) -> dict[str, Any]:
    img = Image.open(path).convert("RGB")
    img.thumbnail((200, 200))
    return color_stats(np.asarray(img))


def analyze_video(path: Path, thumb_out: Path) -> dict[str, Any]:
    ffmpeg = config.ffmpeg_exe()
    if not ffmpeg:
        raise StudioError("Configuration requise : FFmpeg introuvable.")
    fps, w, h = 6, 72, 128
    proc = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=600)
    if proc.returncode != 0 or not proc.stdout:
        raise StudioError("Vidéo illisible : " + proc.stderr.decode(errors="replace")[-200:])
    frames = np.frombuffer(proc.stdout, dtype=np.uint8).reshape(-1, h, w, 3)
    n = len(frames)
    if n < 3:
        raise StudioError("Vidéo trop courte pour être analysée.")
    duration = n / fps
    f32 = frames.astype(np.float32)
    diffs = np.abs(f32[1:] - f32[:-1]).mean(axis=(1, 2, 3))
    hists = np.stack([np.histogram(fr[..., c], bins=16, range=(0, 255))[0] for fr in frames for c in range(3)]
                     ).reshape(n, -1).astype(np.float32)
    hists /= hists.sum(axis=1, keepdims=True)
    hdiff = np.abs(hists[1:] - hists[:-1]).sum(axis=1)
    thr = max(0.35, float(np.median(hdiff) + 3 * np.std(hdiff)))
    cuts = np.where((hdiff > thr) & (diffs > np.median(diffs) * 1.8))[0]
    shots = len(cuts) + 1
    motion = float(np.median(diffs[[i for i in range(len(diffs)) if i not in set(cuts)]] if len(diffs) > len(cuts)
                             else diffs) / 255)
    sample = frames[:: max(1, n // 40)]
    stats = color_stats(sample.reshape(-1, 3))
    Image.fromarray(frames[n // 3]).resize((w * 4, h * 4), Image.LANCZOS).save(thumb_out, quality=88)
    return {**stats, "duration_s": round(duration, 1), "shots": shots, "avg_shot_s": round(duration / shots, 2),
            "cuts_per_min": round(shots / duration * 60, 1), "motion": round(min(1.0, motion * 12), 3)}


def describe(p: dict[str, Any]) -> str:
    if p.get("recipe_summary"):
        return p["recipe_summary"]
    parts = []
    if p.get("avg_shot_s"):
        pace = "très rapide" if p["avg_shot_s"] < 1.5 else "rapide" if p["avg_shot_s"] < 2.5 else \
            "posé" if p["avg_shot_s"] < 4.5 else "lent"
        parts.append(f"montage {pace} (~{p['avg_shot_s']} s par plan, {p['cuts_per_min']} coupes/min)")
    if p.get("motion") is not None:
        parts.append("beaucoup de mouvement" if p["motion"] > 0.5 else "mouvement modéré" if p["motion"] > 0.2
                     else "images plutôt fixes")
    if p.get("brightness") is not None:
        parts.append("image sombre" if p["brightness"] < 0.3 else "image lumineuse" if p["brightness"] > 0.6
                     else "luminosité moyenne")
        parts.append("couleurs saturées" if p["saturation"] > 0.45 else "couleurs douces" if p["saturation"] > 0.2
                     else "couleurs désaturées")
        parts.append("fort contraste" if p["contrast"] > 0.5 else "contraste doux")
    return ", ".join(parts)


# ------------------------------------------------------------------ création

def _save(series_id, kind, url, title, author, notes) -> int:
    if series_id:
        from . import bible
        bible.get_series(series_id)
    return db.execute("INSERT INTO inspirations(series_id, kind, url, title, author, notes, status, created_at)"
                      " VALUES(?,?,?,?,?,?,?,?)", (series_id or None, kind, url, title, author, notes, "ready", db.now()))


def _finish(iid: int, profile: dict, status: str = "ready", error: str | None = None, **paths) -> dict:
    profile["description"] = describe(profile)
    sets = ["profile=?", "status=?", "error=?"]
    params: list[Any] = [db.jdumps(profile), status, error]
    for k, v in paths.items():
        sets.append(f"{k}=?")
        params.append(v)
    db.execute(f"UPDATE inspirations SET {', '.join(sets)} WHERE id=?", (*params, iid))
    return get(iid)


def _enqueue(iid: int) -> None:
    db.execute("UPDATE inspirations SET status='analyzing', error=NULL WHERE id=?", (iid,))
    db.execute("INSERT INTO jobs(episode_id, series_id, kind, heavy, status, params, created_at) VALUES(?,?,?,?,?,?,?)",
               (None, None, "inspiration_analyze", 0, "queued", db.jdumps({"inspiration_id": iid}), db.now()))


def add_tiktok(url: str, series_id: str | None = None, notes: str = "") -> dict:
    url = url.strip()
    if not TIKTOK_RX.match(url):
        raise StudioError("Lien TikTok invalide (il doit commencer par https://www.tiktok.com/ ou https://vm.tiktok.com/).")
    iid = _save(series_id, "tiktok", url, "", "", notes)
    _enqueue(iid)
    return get(iid)


def add_file(src: Path, filename: str, series_id: str | None = None, notes: str = "", url: str = "") -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in VIDEO_EXT | IMAGE_EXT:
        raise StudioError("Format non pris en charge (vidéo mp4/mov/webm ou image png/jpg/webp).")
    kind = "video" if ext in VIDEO_EXT else "image"
    iid = _save(series_id, kind, url, Path(filename).stem[:120], "", notes)
    dest = _dir(iid) / f"reference{ext}"
    shutil.copy2(src, dest)
    db.execute("UPDATE inspirations SET file_path=? WHERE id=?", (dest.relative_to(config.DATA_DIR).as_posix(), iid))
    _enqueue(iid)
    return get(iid)


def analyze(iid: int, progress=lambda m: None) -> dict:
    """Analyse complète (tâche de fond) : mesures, transcription, recette."""
    from . import recipes

    insp = get(iid)
    if not insp:
        raise StudioError("Inspiration introuvable.")
    meta: dict[str, Any] = {}
    video: Path | None = (config.DATA_DIR / insp["file_path"]) if insp.get("file_path") else None
    profile: dict[str, Any] = {}
    if insp["kind"] == "tiktok":
        import httpx
        progress("Lecture du lien TikTok…")
        try:
            r = httpx.get("https://www.tiktok.com/oembed", params={"url": insp["url"]}, timeout=20, follow_redirects=True)
            m = r.json() if r.status_code == 200 else {}
        except Exception:
            m = {}
        meta = {"title": m.get("title", ""), "author": m.get("author_name", "")}
        if m.get("embed_product_id"):
            profile["embed_url"] = f"https://www.tiktok.com/player/v1/{m['embed_product_id']}"
        db.execute("UPDATE inspirations SET title=?, author=? WHERE id=?", (meta["title"][:300], meta["author"], iid))
        progress("Téléchargement de la vidéo (yt-dlp)…")
        try:
            dl = recipes.download(insp["url"], _dir(iid))
            video = dl["file"]
            meta.update({k: dl[k] for k in ("title", "author", "duration", "views", "caption") if dl.get(k)})
            db.execute("UPDATE inspirations SET file_path=?, title=?, author=? WHERE id=?",
                       (video.relative_to(config.DATA_DIR).as_posix(), (meta.get("title") or "")[:300],
                        meta.get("author", ""), iid))
        except recipes.DownloadError as e:
            profile["note"] = str(e)
            thumb_rel = None
            if m.get("thumbnail_url"):
                try:
                    t = httpx.get(m["thumbnail_url"], timeout=20, follow_redirects=True)
                    if t.status_code == 200:
                        p = _dir(iid) / "miniature.jpg"
                        p.write_bytes(t.content)
                        Image.open(p).convert("RGB").save(p, quality=88)
                        profile.update(analyze_image(p))
                        thumb_rel = p.relative_to(config.DATA_DIR).as_posix()
                except Exception:
                    pass
            if thumb_rel:
                return _finish(iid, profile, "partial", thumbnail_path=thumb_rel)
            return _finish(iid, profile, "error", "Vidéo non récupérable automatiquement : importez le fichier "
                           "(bouton « Enregistrer la vidéo » de TikTok) pour une analyse complète.")
    if video is None:
        raise StudioError("Aucun fichier à analyser.")
    try:
        if video.suffix.lower() in IMAGE_EXT:
            profile.update(analyze_image(video))
            return _finish(iid, profile, "partial", thumbnail_path=video.relative_to(config.DATA_DIR).as_posix())
        progress("Mesure du montage, du mouvement et des couleurs…")
        thumb = _dir(iid) / "miniature.jpg"
        profile.update(analyze_video(video, thumb))
        profile = recipes.enrich(profile, video, meta, progress)
        return _finish(iid, profile, thumbnail_path=thumb.relative_to(config.DATA_DIR).as_posix())
    except StudioError as e:
        return _finish(iid, profile, "error", e.message)


def get(iid: int | None) -> dict | None:
    if not iid:
        return None
    r = db.row("SELECT * FROM inspirations WHERE id=?", (iid,))
    if r:
        r["profile"] = db.jloads(r["profile"], {})
    return r


def list_all(series_id: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM inspirations", []
    if series_id:
        sql += " WHERE series_id=? OR series_id IS NULL"
        params.append(series_id)
    out = db.rows(sql + " ORDER BY id DESC", params)
    for r in out:
        r["profile"] = db.jloads(r["profile"], {})
    return out


def style_for(ep: dict) -> dict[str, Any]:
    insp = get(ep.get("inspiration_id"))
    if not insp or insp["status"] == "error":
        return {}
    return insp["profile"]


def applied_summary(profile: dict) -> list[str]:
    """Ce que le moteur applique concrètement (affiché dans le rapport de validation)."""
    out = []
    if profile.get("avg_shot_s"):
        out.append(f"Durée des plans sans dialogue rapprochée de {profile['avg_shot_s']} s.")
    if profile.get("motion") is not None:
        out.append(f"Intensité des mouvements de caméra ×{camera_energy(profile):.2f}.")
    if profile.get("caption_style") == "word_by_word":
        out.append(f"Sous-titres mot par mot ({profile.get('words_on_screen', 3)} mots à l'écran, mot prononcé en couleur).")
    if profile.get("zoom_punch"):
        out.append("Zooms « punch » sur les plans forts.")
    if profile.get("voice_speed") and abs(profile["voice_speed"] - 1) > 0.02:
        out.append(f"Débit des voix ×{profile['voice_speed']:.2f}.")
    if profile.get("music_db"):
        out.append(f"Musique à {profile['music_db']:.0f} dB sous les voix.")
    if profile.get("hook_pattern"):
        out.append(f"Accroche demandée aux scénaristes : {profile['hook_pattern']}.")
    if profile.get("palette"):
        out.append(f"Étalonnage vers la palette {', '.join(profile['palette'][:4])} ; couleur d'accent {profile['accent']}.")
    return out


def camera_energy(profile: dict) -> float:
    m = profile.get("motion")
    return 1.0 if m is None else float(np.clip(0.7 + m * 1.2, 0.6, 1.8))
