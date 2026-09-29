import numpy as np

from precursor.analysis import Finding, analyze_capture, cusum_onset, score_signature
from precursor.models import RawCapture

from conftest import run_scenario


def ramp(n=400, start=150, slope=0.25, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, noise, n) if noise else np.zeros(n)
    z[start:] += np.minimum((np.arange(n - start)) * slope, 12)
    return z


def test_cusum_finds_onset_near_true_start():
    hit = cusum_onset(ramp(noise=0.3), k=1.5, h=12.0)
    assert hit is not None
    onset, alarm, sign = hit
    assert sign == 1 and 145 <= onset <= 175 and alarm > onset


def test_cusum_detects_downward_shift():
    hit = cusum_onset(-ramp(noise=0.3, seed=2), k=1.5, h=12.0)
    assert hit is not None and hit[2] == -1


def test_cusum_ignores_pure_noise():
    rng = np.random.default_rng(1)
    assert cusum_onset(rng.normal(0, 1, 500), k=1.5, h=12.0) is None


def finding(channel, direction, onset):
    return Finding(channel, direction, onset, onset + 5, 100 - onset, 8.0, False, "precursor")


def test_perfect_match_scores_one(settings):
    sig = settings.signatures["bearing_wear"]
    findings = [finding("vibration_g", "up", 0), finding("bearing_temp_c", "up", 60),
                finding("motor_current_a", "up", 120)]
    h = score_signature(findings, sig, tolerance_s=4)
    assert h.score == 1.0 and not h.missing and not h.unexpected


def test_wrong_direction_counts_as_unexpected_and_missing(settings):
    sig = settings.signatures["bearing_wear"]
    findings = [finding("vibration_g", "down", 0), finding("bearing_temp_c", "up", 60)]
    h = score_signature(findings, sig, 4)
    assert "vibration_g" in h.missing and "vibration_g(down)" in h.unexpected
    assert h.score < 0.55


def test_reversed_order_scores_lower(settings):
    sig = settings.signatures["bearing_wear"]
    good = [finding("vibration_g", "up", 0), finding("bearing_temp_c", "up", 60),
            finding("motor_current_a", "up", 120)]
    bad = [finding("motor_current_a", "up", 0), finding("bearing_temp_c", "up", 60),
           finding("vibration_g", "up", 120)]
    assert score_signature(bad, sig, 4).score < score_signature(good, sig, 4).score - 0.3


def test_simultaneous_onsets_count_as_ties(settings):
    sig = settings.signatures["bearing_wear"]
    findings = [finding("vibration_g", "up", 0), finding("bearing_temp_c", "up", 2),
                finding("motor_current_a", "up", 3)]
    h = score_signature(findings, sig, tolerance_s=4)
    assert h.order == 0.5


def test_unknown_pattern_is_not_forced_into_a_label(settings):
    svc = run_scenario(settings, "mystery_heating", seed=3)
    verdict = svc.vault.get("INC-0001")["payload"]["analysis"]["verdict"]
    assert verdict["label"] == "unknown_pattern" and not verdict["confident"]
    assert verdict["first_mover"] == "bearing_temp_c"


def test_no_deviation_result_when_nothing_moved(settings):
    n = 50
    cap = RawCapture(trigger_t=25.0, trigger_channel="vibration_g", trigger_z=5.0,
                     t=[float(i) for i in range(n)], values={"vibration_g": [0.3] * n},
                     z={"vibration_g": [0.0] * n}, baselines={"vibration_g": {"mean": 0.3, "sigma": 0.02}},
                     latched=[], missing={"vibration_g": 0})
    res = analyze_capture(cap, settings.signatures, settings.detection)
    assert res.verdict["label"] == "no_deviation" and res.chain == []


def test_each_known_fault_is_identified(settings):
    for fault in ("bearing_wear", "clogged_intake", "brownout", "discharge_blockage"):
        svc = run_scenario(settings, fault, seed=21)
        incidents = svc.vault.list()
        assert len(incidents) == 1, fault
        assert incidents[0]["verdict"] == fault, fault


def test_first_mover_matches_the_fault_definition(settings):
    expected = {"bearing_wear": "vibration_g", "clogged_intake": "flow_lpm",
                "brownout": "supply_voltage_v", "discharge_blockage": "discharge_pressure_kpa"}
    for fault, channel in expected.items():
        svc = run_scenario(settings, fault, seed=33)
        chain = svc.vault.get("INC-0001")["payload"]["analysis"]["chain"]
        assert chain[0]["channel"] == channel, fault
