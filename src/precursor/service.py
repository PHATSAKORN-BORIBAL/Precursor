"""Glue: recorder -> analysis -> vault, plus the live state the dashboard polls."""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from typing import Optional

from .config import Settings
from .incident import build_incident_payload
from .models import PushResult, Sample
from .recorder import Recorder
from .simulator import PumpRigSimulator, DEFAULT_DURATION_S, RECOVERY_S
from .vault import Vault

LIVE_BUFFER = 1800


class PrecursorService:
    def __init__(self, settings: Settings, vault: Vault, source: str = "simulation"):
        self.settings = settings
        self.vault = vault
        self.source = source            # "simulation" | "live"
        self.recorder = Recorder(settings.channels, settings.detection)
        self._lock = threading.RLock()
        self._live: deque = deque(maxlen=LIVE_BUFFER)
        self._seq = 0
        self._last: Optional[PushResult] = None
        self.incident_ids: list[str] = []

    def ingest(self, sample: Sample) -> tuple[PushResult, Optional[str]]:
        """Process one sample. Returns the recorder result and, if an incident
        was just sealed, its id."""
        with self._lock:
            result = self.recorder.push(sample)
            self._last = result
            incident_id = None
            if result.accepted:
                self._seq += 1
                self._live.append({"seq": self._seq, "t": sample.t,
                                   "values": {k: v for k, v in sample.values.items()
                                              if k in self.recorder.names},
                                   "z": result.z})
            if result.finished is not None:
                payload = build_incident_payload(result.finished, self.settings, self.source)
                bundle = self.vault.append(payload)
                incident_id = bundle["payload"]["id"]
                self.incident_ids.append(incident_id)
            return result, incident_id

    def live(self, since: int = 0, limit: int = 600) -> dict:
        with self._lock:
            items = [s for s in self._live if s["seq"] > since][-limit:]
            last = self._last
            state = {
                "phase": last.phase if last else "warming_up",
                "health": last.health if last else 100.0,
                "warmup_progress": last.warmup_progress if last else 0.0,
                "capture_progress": last.capture_progress if last else 0.0,
                "latched": last.latched if last else [],
                "buffered_s": round(self.recorder.buffered_seconds, 1),
                "ring_capacity_s": self.settings.detection.ring_capacity_s,
                "accepted": self.recorder.samples_accepted,
                "dropped": self.recorder.samples_dropped,
                "incidents": len(self.incident_ids),
                "baselines": self.recorder.baselines(),
                "capture_trigger_t": self.recorder.capture_trigger_t,
            }
            return {"seq": self._seq, "state": state, "samples": items}

    def close(self) -> None:
        self.vault.close()


class SimulatorRunner:
    """Feeds simulated samples into the service in a background thread."""

    def __init__(self, service: PrecursorService, speed: float, seed: int,
                 auto_faults: bool = True):
        self.service = service
        self.speed = speed
        self.auto_faults = auto_faults
        self.sim = PumpRigSimulator(service.settings, seed=seed)
        self._rng = random.Random(seed + 1)
        self._next_fault_t = service.settings.detection.warmup_samples + 90.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def inject(self, fault: str, severity: float = 1.0) -> dict:
        with self._lock:
            active = self.sim.inject(fault, severity=severity)
        return {"fault": fault, "start_t": active.start_t, "severity": severity}

    def _maybe_schedule(self) -> None:
        if not self.auto_faults or self.sim.active_faults or self.sim.t < self._next_fault_t:
            return
        names = list(self.service.settings.faults)
        weights = [0.5 if n == "mystery_heating" else 1.0 for n in names]
        fault = self._rng.choices(names, weights)[0]
        self.sim.inject(fault, severity=self._rng.uniform(0.85, 1.2))
        self._next_fault_t = (self.sim.t + DEFAULT_DURATION_S + RECOVERY_S
                              + self._rng.uniform(150, 300))

    def _loop(self) -> None:
        tick = 0.05
        carry = 0.0
        next_wake = time.monotonic()
        while not self._stop.is_set():
            carry += self.speed * tick
            n = int(carry)
            carry -= n
            for _ in range(n):
                with self._lock:
                    self._maybe_schedule()
                    sample = self.sim.step()
                self.service.ingest(sample)
            next_wake += tick
            delay = next_wake - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_wake = time.monotonic()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="precursor-sim", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
