import pytest

from precursor.simulator import PumpRigSimulator, RECOVERY_S


def test_same_seed_gives_identical_data(settings):
    a = list(PumpRigSimulator(settings, seed=5).stream(50))
    b = list(PumpRigSimulator(settings, seed=5).stream(50))
    c = list(PumpRigSimulator(settings, seed=6).stream(50))
    assert a == b and a != c


def test_timestamps_are_strictly_increasing(settings):
    ts = [s.t for s in PumpRigSimulator(settings, seed=1).stream(100)]
    assert all(b > a for a, b in zip(ts, ts[1:]))


def test_fault_reaches_expected_magnitude_then_recovers(settings):
    sim = PumpRigSimulator(settings, seed=2, jitter=0.0)
    sim.inject("bearing_wear", at=100, duration_s=500)
    samples = list(sim.stream(1000))
    vib = [s.values["vibration_g"] for s in samples]
    assert sum(vib[:90]) / 90 == pytest.approx(0.30, abs=0.02)
    assert sum(vib[400:500]) / 100 == pytest.approx(0.65, abs=0.05)       # +0.35 g at full effect
    assert sum(vib[-100:]) / 100 == pytest.approx(0.30, abs=0.02)          # recovered
    assert 100 + 500 + RECOVERY_S < 900


def test_lags_are_respected(settings):
    sim = PumpRigSimulator(settings, seed=2, jitter=0.0)
    sim.inject("bearing_wear", at=100, duration_s=600)
    s = list(sim.stream(400))
    temp_at_140 = s[140].values["bearing_temp_c"]      # lag 60 s: still ~baseline
    temp_at_300 = s[300].values["bearing_temp_c"]
    assert temp_at_140 < 49.0 and temp_at_300 > 52.0


def test_unknown_fault_and_bad_parameters(settings):
    sim = PumpRigSimulator(settings)
    with pytest.raises(KeyError):
        sim.inject("gremlins")
    with pytest.raises(ValueError):
        sim.inject("brownout", severity=0)


def test_values_never_negative(settings):
    sim = PumpRigSimulator(settings, seed=3)
    sim.inject("brownout", at=10, severity=3.0)
    assert all(v >= 0 for s in sim.stream(200) for v in s.values.values())
