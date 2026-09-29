"""Command-line interface: ``python -m precursor <command>``."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from .config import ConfigError, Settings, load_dotenv, load_settings
from .models import Sample
from .narrative import render_text_report
from .report import render_incident_svg
from .service import PrecursorService
from .simulator import PumpRigSimulator
from .vault import Vault, verify_bundle


# ---------------------------------------------------------------- commands

def cmd_demo(args, settings: Settings) -> int:
    """Headless demo: simulate one fault, print the sealed incident report."""
    if args.fault not in settings.faults:
        print(f"Unknown fault '{args.fault}'. Choose from: {', '.join(settings.faults)}",
              file=sys.stderr)
        return 2
    vault = Vault(args.db or ":memory:")
    service = PrecursorService(settings, vault, source="simulation")
    sim = PumpRigSimulator(settings, seed=args.seed)
    fault_at = settings.detection.warmup_samples + 100.0
    sim.inject(args.fault, at=fault_at, severity=args.severity)
    total = int(fault_at + 600)
    print(f"Simulating {total} s of a healthy machine, with '{args.fault}' injected at "
          f"t={fault_at:.0f} s (seed {args.seed}) ...\n")
    for sample in sim.stream(total):
        service.ingest(sample)
    incidents = vault.list()
    if not incidents:
        print("No incident was recorded.")
        return 1
    bundle = vault.get(incidents[0]["id"])
    print(render_text_report(bundle))
    print(f"\nChain check: {vault.verify().to_dict()}")
    if args.svg:
        Path(args.svg).write_text(render_incident_svg(bundle), encoding="utf-8")
        print(f"Wrote SVG report: {args.svg}")
    if args.export:
        Path(args.export).write_text(json.dumps(bundle, indent=1), encoding="utf-8")
        print(f"Wrote evidence bundle: {args.export}")
    return 0


def cmd_serve(args, settings: Settings) -> int:
    import uvicorn
    from .api import create_app

    server = settings.server
    changes = {}
    if args.host: changes["host"] = args.host
    if args.port: changes["port"] = args.port
    if args.db: changes["db_path"] = args.db
    if args.ingest: changes["mode"] = "ingest"
    if args.simulate: changes["mode"] = "simulate"
    if args.speed: changes["sim_speed"] = args.speed
    if args.seed is not None: changes["sim_seed"] = args.seed
    if args.no_auto_faults: changes["sim_auto_faults"] = False
    server = dataclasses.replace(server, **changes)
    settings = dataclasses.replace(settings, server=server)

    if args.reset_db and server.db_path != ":memory:":
        for suffix in ("", "-wal", "-shm"):
            Path(server.db_path + suffix).unlink(missing_ok=True)
    if server.host not in ("127.0.0.1", "localhost", "::1") and not server.api_key:
        print("WARNING: listening on a non-local address without PRECURSOR_API_KEY. "
              "Anyone who can reach this port can push data.", file=sys.stderr)
    print(f"Precursor dashboard: http://{server.host}:{server.port}  "
          f"(mode: {server.mode}{', x%g speed' % server.sim_speed if server.mode == 'simulate' else ''})")
    uvicorn.run(create_app(settings), host=server.host, port=server.port, log_level="warning")
    return 0


def _read_csv(path: Path, settings: Settings) -> list[Sample]:
    samples: list[Sample] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "t" not in reader.fieldnames:
            raise ValueError("CSV needs a header row with a 't' column (seconds)")
        known = set(settings.channel_names)
        for lineno, row in enumerate(reader, start=2):
            try:
                t = float(row["t"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"line {lineno}: bad 't' value {row.get('t')!r}") from exc
            values = {}
            for key, raw in row.items():
                if key in known and raw not in (None, ""):
                    try:
                        values[key] = float(raw)
                    except ValueError:
                        pass  # treated as a missing reading
            samples.append(Sample(t, values))
    return samples


def cmd_replay(args, settings: Settings) -> int:
    """Feed a CSV file through the recorder and print every incident found."""
    try:
        samples = _read_csv(Path(args.csv), settings)
    except (OSError, ValueError) as exc:
        print(f"Cannot read {args.csv}: {exc}", file=sys.stderr)
        return 2
    vault = Vault(args.db or ":memory:")
    service = PrecursorService(settings, vault, source="replay")
    for sample in samples:
        service.ingest(sample)
    found = vault.list()
    print(f"Replayed {len(samples)} samples, {len(found)} incident(s).")
    for item in reversed(found):
        print()
        print(render_text_report(vault.get(item["id"])))
    return 0


def cmd_generate(args, settings: Settings) -> int:
    """Write simulated data (a healthy run with one fault) to CSV."""
    if args.fault not in settings.faults:
        print(f"Unknown fault '{args.fault}'. Choose from: {', '.join(settings.faults)}",
              file=sys.stderr)
        return 2
    sim = PumpRigSimulator(settings, seed=args.seed)
    fault_at = settings.detection.warmup_samples + 100.0
    sim.inject(args.fault, at=fault_at)
    names = settings.channel_names
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["t", *names])
        for s in sim.stream(int(fault_at + 600)):
            writer.writerow([s.t, *(s.values[n] for n in names)])
    print(f"Wrote {out} (simulated, fault '{args.fault}' injected at t={fault_at:.0f} s)")
    return 0


def _open_vault(args) -> Optional[Vault]:
    path = args.db
    if path != ":memory:" and not Path(path).is_file():
        print(f"No database at {path}", file=sys.stderr)
        return None
    return Vault(path)


def cmd_verify(args, settings: Settings) -> int:
    if args.file:
        try:
            bundle = json.loads(Path(args.file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Cannot read bundle: {exc}", file=sys.stderr)
            return 2
        ok, reason = verify_bundle(bundle)
        print(("VALID: " if ok else "INVALID: ") + reason)
        return 0 if ok else 1
    vault = _open_vault(args)
    if vault is None:
        return 2
    report = vault.verify()
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.ok else 1


def cmd_export(args, settings: Settings) -> int:
    vault = _open_vault(args)
    if vault is None:
        return 2
    bundle = vault.get(args.incident_id)
    if bundle is None:
        print(f"No incident {args.incident_id}", file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(bundle, indent=1), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


def cmd_report(args, settings: Settings) -> int:
    vault = _open_vault(args)
    if vault is None:
        return 2
    bundle = vault.get(args.incident_id)
    if bundle is None:
        print(f"No incident {args.incident_id}", file=sys.stderr)
        return 2
    if args.svg:
        Path(args.svg).write_text(render_incident_svg(bundle), encoding="utf-8")
        print(f"Wrote {args.svg}")
    else:
        print(render_text_report(bundle))
    return 0


def cmd_evaluate(args, settings: Settings) -> int:
    from .evaluation import evaluate
    print(f"Running {args.runs} simulated runs per fault (seed {args.seed}) ...", flush=True)
    report = evaluate(settings, runs=args.runs, seed=args.seed, healthy_runs=args.healthy_runs,
                      jitter=args.jitter, noise_scale=args.noise_scale)
    print(report.to_markdown())
    return 0


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="precursor",
                                description="Precursor: a flight-data recorder for small machines.")
    p.add_argument("--config-dir", help="directory containing default.yaml (default: ./config)")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="headless demo: simulate a fault and print the report")
    d.add_argument("--fault", default="bearing_wear")
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--severity", type=float, default=1.0)
    d.add_argument("--db", help="store in this SQLite file instead of memory")
    d.add_argument("--svg", help="also write an SVG report to this path")
    d.add_argument("--export", help="also write the evidence bundle JSON to this path")
    d.set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", help="run the API and dashboard")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--simulate", action="store_true", help="use the built-in simulator")
    mode.add_argument("--ingest", action="store_true", help="accept data via POST /api/ingest")
    s.add_argument("--host"); s.add_argument("--port", type=int)
    s.add_argument("--db"); s.add_argument("--speed", type=float)
    s.add_argument("--seed", type=int)
    s.add_argument("--no-auto-faults", action="store_true",
                   help="simulator injects faults only when you click a button")
    s.add_argument("--reset-db", action="store_true", help="delete the database before starting")
    s.set_defaults(func=cmd_serve)

    r = sub.add_parser("replay", help="feed a CSV (t + channel columns) through the recorder")
    r.add_argument("csv"); r.add_argument("--db")
    r.set_defaults(func=cmd_replay)

    g = sub.add_parser("generate-data", help="write simulated data to CSV")
    g.add_argument("--fault", default="bearing_wear"); g.add_argument("--seed", type=int, default=7)
    g.add_argument("--out", default="examples/data/bearing_wear.csv")
    g.set_defaults(func=cmd_generate)

    v = sub.add_parser("verify", help="verify the incident chain, or one exported bundle")
    v.add_argument("--db", default="data/precursor.db"); v.add_argument("--file")
    v.set_defaults(func=cmd_verify)

    e = sub.add_parser("export", help="export one incident as an evidence bundle")
    e.add_argument("incident_id"); e.add_argument("--out", required=True)
    e.add_argument("--db", default="data/precursor.db")
    e.set_defaults(func=cmd_export)

    rp = sub.add_parser("report", help="print or render an incident report")
    rp.add_argument("incident_id"); rp.add_argument("--svg")
    rp.add_argument("--db", default="data/precursor.db")
    rp.set_defaults(func=cmd_report)

    ev = sub.add_parser("evaluate", help="synthetic self-check (simulation only)")
    ev.add_argument("--runs", type=int, default=30); ev.add_argument("--seed", type=int, default=1000)
    ev.add_argument("--healthy-runs", type=int, default=10)
    ev.add_argument("--jitter", type=float, default=0.2,
                    help="randomise fault lags/magnitudes by +/- this fraction")
    ev.add_argument("--noise-scale", type=float, default=1.0,
                    help="multiply simulated sensor noise (detector is not re-tuned)")
    ev.set_defaults(func=cmd_evaluate)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv(".env")
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config_dir)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        return args.func(args, settings)
    except BrokenPipeError:      # e.g. output piped into `head`
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
