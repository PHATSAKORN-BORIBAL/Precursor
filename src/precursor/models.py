"""Plain data containers shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional


@dataclass(frozen=True)
class Sample:
    """One multi-channel reading. ``t`` is seconds (sample time, not wall time)."""
    t: float
    values: Mapping[str, float]


@dataclass
class RawCapture:
    """Everything the recorder hands to the analyser after post-roll ends."""
    trigger_t: float
    trigger_channel: str
    trigger_z: float
    t: list[float]
    values: dict[str, list[float]]
    z: dict[str, list[float]]
    baselines: dict[str, dict[str, float]]
    latched: list[str]
    missing: dict[str, int]


@dataclass
class PushResult:
    """What ``Recorder.push`` reports back for one sample."""
    accepted: bool
    phase: str                       # warming_up | armed | capturing | alarm
    health: float                    # 0..100, 100 = every channel near baseline
    warmup_progress: float           # 0..1
    capture_progress: float          # 0..1 while capturing, else 0
    z: Optional[dict[str, float]] = None
    latched: list[str] = field(default_factory=list)
    finished: Optional[RawCapture] = None
