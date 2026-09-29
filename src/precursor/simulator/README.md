# Simulator (`src/precursor/simulator/`)

**Simulation only.** A synthetic "pump rig" that lets anyone run the whole system
without hardware.

- Healthy behaviour: nominal value + AR(1) coloured noise per channel
  (values in `config/default.yaml`, `sim:` blocks).
- Faults: ramped per-channel offsets with lags, defined in `config/faults.yaml`.
  They are hand-written, physically *inspired* curves, not a validated model and not
  fitted to real data.
- `PumpRigSimulator.inject(fault, at=..., severity=..., duration_s=...)` schedules a
  fault; `jitter` randomises lags and magnitudes per run.
- Deterministic for a given seed, which the tests rely on.

The simulator and the diagnosis signatures (`config/signatures.yaml`) are written by
the same author, so results on simulated data measure internal consistency, not
real-world accuracy. See `docs/EVALUATION.md`.
