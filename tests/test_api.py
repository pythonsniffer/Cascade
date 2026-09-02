import pytest

"""REST + WebSocket surface (Backend Instructions §9)."""


def test_health_reports_models_and_provenance(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["models_loaded"] is True
    assert d["models"]["bottleneck"]["ensemble_size"] == 3
    p = d["provenance"]
    assert p["real"] and p["simulated"] and p["assumed"] and p["statement"]


def test_health_does_not_claim_detector_metrics_when_detector_absent(client):
    """Honesty: an unloaded detector must not be advertised as real."""
    d = client.get("/health").json()
    if not d["models"]["defect"]["detector_loaded"]:
        joined = " ".join(d["provenance"]["real"])
        assert "NOT LOADED" in joined
        assert "mAP50" not in joined


def test_line_topology_is_fixed_35_and_read_only(client):
    d = client.get("/line").json()
    assert d["n_stations"] == 35
    assert len(d["nodes"]) == 35
    kinds = {e["kind"] for e in d["edges"]}
    assert "bypass" in kinds and "rework" in kinds, "S13->S15 bypass / S20->S18 rework missing"
    assert any(e["source"] == 13 and e["target"] == 15 for e in d["edges"])
    assert any(e["source"] == 20 and e["target"] == 18 for e in d["edges"])


def test_no_topology_swap_route(client):
    """Context §3b explicitly forbids a topology-swap endpoint."""
    paths = client.app.openapi()["paths"]
    assert not any("topology" in p or "plant" in p for p in paths), paths.keys()
    assert "/line" in paths
    assert "post" not in paths["/line"]


def test_tick_produces_real_bottleneck_and_persists(client):
    for _ in range(4):                      # cross the warm-up window
        r = client.post("/control/tick")
        assert r.status_code == 200
    d = r.json()
    assert d["type"] == "tick"
    b = d["bottleneck"]
    assert b["confidence"] in ("high", "low")
    if b["confidence"] == "high":
        assert b["station"] is not None and 0 <= b["station"] < 35
        assert len(b["blk"]) == 35 and len(b["stv"]) == 35
    assert d["_meta"]["line_data"] == "SIMULATED"
    assert len(client.get("/twin/state?limit=5").json()["twin_states"]) > 0


def test_history_and_alerts(client):
    h = client.get("/history").json()
    assert len(h["shifts"]) > 0
    assert "pnl_series" in h and "zone_counts" in h
    assert "alerts" in client.get("/alerts").json()


def test_control_play_pause(client):
    assert client.post("/control/play", json={"interval_s": 0.1}).json()["playing"] is True
    assert client.post("/control/pause").json()["playing"] is False


def test_websocket_pushes_tick(client):
    with client.websocket_connect("/ws/live") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "status" and hello["state"] == "connected"
        client.post("/control/tick")
        for _ in range(4):
            msg = ws.receive_json()
            if msg["type"] == "tick":
                assert "twin_states" in msg and "pnl_delta" in msg and "_meta" in msg
                return
        raise AssertionError("no tick frame received over the websocket")


def test_reset_clears_session(client):
    client.post("/control/tick")
    assert client.post("/control/reset").json()["cumulative_net"] == 0.0
    assert client.get("/history").json()["shifts"] == []


def test_single_container_mode_serves_the_spa(tmp_path, monkeypatch):
    """With CASCADE_FRONTEND_DIST set, the app serves the dashboard and the API moves
    under /api — otherwise the root-level /pnl route would shadow the SPA's own /pnl
    and a reload would return JSON again."""
    import importlib

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Cascade</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setenv("CASCADE_FRONTEND_DIST", str(dist))

    import backend.main as main
    importlib.reload(main)
    try:
        from fastapi.testclient import TestClient
        with TestClient(main.app) as c:
            # SPA routes return the app, never the API payload of the same name
            for route in ("/", "/pnl", "/history", "/config"):
                r = c.get(route)
                assert r.status_code == 200, route
                assert "<!doctype html>" in r.text.lower(), f"{route} did not serve the SPA"
            # the API is still reachable, under /api
            assert c.get("/api/health").json()["models_loaded"] is True
            assert c.get("/healthz").json()["serving_frontend"] is True
            # a real static file is served as itself, not the fallback
            assert "console.log" in c.get("/assets/app.js").text
    finally:
        monkeypatch.delenv("CASCADE_FRONTEND_DIST", raising=False)
        importlib.reload(main)


def test_detector_frames_are_served(client, app_state):
    """The Quality gallery shows the real image behind each detection, so /frames must
    resolve — including in single-container mode, where a route registered after the
    SPA catch-all would be shadowed."""
    frames = app_state.df.sample_frames
    if not frames:
        pytest.skip("no frames in this instance")
    r = client.get(f"/frames/{frames[0].name}")
    assert r.status_code == 200
    assert len(r.content) > 100
    assert client.get("/frames/nope.png").status_code == 404
    # no path traversal out of the frames directory
    assert client.get("/frames/../../backend/main.py").status_code in (404, 400)
