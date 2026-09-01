"""Config layer — 'nothing hardcoded' (Context §8.1) and fail-fast validation (§3)."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_hardcoded_domain_literals_in_backend():
    """Backend §12: nothing greps as a hardcoded cost, class list, threshold or model path."""
    banned = {
        "yolov8n.pt": "model path must come from model_config",
        "runs/mvtec_finetune": "model path must come from model_config",
        "cam_bodyshop_A": "camera map must come from mappings.json",
        "downtime_cost_per_min\":": "costs must come from pnl_config.json",
    }
    src = []
    for p in (ROOT / "backend").rglob("*.py"):
        src.append((p, p.read_text()))
    for needle, why in banned.items():
        for p, text in src:
            assert needle not in text, f"{p.relative_to(ROOT)} hardcodes '{needle}': {why}"


def test_station_count_is_not_written_as_a_literal_in_services():
    """The 35 must come from graph.pt/config, not be typed into service code."""
    for p in (ROOT / "backend" / "services").rglob("*.py"):
        text = p.read_text()
        for line in text.splitlines():
            if "35" in line and not line.strip().startswith("#") and "[35," not in line:
                assert "n_stations" in line or "N," in line, \
                    f"{p.name}: suspicious literal 35 -> {line.strip()}"


def test_hot_reload_picks_up_an_external_edit(app_state):
    s = app_state.settings
    original = json.loads((s.config_dir / "pnl_config.json").read_text())
    try:
        edited = {**original, "false_alarm_cost": 999.0}
        (s.config_dir / "pnl_config.json").write_text(json.dumps(edited))
        # mtime granularity: force a distinct value
        assert "pnl_config" in s.reload_if_changed() or s.pnl_value("false_alarm_cost") == 999.0
        assert s.pnl_value("false_alarm_cost") == 999.0
    finally:
        s.write("pnl_config", original)


def test_missing_pnl_field_is_reported_not_defaulted(app_state):
    s = app_state.settings
    original = dict(s.pnl)
    try:
        s.pnl = {k: v for k, v in original.items() if k != "false_alarm_cost"}
        assert "false_alarm_cost" in s.missing_pnl_fields()
        assert s.pnl_value("false_alarm_cost") is None
    finally:
        s.pnl = original


def test_zone_outside_range_raises(app_state):
    import pytest
    from backend.config.loader import ConfigError
    with pytest.raises(ConfigError):
        app_state.settings.zone_of(99)


def test_backend_refuses_to_start_without_artifacts(tmp_path):
    """§3: fail fast with a clear message rather than starting half-loaded."""
    env = {
        "PATH": "/usr/bin:/bin",
        "CASCADE_CONFIG_DIR": str(tmp_path / "cfg"),
        "CASCADE_DATA_DIR": str(tmp_path / "data"),
        "CASCADE_ARTIFACTS_DIR": str(tmp_path / "nonexistent-artifacts"),
    }
    r = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-c",
         "import sys;sys.path.insert(0,'.');"
         "from backend.config.loader import load_settings;load_settings()"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert "artifacts" in r.stderr.lower()
    assert "export_artifacts" in r.stderr


def test_metrics_come_from_artifacts_not_source(app_state):
    """Context §8.2: never fabricate a metric — they are read from metrics.json."""
    m = app_state.metrics
    assert m["bottleneck"]["source"] == "measured_at_export"
    assert m["detector"]["source"] == "notebook_validation_run"
    # the detector's numbers are attributed, not silently presented as ours
    assert "note" in m["detector"]
