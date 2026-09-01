"""Cascade Digital Twin — FastAPI application.

Startup: load config + exported artifacts, init the store, optionally autoplay.
The backend NEVER trains (Architecture §7); artifacts come from
tools/export_artifacts.py, run offline.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    # mount the real detector frames so the Quality gallery can show the actual images
    frames = state.settings.artifact(state.settings.model["defect"].get(
        "sample_images_dir", "sample_frames"))
    if frames.exists():
        app.mount("/frames", StaticFiles(directory=str(frames)), name="frames")
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

# The REST surface is served twice, deliberately:
#   - at the root, exactly as Backend Instructions §9 names it (GET /pnl, /history, ...)
#   - under /api, so the dashboard can share one origin with the SPA. Without this the
#     SPA routes /pnl, /history and /config collide with the API paths of the same name
#     and a page reload returns JSON instead of the app.
app.include_router(rest_router)
app.include_router(rest_router, prefix="/api")
app.include_router(ws_router)
app.include_router(ws_router, prefix="/api")


@app.exception_handler(ConfigError)
async def config_error_handler(request, exc: ConfigError):
    return JSONResponse(status_code=500, content={"error": "config_error", "detail": str(exc)})


@app.get("/")
def root():
    return {"name": "Cascade Digital Twin", "docs": "/docs", "health": "/health",
            "ws": "/ws/live"}
