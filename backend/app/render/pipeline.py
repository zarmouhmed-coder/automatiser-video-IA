"""Chaîne vidéo : storyboard (vignettes réelles), assets (voix), mixage audio et export MP4 H.264/AAC."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .. import bible, config, db
from ..core import StudioError, get_settings
from . import audio, backgrounds, characters
from .compositor import RenderContext, render_frame

ENDCARD_S = 3.0


def ep_dir(episode_id: int) -> Path:
    d = config.MEDIA_DIR / f"ep{episode_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rel(p: Path) -> str:
    return Path(p).resolve().relative_to(config.DATA_DIR).as_posix()


def sync_library() -> None:
    """Charge les sprites / décors importés (dernière version de chaque clé) dans le moteur."""
    sprites, bgs = {}, {}
    for a in db.rows("SELECT asset_key, path, kind FROM assets a WHERE version = (SELECT MAX(version) FROM assets b"
                     " WHERE b.asset_key=a.asset_key) AND source='import'"):
        p = config.DATA_DIR / a["path"]
        if a["asset_key"].startswith("char."):
            sprites[a["asset_key"]] = p
        elif a["asset_key"].startswith("bg."):
            bgs[a["asset_key"]] = p
    characters.set_library_sprites(sprites)
    backgrounds.set_library_backgrounds(bgs)


def languages() -> list[str]:
    langs = [x.strip() for x in str(get_settings().get("languages", "fr")).split(",") if x.strip() in ("fr", "en")]
    return langs or ["fr"]


def build_plan(ep: dict, script: dict, durations: dict[str, float] | None = None,
               style: dict | None = None) -> dict[str, Any]:
    cmap = bible.character_map(ep["series_id"])
    shots, scenes, t = [], [], 0.0
    durations = durations or {}
    pace = 1.0
    if style and style.get("avg_shot_s"):
        silent = [sh["duration"] for sc in script["scenes"] for sh in sc["shots"] if not (sh["text"] or sh["narration"])]
        if silent:
            pace = max(0.6, min(1.5, float(style["avg_shot_s"]) / (sum(silent) / len(silent))))
    for sc in script["scenes"]:
        start = t
        for i, sh in enumerate(sc["shots"]):
            d = float(durations.get(sh["id"], sh["duration"]))
            if pace != 1.0 and sh["id"] not in durations and not (sh["text"] or sh["narration"]):
                d = max(1.0, min(8.0, d * pace))
            shots.append({
                "scene_id": sc["id"], "shot_id": sh["id"], "start": round(t, 3), "duration": round(d, 3),
                "kind": sh["kind"], "camera": sh["camera"], "location": sc["location"], "music": sc["music"],
                "characters": sh["characters"], "speaker": sh["speaker"],
                "speaker_name": cmap.get(sh["speaker"], {}).get("name", "") if sh["speaker"] else "",
                "text": sh["text"], "narration": sh["narration"], "caption": sh["caption"], "sfx": sh["sfx"],
                "transition": "fade" if i == 0 else "cut",
            })
            t += d
        scenes.append({"scene_id": sc["id"], "start": round(start, 3), "duration": round(t - start, 3),
                       "music": sc["music"], "location": sc["location"], "summary": sc.get("summary", "")})
    end = script.get("ending", {})
    last_loc = script["scenes"][-1]["location"] if script["scenes"] else "corridor"
    shots.append({"scene_id": "end", "shot_id": "endcard", "start": round(t, 3), "duration": ENDCARD_S,
                  "kind": "endcard", "camera": "push_in", "location": last_loc, "music": "silence",
                  "characters": [], "speaker": "", "speaker_name": "", "text": "", "narration": "", "caption": "",
                  "sfx": ["chime"] if end.get("type") == "vote" else ["heartbeat"], "transition": "cut",
                  "endcard": {"type": end.get("type"), "question": end.get("vote_question", ""),
                              "options": end.get("vote_options", [])}})
    scenes.append({"scene_id": "end", "start": round(t, 3), "duration": ENDCARD_S,
                   "music": scenes[-1]["music"] if scenes else "tension", "location": last_loc, "summary": "Carton final"})
    t += ENDCARD_S
    return {"total": round(t, 3), "shots": shots, "scenes": scenes}


def make_context(ep: dict, width: int, height: int, fps: int, envelopes: dict | None = None,
                 lang: str = "fr") -> RenderContext:
    from .. import inspiration

    s = bible.get_series(ep["series_id"])
    style = inspiration.style_for(ep)
    return RenderContext(width=width, height=height, fps=fps, series_id=ep["series_id"], series_name=s["name"],
                         accent=style.get("accent") or s["accent"], episode_number=ep["number"],
                         characters=bible.character_map(ep["series_id"]), envelopes=envelopes or {},
                         lang=lang, style=style, energy=inspiration.camera_energy(style))


def storyboard_thumbnails(ep: dict, plan: dict, version: int, check: Callable[[], None]) -> None:
    sync_library()
    out_dir = ep_dir(ep["id"]) / f"storyboard_v{version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = make_context(ep, 360, 640, 24)
    for sh in plan["shots"]:
        check()
        t = 0.6 if sh["kind"] != "endcard" else 0.9
        img = render_frame(ctx, sh, t, 1, sh["start"] + t * sh["duration"])
        path = out_dir / f"{sh['shot_id']}.jpg"
        img.save(path, quality=86)
        sh["thumb"] = rel(path)


def _resolve_tts(provider: str, progress) -> tuple[str, list[str]]:
    """Choisit un fournisseur de voix réellement utilisable, avec repli explicite (jamais silencieux)."""
    import shutil as _sh

    from . import voices
    warnings: list[str] = []
    if provider == "piper":
        st = voices.status()
        if not st["library"]:
            warnings.append("Voix Piper indisponibles : paquet piper-tts non installé (relancez start.sh).")
        elif st["missing"]:
            try:
                voices.download(st["missing"], progress)
            except Exception as e:
                warnings.append(f"Téléchargement des voix Piper impossible : {e}")
        if voices.status()["ready"]:
            return "piper", warnings
        if _sh.which("espeak-ng") or _sh.which("espeak"):
            warnings.append("Repli sur espeak-ng (voix robotique).")
            return "espeak", warnings
        warnings.append("AUCUNE VOIX : configuration requise (voir Paramètres → Voix).")
        return "none", warnings
    return provider, warnings


def prepare_assets(ep: dict, script: dict, check: Callable[[], None],
                   progress: Callable[[float | None, str], None] = lambda p, m: None) -> dict[str, Any]:
    """Voix de chaque langue et ajustement des durées à la longueur réelle des voix."""
    from ..agents.translate import localize
    from .. import inspiration

    s = get_settings()
    provider, warnings = _resolve_tts(s["tts_provider"], progress)
    cmap = bible.character_map(ep["series_id"])
    style = inspiration.style_for(ep)
    langs: dict[str, Any] = {}
    for lang in languages():
        plan = build_plan(ep, localize(script, lang), style=style)
        voices_: dict[str, dict] = {}
        adjusted: dict[str, float] = {}
        lw: list[str] = []
        vdir = ep_dir(ep["id"]) / "voices" / lang
        lines = [sh for sh in plan["shots"] if sh["text"] or sh["narration"]]
        for i, sh in enumerate(lines):
            check()
            progress(None, f"Voix {lang.upper()} : réplique {i + 1}/{len(lines)}")
            text, who = (sh["text"], sh["speaker"]) if sh["text"] else (sh["narration"], "")
            ch = cmap.get(who) or {"name": "Narrateur", "voice": {"pitch": 0.95}}
            try:
                path = audio.synthesize_voice(text, ch, vdir / f"{sh['shot_id']}.wav", provider, lang)
            except Exception as e:
                msg = getattr(e, "message", None) or str(e)
                if msg not in lw:
                    lw.append(msg)
                path = None
            if path:
                dur = len(audio.read_wav(path)) / audio.SR
                voices_[sh["shot_id"]] = {"path": str(path), "rel": rel(path), "duration": round(dur, 3),
                                          "speaker": ch["name"]}
                if dur + 0.45 > sh["duration"]:
                    adjusted[sh["shot_id"]] = round(dur + 0.45, 3)
        status = (f"{len(voices_)}/{len(lines)} répliques doublées ({provider})" if voices_
                  else "aucune voix : sous-titres et sound design uniquement")
        langs[lang] = {"voices": voices_, "adjusted_durations": adjusted, "warnings": lw, "voice_status": status,
                       "lines": len(lines)}
    manifest = {"tts_provider": provider, "requested_provider": s["tts_provider"], "warnings": warnings,
                "langs": langs, "voice_status": "; ".join(f"{k.upper()} : {v['voice_status']}" for k, v in langs.items())}
    (ep_dir(ep["id"]) / "assets_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                                            encoding="utf-8")
    return manifest


def load_manifest(episode_id: int) -> dict[str, Any]:
    p = ep_dir(episode_id) / "assets_manifest.json"
    m = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    if "langs" not in m:  # format v1 (français seul)
        m = {"tts_provider": m.get("tts_provider"), "warnings": m.get("warnings", []),
             "voice_status": m.get("voice_status", ""),
             "langs": {"fr": {"voices": m.get("voices", {}), "adjusted_durations": m.get("adjusted_durations", {}),
                              "warnings": [], "voice_status": m.get("voice_status", "")}} if m else {}}
    return m


def lang_manifest(episode_id: int, lang: str) -> dict[str, Any]:
    return load_manifest(episode_id).get("langs", {}).get(lang) or {"voices": {}, "adjusted_durations": {}}


def render_video(ep: dict, script: dict, kind: str, progress: Callable[[float, str], None],
                 check: Callable[[], None], lang: str = "fr") -> dict[str, Any]:
    from ..agents.translate import localize
    from .. import inspiration

    script = localize(script, lang)
    s = get_settings()
    ffmpeg = config.ffmpeg_exe()
    if not ffmpeg:
        raise StudioError("Configuration requise : FFmpeg introuvable (installez FFmpeg ou imageio-ffmpeg).")
    sync_library()
    manifest = lang_manifest(ep["id"], lang)
    plan = build_plan(ep, script, manifest.get("adjusted_durations"), inspiration.style_for(ep))
    if kind == "preview":
        scale = float(s["preview_scale"])
        W, H = int(s["video_width"] * scale) // 2 * 2, int(s["video_height"] * scale) // 2 * 2
        fps, crf, preset = int(s["preview_fps"]), 26, "veryfast"
        limit = float(s["preview_max_seconds"]) or plan["total"]
    else:
        W, H = int(s["video_width"]) // 2 * 2, int(s["video_height"]) // 2 * 2
        fps, crf, preset = int(s["video_fps"]), int(s["video_crf"]), s["video_preset"]
        limit = plan["total"]
    total = min(plan["total"], limit)
    envelopes = {}
    for sid, v in manifest.get("voices", {}).items():
        try:
            envelopes[sid] = audio.envelope(audio.read_wav(Path(v["path"])), fps)
        except Exception:
            pass
    ctx = make_context(ep, W, H, fps, envelopes, lang)
    out_dir = ep_dir(ep["id"])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    wav = out_dir / f"{kind}-{lang}-{stamp}.wav"
    mp4 = out_dir / f"{kind}-{lang}-{stamp}.mp4"
    progress(0.0, f"Mixage audio ({lang.upper()})")
    audio.mix_episode(plan, ep["series_id"], manifest.get("voices", {}), wav)
    check()
    n_frames = int(total * fps)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
           "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", s["audio_bitrate"],
           "-movflags", "+faststart", "-t", f"{total:.3f}", str(mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t0 = time.monotonic()
    workers = _worker_count(s)
    try:
        for f, frame_bytes in _frames(ctx, plan["shots"], n_frames, fps, workers, check):
            proc.stdin.write(frame_bytes)
            if f % 6 == 0:
                el = time.monotonic() - t0
                progress(f / n_frames, f"{lang.upper()} · image {f}/{n_frames} — {el:.0f} s — {workers} processus")
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        rc = proc.wait(timeout=600)
    except BaseException:
        proc.kill()
        proc.wait()
        mp4.unlink(missing_ok=True)
        wav.unlink(missing_ok=True)
        raise
    wav.unlink(missing_ok=True)
    if rc != 0 or not mp4.exists():
        raise StudioError(f"FFmpeg a échoué : {err[-400:]}")
    progress(1.0, f"Encodé : {n_frames} images")
    return {"lang": lang, "path": rel(mp4), "width": W, "height": H, "fps": fps, "duration_s": round(n_frames / fps, 3),
            "size_bytes": mp4.stat().st_size, "plan": plan,
            "meta": {"crf": crf, "preset": preset, "voice_status": manifest.get("voice_status"),
                     "render_seconds": round(time.monotonic() - t0, 1), "workers": workers, "partial": total < plan["total"]}}


# ------------------------------------------------------------- rendu parallèle

_W: dict[str, Any] = {}
CHUNK = 6


def _worker_count(s: dict) -> int:
    import os
    n = int(s.get("render_workers", 0) or 0)
    if n <= 0:
        n = max(1, (os.cpu_count() or 2) - 1)
    return max(1, min(n, 16))


def _shot_at(shots: list, tg: float) -> dict:
    for sh in shots:
        if tg < sh["start"] + sh["duration"]:
            return sh
    return shots[-1]


def _render_one(ctx: RenderContext, shots: list, f: int, fps: int) -> bytes:
    tg = f / fps
    sh = _shot_at(shots, tg)
    return render_frame(ctx, sh, (tg - sh["start"]) / sh["duration"], f, tg).tobytes()


def _init_worker(ctx: RenderContext, shots: list, sprites: dict, bgs: dict) -> None:
    characters.set_library_sprites(sprites)
    backgrounds.set_library_backgrounds(bgs)
    _W.update(ctx=ctx, shots=shots)


def _render_chunk(start: int, end: int) -> list[bytes]:
    return [_render_one(_W["ctx"], _W["shots"], f, _W["ctx"].fps) for f in range(start, end)]


def _frames(ctx: RenderContext, shots: list, n: int, fps: int, workers: int, check: Callable[[], None]):
    """Génère (index, octets RGB) dans l'ordre ; rendu réparti sur plusieurs processus si possible."""
    if workers <= 1:
        for f in range(n):
            if f % CHUNK == 0:
                check()
            yield f, _render_one(ctx, shots, f, fps)
        return
    from collections import deque
    from concurrent.futures import ProcessPoolExecutor

    import multiprocessing

    # « spawn » partout (comportement Windows) : pas de fork d'un processus multi-thread.
    pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                               initializer=_init_worker,
                               initargs=(ctx, shots, dict(characters._library_sprites),
                                         dict(backgrounds._library_bgs)))
    pending: deque = deque()
    nxt = 0
    try:
        while nxt < n or pending:
            while nxt < n and len(pending) < workers * 2:
                pending.append((nxt, pool.submit(_render_chunk, nxt, min(n, nxt + CHUNK))))
                nxt += CHUNK
            start, fut = pending.popleft()
            check()
            for i, b in enumerate(fut.result(timeout=600)):
                yield start + i, b
    finally:
        for _, fut in pending:
            fut.cancel()
        pool.shutdown(wait=True, cancel_futures=True)


def thumbnail(ep: dict, script: dict, out: Path, lang: str = "fr") -> Path:
    """Miniature 1080×1920 : plan le plus fort (révélation/technique) + titre."""
    from PIL import ImageDraw

    from .characters import font, hex_rgb
    from ..agents.translate import localize

    script = localize(script, lang)
    plan = build_plan(ep, script, lang_manifest(ep["id"], lang).get("adjusted_durations"))
    pref = ["reveal", "technique", "action", "dialogue"]
    shot = sorted([s for s in plan["shots"] if s["kind"] != "endcard"],
                  key=lambda s: (pref.index(s["kind"]) if s["kind"] in pref else 9, -len(s["characters"])))[0]
    shot = dict(shot, text="", narration="", caption="")
    ctx = make_context(ep, 1080, 1920, 30, lang=lang)
    img = render_frame(ctx, shot, 0.7, 3, 10.0)
    d = ImageDraw.Draw(img, "RGBA")
    title = (script.get("title") or "").upper()
    f = font(120)
    words, lines, cur = title.split(), [], ""
    for w in words:
        if d.textlength((cur + " " + w).strip(), font=f) < 960:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    y = 1250
    d.rectangle((0, 1180, 1080, 1180 + 150 * len(lines) + 120), fill=(0, 0, 0, 150))
    for line in lines:
        lw = d.textlength(line, font=f)
        d.text(((1080 - lw) / 2, y), line, font=f, fill=hex_rgb(ctx.accent), stroke_width=8, stroke_fill=(0, 0, 0))
        y += 150
    sf = font(48)
    sub = f"{ctx.series_name} • {'ÉPISODE' if lang == 'fr' else 'EPISODE'} {ep['number']}"
    d.text(((1080 - d.textlength(sub, font=sf)) / 2, y + 10), sub, font=sf, fill=(240, 240, 240))
    img.convert("RGB").save(out, quality=92)
    return out
