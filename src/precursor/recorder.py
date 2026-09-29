"""The black-box recorder core.

Responsibilities:

* learn a robust healthy baseline (median / MAD) from the first samples,
* keep a rolling ring buffer of raw values *and* the z-scores that were live
  when each sample arrived,
* watch for persistent excursions and open an incident (rising edge only),
* keep recording through the post-roll, then hand a ``RawCapture`` onward.

The recorder does no diagnosis; that is ``analysis.py``.
"""

from __future__ import annotations

import math
import warnings
from collections import deque
from typing import Optional, Sequence

import numpy as np

from .config import ChannelSpec, DetectionConfig
from .models import PushResult, RawCapture, Sample

MAD_TO_SIGMA = 1.4826  # converts median absolute deviation to a std-dev estimate


class Recorder:
    def __init__(self, channels: Sequence[ChannelSpec], cfg: DetectionConfig):
        self.channels = tuple(channels)
        self.cfg = cfg
        self.names = [c.name for c in self.channels]
        self._index = {n: i for i, n in enumerate(self.names)}
        n = len(self.names)
        self._min_sigma = np.array([c.min_sigma for c in self.channels], dtype=float)

        self.mean = np.full(n, np.nan)
        self.sigma = np.full(n, np.nan)
        self.ready = False

        self._warm_rows: list[np.ndarray] = []
        self._ring: deque = deque()          # (t, values[n], z[n])
        self._run = np.zeros(n, dtype=int)   # consecutive |z| > z_trigger
        self._latched = np.zeros(n, dtype=bool)
        self._calm = np.zeros(n, dtype=int)  # consecutive |z| < z_clear while latched
        self._capture: Optional[dict] = None
        self._last_t = -math.inf

        self.samples_accepted = 0
        self.samples_dropped = 0

    # ------------------------------------------------------------ public

    @property
    def capture_trigger_t(self) -> Optional[float]:
        return self._capture["trigger_t"] if self._capture else None

    def baselines(self) -> dict[str, dict[str, float]]:
        """Current learned baseline per usable channel (empty until warm-up ends)."""
        if not self.ready:
            return {}
        return {n: {"mean": round(float(self.mean[i]), 4), "sigma": round(float(self.sigma[i]), 4)}
                for i, n in enumerate(self.names) if self.mean[i] == self.mean[i]}

    @property
    def buffered_seconds(self) -> float:
        return (self._ring[-1][0] - self._ring[0][0]) if len(self._ring) > 1 else 0.0

    def push(self, sample: Sample) -> PushResult:
        """Feed one sample. Out-of-order, duplicate or empty samples are dropped."""
        t = float(sample.t)
        if not math.isfinite(t) or t <= self._last_t:
            self.samples_dropped += 1
            return self._result(False, None, None)
        row = self._row_from_sample(sample)
        if np.all(np.isnan(row)):
            self.samples_dropped += 1
            return self._result(False, None, None)

        self._last_t = t
        self.samples_accepted += 1
        finished = None

        if not self.ready:
            self._ring.append((t, row, np.full(len(row), np.nan)))
            self._warm_rows.append(row)
            if len(self._warm_rows) >= self.cfg.warmup_samples:
                self._finish_warmup()
            z = None
        else:
            z = (row - self.mean) / self.sigma
            self._adapt(row, z)
            self._ring.append((t, row, z))
            finished = self._update_alarms(t, z)

        while self._ring and self._ring[0][0] < t - self.cfg.ring_capacity_s:
            self._ring.popleft()
        return self._result(True, z, finished, t)

    # ----------------------------------------------------------- internals

    def _row_from_sample(self, sample: Sample) -> np.ndarray:
        row = np.full(len(self.names), np.nan)
        for name, value in sample.values.items():
            idx = self._index.get(name)
            if idx is None:
                continue
            try:
                f = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(f):
                row[idx] = f
        return row

    def _finish_warmup(self) -> None:
        data = np.vstack(self._warm_rows)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            med = np.nanmedian(data, axis=0)
            mad = np.nanmedian(np.abs(data - med), axis=0)
        enough = np.sum(~np.isnan(data), axis=0) >= 0.5 * len(data)
        sigma = np.maximum(mad * MAD_TO_SIGMA, self._min_sigma)
        self.mean = np.where(enough, med, np.nan)
        self.sigma = np.where(enough, sigma, np.nan)
        self.ready = True
        self._warm_rows = []
        # Back-fill z-scores for warm-up samples so early incidents have them.
        self._ring = deque((t, v, (v - self.mean) / self.sigma) for t, v, _ in self._ring)

    def _adapt(self, row: np.ndarray, z: np.ndarray) -> None:
        """Track slow drift, but never while a channel is excited or latched."""
        calm = np.isfinite(z) & (np.abs(z) < self.cfg.z_clear) & ~self._latched
        self.mean[calm] += self.cfg.adapt_alpha * (row[calm] - self.mean[calm])

    def _update_alarms(self, t: float, z: np.ndarray) -> Optional[RawCapture]:
        cfg = self.cfg
        finite = np.isfinite(z)
        exceed = finite & (np.abs(z) > cfg.z_trigger)
        self._run = np.where(exceed, self._run + 1, np.where(finite, 0, self._run))

        was_latched = bool(self._latched.any())
        newly = (self._run >= cfg.persist_samples) & ~self._latched

        calm_now = finite & (np.abs(z) < cfg.z_clear)
        self._calm = np.where(self._latched & calm_now, self._calm + 1,
                              np.where(self._latched & finite, 0, self._calm))
        release = self._latched & (self._calm >= cfg.clear_samples)
        self._latched[release] = False
        self._calm[release] = 0
        self._run[release] = 0
        self._latched |= newly

        # Open an incident only on the rising edge of the *episode*.
        if self._capture is None and newly.any() and not was_latched:
            idx = np.flatnonzero(newly)
            j = int(idx[np.argmax(np.abs(z[idx]))])
            self._capture = {"trigger_t": t, "channel": self.names[j], "z": float(z[j]),
                             "end_t": t + cfg.post_roll_s}

        if self._capture is not None and t >= self._capture["end_t"]:
            capture = self._build_capture()
            self._capture = None
            return capture
        return None

    def _build_capture(self) -> RawCapture:
        cap = self._capture or {}
        start_t = cap["trigger_t"] - self.cfg.pre_roll_s
        entries = [e for e in self._ring if e[0] >= start_t]
        ts = [e[0] for e in entries]
        values = np.vstack([e[1] for e in entries])
        zs = np.vstack([e[2] for e in entries])

        out_values: dict[str, list[float]] = {}
        out_z: dict[str, list[float]] = {}
        baselines: dict[str, dict[str, float]] = {}
        missing: dict[str, int] = {}
        for i, name in enumerate(self.names):
            if not np.isfinite(self.mean[i]):
                continue  # channel never produced usable warm-up data
            col = values[:, i].copy()
            missing[name] = int(np.isnan(col).sum())
            last = float(self.mean[i])
            for k in range(len(col)):        # forward-fill gaps
                if np.isnan(col[k]):
                    col[k] = last
                else:
                    last = col[k]
            out_values[name] = col.tolist()
            out_z[name] = np.nan_to_num(zs[:, i], nan=0.0).tolist()
            baselines[name] = {"mean": float(self.mean[i]), "sigma": float(self.sigma[i])}
        return RawCapture(
            trigger_t=cap["trigger_t"], trigger_channel=cap["channel"], trigger_z=cap["z"],
            t=ts, values=out_values, z=out_z, baselines=baselines,
            latched=[self.names[i] for i in np.flatnonzero(self._latched)],
            missing=missing)

    def _result(self, accepted: bool, z: Optional[np.ndarray],
                finished: Optional[RawCapture], t: float = 0.0) -> PushResult:
        cfg = self.cfg
        if not self.ready:
            phase = "warming_up"
        elif self._capture is not None:
            phase = "capturing"
        elif self._latched.any():
            phase = "alarm"
        else:
            phase = "armed"
        health = 100.0
        z_map = None
        if z is not None:
            finite = np.abs(z[np.isfinite(z)])
            worst = float(finite.max()) if finite.size else 0.0
            if worst > cfg.z_clear:
                health = float(np.clip(100.0 * (1.0 - (worst - cfg.z_clear) / 10.0), 0, 100))
            z_map = {n: (round(float(v), 2) if math.isfinite(v) else 0.0)
                     for n, v in zip(self.names, z)}
        progress = 0.0
        if self._capture is not None:
            progress = float(np.clip((t - self._capture["trigger_t"]) / cfg.post_roll_s, 0, 1))
        return PushResult(
            accepted=accepted, phase=phase, health=round(health, 1),
            warmup_progress=min(1.0, self.samples_accepted / cfg.warmup_samples)
            if not self.ready else 1.0,
            capture_progress=progress, z=z_map,
            latched=[self.names[i] for i in np.flatnonzero(self._latched)],
            finished=finished)
