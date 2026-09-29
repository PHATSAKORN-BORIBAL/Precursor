# Project Pitch

How to present Precursor in a portfolio or interview. Wording is deliberately factual: it describes what the project is *designed to do* and what has actually been *demonstrated on simulated data*. Edit the "my contribution" parts to match what you personally did; nothing here invents experience for you.

## 30-second explanation

"Precursor is a flight-data recorder for small machines. It keeps a rolling buffer of sensor data, and when something goes wrong it seals the minutes *before* the fault and works out which sensor moved first: for example vibration, then temperature, then motor current. It matches that order against known fault patterns, says 'unknown' when nothing fits, and stores the evidence in a hash chain so edits are detectable. There is a replay dashboard and a built-in simulator, so you can try it without hardware."

## 1-minute explanation

"Threshold alarms tell you something is wrong, but by then the earliest clue has usually scrolled off the chart. Precursor is designed around the question *what happened just before?*

It learns each channel's normal range, triggers on a persistent excursion, and keeps recording through a post-roll. Then a CUSUM change-point detector estimates when each channel started to deviate, which gives a 'precursor ladder'. The order of that ladder is compared with hand-written fault signatures. If nothing matches well, it reports an unknown pattern instead of guessing. Each incident is sealed with a SHA-256 hash chained to the previous one, and can be exported and verified offline.

Everything runs on a simulated pump rig with five fault types; there is a live dashboard with time-travel replay. So far it has only been exercised on simulated data. The next step would be validating it on real recordings."

## Problem

Failures in small machines cascade. Alerts fire on the last symptom, and the early ones are lost, unlabelled, or editable in ordinary logs.

## Solution

Pre-trigger recording, onset-order analysis, explainable signature matching with an explicit unknown outcome, and tamper-evident evidence bundles, presented in a replay UI.

## My technical contribution (edit to reflect your own work)

- Designed the recording, trigger and latching logic (`recorder.py`).
- Implemented CUSUM onset detection and the signature scoring formula (`analysis.py`).
- Built the hash-chained vault and offline verification (`vault.py`).
- Built the FastAPI service and a dependency-free canvas dashboard with replay.
- Wrote the simulator, 63 automated tests and a synthetic evaluation harness.

## Main technologies

Python, NumPy, FastAPI, Pydantic, SQLite, SHA-256 hash chains, CUSUM change-point detection, robust statistics (median / MAD), vanilla JavaScript and Canvas, pytest, YAML configuration. Optional: ESP32 (example sketch, untested).

## Interesting technical challenge

**Making the change-point detector trustworthy.** With textbook CUSUM settings, the detector produced false onsets on *healthy* simulated data, because the simulated sensor noise is autocorrelated and the baseline comes from a finite warm-up. That would have corrupted the "who moved first" ranking. I swept warm-up length and CUSUM parameters on healthy data, picked settings with no false onsets, and then confirmed with the evaluation harness (0 false incidents in 60,000 s of healthy simulation). A second challenge was scoring: a weighted-sum score rated an unknown event 0.73 against a known pattern, so I switched to a multiplicative score (0.40 for the same event) and added an explicit "unknown pattern" outcome.

Be ready to say that these results are on simulated data and that the tuning was done against the same simulator.

## Honest talking points

- "Signatures and scoring are my own design, hand-written, not validated on real machines."
- "The evaluation is circular by construction; I documented that rather than hiding it."
- "The hash chain is tamper-evident, not tamper-proof. Anchoring the head hash externally is the obvious next step."

## Future development

Validate on real run-to-failure data, learn or refine signatures, add spectral triggers for vibration, multi-machine support, authentication for read endpoints, MQTT input, alert hooks, and exportable incident reports.

## Likely interview questions

- *Why not use ML?* No real labelled failures; explainability; a clear seam to add it later.
- *How do you avoid false positives?* Persistence, robust baselines, latching, tuned CUSUM; measured 0 false incidents on simulated healthy data, real data unknown.
- *What if two faults overlap?* They merge into one episode (known limitation).
- *How would you validate it?* Real recordings, signatures written before looking at data, false-alarm rate on weeks of healthy data.
