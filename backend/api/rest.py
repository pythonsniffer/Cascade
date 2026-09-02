"""REST routes (Backend Instructions §9)."""
from __future__ import annotations

import json
import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.api import schemas
from backend.api.state import state
from backend.store import repo
from backend.store.db import session_scope

router = APIRouter()


# ─────────────────────────── health / config ───────────────────────────
@router.get("/health", response_model=schemas.HealthResponse)
def health():
    models = state.models_status()
    metrics = dict(state.metrics)
    # the running detector's own recorded numbers, straight from the artifact
    if state.df.checkpoint_metrics:
        metrics = {**metrics, "detector_checkpoint": state.df.checkpoint_metrics}
    return {
        "status": "ok",
        # bottleneck models are mandatory; the detector is reported separately so the
        # UI can degrade honestly rather than implying a full stack.
        "models_loaded": models["bottleneck"]["loaded"] and models["chains"]["loaded"],
        "models": models,
        "mode": state.settings.line["simulator"]["mode"],
        "metrics": metrics,
        "provenance": state.provenance(),
        "playing": state.engine.playing,
        "tick_count": state.engine.tick_count,
        "interval_s": state.engine.interval_s,
    }


@router.get("/config", response_model=schemas.ConfigResponse)
def get_config():
    state.settings.reload_if_changed()
    chains = json.loads(state.df.learned_chains.to_json(orient="records"))
    audits = [{"config_name": a.config_name, "actor": a.actor,
               "created_at": a.created_at.isoformat(), "changes": a.changes, "note": a.note}
              for a in repo.config_audits()]
    return {"config": state.settings.effective(), "provenance": state.provenance(),
            "chains": chains, "audits": audits}


@router.post("/config/pnl")
def update_pnl_config(body: schemas.PnLConfigUpdate):
    """Edit P&L assumptions live. Audited, hot-reloaded, re-projects with no model rerun."""
    s = state.settings
    current = dict(s.pnl)
    changes = {}
    for k, v in body.values.items():
        if k.startswith("_"):
            raise HTTPException(400, f"'{k}' is metadata, not an assumption")
        if k != "currency":
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"'{k}' must be numeric, got {v!r}")
            if math.isnan(v) or math.isinf(v):
                raise HTTPException(400, f"'{k}' must be a finite number")
        changes[k] = {"from": current.get(k), "to": v}
        current[k] = v
    s.write("pnl_config", current)
    with session_scope() as sess:
        repo.audit_config(sess, "pnl_config", changes, actor=body.actor, note=body.note)
    cumulative = state.engine.recompute_cumulative()
    return {"ok": True, "changed": changes, "pnl_config": s.pnl,
            "cumulative_net": cumulative, "missing_config": s.missing_pnl_fields()}


@router.post("/config/mappings")
def update_mappings(body: schemas.MappingsUpdate):
    """Edit camera->station / visual->process. Audited and hot-reloaded."""
    s = state.settings
    current = dict(s.mappings)
    changes = {}
    if body.CAMERA_TO_STATION is not None:
        for cam, st in body.CAMERA_TO_STATION.items():
            if not 0 <= int(st) < s.n_stations:
                raise HTTPException(400, f"station {st} for '{cam}' outside 0..{s.n_stations - 1}")
        changes["CAMERA_TO_STATION"] = {"from": current.get("CAMERA_TO_STATION"),
                                        "to": body.CAMERA_TO_STATION}
        current["CAMERA_TO_STATION"] = {k: int(v) for k, v in body.CAMERA_TO_STATION.items()}
    if body.VISUAL_TO_PROCESS is not None:
        unknown = set(body.VISUAL_TO_PROCESS) - set(current["VISUAL_CLASSES"])
        if unknown:
            raise HTTPException(400, f"unknown visual classes: {sorted(unknown)}")
        bad = set(body.VISUAL_TO_PROCESS.values()) - set(current["DEFECT_TYPES"])
        if bad:
            raise HTTPException(400, f"unknown process defect types: {sorted(bad)}")
        changes["VISUAL_TO_PROCESS"] = {"from": current.get("VISUAL_TO_PROCESS"),
                                        "to": body.VISUAL_TO_PROCESS}
        current["VISUAL_TO_PROCESS"] = body.VISUAL_TO_PROCESS
    if not changes:
        raise HTTPException(400, "nothing to update")
    s.write("mappings", current)
    with session_scope() as sess:
        repo.audit_config(sess, "mappings", changes, actor=body.actor, note=body.note)
    return {"ok": True, "changed": changes, "mappings": s.mappings}


# ─────────────────────────── line topology ───────────────────────────
@router.get("/line", response_model=schemas.LineResponse)
def get_line():
    """FIXED 35-station topology from graph.pt. Read-only by design (Context §3b)."""
    s, bn = state.settings, state.bn
    zones = s.zones

    nodes = []
    for i in range(bn.n_stations):
        zone = s.zone_of(i)
        z = zones[zone]
        span = max(1, z["end"] - z["start"])
        # serpentine layout: one row per zone, so 35 stations fit a floor view
        row = list(zones).index(zone)
        col = (i - z["start"]) / span
        nodes.append({
            "station_id": i, "zone": zone, "zone_label": z["label"],
            "sensor_poor": bool(bn.G.nodes[i].get("sensor_poor", False)),
            "x": round(col, 4), "y": round(row, 4),
        })

    edges = []
    for u, v, d in bn.G_dir.edges(data=True):
        kind = "serial"
        if u == 13 and v == 15:
            kind = "bypass"
        elif u > v:
            kind = "rework"
        edges.append({"source": int(u), "target": int(v), "buffer": int(d.get("buffer", 0)),
                      "weight": round(float(d.get("weight", 0.0)), 4), "kind": kind})

    return {
        "n_stations": bn.n_stations, "zones": zones, "nodes": nodes, "edges": edges,
        "note": ("Topology is fixed at 35 stations because BSTAN is trained for this specific "
                 "graph; it is loaded from the graph.pt artifact and served read-only. "
                 "Extending to a different line is a retraining task, not a config swap."),
    }


# ─────────────────────────── twin state ───────────────────────────
def _twin_row_to_dict(r) -> dict:
    return {
        "vehicle_id": r.vehicle_id, "timestamp": r.timestamp, "shift_id": r.shift_id,
        "bottleneck_station": r.bottleneck_station, "bottleneck_zone": r.bottleneck_zone,
        "bottleneck_confidence": r.bottleneck_confidence,
        "bottleneck_abstained": r.bottleneck_abstained,
        "visual_defects": r.visual_defects or [], "process_defects": r.process_defects or [],
        "downstream_inspection_alerts": r.downstream_inspection_alerts or [],
        "_meta": r.meta or {},
    }


@router.get("/twin/state")
def twin_states(limit: int = Query(50, ge=1, le=500)):
    return {"twin_states": [_twin_row_to_dict(r) for r in repo.recent_twin_states(limit)],
            "last_tick": state.engine.last_tick}


@router.get("/twin/state/{vehicle_id}")
def twin_state(vehicle_id: int):
    row = repo.twin_state_by_vehicle(vehicle_id)
    if row is None:
        raise HTTPException(404, f"no twin-state record for vehicle {vehicle_id}")
    return _twin_row_to_dict(row)


@router.get("/alerts")
def alerts(active: bool = True, limit: int = Query(50, ge=1, le=200)):
    return {"alerts": repo.active_alerts(limit), "active": active}


@router.get("/detections")
def detections(limit: int = Query(60, ge=1, le=300)):
    """Recent YOLO detections for the Quality gallery. Empty when the detector is off."""
    rows = repo.defect_events(limit)
    return {
        "detections": [{
            "shift_id": r.shift_id, "vehicle_id": r.vehicle_id, "station_id": r.station_id,
            "timestamp": r.timestamp, "defect_class": r.defect_class,
            "defect_type": r.defect_type, "confidence": r.confidence, "bbox": r.bbox,
            "source": r.source, "camera_id": r.camera_id, "station_source": r.station_source,
            "frame": r.frame, "chains": r.chains or [],
        } for r in rows],
        "detector": state.engine.defect.status(),
    }


# ─────────────────────────── P&L ───────────────────────────
@router.get("/pnl", response_model=schemas.PnLResponse)
def pnl(sensitivity_key: str = "downtime_cost_per_min", sensitivity_pct: float = 0.2):
    state.settings.reload_if_changed()
    counts = repo.all_pnl_counts()
    result = state.engine.pnl.recompute_series(counts)
    result["sensitivity"] = (state.engine.pnl.sensitivity(counts, sensitivity_key, sensitivity_pct)
                             if counts else None)
    audits = [a for a in repo.config_audits(50) if a.config_name == "pnl_config"]
    result["last_changed"] = ({"at": audits[0].created_at.isoformat(), "actor": audits[0].actor,
                               "changes": audits[0].changes} if audits else None)
    return result


@router.post("/pnl/config/reset")
def reset_pnl_config(actor: str = "dashboard"):
    """Restore the shipped default assumptions."""
    from backend.config.loader import DEFAULTS_DIR
    defaults = json.loads((DEFAULTS_DIR / "pnl_config.json").read_text())
    before = dict(state.settings.pnl)
    state.settings.write("pnl_config", defaults)
    with session_scope() as sess:
        repo.audit_config(sess, "pnl_config", {"reset_to_defaults": {"from": before}},
                          actor=actor, note="reset to defaults")
    return {"ok": True, "pnl_config": state.settings.pnl,
            "cumulative_net": state.engine.recompute_cumulative()}


# ─────────────────────────── history ───────────────────────────
@router.get("/history", response_model=schemas.HistoryResponse)
def history(frm: Optional[int] = Query(None, alias="from"), to: Optional[int] = None,
            limit: int = Query(500, ge=1, le=2000)):
    shifts = repo.shifts_between(frm, to, limit)
    zone_counts: dict = {}
    station_counts: dict = {}
    for sh in shifts:
        if sh.predicted_bottleneck_station is not None and not sh.abstained:
            zone_counts[sh.bottleneck_zone] = zone_counts.get(sh.bottleneck_zone, 0) + 1
            k = str(sh.predicted_bottleneck_station)
            station_counts[k] = station_counts.get(k, 0) + 1
    series = state.engine.pnl.recompute_series(repo.all_pnl_counts())["series"]
    return {
        "shifts": [{
            "shift_id": s.shift_id, "shift_name": s.shift_name,
            "predicted_bottleneck_station": s.predicted_bottleneck_station,
            "bottleneck_zone": s.bottleneck_zone, "confidence": s.confidence,
            "uncertainty": s.uncertainty, "abstained": s.abstained,
            "n_defect_events": s.n_defect_events, "n_chain_alerts": s.n_chain_alerts,
            "ground_truth_station": s.ground_truth_station,
            "is_anomaly_shift": s.is_anomaly_shift,
        } for s in shifts],
        "pnl_series": series, "zone_counts": zone_counts, "station_counts": station_counts,
    }


# ─────────────────────────── control ───────────────────────────
@router.post("/control/tick")
async def control_tick():
    return await state.engine.tick_and_broadcast()


@router.post("/control/play")
async def control_play(body: schemas.PlayRequest | None = None):
    await state.engine.play(body.interval_s if body else None)
    return {"playing": True, "interval_s": state.engine.interval_s}


@router.post("/control/pause")
async def control_pause():
    await state.engine.pause()
    return {"playing": False}


@router.post("/control/reset")
async def control_reset():
    await state.engine.reset()
    return {"ok": True, "tick_count": 0, "cumulative_net": 0.0}
