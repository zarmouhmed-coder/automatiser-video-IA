"""Point d'entrée FastAPI : API + fichiers médias + interface web (React compilée)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, seed
from .api.routes import router
from .core import StudioError, log
from .workflow import jobs as _jobs  # noqa: F401  (enregistre les tâches)
from .workflow import engine, queue


def startup(start_worker: bool = True) -> None:
    config.load_env_file()
    config.ensure_dirs()
    applied = db.migrate()
    seeded = seed.seed()
    if applied:
        log("db.migrate", f"Migrations appliquées : {', '.join(applied)}")
    today = datetime.now().strftime("%Y%m%d")
    if not seeded and not any(today in b["name"] for b in db.list_backups()):
        db.backup("daily")
    n = queue.recover_on_startup()
    log("app.start", "Démarrage de MULTIVERSE STUDIO" + (f" — {n} tâche(s) reprise(s)" if n else ""))
    if seeded:
        engine.enqueue("library_seed", None)
    if start_worker:
        queue.worker.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup()
    yield
    queue.worker.stop()


app = FastAPI(title="MULTIVERSE STUDIO", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(StudioError)
async def studio_error(_: Request, exc: StudioError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message, "code": exc.code})


config.ensure_dirs()
for sub in ("media", "exports", "library"):
    (config.DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    app.mount(f"/files/{sub}", StaticFiles(directory=config.DATA_DIR / sub), name=f"files-{sub}")

if (config.FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    index = config.FRONTEND_DIST / "index.html"
    if path.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": "Route inconnue"})
    candidate = (config.FRONTEND_DIST / path).resolve()
    if path and candidate.is_file() and config.FRONTEND_DIST.resolve() in candidate.parents:
        return FileResponse(candidate)
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"message": "Interface non compilée : lancez start.sh / start.bat (npm run build)."})
