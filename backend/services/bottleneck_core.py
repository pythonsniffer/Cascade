"""Ensemble confidence gating + LiveBottleneckMonitor.

COPIED VERBATIM from Cascade_Integrated.ipynb cells A10 (forecast_with_confidence)
and A11 (LiveBottleneckMonitor). Do not modify — Backend Instructions §11.3.
"""
import numpy as np
import torch

from backend.models.graph import turning_point_general


# ─── A10 · Ensemble Confidence Gating ────────────────────────────────────
def forecast_with_confidence(ensemble, X_window, edge_index, edge_weight, threshold):
    """Run all ensemble members, use prediction variance as uncertainty proxy.

    Returns:
        mean_pred:    array [N_stations, 2]  (ensemble-averaged forecast)
        is_confident: bool (True if uncertainty < threshold)
        uncertainty:  float (mean prediction variance across stations & features)
    """
    preds = []
    with torch.no_grad():
        for m in ensemble:
            p = m(X_window, edge_index, edge_weight).numpy()
            preds.append(p)

    preds = np.stack(preds)                  # [K, N, 2]
    mean_pred = preds.mean(axis=0)           # [N, 2]
    var_pred = preds.var(axis=0)             # [N, 2]
    uncertainty = float(var_pred.mean())     # scalar

    is_confident = uncertainty < threshold
    return mean_pred, is_confident, uncertainty


# ─── A11 · LiveBottleneckMonitor ─────────────────────────────────────────
class LiveBottleneckMonitor:
    """Streaming bottleneck forecaster for the digital twin's live loop."""

    def __init__(self, ensemble, edge_index, edge_weight, G_dir, T_w, conf_threshold):
        self.ensemble = ensemble
        self.edge_index = edge_index
        self.edge_weight = edge_weight
        self.G_dir = G_dir
        self.T_w = T_w
        self.conf_threshold = conf_threshold
        self.window = []               # rolling buffer of last T_w shifts
        self.shift_counter = 0

    def step(self, new_shift_features, shift_id=None):
        """Process one shift's per-station features, return a structured alert."""
        self.shift_counter += 1
        sid = shift_id if shift_id is not None else self.shift_counter

        self.window.append(new_shift_features)
        if len(self.window) > self.T_w:
            self.window.pop(0)

        if len(self.window) < self.T_w:
            return dict(shift_id=int(sid),
                        predicted_bottleneck_station=None,
                        confidence="warming_up",
                        uncertainty=None,
                        predicted_blockage=None,
                        predicted_starvation=None,
                        abstained=True)

        X_window = torch.tensor(np.stack(self.window), dtype=torch.float)

        mean_pred, is_confident, unc = forecast_with_confidence(
            self.ensemble, X_window, self.edge_index, self.edge_weight,
            self.conf_threshold)

        bn = None
        if is_confident:
            bn = turning_point_general(self.G_dir, mean_pred[:, 0], mean_pred[:, 1])

        return dict(
            shift_id=int(sid),
            predicted_bottleneck_station=int(bn) if bn is not None else None,
            confidence="high" if is_confident else "low",
            uncertainty=round(float(unc), 6),
            predicted_blockage=[round(float(v), 3) for v in mean_pred[:, 0]],
            predicted_starvation=[round(float(v), 3) for v in mean_pred[:, 1]],
            abstained=not is_confident,
        )

    def reset(self):
        """Clear the rolling window (used by POST /control/reset)."""
        self.window = []
        self.shift_counter = 0
