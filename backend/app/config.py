"""Configuration centrale : chemins, variables d'environnement, réglages persistants.

Les secrets (clés API) sont lus depuis le fichier `.env` à la racine du projet
(ignoré par Git) ou depuis les variables d'environnement. Ils ne sont jamais
écrits dans la base de données ni renvoyés en clair à l'interface.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("MVS_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = DATA_DIR / "studio.db"
MEDIA_DIR = DATA_DIR / "media"
LIBRARY_DIR = DATA_DIR / "library"
EXPORTS_DIR = DATA_DIR / "exports"
BACKUPS_DIR = DATA_DIR / "backups"
BIBLES_DIR = DATA_DIR / "bibles"
MODELS_DIR = Path(os.environ.get("MVS_MODELS_DIR", DATA_DIR / "models")).resolve()
INSPIRATIONS_DIR = DATA_DIR / "inspirations"
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
FRONTEND_DIST = ROOT / "frontend" / "dist"
ENV_FILE = ROOT / ".env"

SECRET_KEYS = ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")

# Réglages par défaut (modifiables dans la page Paramètres, stockés en base)
DEFAULT_SETTINGS: dict[str, object] = {
    "llm_provider": "demo",            # demo | anthropic | ollama
    "anthropic_model": "claude-opus-5-5",
    "anthropic_effort": "medium",      # low | medium | high | xhigh | max
    "anthropic_fallbacks": True,       # repli serveur en cas de refus de sécurité
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3.1",
    "tts_provider": "piper",           # piper | espeak | elevenlabs | none
    "languages": "fr,en",              # versions produites pour chaque épisode
    "validation_mode": "episode",      # episode (1 validation expliquée) | detailed (4 validations)
    "caption_style": "tiktok",         # tiktok (mot par mot) | classic
    "translation_provider": "auto",    # auto | llm | argos
    "elevenlabs_model": "eleven_multilingual_v2",
    "budget_monthly_usd": 20.0,
    "budget_episode_usd": 2.0,
    "max_llm_calls_per_episode": 30,
    "llm_timeout_s": 300,
    "render_timeout_s": 3600,
    "max_parallel_workflows": 3,
    "render_workers": 0,               # 0 = automatique (cœurs - 1)
    "video_width": 1080,
    "video_height": 1920,
    "video_fps": 30,
    "video_crf": 20,
    "video_preset": "medium",
    "audio_bitrate": "192k",
    "preview_scale": 0.5,
    "preview_fps": 24,
    "preview_max_seconds": 0,          # 0 = épisode complet en basse définition
    "backups_keep": 10,
    "queue_paused": False,
}


def load_env_file() -> None:
    """Charge `.env` (format KEY=VALUE) sans écraser l'environnement existant."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def save_secret(key: str, value: str) -> None:
    """Écrit/actualise une clé dans `.env` (fichier local ignoré par Git)."""
    if key not in SECRET_KEYS:
        raise ValueError(f"Clé non autorisée : {key}")
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines if not l.strip().startswith(f"{key}=")]
    if value:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass
    if value:
        os.environ[key] = value
    else:
        os.environ.pop(key, None)


def secret_status() -> dict[str, bool]:
    return {k: bool(os.environ.get(k)) for k in SECRET_KEYS}


def ffmpeg_exe() -> str | None:
    """FFmpeg du système, sinon le binaire fourni par imageio-ffmpeg."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ensure_dirs() -> None:
    for d in (DATA_DIR, MEDIA_DIR, LIBRARY_DIR, EXPORTS_DIR, BACKUPS_DIR, BIBLES_DIR, MODELS_DIR, INSPIRATIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)
