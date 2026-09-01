"""P&L engine — Workflow §5 formula, §7 sourcing and missing-config rules."""
import json

import pytest

from backend.services.pnl import PnLEngine, ShiftCounts


@pytest.fixture
def counts():
    return ShiftCounts(shift_id=1, confident_bottleneck_flags=2, defects_caught=3,
                       chains_flagged=4, inspections_raised=4, low_confidence_acted=1)


def test_formula_matches_workflow_section_5(app_state, counts):
    s = app_state.settings
    r = PnLEngine(s).compute(counts)
    b = r["breakdown"]
    assert b["value_from_bottleneck"] == pytest.approx(
        2 * s.pnl_value("downtime_minutes_avoided_per_flag") * s.pnl_value("downtime_cost_per_min"))
    assert b["value_from_defects"] == pytest.approx(
        3 * s.pnl_value("avg_units_that_would_carry_it") * s.pnl_value("scrap_cost_per_unit"))
    assert b["value_from_chains"] == pytest.approx(4 * s.pnl_value("defect_caught_value"))
    assert b["cost_of_inspections"] == pytest.approx(-4 * s.pnl_value("inspection_cost_per_check"))
    assert b["cost_of_false_alarms"] == pytest.approx(-1 * s.pnl_value("false_alarm_cost"))
    assert r["net"] == pytest.approx(sum(b.values()))


def test_every_term_is_tagged_model_output_or_assumption(app_state, counts):
    """§7: every number traces to a model output or a named config assumption."""
    r = PnLEngine(app_state.settings).compute(counts)
    for line, src in r["sources"].items():
        assert src["status"] == "ok", line
        assert src["count_source"] == "model_output"
        assert src["assumption_source"] == "assumption"
        assert src["assumptions"], f"{line} has no named assumptions"


def test_disclaimer_always_present(app_state, counts):
    r = PnLEngine(app_state.settings).compute(counts)
    assert r["is_projection"] is True
    assert "not measured savings" in r["disclaimer"].lower()


def test_missing_config_yields_null_line_not_an_invented_value(app_state, counts):
    """Architecture §9: refuse to compute, never assume."""
    s = app_state.settings
    original = dict(s.pnl)
    try:
        s.pnl = {k: v for k, v in original.items() if k != "scrap_cost_per_unit"}
        r = PnLEngine(s).compute(counts)
        assert r["breakdown"]["value_from_defects"] is None
        assert r["sources"]["value_from_defects"]["status"] == "missing_config"
        assert "scrap_cost_per_unit" in r["missing_config"]
        assert r["complete"] is False
        # other lines still compute
        assert r["breakdown"]["value_from_chains"] is not None
    finally:
        s.pnl = original


def test_editing_an_assumption_reprojects_without_model_rerun(client, app_state):
    """§7 / Frontend §10: the headline changes with no restart and no inference."""
    client.post("/control/reset")
    for _ in range(5):
        client.post("/control/tick")
    before = client.get("/pnl").json()
    assert before["shifts_counted"] > 0

    yolo_calls_before = getattr(app_state.df.yolo, "calls", None)
    base = before["assumptions"]["downtime_cost_per_min"]
    r = client.post("/config/pnl", json={"values": {"downtime_cost_per_min": base * 2}})
    assert r.status_code == 200

    after = client.get("/pnl").json()
    assert after["assumptions"]["downtime_cost_per_min"] == base * 2
    assert after["cumulative_net"] != before["cumulative_net"]
    assert after["shifts_counted"] == before["shifts_counted"], "counts must not change"
    assert after["last_changed"] is not None, "the edit must be audited"
    if yolo_calls_before is not None:
        assert app_state.df.yolo.calls == yolo_calls_before, "models must not re-run"

    client.post("/pnl/config/reset")


def test_pnl_config_rejects_non_numeric(client):
    assert client.post("/config/pnl", json={"values": {"downtime_cost_per_min": "free"}}).status_code == 400
    assert client.post("/config/pnl", json={"values": {"_provenance": "x"}}).status_code == 400


def test_sensitivity_brackets_the_base(client):
    client.post("/control/reset")
    for _ in range(5):
        client.post("/control/tick")
    s = client.get("/pnl").json()["sensitivity"]
    assert s["cumulative_low"] <= s["cumulative_base"] <= s["cumulative_high"]
