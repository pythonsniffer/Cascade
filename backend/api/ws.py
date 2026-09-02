"""WebSocket live stream (Backend Instructions §9)."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.state import state

log = logging.getLogger("cascade.ws")
router = APIRouter()


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    engine = state.engine
    q = engine.subscribe()
    try:
        # hello: current state, so a late joiner renders immediately without polling
        await websocket.send_json({
            "type": "status", "state": "connected", "playing": engine.playing,
            "interval_s": engine.interval_s, "tick_count": engine.tick_count,
            "defect_layer_enabled": engine.defect.enabled,
            "warming_up": engine.bottleneck.warming_up,
        })
        if engine.last_tick is not None:
            await websocket.send_json(engine.last_tick)

        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=20.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:                            # noqa: BLE001
        log.exception("websocket error")
    finally:
        engine.unsubscribe(q)
