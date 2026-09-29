# Examples

| File | What it is |
|---|---|
| `data/bearing_wear.csv` | Simulated run (seed 7): healthy, then a bearing-wear fault at t=340 s |
| `data/mystery_heating.csv` | Simulated run whose fault is deliberately *not* in the signature library |
| `sample_incident_bundle.json` | A sealed evidence bundle exported from the bearing-wear demo |
| `curl_ingest.sh` | Push one reading to a server running in `--ingest` mode |
| `esp32/precursor_node/` | Example ESP32 sketch. **Not tested on hardware.** |

Try them

```bash
python -m precursor replay examples/data/bearing_wear.csv
python -m precursor replay examples/data/mystery_heating.csv
python -m precursor verify --file examples/sample_incident_bundle.json
```

Regenerate the data: `python -m precursor generate-data --fault bearing_wear --out examples/data/bearing_wear.csv`

CSV format for your own data: a header row with `t` (seconds, strictly increasing) plus
one column per channel name from `config/default.yaml`. Empty cells count as missing readings.
