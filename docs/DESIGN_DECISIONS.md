# Design Decisions

Each entry: what, why, and what it costs. "Established" means a well-known technique; "Proposed" means my own design choice.

## Established building blocks

- **Black-box style rolling buffer.** Keep recent history so the seconds before an event are available.
- **Median / MAD for baseline.** Robust to spikes during warm-up. sigma = 1.4826 x MAD.
- **CUSUM change-point detection (Page, 1954).** Estimates when a shift began, not just that it happened.
- **Hash chains.** Each record commits to the previous one, so edits are detectable.

## Proposed design (mine)

### 1. Rank channels by *onset time*, then match the *order*
A threshold alarm only reports the last, loudest symptom. Ordering the onsets gives a cheap, explainable clue about propagation. Signatures store **order and direction only, no magnitudes**, because magnitudes vary by machine while sequences are more likely to carry over. *Cost:* onset estimates are noisy for fast faults (seconds apart), so ties within 4 s count as simultaneous, and sequence never proves cause.

### 2. Scoring formula
`score = coverage x precision x (0.6 x order + 0.4 x first_mover)`

Multiplying makes the score collapse when a signature is only partly matched. A weighted-sum variant I tried (0.35 coverage + 0.25 precision + 0.25 order + 0.15 first-mover) scored the simulated `mystery_heating` event at 0.73 against the bearing-wear signature, which would have been reported as a confident wrong answer. The multiplicative form gives 0.40, below the 0.55 confidence floor (checked on three seeds). The weights (0.6/0.4) and the floor are judgement calls, not fitted. Scores are **not probabilities**.

### 3. "Unknown pattern" is a first-class outcome
The simulator includes `mystery_heating`, deliberately absent from the signature library, to prove the analyser can decline. A diagnosis tool that always answers is worse than one that admits doubt.

### 4. Latching and rising-edge triggers
One long fault should be one incident. A channel stays latched until it is calm for 30 samples, and an incident opens only if nothing was latched. *Cost:* overlapping faults merge into one episode (documented limitation).

### 5. Store live z-scores with the raw values
The analysis uses the z-scores that were live at the time (using the baseline as it was then) instead of recomputing with a later baseline. This keeps the sealed record reproducible and matches what an operator would have seen.

### 6. CUSUM parameters `k=1.5`, `h=12`, warm-up 240
Textbook `k=0.5, h=8` fired on healthy simulated data because sensor noise is autocorrelated (AR(1)) and the baseline is estimated from a finite warm-up. I swept warm-up length and CUSUM settings on healthy simulated runs and chose values that gave no false onsets, then confirmed with the evaluation. *Cost:* tuned against **simulated** noise; real sensors will need re-tuning, and less sensitive settings delay onset estimates for weak drifts.

### 7. No machine learning
There is no real labelled failure data here. A trained model would learn the simulator's quirks and would be less explainable. The design leaves a clean seam (`analysis.py`) where a learned model could be compared against the rule-based one once real data exists.

### 8. Tamper-evident, not tamper-proof
A SHA-256 chain in SQLite is simple and verifiable offline. Anyone who can rewrite the whole file can rebuild it, so the honest label is "tamper-evident". Publishing the head hash elsewhere would strengthen it (future work).

### 9. `source` is sealed into every incident
Each incident records whether it came from `simulation`, `live` or `replay` so demo data can never be mistaken for real evidence later.

### 10. FastAPI + vanilla JS + SQLite
Zero build tooling and one `pip install` keep the project easy to clone and run. The dashboard uses canvas and no CDN, so it works offline and the CSP can be strict (`script-src 'self'`).

### 11. Polling instead of WebSockets
`GET /api/live?since=N` every 500 ms is simple, stateless and easy to test. *Cost:* slightly higher latency and overhead than a push channel.

### 12. Simulator inside the package
The simulator lives in `src/precursor/simulator/` (not a top-level `simulator/`) so the CLI, tests and evaluation can import it without path hacks.

### 13. Config in YAML, secrets in the environment
Detector settings, faults and signatures are reviewable data. The only secret (`PRECURSOR_API_KEY`) never appears in a file that can be committed.

## Alternatives considered

- **Isolation Forest / autoencoder for anomaly detection:** no real training data; less explainable.
- **Cross-correlation lag between channels:** ambiguous for slow ramps (all correlate at many lags); onset ordering was more robust.
- **Blockchain anchoring:** overkill for a portfolio prototype; noted as a future option.
