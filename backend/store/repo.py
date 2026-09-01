"""Read/write helpers over the store (Backend Instructions §8)."""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, delete, select

from backend.services.pnl import ShiftCounts
from backend.store.db import session_scope
from backend.store.models import ConfigAudit, DefectEvent, PnLSnapshot, Shift, TwinState


# ── writes ──
def save_shift(s: Session, **kw) -> Shift:
    row = Shift(**kw)
    s.add(row)
    return row


def save_defect_events(s: Session, shift_id: int, events: list[dict]) -> None:
    for e in events:
        s.add(DefectEvent(
            shift_id=shift_id, vehicle_id=int(e["vehicle_id"]), station_id=int(e["station_id"]),
            timestamp=e["timestamp"], defect_class=e["defect_class"],
            defect_type=e.get("defect_type"), confidence=float(e["confidence"]),
            bbox=e.get("bbox"), source=e.get("source", "FINE_TUNED_YOLO"),
            camera_id=e.get("camera_id"), station_source=e.get("station_source"),
            frame=e.get("frame"), chains=e.get("chains"),
        ))


def save_twin_states(s: Session, shift_id: int, records: list[dict]) -> None:
    for r in records:
        s.add(TwinState(
            shift_id=shift_id, vehicle_id=r["vehicle_id"], timestamp=r["timestamp"],
            bottleneck_station=r["bottleneck_station"], bottleneck_zone=r["bottleneck_zone"],
            bottleneck_confidence=r["bottleneck_confidence"],
            bottleneck_abstained=r["bottleneck_abstained"],
            visual_defects=r["visual_defects"], process_defects=r["process_defects"],
            downstream_inspection_alerts=r["downstream_inspection_alerts"],
            meta=r["_meta"],
        ))


def save_pnl(s: Session, shift_id: int, counts: ShiftCounts, result: dict,
             cumulative: float) -> None:
    s.add(PnLSnapshot(
        shift_id=shift_id, net=result["net"], cumulative=cumulative,
        breakdown=result["breakdown"], sources=result["sources"],
        **{k: v for k, v in counts.as_dict().items() if k != "shift_id"},
    ))


def audit_config(s: Session, config_name: str, changes: dict, actor: str = "dashboard",
                 note: str | None = None) -> None:
    s.add(ConfigAudit(config_name=config_name, changes=changes, actor=actor, note=note))


# ── reads ──
def recent_twin_states(limit: int = 50) -> list[TwinState]:
    with session_scope() as s:
        return list(s.exec(select(TwinState).order_by(TwinState.id.desc()).limit(limit)))


def twin_state_by_vehicle(vehicle_id: int) -> Optional[TwinState]:
    with session_scope() as s:
        return s.exec(select(TwinState).where(TwinState.vehicle_id == vehicle_id)
                      .order_by(TwinState.id.desc())).first()


def all_pnl_counts() -> list[ShiftCounts]:
    """Stored per-shift REAL counts — the basis for re-projection without model rerun."""
    with session_scope() as s:
        rows = s.exec(select(PnLSnapshot).order_by(PnLSnapshot.id)).all()
    return [ShiftCounts(shift_id=r.shift_id,
                        confident_bottleneck_flags=r.confident_bottleneck_flags,
                        defects_caught=r.defects_caught, chains_flagged=r.chains_flagged,
                        inspections_raised=r.inspections_raised,
                        low_confidence_acted=r.low_confidence_acted) for r in rows]


def shifts_between(frm: int | None = None, to: int | None = None,
                   limit: int = 500) -> list[Shift]:
    with session_scope() as s:
        q = select(Shift).order_by(Shift.id)
        if frm is not None:
            q = q.where(Shift.shift_id >= frm)
        if to is not None:
            q = q.where(Shift.shift_id <= to)
        return list(s.exec(q.limit(limit)))


def defect_events(limit: int = 200) -> list[DefectEvent]:
    with session_scope() as s:
        return list(s.exec(select(DefectEvent).order_by(DefectEvent.id.desc()).limit(limit)))


def active_alerts(limit: int = 50) -> list[dict]:
    """Current downstream-inspection alerts, newest first, flattened for the rail."""
    out = []
    with session_scope() as s:
        rows = s.exec(select(TwinState).order_by(TwinState.id.desc()).limit(limit * 4)).all()
    for r in rows:
        for a in (r.downstream_inspection_alerts or []):
            out.append({**a, "vehicle_id": r.vehicle_id, "shift_id": r.shift_id,
                        "timestamp": r.timestamp})
            if len(out) >= limit:
                return out
    return out


def config_audits(limit: int = 20) -> list[ConfigAudit]:
    with session_scope() as s:
        return list(s.exec(select(ConfigAudit).order_by(ConfigAudit.id.desc()).limit(limit)))


def reset_session_data() -> None:
    """POST /control/reset — clear the session's twin data (config audits are kept)."""
    with session_scope() as s:
        for model in (TwinState, DefectEvent, PnLSnapshot, Shift):
            s.exec(delete(model))
