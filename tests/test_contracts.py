"""The data contracts from 00_PROJECT_CONTEXT.md §5 must not drift."""
import numpy as np

FEATURES = ["blockage", "starvation", "downtime", "cycle_time",
            "product_mix", "production_volume", "seq_variability",
            "planned_product_mix", "planned_production_volume", "planned_seq_variability"]


def test_feature_order_matches_contract(app_state):
    assert app_state.bn.features == FEATURES


def test_monitor_input_shape_is_35x10(app_state):
    assert app_state.bn.n_stations == 35
    assert len(app_state.bn.features) == 10


def test_monitor_output_keys(app_state):
    svc = app_state.engine.bottleneck
    svc.reset()
    feats = np.zeros((35, 10), dtype=np.float32)
    out = svc.step(0, feats)
    for k in ("shift_id", "predicted_bottleneck_station", "confidence", "uncertainty",
              "predicted_blockage", "predicted_starvation", "abstained"):
        assert k in out, f"monitor output missing contract key {k}"


def test_warming_up_is_honest_not_a_fake_station(app_state):
    """Architecture §9: warming up must never name a station."""
    svc = app_state.engine.bottleneck
    svc.reset()
    feats = np.zeros((35, 10), dtype=np.float32)
    for i in range(app_state.bn.T_w - 1):
        out = svc.step(i, feats)
        assert out["confidence"] == "warming_up"
        assert out["predicted_bottleneck_station"] is None
        assert out["abstained"] is True


def test_wrong_feature_shape_rejected(app_state):
    import pytest
    svc = app_state.engine.bottleneck
    with pytest.raises(ValueError):
        svc.step(0, np.zeros((10, 35), dtype=np.float32))


def test_twin_state_record_shape(app_state):
    import pandas as pd
    rec = app_state.engine.integration.build_twin_state(
        1, "2026-01-01T00:00:00Z",
        {"predicted_bottleneck_station": 5, "confidence": "high", "abstained": False},
        pd.DataFrame([]))
    for k in ("vehicle_id", "timestamp", "bottleneck_station", "bottleneck_zone",
              "bottleneck_confidence", "bottleneck_abstained", "visual_defects",
              "process_defects", "downstream_inspection_alerts", "_meta"):
        assert k in rec, f"twin-state missing contract key {k}"
    assert rec["bottleneck_zone"] == "body"


def test_zone_boundaries_match_context_section_2(app_state):
    s = app_state.settings
    assert s.zone_of(0) == "body" and s.zone_of(14) == "body"
    assert s.zone_of(15) == "paint" and s.zone_of(22) == "paint"
    assert s.zone_of(23) == "final_assembly" and s.zone_of(34) == "final_assembly"
