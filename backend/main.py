"""Cascade Digital Twin — FastAPI application.

Startup: load config + exported artifacts, init the store, optionally autoplay.
The backend NEVER trains (Architecture §7); artifacts come from
tools/export_artifacts.py, run offline.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.rest import router as rest_router
from backend.api.state import state
from backend.api.ws import router as ws_router
from backend.config.loader import ConfigError

logging.basicConfig(
    level=os.environ.get("CASCADE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("cascade")


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.boot()
    if state.settings.line["tick"].get("autoplay_on_start"):
        await state.engine.play()
    yield
    await state.engine.pause()


app = FastAPI(
    title="Cascade Digital Twin",
    version="1.0.0",
    description=("3-layer live digital twin for a 35-station vehicle assembly line. "
                 "Bottleneck forecasting (BSTAN) + defect detection (fine-tuned YOLOv8) + "
                 "defect-chain prediction, joined into one twin-state."),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CASCADE_CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Where the built dashboard lives when this process also serves it (single-container
# deployments: Hugging Face Spaces, `docker run` of the all-in-one image). Empty in the
# two-container compose setup, where nginx serves the SPA instead.
FRONTEND_DIST = Path(os.environ.get("CASCADE_FRONTEND_DIST", "")).resolve() \
    if os.environ.get("CASCADE_FRONTEND_DIST") else None
SERVING_FRONTEND = bool(FRONTEND_DIST and (FRONTEND_DIST / "index.html").exists())

# The REST surface is served under /api so the dashboard can share one origin with the
# SPA: the frontend's own routes (/pnl, /history, /config) share names with API paths,
# so a reload would otherwise return JSON instead of the app.
app.include_router(rest_router, prefix="/api")
app.include_router(ws_router, prefix="/api")

# Also at the root, exactly as Backend Instructions §9 names it — but ONLY when this
# process is not serving the SPA. Registering both would shadow the SPA's own routes.
if not SERVING_FRONTEND:
    app.include_router(rest_router)
    app.include_router(ws_router)


@app.exception_handler(ConfigError)
async def config_error_handler(request, exc: ConfigError):
    return JSONResponse(status_code=500, content={"error": "config_error", "detail": str(exc)})


@app.get("/frames/{name}", include_in_schema=False)
def frame(name: str):
    """Serve a real detector frame so the Quality gallery can show the actual image.

    Declared here rather than mounted during startup: the SPA catch-all below is
    registered at import time, and Starlette matches routes in order, so a mount added
    later would never be reached in single-container mode.
    """
    root = state.settings.artifact(
        state.settings.model["defect"].get("sample_images_dir", "sample_frames")).resolve()
    candidate = (root / name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise HTTPException(404, f"no such frame: {name}")
    return FileResponse(candidate)


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Liveness probe that stays at the root in every deployment shape."""
    return {"status": "ok", "serving_frontend": SERVING_FRONTEND}


if SERVING_FRONTEND:
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve the dashboard, falling back to index.html so a deep link or reload on
        /pnl, /history or /config returns the app rather than a 404."""
        candidate = (FRONTEND_DIST / full_path).resolve()
        # containment check: never serve outside the build directory
        if full_path and FRONTEND_DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def root():
        return {"name": "Cascade Digital Twin", "docs": "/docs", "health": "/health",
                "ws": "/ws/live"}
