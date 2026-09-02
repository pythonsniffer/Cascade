"""Defect layer: detector -> events -> chain engine, and the honesty rules.

The FakeYOLO double exercises the code path. The running application never
substitutes it — without best.pt the layer emits nothing.
"""
import pandas as pd
import pytest

from conftest import FakeBox, FakeYOLO
from backend.services.defect import predict_chain
from backend.services.simulator import VehicleFrame


@pytest.fixture
def wired_detector(app_state, tmp_path):
    """Temporarily wire a test double + one frame into the loaded bundle."""
    svc = app_state.engine.defect
    bundle = svc.bundle
    frame = tmp_path / "frame_0.png"
    frame.write_bytes(b"not-a-real-png")
    saved = (bundle.yolo, bundle.yolo_loaded, list(bundle.sample_frames))
    classes = app_state.settings.visual_classes
    bundle.yolo = FakeYOLO([
        FakeBox(cls=classes.index("cut_lead"), conf=0.91, xyxy=[10.0, 12.0, 90.0, 88.0]),
        FakeBox(cls=classes.index("thread_top"), conf=0.44, xyxy=[5.0, 6.0, 40.0, 42.0]),
    ])
    bundle.yolo_loaded = True
    bundle.sample_frames = [frame]
    yield svc, frame
    bundle.yolo, bundle.yolo_loaded, bundle.sample_frames = saved


# ── honesty ──
def test_no_detector_means_no_events(app_state):
    """Architecture §9: no detection is not a zero-defect claim; it emits nothing."""
    svc = app_state.engine.defect
    if svc.bundle.yolo_loaded:
        pytest.skip("a real detector is loaded in this instance")
    assert svc.enabled is False
    v = VehicleFrame(vehicle_id=1, camera_id="cam_bodyshop_A", timestamp="t", frame_path=None)
    assert svc.detect(v) == []
    assert svc.status()["detector_loaded"] is False
    assert svc.status()["error"]


def test_empty_detection_emits_no_event(app_state, wired_detector):
    svc, frame = wired_detector
    svc.bundle.yolo = FakeYOLO([])          # detector ran, found nothing
    v = VehicleFrame(1, "cam_bodyshop_A", "2026-01-01T00:00:00Z", frame)
    assert svc.detect(v) == []


# ── event contract ──
def test_event_shape_matches_context_section_5(app_state, wired_detector):
    svc, frame = wired_detector
    v = VehicleFrame(7, "cam_paint_2", "2026-01-01T00:00:00Z", frame)
    events = svc.detect(v)
    assert len(events) == 2
    e = events[0]
    for k in ("vehicle_id", "station_id", "timestamp", "defect_class", "confidence",
              "bbox", "defect_type", "source", "camera_id"):
        assert k in e, f"defect event missing contract key {k}"
    assert e["source"] == "FINE_TUNED_YOLO"
    assert e["station_id"] == app_state.settings.camera_to_station["cam_paint_2"]
    assert e["station_source"] == "camera_map"
    assert len(e["bbox"]) == 4


def test_unknown_camera_is_flagged_simulated(app_state, wired_detector):
    svc, frame = wired_detector
    v = VehicleFrame(8, "cam_not_configured", "2026-01-01T00:00:00Z", frame)
    e = svc.detect(v)[0]
    assert e["station_id"] == app_state.settings.default_station
    assert e["station_source"] == "SIMULATED_default"


def test_visual_to_process_bridge_uses_config(app_state, wired_detector):
    svc, frame = wired_detector
    events = svc.detect(VehicleFrame(9, "cam_bodyshop_A", "t", frame))
    v2p = app_state.settings.visual_to_process
    assert events[0]["defect_type"] == v2p["cut_lead"] == "weld_gap"
    assert events[1]["defect_type"] == v2p["thread_top"] == "rattle"


# ── chain engine (a separate layer) ──
def test_chain_engine_recovers_planted_chains(app_state):
    learned = app_state.df.learned_chains
    pairs = set(zip(learned.trigger, learned.downstream))
    for a, b in [("weld_gap", "misalign"), ("paint_run", "seal_fail"), ("torque_low", "rattle")]:
        assert (a, b) in pairs, f"planted chain {a}->{b} not recovered"
    assert learned.lift.min() >= 1.2


def test_predict_chain_respects_min_lift(app_state):
    learned = app_state.df.learned_chains
    assert len(predict_chain("weld_gap", learned, 1.2)) >= 1
    assert len(predict_chain("weld_gap", learned, 99.0)) == 0


def test_chain_is_attached_downstream_of_detection(app_state, wired_detector):
    svc, frame = wired_detector
    events = svc.chain(svc.detect(VehicleFrame(11, "cam_bodyshop_A", "t", frame)))
    weld = next(e for e in events if e["defect_type"] == "weld_gap")
    assert weld["chains"], "weld_gap should chain to misalign"
    c = weld["chains"][0]
    assert c["predicted_downstream_defect"] == "misalign"
    assert c["lift"] >= app_state.settings.min_lift
    assert c["origin_station"] == weld["station_id"]


def test_chain_engine_is_separate_from_bstan(app_state):
    """Context §8.5: the layers must not be merged."""
    bstan_features = set(app_state.bn.features)
    visual = set(app_state.settings.visual_classes)
    process = set(app_state.settings.defect_types)
    assert not (bstan_features & visual), "YOLO classes must not become BSTAN features"
    assert not (bstan_features & process)


# ── integration join ──
def test_twin_state_joins_both_layers(app_state, wired_detector):
    svc, frame = wired_detector
    events = svc.chain(svc.detect(VehicleFrame(12, "cam_bodyshop_A", "t", frame)))
    alert = {"predicted_bottleneck_station": 18, "confidence": "high", "abstained": False}
    rec = app_state.engine.integration.build_twin_state(12, "t", alert, pd.DataFrame(events))
    assert rec["bottleneck_station"] == 18 and rec["bottleneck_zone"] == "paint"
    assert len(rec["visual_defects"]) == 2
    assert {v["defect_class"] for v in rec["visual_defects"]} == {"cut_lead", "thread_top"}
    assert rec["downstream_inspection_alerts"]
    assert rec["_meta"]["defect_source"] == "FINE_TUNED_YOLO"


def test_abstained_shift_yields_no_station(app_state):
    alert = {"predicted_bottleneck_station": None, "confidence": "low", "abstained": True}
    rec = app_state.engine.integration.build_twin_state(13, "t", alert, pd.DataFrame([]))
    assert rec["bottleneck_station"] is None
    assert rec["bottleneck_zone"] is None
    assert rec["bottleneck_abstained"] is True


def test_layer_state_distinguishes_no_detector_from_no_frames(app_state):
    """A loaded detector with nothing to look at is not the same as no detector."""
    st = app_state.engine.defect.status()
    assert st["state"] in ("ready", "no_frames", "no_detector")
    if st["detector_loaded"] and st["frames_available"] == 0:
        assert st["state"] == "no_frames"
        assert "no camera frames" in st["detail"].lower()
        assert st["enabled"] is False
    elif not st["detector_loaded"]:
        assert st["state"] == "no_detector"


def test_checkpoint_metrics_are_read_from_the_artifact(app_state):
    """Never typed into config — read from best.pt itself, or absent."""
    cm = app_state.df.checkpoint_metrics
    if not app_state.df.yolo_loaded:
        pytest.skip("no detector loaded in this instance")
    assert cm is not None, "a loaded detector should expose its recorded metrics"
    assert cm["source"] == "checkpoint_train_metrics"
    assert 0 < cm["mAP50"] <= 1


# ── the REAL detector, when one is present ───────────────────────────────
def test_real_detector_inference_path(app_state, tmp_path):
    """Drive the actual fine-tuned detector through detect() -> chain().

    Uses an arbitrary photograph purely to exercise the inference path: whatever
    the model outputs on an out-of-domain image is meaningless as a defect claim,
    so this asserts only that events are WELL-FORMED, never what they contain.
    This image is a test fixture and is never used as a demo frame.
    """
    from pathlib import Path as _P
    import ultralytics

    if not app_state.df.yolo_loaded:
        pytest.skip("no detector loaded in this instance")
    asset = _P(ultralytics.__file__).parent / "assets" / "bus.jpg"
    if not asset.exists():
        pytest.skip("no test image available")

    svc = app_state.engine.defect
    bundle = svc.bundle
    saved = list(bundle.sample_frames)
    bundle.sample_frames = [asset]
    try:
        events = svc.chain(svc.detect(
            VehicleFrame(901, "cam_bodyshop_A", "2026-01-01T00:00:00Z", asset)))
    finally:
        bundle.sample_frames = saved

    classes = set(app_state.settings.visual_classes)
    for e in events:
        assert e["source"] == "FINE_TUNED_YOLO"
        assert e["defect_class"] in classes, "detector emitted a class outside VISUAL_CLASSES"
        assert 0.0 <= e["confidence"] <= 1.0
        assert len(e["bbox"]) == 4 and e["bbox"][2] >= e["bbox"][0]
        assert e["station_id"] == app_state.settings.camera_to_station["cam_bodyshop_A"]
        assert isinstance(e["chains"], list)


def test_real_detector_is_not_coco(app_state):
    """Context: the detector must never silently fall back to COCO."""
    if not app_state.df.yolo_loaded:
        pytest.skip("no detector loaded in this instance")
    names = set(app_state.df.yolo.names.values())
    assert names == set(app_state.settings.visual_classes)
    assert "person" not in names and "car" not in names, "this is a COCO model"
