import json
import sqlite3

from precursor.vault import GENESIS_HASH, Vault, canonical_json, verify_bundle


def payload(n=1):
    return {"trigger": {"t": 100.0 * n, "channel": "vibration_g", "z": 5.1},
            "analysis": {"verdict": {"label": "bearing_wear", "score": 0.9}},
            "t": [1.0, 2.0], "note": "°C ok"}


def test_append_assigns_sequential_ids_and_links_hashes():
    v = Vault(":memory:")
    a = v.append(payload(1))
    b = v.append(payload(2))
    assert a["payload"]["id"] == "INC-0001" and b["payload"]["id"] == "INC-0002"
    assert a["seal"]["prev_hash"] == GENESIS_HASH
    assert b["seal"]["prev_hash"] == a["seal"]["hash"]
    assert v.head_hash() == b["seal"]["hash"]
    assert v.verify().ok


def test_empty_vault_verifies():
    r = Vault(":memory:").verify()
    assert r.ok and r.count == 0


def test_get_roundtrip_matches_seal():
    v = Vault(":memory:")
    v.append(payload())
    bundle = v.get("INC-0001")
    assert verify_bundle(bundle) == (True, "payload matches its seal")
    assert v.get("INC-0404") is None


def test_modifying_a_payload_is_detected(tmp_path):
    path = tmp_path / "v.db"
    v = Vault(path)
    v.append(payload(1)); v.append(payload(2))
    raw = sqlite3.connect(path)
    body = json.loads(raw.execute("SELECT payload FROM incidents WHERE id='INC-0001'").fetchone()[0])
    body["trigger"]["z"] = 0.1                                  # quietly rewrite history
    raw.execute("UPDATE incidents SET payload=? WHERE id='INC-0001'", (canonical_json(body),))
    raw.commit()
    report = Vault(path).verify()
    assert not report.ok and report.broken_at == "INC-0001" and "modified" in report.reason


def test_deleting_an_incident_is_detected(tmp_path):
    path = tmp_path / "v.db"
    v = Vault(path)
    for n in (1, 2, 3):
        v.append(payload(n))
    raw = sqlite3.connect(path)
    raw.execute("DELETE FROM incidents WHERE id='INC-0002'")
    raw.commit()
    report = Vault(path).verify()
    assert not report.ok and report.broken_at == "INC-0003" and "chain link" in report.reason


def test_tampered_bundle_fails_offline_verification():
    v = Vault(":memory:")
    v.append(payload())
    bundle = v.get("INC-0001")
    bundle["payload"]["trigger"]["channel"] = "flow_lpm"
    ok, reason = verify_bundle(bundle)
    assert not ok and "modified" in reason
    assert verify_bundle({"nope": 1})[0] is False


def test_data_survives_reopening(tmp_path):
    path = tmp_path / "v.db"
    Vault(path).append(payload())
    again = Vault(path)
    assert [i["id"] for i in again.list()] == ["INC-0001"]
    assert again.verify().ok
