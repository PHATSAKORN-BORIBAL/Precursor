#!/usr/bin/env bash
# Push one reading to a Precursor server started with:  python -m precursor serve --ingest
# Set PRECURSOR_API_KEY in your shell if the server was started with one.
set -euo pipefail
URL="${PRECURSOR_URL:-http://127.0.0.1:8000}"
KEY_HEADER=()
if [[ -n "${PRECURSOR_API_KEY:-}" ]]; then KEY_HEADER=(-H "X-API-Key: ${PRECURSOR_API_KEY}"); fi

curl -sS -X POST "${URL}/api/ingest" \
  -H "Content-Type: application/json" "${KEY_HEADER[@]}" \
  -d '{"values": {"motor_current_a": 4.21, "vibration_g": 0.31, "bearing_temp_c": 48.1,
                  "supply_voltage_v": 12.0, "flow_lpm": 6.0, "discharge_pressure_kpa": 179.6}}'
echo
