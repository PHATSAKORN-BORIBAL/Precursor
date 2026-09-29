import json
import xml.dom.minidom

from precursor.cli import main
from precursor.evaluation import evaluate
from precursor.report import render_incident_svg
from precursor.vault import verify_bundle

from conftest import run_scenario


def test_demo_prints_report_and_writes_files(tmp_path, capsys):
    svg, bundle = tmp_path / "r.svg", tmp_path / "b.json"
    code = main(["demo", "--fault", "brownout", "--svg", str(svg), "--export", str(bundle)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Verdict : brownout" in out and "Precursor ladder" in out and "Chain check" in out
    assert svg.stat().st_size < 60_000
    xml.dom.minidom.parseString(svg.read_text(encoding="utf-8"))       # well-formed XML
    assert verify_bundle(json.loads(bundle.read_text()))[0]


def test_demo_rejects_unknown_fault(capsys):
    assert main(["demo", "--fault", "gremlins"]) == 2
    assert "Unknown fault" in capsys.readouterr().err


def test_generate_replay_roundtrip(tmp_path, capsys):
    csv_path = tmp_path / "run.csv"
    assert main(["generate-data", "--fault", "clogged_intake", "--out", str(csv_path)]) == 0
    capsys.readouterr()
    assert main(["replay", str(csv_path)]) == 0
    out = capsys.readouterr().out
    assert "1 incident(s)" in out and "clogged_intake" in out


def test_replay_reports_bad_files(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("time,x\n1,2\n")
    assert main(["replay", str(bad)]) == 2
    assert "'t' column" in capsys.readouterr().err
    assert main(["replay", str(tmp_path / "missing.csv")]) == 2


def test_export_verify_and_tamper_detection(tmp_path, capsys):
    db, out = tmp_path / "v.db", tmp_path / "inc.json"
    assert main(["demo", "--fault", "bearing_wear", "--db", str(db)]) == 0
    assert main(["verify", "--db", str(db)]) == 0
    assert main(["export", "INC-0001", "--out", str(out), "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["verify", "--file", str(out)]) == 0
    data = json.loads(out.read_text())
    data["payload"]["trigger"]["z"] = 0.0
    out.write_text(json.dumps(data))
    assert main(["verify", "--file", str(out)]) == 1
    assert "INVALID" in capsys.readouterr().out
    assert main(["export", "INC-0099", "--out", str(out), "--db", str(db)]) == 2
    assert main(["verify", "--db", str(tmp_path / "none.db")]) == 2


def test_report_command_text_and_svg(tmp_path, capsys):
    db = tmp_path / "v.db"
    main(["demo", "--fault", "discharge_blockage", "--db", str(db)])
    capsys.readouterr()
    assert main(["report", "INC-0001", "--db", str(db)]) == 0
    assert "discharge_blockage" in capsys.readouterr().out
    svg = tmp_path / "x.svg"
    assert main(["report", "INC-0001", "--svg", str(svg), "--db", str(db)]) == 0
    assert svg.read_text().startswith("<svg")


def test_svg_escapes_text(settings):
    svc = run_scenario(settings, "bearing_wear", seed=7)
    bundle = svc.vault.get("INC-0001")
    bundle["payload"]["machine"]["name"] = "<script>x</script>"
    bundle["payload"]["channels"][0]["label"] = "A & <B>"
    svg = render_incident_svg(bundle)
    assert "<script>" not in svg
    xml.dom.minidom.parseString(svg)


def test_small_evaluation_run(settings):
    report = evaluate(settings, runs=2, healthy_runs=1, seed=5)
    assert set(report.per_fault) == set(settings.faults)
    assert report.false_incidents == 0
    assert "| bearing_wear |" in report.to_markdown()
