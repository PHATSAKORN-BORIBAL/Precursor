"""Tamper-evident incident storage.

Every sealed incident stores ``hash = SHA-256(prev_hash + canonical_json)``.
Editing, deleting or re-ordering a stored incident breaks the chain, and
``Vault.verify`` reports where. This is *tamper-evidence*, not tamper-proofing:
someone with write access to the whole database could rebuild the chain. See
``docs/DESIGN_DECISIONS.md`` for how to strengthen it (anchoring the head hash).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

GENESIS_HASH = "0" * 64
ALGO = "sha256"

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    id              TEXT UNIQUE NOT NULL,
    trigger_time    REAL NOT NULL,
    trigger_channel TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    score           REAL NOT NULL,
    prev_hash       TEXT NOT NULL,
    hash            TEXT NOT NULL,
    payload         TEXT NOT NULL
);
"""


def canonical_json(obj: Any) -> str:
    """Deterministic JSON used for hashing (sorted keys, no whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, payload_json: str) -> str:
    return hashlib.sha256((prev_hash + payload_json).encode("utf-8")).hexdigest()


def round_floats(obj: Any, digits: int = 4) -> Any:
    """Recursively round floats so stored JSON is compact and stable."""
    if isinstance(obj, float):
        return round(obj, digits)
    if isinstance(obj, dict):
        return {k: round_floats(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, digits) for v in obj]
    return obj


@dataclass
class ChainReport:
    ok: bool
    count: int
    head_hash: str
    broken_at: Optional[str] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "count": self.count, "head_hash": self.head_hash,
                "broken_at": self.broken_at, "reason": self.reason, "algo": ALGO}


def verify_bundle(bundle: dict) -> tuple[bool, str]:
    """Verify one exported evidence bundle in isolation (payload vs its own seal).

    This proves the payload was not altered after sealing; it cannot prove the
    bundle was not replaced *wholesale* by a re-sealed one (see module docs).
    """
    try:
        payload, seal = bundle["payload"], bundle["seal"]
        expected = compute_hash(seal["prev_hash"], canonical_json(payload))
    except (KeyError, TypeError) as exc:
        return False, f"malformed bundle: {exc}"
    if expected != seal.get("hash"):
        return False, "hash mismatch: payload was modified after sealing"
    return True, "payload matches its seal"


class Vault:
    """SQLite-backed hash-chained store. Thread-safe via an internal lock."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def head_hash(self) -> str:
        with self._lock:
            row = self._db.execute(
                "SELECT hash FROM incidents ORDER BY seq DESC LIMIT 1").fetchone()
        return row["hash"] if row else GENESIS_HASH

    def append(self, payload: dict) -> dict:
        """Assign an id, seal and store. Returns the full bundle."""
        with self._lock:
            row = self._db.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM incidents").fetchone()
            incident_id = f"INC-{row['n']:04d}"
            payload = round_floats({**payload, "id": incident_id})
            body = canonical_json(payload)
            prev = self.head_hash()
            digest = compute_hash(prev, body)
            analysis = payload.get("analysis", {}).get("verdict", {})
            self._db.execute(
                "INSERT INTO incidents (id, trigger_time, trigger_channel, verdict, score,"
                " prev_hash, hash, payload) VALUES (?,?,?,?,?,?,?,?)",
                (incident_id, payload["trigger"]["t"], payload["trigger"]["channel"],
                 analysis.get("label", "unknown"), float(analysis.get("score", 0.0)),
                 prev, digest, body))
            self._db.commit()
        return {"payload": payload, "seal": {"algo": ALGO, "prev_hash": prev, "hash": digest}}

    def list(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, trigger_time, trigger_channel, verdict, score, hash "
                "FROM incidents ORDER BY seq DESC").fetchall()
        return [dict(r) for r in rows]

    def get(self, incident_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        if row is None:
            return None
        return {"payload": json.loads(row["payload"]),
                "seal": {"algo": ALGO, "prev_hash": row["prev_hash"], "hash": row["hash"]}}

    def verify(self) -> ChainReport:
        """Recompute every hash and check the links end to end."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM incidents ORDER BY seq ASC").fetchall()
        prev = GENESIS_HASH
        for row in rows:
            if row["prev_hash"] != prev:
                return ChainReport(False, len(rows), self.head_hash(), row["id"],
                                   "chain link broken (an earlier incident was removed or reordered)")
            if compute_hash(row["prev_hash"], row["payload"]) != row["hash"]:
                return ChainReport(False, len(rows), self.head_hash(), row["id"],
                                   "payload does not match its hash (modified after sealing)")
            prev = row["hash"]
        return ChainReport(True, len(rows), prev)
