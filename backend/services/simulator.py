"""Line simulator — the ONLY simulated component (Architecture §2).

Backend Instructions §5. Two modes from line_config.simulator.mode:
  - "replay"   : replay the exact normalized [35,10] shifts exported alongside the
                 models (line_shifts.npz). Byte-for-byte the notebook's inputs.
  - "generate" : re-run the notebook's simulate() live, then normalize with the
                 LOADED xmin/xmax (never refit — Backend Instructions §5).

Per tick it yields a shift_id, the [N,F] normalized array, and the vehicle frames
"produced" this shift. Vehicle frames are REAL YOLO test images tagged with
SIMULATED line metadata — the honest split.
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.config.loader import ConfigError, Settings
from backend.models.loader import BottleneckBundle, DefectBundle

log = logging.getLogger("cascade.simulator")


@dataclass
class VehicleFrame:
    vehicle_id: int
    camera_id: str
    timestamp: str
    frame_path: Path | None       # None when no detector/frames are available


@dataclass
class ShiftTick:
    shift_id: int
    features: np.ndarray          # [N, F] normalized, FEATURES order
    vehicles: list[VehicleFrame]
    shift_name: str
    ground_truth_station: int | None   # simulator's injected bottleneck, for honesty/debug
    is_anomaly_shift: bool


class LineSimulator:
    def __init__(self, settings: Settings, bn: BottleneckBundle, df: DefectBundle):
        self.settings = settings
        self.bn = bn
        self.defect = df
        sim = settings.line["simulator"]
        self.mode = sim["mode"]
        self.vehicles_per_shift = int(sim["vehicles_per_shift"])
        self.start_shift = int(sim.get("start_shift", 0))
        self.shift_names = list(settings.line["shift_names"])
        self.shift_minutes = int(settings.line["shift_duration_minutes"])
        self._cursor = 0
        self._vehicle_counter = 0
        self._rng = np.random.default_rng(int(sim["seed"]))
        self._X = None
        self._truth = None
        self._anomalies: set[int] = set()
        self._load_source()

    # ── sources ──
    def _load_source(self) -> None:
        if self.mode == "replay":
            npz_path = self.settings.artifact("line_shifts.npz")
            if not npz_path.exists():
                raise ConfigError(
                    f"simulator mode 'replay' needs {npz_path}; run tools/export_artifacts.py")
            blob = np.load(npz_path)
            self._X = blob["X"]
            self._truth = blob["truth"]
            pairs = blob["anomaly_shifts"]
            self._anomalies = {int(s) for s, _ in pairs} if pairs.size else set()
            log.info("simulator: replay mode, %d shifts from %s", len(self._X), npz_path.name)
        elif self.mode == "generate":
            self._generate()
        else:
            raise ConfigError(f"unknown simulator mode '{self.mode}' (expected replay|generate)")

    def _generate(self) -> None:
        """Re-run the notebook simulator, normalize with the LOADED xmin/xmax."""
        from tools.export_artifacts import simulate, inject_anomalies  # notebook code, verbatim
        import pandas as pd  # noqa: F401  (used by simulate)

        df, _G, truth = simulate()
        anomalies = inject_anomalies(df)
        feats = self.bn.features
        S = int(df.shift_id.nunique())
        X = np.stack([df[df.shift_id == s].sort_values("station_id")[feats].values
                      for s in range(S)])
        # apply the TRAINING normalization; do not refit (Backend Instructions §5)
        self._X = ((X - self.bn.xmin) / (self.bn.xmax - self.bn.xmin + 1e-9)).astype(np.float32)
        self._truth = truth
        self._anomalies = set(anomalies)
        log.info("simulator: generate mode, %d shifts synthesized", S)

    # ── ticking ──
    @property
    def n_shifts(self) -> int:
        return int(len(self._X))

    def reset(self) -> None:
        self._cursor = 0
        self._vehicle_counter = 0
        self._rng = np.random.default_rng(int(self.settings.line["simulator"]["seed"]))

    def next_shift(self) -> ShiftTick:
        sid = (self.start_shift + self._cursor) % self.n_shifts
        self._cursor += 1
        gt = int(self._truth[sid]) if self._truth is not None else -1
        base = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc) + _dt.timedelta(
            minutes=self.shift_minutes * self._cursor)

        vehicles = []
        cams = list(self.defect.camera_to_station) or ["cam_unassigned"]
        frames = self.defect.sample_frames
        for k in range(self.vehicles_per_shift):
            self._vehicle_counter += 1
            ts = (base + _dt.timedelta(minutes=k * 3)).isoformat(timespec="seconds").replace("+00:00", "Z")
            frame = frames[(self._vehicle_counter - 1) % len(frames)] if frames else None
            vehicles.append(VehicleFrame(
                vehicle_id=self._vehicle_counter,
                camera_id=cams[(self._vehicle_counter - 1) % len(cams)],
                timestamp=ts,
                frame_path=frame,
            ))

        return ShiftTick(
            shift_id=sid,
            features=np.asarray(self._X[sid], dtype=np.float32),
            vehicles=vehicles,
            shift_name=self.shift_names[self._cursor % len(self.shift_names)],
            ground_truth_station=gt if gt >= 0 else None,
            is_anomaly_shift=sid in self._anomalies,
        )

    def provenance(self) -> dict:
        return {
            "mode": self.mode,
            "n_shifts": self.n_shifts,
            "vehicles_per_shift": self.vehicles_per_shift,
            "process_features": "SIMULATED (seed %s)" % self.settings.line["simulator"]["seed"],
            "vehicle_frames": ("REAL images, SIMULATED line metadata"
                               if self.defect.sample_frames else "no frames available"),
        }
