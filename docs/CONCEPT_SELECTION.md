# Concept Selection

Before building, I brainstormed several ideas and scored them. The scores are **my own subjective 1-5 ratings**, meant to show the reasoning, not a measurement.

## Candidates

| # | Idea | One line |
|---|---|---|
| A | **Precursor** (chosen) | Flight recorder for machines: seals the seconds *before* a fault and ranks which sensor moved first |
| B | Acoustic fingerprint monitor | Learn a machine's normal sound from a phone mic and flag drift |
| C | Non-intrusive load monitor | Identify appliances from a single power signal |
| D | Wi-Fi signal room-presence sensor | Infer occupancy from RSSI fluctuations |
| E | Routine-drift tracker | Notice slow changes in a person's daily activity pattern |
| F | Sensor "digital twin" replay tool | Re-run recorded sensor sessions against changed alert rules |

## Scoring (1 = weak, 5 = strong)

| Criterion | A | B | C | D | E | F |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Originality of the *combination* | 4 | 3 | 2 | 2 | 3 | 3 |
| Technical depth | 4 | 4 | 4 | 3 | 3 | 3 |
| Real-world usefulness | 4 | 4 | 3 | 2 | 3 | 3 |
| Demo potential | 5 | 3 | 3 | 2 | 2 | 3 |
| Portfolio / GitHub value | 5 | 3 | 3 | 2 | 2 | 3 |
| Prototype without expensive hardware | 5 | 4 | 3 | 2 | 3 | 5 |
| **Total (of 30)** | **27** | 21 | 18 | 13 | 16 | 20 |

## Why A won

- **A clear story in one sentence** ("it keeps the seconds before the failure") and a distinctive visual (the precursor ladder).
- **Fully demoable offline**: a simulator can generate realistic-looking fault chains, and an honest "unknown pattern" case shows integrity.
- **Every technology has a job**: buffering and statistics for detection, CUSUM for timing, signatures for explanation, hash chain for evidence, API and UI for exploration.
- **B, C, D, E** need real recordings or hardware to be convincing, and some are already common tutorial projects. **F** is useful but visually less compelling.

## Honest note on originality

Event-triggered data loggers, condition monitoring, change-point detection and AIOps root-cause tools all exist. I am not claiming any single part is new. The proposed contribution is the specific combination and workflow described in [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md), packaged as a runnable, well-documented demo.
