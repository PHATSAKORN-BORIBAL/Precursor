# Installation

Requires **Python 3.10+**. Nothing else is needed for simulation mode. Developed and tested with Python 3.12 on Linux.

## 1. Get the code

```bash
git clone https://github.com/<your-username>/precursor.git
cd precursor
```

## 2. Create a virtual environment and install

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Without editable install (run from the repo root):

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src python -m precursor demo        # Windows PowerShell: $env:PYTHONPATH="src"
```

## 3. Check it works

```bash
python -m pytest
python -m precursor demo
```

## 4. Optional configuration

```bash
cp .env.example .env      # then edit; .env is git-ignored
```

## 5. Start the dashboard

```bash
python -m precursor serve --simulate --reset-db
```

Open <http://127.0.0.1:8000>.

## Running from another directory

The app looks for `config/` and `app/` in the current directory, then next to the source tree. Otherwise set `PRECURSOR_CONFIG_DIR` and `PRECURSOR_APP_DIR`.

## Optional dev tool: dashboard smoke test

```bash
npm install jsdom            # in any scratch folder; node_modules is git-ignored
python -m precursor serve --simulate --speed 200 --port 8765 &
node scripts/dashboard_smoke.js http://127.0.0.1:8765
```
