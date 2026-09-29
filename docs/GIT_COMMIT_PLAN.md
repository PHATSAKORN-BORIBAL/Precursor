# Git Commit Plan

A clean history tells the story of the build. Suggested order (subjects are 50 characters or fewer):

| # | Commit message | Files |
|---|---|---|
| 1 | `Initial project structure` | `README.md` (stub), `LICENSE`, `.gitignore`, `.env.example`, `pyproject.toml`, `requirements*.txt` |
| 2 | `Add YAML config and loader` | `config/*.yaml`, `src/precursor/{__init__,config,models}.py`, `tests/test_config.py` |
| 3 | `Add recorder with ring buffer and trigger` | `recorder.py`, `tests/conftest.py`, `tests/test_recorder.py` |
| 4 | `Add pump rig simulator` | `src/precursor/simulator/`, `tests/test_simulator.py` |
| 5 | `Add CUSUM onset and signature analysis` | `analysis.py`, `tests/test_analysis.py` |
| 6 | `Add hash-chained incident vault` | `vault.py`, `tests/test_vault.py` |
| 7 | `Add incident builder and narrative` | `incident.py`, `narrative.py` |
| 8 | `Add service and simulator runner` | `service.py` |
| 9 | `Add FastAPI app with ingest and security` | `api.py`, `tests/test_api.py`, `SECURITY.md` |
| 10 | `Add CLI: demo, replay, verify, export` | `cli.py`, `__main__.py` |
| 11 | `Add live dashboard` | `app/index.html`, `app/static/style.css`, `app/static/app.js`, `app/README.md` |
| 12 | `Add incident replay view` | further `app.js` / `style.css` changes, if you split the work |
| 13 | `Add SVG report renderer` | `report.py`, `docs/assets/*.svg` |
| 14 | `Add synthetic evaluation harness` | `evaluation.py`, `tests/test_cli_report.py` |
| 15 | `Add sample data and ESP32 example` | `examples/` |
| 16 | `Add dashboard smoke test script` | `scripts/dashboard_smoke.js` |
| 17 | `Add architecture and design docs` | `docs/*.md` |
| 18 | `Write README and pitch` | `README.md`, `docs/PROJECT_PITCH.md`, `CONTRIBUTING.md` |

If you would rather commit once, use the single recommended first commit:

```
Add Precursor: machine flight recorder
```

Tips

- Make sure `python -m pytest` passes before each commit that adds code.
- Do not commit `.env`, `data/`, `*.db` or `node_modules/` (all are in `.gitignore`).
- Tag the first working release: `git tag v0.1.0`.
