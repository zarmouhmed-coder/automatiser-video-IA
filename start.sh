#!/usr/bin/env bash
# MULTIVERSE STUDIO — démarrage Linux / macOS
set -euo pipefail
cd "$(dirname "$0")"
PORT="${MVS_PORT:-8765}"
PY="${PYTHON:-python3}"

command -v "$PY" >/dev/null || { echo "Python 3.10+ requis."; exit 1; }
if [ ! -d .venv ]; then
  echo "▸ Création de l'environnement Python (.venv)…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if [ ! -f .venv/.deps-ok ] || [ backend/requirements.txt -nt .venv/.deps-ok ]; then
  echo "▸ Installation des dépendances Python…"
  pip install -q --upgrade pip
  pip install -q -r backend/requirements.txt
  touch .venv/.deps-ok
fi
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src -newer frontend/dist/index.html -print -quit 2>/dev/null)" ]; then
  command -v npm >/dev/null || { echo "Node.js 18+ requis pour compiler l'interface."; exit 1; }
  echo "▸ Compilation de l'interface…"
  (cd frontend && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build)
fi
[ -f .env ] || cp .env.example .env
URL="http://127.0.0.1:${PORT}"
echo ""
echo "  MULTIVERSE STUDIO → ${URL}"
echo "  (Ctrl+C pour arrêter ; tout est enregistré dans ./data)"
echo ""
( sleep 2; command -v xdg-open >/dev/null && xdg-open "$URL" >/dev/null 2>&1 || command -v open >/dev/null && open "$URL" ) &
cd backend
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
