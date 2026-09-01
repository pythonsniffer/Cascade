"""Bottleneck service — thin wrapper over LiveBottleneckMonitor (Backend §6).

step() calls monitor.step() unchanged and passes its dict straight through.
"""
from __future__ import annotations

import numpy as np

from backend.config.loader import Settings
from backend.models.loader import BottleneckBundle


class BottleneckService:
    def __init__(self, settings: Settings, bundle: BottleneckBundle):
        self.settings = settings
        self.bundle = bundle

    def step(self, shift_id: int, features: np.ndarray) -> dict:
        """features: normalized [N, F] in FEATURES order. Returns the monitor's alert."""
        expected = (self.bundle.n_stations, len(self.bundle.features))
        if tuple(features.shape) != expected:
            raise ValueError(f"bottleneck features must be {expected}, got {tuple(features.shape)}")
        alert = self.bundle.monitor.step(features, shift_id=shift_id)
        bn = alert.get("predicted_bottleneck_station")
        alert["zone"] = self.settings.zone_of(bn) if bn is not None else None
        return alert

    def reset(self) -> None:
        self.bundle.monitor.reset()

    @property
    def warming_up(self) -> bool:
        return len(self.bundle.monitor.window) < self.bundle.T_w
