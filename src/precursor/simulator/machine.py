"""A small synthetic machine ("pump rig") for demos and tests. SIMULATION ONLY.

Healthy behaviour is a nominal value plus AR(1) coloured noise per channel.
Faults add ramped offsets defined in ``config/faults.yaml``. The curves are
hand-written and physically *inspired*; they are not a validated physical model.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

from ..config import Effect, Settings
from ..models import Sample

RECOVERY_S = 60.0          # time for all effects to fade after the fault ends
DEFAULT_DURATION_S = 420.0


@dataclass
class ActiveFault:
    name: str
    start_t: float
    duration_s: float
    effects: list[Effect]    # already scaled / jittered for this run

    @property
    def end_t(self) -> float:
        return self.start_t + self.duration_s + RECOVERY_S


def _ease_out(x: float) -> float:
    """Fast start, gentle finish: 1 - (1 - x)^2 on [0, 1]."""
    x = min(1.0, max(0.0, x))
    return 1.0 - (1.0 - x) ** 2


class PumpRigSimulator:
    def __init__(self, settings: Settings, seed: int = 42, dt: float = 1.0,
                 start_t: float = 0.0, jitter: float = 0.1, phi: float = 0.5):
        self.settings = settings
        self.dt = dt
        self.jitter = jitter
        self._phi = phi
        self._rng = np.random.default_rng(seed)
        self._py_rng = random.Random(seed)
        self._chan = settings.channels
        self._noise = np.zeros(len(self._chan))
        self._t = start_t - dt
        self._faults: list[ActiveFault] = []

    # ------------------------------------------------------------ control

    @property
    def t(self) -> float:
        return self._t

    @property
    def active_faults(self) -> list[ActiveFault]:
        return [f for f in self._faults if f.end_t > self._t]

    def inject(self, fault: str, at: Optional[float] = None, severity: float = 1.0,
               duration_s: float = DEFAULT_DURATION_S) -> ActiveFault:
        """Schedule a fault. ``at`` defaults to the next sample."""
        spec = self.settings.faults.get(fault)
        if spec is None:
            raise KeyError(f"Unknown fault '{fault}'. Known: {sorted(self.settings.faults)}")
        if severity <= 0 or duration_s <= 0:
            raise ValueError("severity and duration_s must be > 0")
        start = self._t + self.dt if at is None else float(at)
        j = self.jitter
        effects = [Effect(e.channel,
                          e.delta * severity * (1 + self._py_rng.uniform(-j, j)),
                          max(0.0, e.lag_s * (1 + self._py_rng.uniform(-j, j))),
                          e.ramp_s) for e in spec.effects]
        active = ActiveFault(fault, start, duration_s, effects)
        self._faults.append(active)
        return active

    # ------------------------------------------------------------- output

    def _effect_offsets(self, t: float) -> dict[str, float]:
        offsets: dict[str, float] = {}
        for fault in self._faults:
            if t < fault.start_t or t > fault.end_t:
                continue
            fall = min(1.0, max(0.0, (t - (fault.start_t + fault.duration_s)) / RECOVERY_S))
            for e in fault.effects:
                rise = _ease_out((t - fault.start_t - e.lag_s) / e.ramp_s)
                offsets[e.channel] = offsets.get(e.channel, 0.0) + e.delta * rise * (1 - fall)
        return offsets

    def step(self) -> Sample:
        self._t += self.dt
        offsets = self._effect_offsets(self._t)
        eps = self._rng.standard_normal(len(self._chan))
        innovation = math.sqrt(1 - self._phi ** 2)
        values = {}
        for i, ch in enumerate(self._chan):
            self._noise[i] = self._phi * self._noise[i] + innovation * ch.noise_sd * eps[i]
            v = ch.nominal + self._noise[i] + offsets.get(ch.name, 0.0)
            if ch.unit in ("A", "g", "L/min", "kPa", "V"):
                v = max(0.0, v)
            values[ch.name] = round(v, 4)
        return Sample(round(self._t, 3), values)

    def stream(self, n: int) -> Iterator[Sample]:
        for _ in range(n):
            yield self.step()
