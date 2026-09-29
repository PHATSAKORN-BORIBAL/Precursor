# Evaluation (simulation only)

## What this is and is not

`python -m precursor evaluate` injects each simulated fault many times with random noise seeds, random severity (0.8x to 1.25x), and random timing jitter, then checks that the pipeline (a) opens exactly one incident and (b) gives the right verdict. It also runs long healthy simulations to count false incidents.

**It is an internal consistency check, not an accuracy measurement.** The simulator (`config/faults.yaml`) and the diagnosis signatures (`config/signatures.yaml`) were written by the same person, so agreement is expected. Detector parameters were also tuned against the simulator's noise model. Nothing here says how the system would perform on a real machine.

## Results (measured)

Command: `python -m precursor evaluate --runs 30 --healthy-runs 10 --seed 1000`
Environment: development sandbox, Python 3.12, one run of the command.

| Injected fault | Runs | Exactly 1 incident | Correct verdict | Median trigger delay |
|---|---:|---:|---:|---:|
| bearing_wear | 30 | 30/30 | 30/30 | 34 s |
| clogged_intake | 30 | 30/30 | 30/30 | 14 s |
| brownout | 30 | 30/30 | 30/30 | 6 s |
| discharge_blockage | 30 | 30/30 | 30/30 | 6 s |
| mystery_heating | 30 | 30/30 | 30/30 | 7 s |

- "Correct verdict" for `mystery_heating` means `unknown_pattern`, because that fault has no signature.
- "Trigger delay" is sample-time seconds from fault start to the trigger.
- Healthy runs: 10 x 6000 s, **0 false incidents** (60,000 s total).

## Stress run (measured)

Command: `python -m precursor evaluate --runs 30 --healthy-runs 10 --seed 1000 --jitter 0.5 --noise-scale 1.8`

Fault lags and magnitudes vary by +/-50% and sensor noise is 1.8x larger, **without re-tuning the detector**.

| Injected fault | Exactly 1 incident | Correct verdict | Median trigger delay |
|---|---:|---:|---:|
| bearing_wear | 30/30 | 29/30 | 60 s |
| clogged_intake | 30/30 | 30/30 | 18 s |
| brownout | 30/30 | 30/30 | 6 s |
| discharge_blockage | 30/30 | 30/30 | 8 s |
| mystery_heating | 30/30 | 30/30 | 9 s |

Healthy: 0 false incidents. One bearing-wear run was mislabelled; I did not investigate that individual case.

## Throughput

The evaluation prints ingest throughput: about 11,000 samples/s (6 channels, includes analysis and an in-memory vault) on the development sandbox. This was a single measurement, not a benchmark.

## What would make this meaningful

1. Run the same pipeline on recorded real data with known failures (public run-to-failure datasets, or a real rig).
2. Write signatures from domain knowledge *before* looking at the data, then report hit rate honestly.
3. Report false-alarm rates on weeks of healthy real data.
