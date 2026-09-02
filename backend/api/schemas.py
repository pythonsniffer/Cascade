"""Pydantic response models — mirror 00_PROJECT_CONTEXT.md §5 field-for-field."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Confidence = Literal["high", "low", "warming_up"]


class Provenance(BaseModel):
    """What is real vs simulated vs assumed — rendered by the UI honesty strip."""
    real: list[str]
    simulated: list[str]
    assumed: list[str]
    statement: str


class HealthResponse(BaseModel):
    status: str
    models_loaded: bool
    models: dict
    mode: str
    metrics: dict
    provenance: Provenance
    playing: bool
    tick_count: int
    interval_s: float


class LineNode(BaseModel):
    station_id: int
    zone: str
    zone_label: str
    sensor_poor: bool
    x: float
    y: float


class LineEdge(BaseModel):
    source: int
    target: int
    buffer: int
    weight: float
    kind: Literal["serial", "bypass", "rework"]


class LineResponse(BaseModel):
    """FIXED topology, loaded from graph.pt, read-only (Backend §9 / Context §3b)."""
    n_stations: int
    zones: dict
    nodes: list[LineNode]
    edges: list[LineEdge]
    note: str


class VisualDefect(BaseModel):
    station_id: int
    zone: str
    defect_class: str
    confidence: float
    bbox: list[float]


class ProcessDefect(BaseModel):
    station_id: int
    defect_type: Optional[str] = None


class ChainAlert(BaseModel):
    trigger_defect: str
    predicted_downstream_defect: str
    P_B_given_A: float
    lift: float
    origin_station: int
    action: str
    vehicle_id: Optional[int] = None
    shift_id: Optional[int] = None
    timestamp: Optional[str] = None


class TwinStateResponse(BaseModel):
    """The canonical integration output (Context §5)."""
    vehicle_id: int
    timestamp: str
    bottleneck_station: Optional[int] = None
    bottleneck_zone: Optional[str] = None
    bottleneck_confidence: Optional[str] = None
    bottleneck_abstained: Optional[bool] = None
    visual_defects: list[VisualDefect] = []
    process_defects: list[ProcessDefect] = []
    downstream_inspection_alerts: list[ChainAlert] = []
    shift_id: Optional[int] = None
    meta: dict = Field(default_factory=dict, alias="_meta")

    model_config = {"populate_by_name": True}


class DefectEventResponse(BaseModel):
    shift_id: int
    vehicle_id: int
    station_id: int
    timestamp: str
    defect_class: str
    defect_type: Optional[str] = None
    confidence: float
    bbox: Optional[list[float]] = None
    source: str
    camera_id: Optional[str] = None
    station_source: Optional[str] = None
    frame: Optional[str] = None
    chains: list[dict] = []


class PnLResponse(BaseModel):
    latest: Optional[dict] = None
    series: list[dict] = []
    cumulative_net: float = 0.0
    cumulative_breakdown: dict = {}
    cumulative_counts: dict = {}
    shifts_counted: int = 0
    assumptions: dict = {}
    missing_config: list[str] = []
    currency: str = "USD"
    is_projection: bool = True
    disclaimer: str
    sensitivity: Optional[dict] = None
    last_changed: Optional[dict] = None


class ShiftHistory(BaseModel):
    shift_id: int
    shift_name: str
    predicted_bottleneck_station: Optional[int] = None
    bottleneck_zone: Optional[str] = None
    confidence: str
    uncertainty: Optional[float] = None
    abstained: bool
    n_defect_events: int
    n_chain_alerts: int
    ground_truth_station: Optional[int] = None
    is_anomaly_shift: bool = False


class HistoryResponse(BaseModel):
    shifts: list[ShiftHistory]
    pnl_series: list[dict]
    zone_counts: dict
    station_counts: dict


class ConfigResponse(BaseModel):
    config: dict
    provenance: Provenance
    chains: list[dict]
    audits: list[dict]


class PnLConfigUpdate(BaseModel):
    values: dict[str, Any]
    actor: str = "dashboard"
    note: Optional[str] = None


class MappingsUpdate(BaseModel):
    CAMERA_TO_STATION: Optional[dict[str, int]] = None
    VISUAL_TO_PROCESS: Optional[dict[str, str]] = None
    actor: str = "dashboard"
    note: Optional[str] = None


class PlayRequest(BaseModel):
    interval_s: Optional[float] = None
