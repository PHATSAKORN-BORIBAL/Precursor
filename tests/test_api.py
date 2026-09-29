import dataclasses

from fastapi.testclient import TestClient

from precursor.api import create_app
from precursor.simulator import PumpRigSimulator


def make_client(settings, mode="simulate", api_key="", tmp_path=None):
    server = dataclasses.replace(settings.server, mode=mode, api_key=api_key)
    cfg = dataclasses.replace(settings, server=server)
    app = create_app(cfg, start_simulator=False, db_path=":memory:")
    return TestClient(app), app


def feed_fault(app, settings, fault="bearing_wear"):
    sim = PumpRigSimulator(settings, seed=7)
    sim.inject(fault, at=400)
    for s in sim.stream(1000):
        app.state.service.ingest(s)


def test_health_config_and_security_headers(settings):
    client, _ = make_client(settings)
    assert client.get("/api/health").json()["status"] == "ok"
    cfg = client.get("/api/config").json()
    assert len(cfg["channels"]) == 6 and cfg["mode"] == "simulate" and cfg["faults"]
    r = client.get("/")
    assert r.status_code == 200 and "Precursor" in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_static_assets_served(settings):
    client, _ = make_client(settings)
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_live_endpoint_pages_by_sequence(settings):
    client, app = make_client(settings)
    sim = PumpRigSimulator(settings, seed=1)
    for s in sim.stream(50):
        app.state.service.ingest(s)
    first = client.get("/api/live?since=0&limit=10").json()
    assert first["seq"] == 50 and len(first["samples"]) == 10
    later = client.get("/api/live?since=45").json()
    assert [s["seq"] for s in later["samples"]] == [46, 47, 48, 49, 50]
    assert first["state"]["phase"] == "warming_up"
    assert client.get("/api/live?since=-1").status_code == 422


def test_incident_lifecycle_over_http(settings):
    client, app = make_client(settings)
    feed_fault(app, settings)
    listing = client.get("/api/incidents").json()["incidents"]
    assert len(listing) == 1 and listing[0]["verdict"] == "bearing_wear"
    detail = client.get("/api/incidents/INC-0001").json()
    assert detail["payload"]["provenance"]["source"] == "simulation"
    assert detail["seal"]["prev_hash"] == "0" * 64
    bundle = client.get("/api/incidents/INC-0001/bundle")
    assert "attachment" in bundle.headers["content-disposition"]
    assert bundle.json()["self_check"]["ok"] is True
    assert client.get("/api/vault/verify").json()["ok"] is True
    assert client.get("/api/incidents/INC-9999").status_code == 404


def test_ingest_disabled_in_simulate_mode(settings):
    client, _ = make_client(settings, mode="simulate")
    r = client.post("/api/ingest", json={"values": {"vibration_g": 0.3}})
    assert r.status_code == 409


def test_ingest_mode_accepts_single_and_batch(settings):
    client, app = make_client(settings, mode="ingest")
    assert app.state.service.source == "live"
    r = client.post("/api/ingest", json={"t": 1.0, "values": {"vibration_g": 0.3}})
    assert r.status_code == 200 and r.json()["accepted"] == 1
    batch = {"samples": [{"t": 2.0, "values": {"vibration_g": 0.3}},
                         {"t": 2.0, "values": {"vibration_g": 0.3}}]}   # duplicate time
    body = client.post("/api/ingest", json=batch).json()
    assert body["accepted"] == 1 and body["dropped"] == 1


def test_ingest_validation_errors(settings):
    client, _ = make_client(settings, mode="ingest")
    assert client.post("/api/ingest", json={"values": {}}).status_code == 422
    assert client.post("/api/ingest", json={"values": {"vibration_g": "abc"}}).status_code == 422
    assert client.post("/api/ingest", json={"samples": []}).status_code == 422
    assert client.post("/api/ingest", content=b"not json",
                       headers={"content-type": "application/json"}).status_code == 422


def test_ingest_requires_api_key_when_configured(settings):
    client, _ = make_client(settings, mode="ingest", api_key="test-key-not-real")
    body = {"values": {"vibration_g": 0.3}}
    assert client.post("/api/ingest", json=body).status_code == 401
    assert client.post("/api/ingest", json=body, headers={"X-API-Key": "wrong"}).status_code == 401
    ok = client.post("/api/ingest", json=body, headers={"X-API-Key": "test-key-not-real"})
    assert ok.status_code == 200
    # read-only endpoints stay open
    assert client.get("/api/incidents").status_code == 200


def test_live_ingest_end_to_end_seals_an_incident(settings):
    client, _ = make_client(settings, mode="ingest")
    sim = PumpRigSimulator(settings, seed=7)
    sim.inject("brownout", at=400)
    sealed = []
    for s in sim.stream(800):
        r = client.post("/api/ingest", json={"t": s.t, "values": dict(s.values)})
        sealed += r.json()["incidents_sealed"]
    assert sealed == ["INC-0001"]
    detail = client.get("/api/incidents/INC-0001").json()
    assert detail["payload"]["provenance"]["source"] == "live"
    assert detail["payload"]["analysis"]["verdict"]["label"] == "brownout"


def test_inject_endpoint(settings):
    client, app = make_client(settings)
    from precursor.service import SimulatorRunner
    assert isinstance(app.state.runner, SimulatorRunner)
    ok = client.post("/api/sim/inject", json={"fault": "brownout", "severity": 1.5})
    assert ok.status_code == 200 and ok.json()["fault"] == "brownout"
    assert client.post("/api/sim/inject", json={"fault": "nope"}).status_code == 422
    assert client.post("/api/sim/inject", json={"fault": "brownout", "severity": 0}).status_code == 422
    ing, _ = make_client(settings, mode="ingest")
    assert ing.post("/api/sim/inject", json={"fault": "brownout"}).status_code == 409


def test_runner_thread_produces_samples(settings):
    import time
    server = dataclasses.replace(settings.server, mode="simulate", sim_speed=400.0)
    app = create_app(dataclasses.replace(settings, server=server), start_simulator=False,
                     db_path=":memory:")
    runner = app.state.runner
    runner.start()
    try:
        time.sleep(0.6)
    finally:
        runner.stop()
    assert app.state.service.live()["seq"] > 50
