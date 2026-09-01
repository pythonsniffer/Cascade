"""SQLModel tables (Backend Instructions §8).

SQLite for the demo, Postgres-ready — only the connection string changes.
JSON columns keep the raw contract shapes for visual_defects, process_defects,
downstream_inspection_alerts and _meta.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from sqlalchemy import Column, Text
from sqlmodel import JSON, Field, SQLModel


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class Shift(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(index=True)
    shift_name: str
    created_at: _dt.datetime = Field(default_factory=_utcnow, index=True)
    predicted_bottleneck_station: Optional[int] = None
    bottleneck_zone: Optional[str] = None
    confidence: str = "warming_up"
    uncertainty: Optional[float] = None
    abstained: bool = True
    ground_truth_station: Optional[int] = None
    is_anomaly_shift: bool = False
    predicted_blockage: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    predicted_starvation: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    n_vehicles: int = 0
    n_defect_events: int = 0
    n_chain_alerts: int = 0


class DefectEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(index=True)
    vehicle_id: int = Field(index=True)
    station_id: int = Field(index=True)
    timestamp: str
    defect_class: str
    defect_type: Optional[str] = None
    confidence: float
    bbox: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    source: str = "FINE_TUNED_YOLO"
    camera_id: Optional[str] = None
    station_source: Optional[str] = None
    frame: Optional[str] = None
    chains: Optional[Any] = Field(default=None, sa_column=Column(JSON))


class TwinState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(index=True)
    vehicle_id: int = Field(index=True)
    timestamp: str
    bottleneck_station: Optional[int] = None
    bottleneck_zone: Optional[str] = None
    bottleneck_confidence: Optional[str] = None
    bottleneck_abstained: Optional[bool] = None
    visual_defects: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    process_defects: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    downstream_inspection_alerts: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    meta: Optional[Any] = Field(default=None, sa_column=Column("_meta", JSON))
    created_at: _dt.datetime = Field(default_factory=_utcnow, index=True)


class PnLSnapshot(SQLModel, table=True):
    """Per-shift REAL counts + the projection computed under the then-current config.

    The counts are what make re-projection possible without rerunning any model.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    shift_id: int = Field(index=True)
    created_at: _dt.datetime = Field(default_factory=_utcnow, index=True)
    confident_bottleneck_flags: int = 0
    defects_caught: int = 0
    chains_flagged: int = 0
    inspections_raised: int = 0
    low_confidence_acted: int = 0
    net: float = 0.0
    cumulative: float = 0.0
    breakdown: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    sources: Optional[Any] = Field(default=None, sa_column=Column(JSON))


class ConfigAudit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: _dt.datetime = Field(default_factory=_utcnow, index=True)
    config_name: str = Field(index=True)
    actor: str = "dashboard"
    changes: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    note: Optional[str] = Field(default=None, sa_column=Column(Text))
