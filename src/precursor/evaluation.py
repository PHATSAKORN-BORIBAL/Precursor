"""Synthetic self-check of the whole pipeline. SIMULATION ONLY.

The simulator (config/faults.yaml) and the signature library
(config/signatures.yaml) are written by the same author, so this measures
whether the pipeline is *internally consistent* under random noise, jitter and
severity changes. It says nothing about accuracy on real machines.
"""

from __future__ import annotations

import dataclasses
import random
import time
from dataclasses import dataclass, field

from .config import Settings
from .service import PrecursorService
from .simulator import PumpRigSimulator
from .vault import Vault

FAULT_START_T = 400.0
RUN_LENGTH = 1000
HEALTHY_LENGTH = 6000


@dataclass
class FaultStats:
    runs: int = 0
    one_incident: int = 0
    correct: int = 0
    latencies: list[float] = field(default_factory=list)


@dataclass
class EvaluationReport:
    per_fault: dict[str, FaultStats]
    healthy_runs: int
    healthy_seconds: int
    false_incidents: int
    throughput_sps: float

    def to_markdown(self) -> str:
        rows = ["| Injected fault | Runs | Exactly 1 incident | Correct verdict | Median trigger delay |",
                "|---|---:|---:|---:|---:|"]
        for name, s in self.per_fault.items():
            med = sorted(s.latencies)[len(s.latencies) // 2] if s.latencies else float("nan")
            rows.append(f"| {name} | {s.runs} | {s.one_incident}/{s.runs} | "
                        f"{s.correct}/{s.runs} | {med:.0f} s |")
        rows.append("")
        rows.append(f"Healthy runs: {self.healthy_runs} x {self.healthy_seconds} s of sample time, "
                    f"false incidents: {self.false_incidents}. "
                    f"Ingest throughput on this machine: ~{self.throughput_sps:,.0f} samples/s.")
        return "\n".join(rows)


def _expected_label(fault: str, settings: Settings) -> str:
    return fault if fault in settings.signatures else "unknown_pattern"


def evaluate(settings: Settings, runs: int = 30, seed: int = 1000,
             healthy_runs: int = 10, jitter: float = 0.2,
             noise_scale: float = 1.0) -> EvaluationReport:
    """``jitter`` randomises fault lags/magnitudes by +/- that fraction;
    ``noise_scale`` multiplies simulated sensor noise (detector settings are
    NOT re-tuned, which is the point of a stress run)."""
    if noise_scale != 1.0:
        noisy = tuple(dataclasses.replace(c, noise_sd=c.noise_sd * noise_scale)
                      for c in settings.channels)
        sim_settings = dataclasses.replace(settings, channels=noisy)
    else:
        sim_settings = settings
    rng = random.Random(seed)
    per_fault: dict[str, FaultStats] = {}
    total_samples, total_time = 0, 0.0

    for fault in settings.faults:
        stats = per_fault.setdefault(fault, FaultStats())
        for _ in range(runs):
            run_seed = rng.randrange(1_000_000)
            svc = PrecursorService(settings, Vault(":memory:"))
            sim = PumpRigSimulator(sim_settings, seed=run_seed, jitter=jitter)
            sim.inject(fault, at=FAULT_START_T, severity=rng.uniform(0.8, 1.25))
            started = time.perf_counter()
            for sample in sim.stream(RUN_LENGTH):
                svc.ingest(sample)
            total_time += time.perf_counter() - started
            total_samples += RUN_LENGTH
            incidents = svc.vault.list()
            stats.runs += 1
            if len(incidents) == 1:
                stats.one_incident += 1
                if incidents[0]["verdict"] == _expected_label(fault, settings):
                    stats.correct += 1
                stats.latencies.append(incidents[0]["trigger_time"] - FAULT_START_T)
            svc.close()

    false_incidents = 0
    for _ in range(healthy_runs):
        svc = PrecursorService(settings, Vault(":memory:"))
        sim = PumpRigSimulator(sim_settings, seed=rng.randrange(1_000_000), jitter=jitter)
        for sample in sim.stream(HEALTHY_LENGTH):
            svc.ingest(sample)
        false_incidents += len(svc.vault.list())
        svc.close()

    return EvaluationReport(per_fault, healthy_runs, HEALTHY_LENGTH, false_incidents,
                            total_samples / total_time if total_time else 0.0)
