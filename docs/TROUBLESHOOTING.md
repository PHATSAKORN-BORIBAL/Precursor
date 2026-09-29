# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'precursor'` | Package not installed and `src/` not on the path | `pip install -e .` or run with `PYTHONPATH=src` |
| `Configuration error: Could not find config/default.yaml` | Running from a different directory | `cd` to the repo root or set `PRECURSOR_CONFIG_DIR` |
| Browser shows `{"detail":"Dashboard files not found..."}` | `app/` not found | Run from the repo root or set `PRECURSOR_APP_DIR` |
| `Address already in use` | Port 8000 taken | `python -m precursor serve --port 8001` |
| Dashboard says "Recorder unreachable" | Server stopped or wrong port | Check the terminal running `serve`; reload the page |
| Status stays on "Learning normal range" | Needs 240 samples (about 12 s at the default 20x) | Wait, or raise `--speed` |
| No incident appears | Auto faults happen a few simulated minutes in; or `--no-auto-faults` was used | Wait ~30 s, or click a button under **Inject a fault** |
| Inject buttons missing | Server is in `ingest` mode | Start with `--simulate` |
| `POST /api/ingest` returns 409 | Server is in `simulate` mode | Start with `--ingest` |
| `POST` returns 401 | `PRECURSOR_API_KEY` is set | Send `-H "X-API-Key: <value>"` |
| Ingest returns `"dropped": N` | Duplicate or decreasing `t`, empty values, or no known channel names | Omit `t` (server time is used) or send increasing values; check channel names against `config/default.yaml` |
| Real data never triggers | Signals inside normal noise, or the 240-sample warm-up is still running | Lower `z_trigger` cautiously; check that your channel names match; verify sample rate |
| Constant false incidents on real data | Sensor noise is not like the simulator's | Raise `min_sigma` for the channel, `cusum_h`, or `persist_samples`; re-run `evaluate` |
| `verify` says chain broken | A row was edited or deleted, or the DB mixes files | This is the tamper check working. Restore from backup, or start a fresh DB with `--reset-db` |
| `pytest` collects nothing or import errors | Wrong directory | Run `python -m pytest` from the repo root |
| Dashboard blank, console shows CSP errors | A proxy rewrote headers, or inline scripts were added | Keep scripts in `app/static/`; the CSP allows only same-origin scripts |
| Old incidents mixed into a new demo | Existing `data/precursor.db` reused | Add `--reset-db` |
| ESP32 cannot connect | Firewall, wrong IP, server on `127.0.0.1` | Start with `--host 0.0.0.0` **and** set `PRECURSOR_API_KEY`; the sketch is untested |

Still stuck? Run `python -m precursor demo`. If that works, the core is fine and the issue is in serving or configuration.
