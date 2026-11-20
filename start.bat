@echo off
REM MULTIVERSE STUDIO - demarrage Windows
setlocal
cd /d "%~dp0"
if "%MVS_PORT%"=="" set MVS_PORT=8765

where python >nul 2>nul || (echo Python 3.10+ requis : https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv (
  echo Creation de l'environnement Python...
  python -m venv .venv || (pause & exit /b 1)
)
call .venv\Scripts\activate.bat
if not exist .venv\.deps-ok (
  echo Installation des dependances Python...
  python -m pip install -q --upgrade pip
  pip install -q -r backend\requirements.txt || (pause & exit /b 1)
  echo ok> .venv\.deps-ok
)
if not exist frontend\dist\index.html (
  where npm >nul 2>nul || (echo Node.js 18+ requis : https://nodejs.org & pause & exit /b 1)
  echo Compilation de l'interface...
  pushd frontend
  if not exist node_modules call npm install --no-audit --no-fund
  call npm run build || (popd & pause & exit /b 1)
  popd
)
if not exist .env copy .env.example .env >nul
echo.
echo   MULTIVERSE STUDIO : http://127.0.0.1:%MVS_PORT%
echo   (fermez cette fenetre ou Ctrl+C pour arreter ; donnees dans .\data)
echo.
start "" "http://127.0.0.1:%MVS_PORT%"
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port %MVS_PORT%
