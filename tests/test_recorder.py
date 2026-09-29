import math

import numpy as np

from precursor.models import Sample
from precursor.recorder import Recorder
from precursor.simulator import PumpRigSimulator

from conftest import run_scenario


def feed(recorder, samples):
    results = [recorder.push(s) for s in samples]
    return results


def test_warmup_learns_baseline_close_to_truth(settings):
    rec = Recorder(settings.channels, settings.detection)
    sim = PumpRigSimulator(settings, seed=3)
    feed(rec, sim.stream(settings.detection.warmup_samples))
    assert rec.ready
    for i, ch in enumerate(settings.channels):
        assert abs(rec.mean[i] - ch.nominal) < 3 * ch.noise_sd
        assert 0.4 * ch.noise_sd < rec.sigma[i] < 2.5 * ch.noise_sd


def test_phase_progression(settings):
    rec = Recorder(settings.channels, settings.detection)
    sim = PumpRigSimulator(settings, seed=3)
    first = rec.push(sim.step())
    assert first.phase == "warming_up" and first.z is None
    feed(rec, sim.stream(settings.detection.warmup_samples))
    assert rec.push(sim.step()).phase == "armed"


def test_healthy_machine_raises_no_incident(settings):
    svc = run_scenario(settings, fault=None, seed=11, length=5000)
    assert svc.vault.list() == []


def test_fault_opens_exactly_one_incident(settings):
    svc = run_scenario(settings, "bearing_wear", seed=5)
    incidents = svc.vault.list()
    assert len(incidents) == 1
    assert incidents[0]["trigger_channel"] == "vibration_g"
    assert incidents[0]["trigger_time"] > 400.0


def test_capture_window_holds_pre_and_post_roll(settings):
    svc = run_scenario(settings, "brownout", seed=2)
    p = svc.vault.get("INC-0001")["payload"]
    d = settings.detection
    assert p["window"]["start_t"] <= p["trigger"]["t"] - d.pre_roll_s + 1
    assert p["window"]["end_t"] >= p["trigger"]["t"] + d.post_roll_s - 1
    assert all(len(v) == len(p["t"]) for v in p["values"].values())


def test_latching_prevents_duplicate_incident_for_one_episode(settings):
    # One long fault should stay a single incident even though it keeps deviating.
    svc = run_scenario(settings, "clogged_intake", seed=4, length=1200)
    assert len(svc.vault.list()) == 1


def test_second_episode_after_recovery_opens_new_incident(settings):
    svc = PrecursorServiceFactory(settings)
    sim = PumpRigSimulator(settings, seed=9)
    sim.inject("brownout", at=300, duration_s=200)
    sim.inject("bearing_wear", at=1200)
    for s in sim.stream(2000):
        svc.ingest(s)
    verdicts = [i["verdict"] for i in reversed(svc.vault.list())]
    assert verdicts == ["brownout", "bearing_wear"]


def PrecursorServiceFactory(settings):
    from precursor.service import PrecursorService
    from precursor.vault import Vault
    return PrecursorService(settings, Vault(":memory:"))


def test_out_of_order_and_duplicate_timestamps_are_dropped(settings):
    rec = Recorder(settings.channels, settings.detection)
    ok = rec.push(Sample(10.0, {"vibration_g": 0.3}))
    dup = rec.push(Sample(10.0, {"vibration_g": 0.3}))
    back = rec.push(Sample(5.0, {"vibration_g": 0.3}))
    nan_t = rec.push(Sample(float("nan"), {"vibration_g": 0.3}))
    assert ok.accepted and not dup.accepted and not back.accepted and not nan_t.accepted
    assert rec.samples_dropped == 3


def test_empty_or_unknown_only_samples_are_dropped(settings):
    rec = Recorder(settings.channels, settings.detection)
    assert not rec.push(Sample(1.0, {})).accepted
    assert not rec.push(Sample(2.0, {"not_a_channel": 1.0})).accepted
    assert not rec.push(Sample(3.0, {"vibration_g": float("nan")})).accepted


def test_missing_readings_do_not_crash_and_are_reported(settings):
    from precursor.service import PrecursorService
    from precursor.vault import Vault
    svc = PrecursorService(settings, Vault(":memory:"))
    sim = PumpRigSimulator(settings, seed=6)
    sim.inject("bearing_wear", at=400)
    rng = np.random.default_rng(0)
    for s in sim.stream(1000):
        values = dict(s.values)
        if rng.random() < 0.05:
            values.pop("flow_lpm")                       # sensor dropout
        if rng.random() < 0.02:
            values["bearing_temp_c"] = float("nan")      # garbage reading
        svc.ingest(Sample(s.t, values))
    p = svc.vault.get("INC-0001")["payload"]
    assert p["data_quality"]["missing_samples"]["flow_lpm"] > 0
    assert p["analysis"]["verdict"]["label"] == "bearing_wear"
    assert all(math.isfinite(v) for col in p["values"].values() for v in col)


def test_channel_without_warmup_data_is_disabled(settings):
    rec = Recorder(settings.channels, settings.detection)
    sim = PumpRigSimulator(settings, seed=1)
    for s in sim.stream(settings.detection.warmup_samples):
        values = {k: v for k, v in s.values.items() if k != "flow_lpm"}
        rec.push(Sample(s.t, values))
    assert "flow_lpm" not in rec.baselines()


def test_ring_buffer_is_bounded(settings):
    rec = Recorder(settings.channels, settings.detection)
    sim = PumpRigSimulator(settings, seed=1)
    feed(rec, sim.stream(3000))
    assert rec.buffered_seconds <= settings.detection.ring_capacity_s + 1
