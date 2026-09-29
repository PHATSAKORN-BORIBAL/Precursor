# Contributing

Thanks for looking. This is a small, readable codebase; keep it that way.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest
```

## Ground rules

- **Tests first for behaviour changes.** `python -m pytest` must stay green.
- **Keep claims honest.** Anything measured only on simulated data must say so.
- **No secrets, no large files.** Do not commit `.env`, databases or data dumps.
- **Detection changes need evidence.** If you change `config/default.yaml` detector
  values, re-run `python -m precursor evaluate` and paste the table in your PR.
- **New fault or signature?** Add it to `config/faults.yaml` (simulation) and
  `config/signatures.yaml` (diagnosis) and add a test in `tests/test_analysis.py`.

## Commit style

Short imperative subject, 50 characters or fewer (see `docs/GIT_COMMIT_PLAN.md`).
