"""Tick engine — orchestrates one shift end-to-end (Workflow §3, Backend §6).

One tick = one shift:
  1. simulator emits shift features + vehicle frames
  2. bottleneck service -> monitor.step()
  3. defect service -> YOLO -> events -> chain engine
  4. integration service -> build_twin_state() per vehicle
  5. P&L engine updates the running projection
  6. store persists; the payload is pushed over the WebSocket
"""
from __future__ import annotations

import asyncio
import logging

from backend.config.loader import Settings
from backend.services.bottleneck import BottleneckService
from backend.services.defect import DefectService
from backend.services.integration import IntegrationService
from backend.services.pnl import PnLEngine, ShiftCounts
from backend.services.simulator import LineSimulator
from backend.store import repo
from backend.store.db import session_scope

log = logging.getLogger("cascade.engine")


class TwinEngine:
    def __init__(self, settings: Settings, simulator: LineSimulator,
                 bottleneck: BottleneckService, defect: DefectService,
                 integration: IntegrationService, pnl: PnLEngine):
        self.settings = settings
        self.simulator = simulator
        self.bottleneck = bottleneck
        self.defect = defect
        self.integration = integration
        self.pnl = pnl

        self.subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.playing = False
        self.interval_s = settings.tick_interval_s
        self.cumulative_net = 0.0
        self.last_tick: dict | None = None
        self.tick_count = 0

    # ── pub/sub ──
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    async def broadcast(self, message: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("ws subscriber slow, dropping message")

    async def push_status(self, state: str, **extra) -> None:
        await self.broadcast({"type": "status", "state": state, "playing": self.playing,
                              "interval_s": self.interval_s, "tick_count": self.tick_count,
                              **extra})

    # ── the tick ──
    async def tick(self) -> dict:
        async with self._lock:
            return await asyncio.to_thread(self._tick_sync)

    def _tick_sync(self) -> dict:
        self.settings.reload_if_changed()      # hot-reload P&L/mappings between ticks
        s = self.simulator.next_shift()

        # (2) bottleneck — real monitor.step()
        alert = self.bottleneck.step(s.shift_id, s.features)

        # (3) defects — real YOLO + chain engine (separate layers)
        all_events: list[dict] = []
        for v in s.vehicles:
            ev = self.defect.chain(self.defect.detect(v))
            all_events.extend(ev)

        # (4) integration — build_twin_state per vehicle that produced events.
        #     A vehicle with no detection yields no defect content, but still gets a
        #     twin-state so the shift's bottleneck call is visible for that vehicle.
        twin_states = []
        for v in s.vehicles:
            v_events = [e for e in all_events if e["vehicle_id"] == v.vehicle_id]
            frame = self.defect.events_frame(v_events)
            twin_states.append(
                self.integration.build_twin_state(v.vehicle_id, v.timestamp, alert, frame))

        new_alerts = [
            {**a, "vehicle_id": t["vehicle_id"], "shift_id": s.shift_id,
             "timestamp": t["timestamp"]}
            for t in twin_states for a in t["downstream_inspection_alerts"]
        ]

        # (5) P&L — counts are REAL model outputs this shift
        counts = ShiftCounts(
            shift_id=s.shift_id,
            confident_bottleneck_flags=int(
                alert["confidence"] == "high" and alert["predicted_bottleneck_station"] is not None),
            defects_caught=len(all_events),
            chains_flagged=len(new_alerts),
            inspections_raised=len(new_alerts),
            low_confidence_acted=int(alert["confidence"] == "low"),
        )
        pnl_result = self.pnl.compute(counts)
        self.cumulative_net = round(self.cumulative_net + pnl_result["net"], 2)
        pnl_result["cumulative"] = self.cumulative_net

        # (6) persist
        with session_scope() as sess:
            repo.save_shift(sess, shift_id=s.shift_id, shift_name=s.shift_name,
                            predicted_bottleneck_station=alert["predicted_bottleneck_station"],
                            bottleneck_zone=alert.get("zone"),
                            confidence=alert["confidence"], uncertainty=alert["uncertainty"],
                            abstained=bool(alert["abstained"]),
                            ground_truth_station=s.ground_truth_station,
                            is_anomaly_shift=s.is_anomaly_shift,
                            predicted_blockage=alert["predicted_blockage"],
                            predicted_starvation=alert["predicted_starvation"],
                            n_vehicles=len(s.vehicles), n_defect_events=len(all_events),
                            n_chain_alerts=len(new_alerts))
            repo.save_defect_events(sess, s.shift_id, all_events)
            repo.save_twin_states(sess, s.shift_id, twin_states)
            repo.save_pnl(sess, s.shift_id, counts, pnl_result, self.cumulative_net)

        self.tick_count += 1
        payload = {
            "type": "tick",
            "shift_id": s.shift_id,
            "shift_name": s.shift_name,
            "tick_count": self.tick_count,
            "bottleneck": {
                "station": alert["predicted_bottleneck_station"],
                "zone": alert.get("zone"),
                "confidence": alert["confidence"],
                "uncertainty": alert["uncertainty"],
                "abstained": alert["abstained"],
                "blk": alert["predicted_blockage"],
                "stv": alert["predicted_starvation"],
            },
            "twin_states": twin_states,
            "defect_events": all_events,
            "new_alerts": new_alerts,
            "pnl_delta": pnl_result,
            "_meta": {
                "bottleneck_source": "BSTAN_LiveBottleneckMonitor (real, loaded artifacts)",
                "defect_source": ("FINE_TUNED_YOLO (real)" if self.defect.enabled
                                  else "detector unavailable - no events emitted"),
                "defect_layer_enabled": self.defect.enabled,
                "line_data": "SIMULATED",
                "ids": "SIMULATED_prototype_metadata",
                "pnl": "PROJECTION from model outputs x user assumptions",
                "simulator_ground_truth_station": s.ground_truth_station,
                "is_anomaly_shift": s.is_anomaly_shift,
            },
        }
        self.last_tick = payload
        return payload

    async def tick_and_broadcast(self) -> dict:
        payload = await self.tick()
        await self.broadcast(payload)
        return payload

    # ── play / pause / reset ──
    async def _loop(self) -> None:
        try:
            while self.playing:
                await self.tick_and_broadcast()
                await asyncio.sleep(self.interval_s)
        except asyncio.CancelledError:
            raise
        except Exception:                       # noqa: BLE001
            log.exception("tick loop crashed")
            self.playing = False
            await self.push_status("error")

    async def play(self, interval_s: float | None = None) -> None:
        if interval_s is not None:
            self.interval_s = float(interval_s)
        if self.playing:
            return
        self.playing = True
        self._task = asyncio.create_task(self._loop())
        await self.push_status("playing")

    async def pause(self) -> None:
        self.playing = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.push_status("paused")

    async def reset(self) -> None:
        await self.pause()
        self.simulator.reset()
        self.bottleneck.reset()
        self.cumulative_net = 0.0
        self.tick_count = 0
        self.last_tick = None
        await asyncio.to_thread(repo.reset_session_data)
        await self.push_status("reset")

    def recompute_cumulative(self) -> float:
        """After a P&L config edit: re-project from stored counts, no model rerun."""
        series = self.pnl.recompute_series(repo.all_pnl_counts())
        self.cumulative_net = series["cumulative_net"]
        return self.cumulative_net
