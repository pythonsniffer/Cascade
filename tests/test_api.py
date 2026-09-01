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
