"""Post-incident analysis: *who moved first, and does the order look familiar?*

Two stages, both deliberately simple and explainable:

1. **Onset detection.** A two-sided CUSUM runs over each channel's z-score
   series and estimates when that channel started to leave its baseline.
2. **Signature matching.** The observed order of onsets is compared with the
   expected order of each known fault in ``config/signatures.yaml``.

The scoring weights below are design choices, not learned parameters.
Sequence evidence is not proof of causation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from .config import DetectionConfig, Signature
from .models import RawCapture


@dataclass
class Finding:
    channel: str
    direction: str       # "up" | "down"
    onset_t: float
    alarm_t: float
    lead_s: float        # trigger_t - onset_t (negative: moved after the trigger)
    peak_z: float
    clipped: bool        # onset is at the start of the window: began even earlier
    role: str            # "precursor" (onset before/at trigger) | "follower"


@dataclass
class Hypothesis:
    fault: str
    title: str
    score: float
    coverage: float
    precision: float
    order: float
    first_mover: float
    matched: list[str]
    missing: list[str]
    unexpected: list[str]
    summary: str
    checks: list[str]


@dataclass
class AnalysisResult:
    chain: list[Finding] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    verdict: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"chain": [asdict(f) for f in self.chain],
                "hypotheses": [asdict(h) for h in self.hypotheses],
                "verdict": self.verdict}


def cusum_onset(z: Sequence[float], k: float, h: float) -> Optional[tuple[int, int, int]]:
    """Two-sided CUSUM on a z-score series.

    Returns ``(onset_index, alarm_index, sign)`` for the first alarm, or None.
    ``onset_index`` is where the accumulating run that led to the alarm began,
    which is the standard CUSUM change-point estimate.
    """
    s_pos = s_neg = 0.0
    start_pos = start_neg = 0
    for i, value in enumerate(z):
        prev_pos, prev_neg = s_pos, s_neg
        s_pos = max(0.0, s_pos + value - k)
        s_neg = max(0.0, s_neg - value - k)
        if prev_pos == 0.0 and s_pos > 0.0:
            start_pos = i
        if prev_neg == 0.0 and s_neg > 0.0:
            start_neg = i
        if s_pos > h or s_neg > h:
            return (start_pos, i, 1) if s_pos >= s_neg else (start_neg, i, -1)
    return None


def find_onsets(capture: RawCapture, cfg: DetectionConfig) -> list[Finding]:
    """Locate the onset of every channel that deviated during the capture."""
    t = np.asarray(capture.t, dtype=float)
    findings: list[Finding] = []
    for name, z_list in capture.z.items():
        z = np.asarray(z_list, dtype=float)
        hit = cusum_onset(z, cfg.cusum_k, cfg.cusum_h)
        if hit is None:
            continue
        onset_i, alarm_i, sign = hit
        peak = float(z[np.argmax(np.abs(z))])
        findings.append(Finding(
            channel=name, direction="up" if sign > 0 else "down",
            onset_t=float(t[onset_i]), alarm_t=float(t[alarm_i]),
            lead_s=float(capture.trigger_t - t[onset_i]), peak_z=peak,
            clipped=onset_i == 0,
            role="precursor" if t[onset_i] <= capture.trigger_t else "follower"))
    findings.sort(key=lambda f: (f.onset_t, f.channel))
    return findings


def score_signature(findings: Sequence[Finding], sig: Signature,
                    tolerance_s: float) -> Hypothesis:
    """Compare the observed onset order with one signature.

    score = coverage * precision * (0.6 * order + 0.4 * first_mover)

    * coverage    - fraction of signature steps observed in the right direction
    * precision   - matched / (matched + unexpected channels that also moved)
    * order       - pairwise agreement with the expected order (ties count 0.5)
    * first_mover - 1 if the signature's first channel is among the earliest movers
    """
    observed = {f.channel: f for f in findings}
    matched_steps, missing = [], []
    for step in sig.sequence:
        f = observed.get(step.channel)
        if f is not None and f.direction == step.direction:
            matched_steps.append((step, f))
        else:
            missing.append(step.channel)
    matched_channels = {s.channel for s, _ in matched_steps}
    unexpected = [f"{f.channel}({f.direction})" for f in findings
                  if f.channel not in matched_channels]

    coverage = len(matched_steps) / len(sig.sequence)
    precision = len(matched_steps) / (len(matched_steps) + len(unexpected)) \
        if matched_steps else 0.0

    if len(matched_steps) >= 2:
        agree, pairs = 0.0, 0
        for i in range(len(matched_steps)):
            for j in range(i + 1, len(matched_steps)):
                a, b = matched_steps[i][1].onset_t, matched_steps[j][1].onset_t
                pairs += 1
                if a + tolerance_s < b:
                    agree += 1.0
                elif abs(a - b) <= tolerance_s:
                    agree += 0.5
        order = agree / pairs
    else:
        order = 0.5  # a single match says nothing about order

    first_mover = 0.0
    if findings:
        earliest = findings[0].onset_t
        group = {f.channel for f in findings if f.onset_t <= earliest + tolerance_s}
        first = sig.sequence[0]
        if first.channel in group and observed[first.channel].direction == first.direction:
            first_mover = 1.0

    score = coverage * precision * (0.6 * order + 0.4 * first_mover)
    return Hypothesis(
        fault=sig.name, title=sig.title, score=round(score, 3), coverage=round(coverage, 3),
        precision=round(precision, 3), order=round(order, 3), first_mover=first_mover,
        matched=[s.channel for s, _ in matched_steps], missing=missing,
        unexpected=unexpected, summary=sig.summary, checks=list(sig.checks))


def analyze_capture(capture: RawCapture, signatures: Mapping[str, Signature],
                    cfg: DetectionConfig) -> AnalysisResult:
    findings = find_onsets(capture, cfg)
    hypotheses = sorted((score_signature(findings, s, cfg.onset_tolerance_s)
                         for s in signatures.values()),
                        key=lambda h: (-h.score, h.fault))
    if not findings:
        verdict = {"label": "no_deviation", "score": 0.0, "confident": False,
                   "ambiguous_with": [], "first_mover": None}
        return AnalysisResult(findings, hypotheses, verdict)

    best = hypotheses[0] if hypotheses else None
    confident = bool(best and best.score >= cfg.min_confidence)
    ambiguous = [h.fault for h in hypotheses[1:]
                 if confident and best.score - h.score < cfg.ambiguity_margin
                 and h.score >= cfg.min_confidence]
    verdict = {"label": best.fault if confident else "unknown_pattern",
               "score": best.score if best else 0.0, "confident": confident,
               "ambiguous_with": ambiguous, "first_mover": findings[0].channel}
    return AnalysisResult(findings, hypotheses, verdict)
