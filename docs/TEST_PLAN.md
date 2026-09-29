# Test Plan

Goal: show the pipeline behaves correctly and fails safely. All automated tests use simulated or hand-built data; nothing was tested on hardware.

## Run

```bash
python -m pytest                     # 63 tests, ~8 s
python -m precursor evaluate         # synthetic self-check, see EVALUATION.md
node scripts/dashboard_smoke.js http://127.0.0.1:8000   # optional, dev-only (needs jsdom)
```

## Automated tests

| File | Focus | Examples |
|---|---|---|
| `test_config.py` | Loading and validation | env overrides, invalid mode, unknown channel in signature, `.env` parsing without overriding real env |
| `test_recorder.py` | Baseline, trigger, windows | baseline near truth, no incident on 5000 s healthy data, exactly one incident per fault, pre/post-roll present, latching, second episode after recovery, duplicate / out-of-order / NaN samples dropped, missing readings, disabled channel, bounded ring buffer |
| `test_analysis.py` | Onsets and scoring | CUSUM onset near true start, downward shifts, pure noise ignored, perfect / reversed / tied order, wrong direction, unknown pattern not forced, `no_deviation`, every known fault identified, first mover matches fault definition |
| `test_simulator.py` | Determinism and physics-ish behaviour | same seed identical, increasing timestamps, magnitude / lag / recovery, bad parameters, no negative values |
| `test_vault.py` | Integrity | chained hashes, empty vault, modified payload detected, deleted incident detected, tampered bundle fails offline, persistence on reopen |
| `test_api.py` | HTTP behaviour | health / config / headers (CSP), static assets, live paging, incident lifecycle, ingest disabled in simulate, single + batch ingest, validation errors (422), API key (401 / 200), live end-to-end, inject endpoint, background runner thread |
| `test_cli_report.py` | CLI and reports | demo output and files, unknown fault, generate → replay round-trip, bad CSV, export / verify / tamper, report text and SVG, SVG escaping and well-formed XML, small evaluation |

## Manual demo checklist

- [ ] `python -m precursor demo` prints a ladder and "Chain check: ok True".
- [ ] `serve --simulate`: status goes learning → recording → triggered → sealed.
- [ ] Inject **Mystery heating**: verdict shows "Unknown pattern".
- [ ] Open an incident, drag the scrubber: cursor moves on all rows.
- [ ] **Verify chain** shows intact; after editing the SQLite file it reports the broken incident.
- [ ] `serve --ingest` + `examples/curl_ingest.sh`: returns `{"accepted":1,...}`.

## Dashboard smoke test

`scripts/dashboard_smoke.js` loads the real dashboard against a running simulate-mode server in jsdom (canvas stubbed) and checks 21 behaviours: lanes render, incident list fills, replay view builds, seal pill, scrubber and play, back to live, verify, inject, no JS errors. It does **not** check visual appearance.

## Not covered (be honest)

- Real hardware, real sensors, real machines. The ESP32 sketch is untested.
- Real-browser rendering, cross-browser behaviour, mobile layout, accessibility tools.
- Load testing and long-running soak tests (the sandbox measured ~11,000 samples/s once; this is not a benchmark).
- Security testing beyond the unit tests (no penetration test, no fuzzing).
- Accuracy on real faults. Evaluation is circular by construction (see EVALUATION.md).

## Coverage

Coverage was not measured with a tool. The list above reflects intent, not a percentage.
