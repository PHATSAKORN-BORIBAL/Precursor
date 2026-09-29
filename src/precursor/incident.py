"""Turn a ``RawCapture`` plus its analysis into a sealable incident payload."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone

from . import __version__
from .analysis import analyze_capture
from .config import Settings
from .models import RawCapture
from .narrative import build_narrative

SCHEMA_ID = "precursor.incident/1"


def build_incident_payload(capture: RawCapture, settings: Settings, source: str) -> dict:
    """``source`` is "simulation" or "live" and is stored in the sealed record so
    demo data can never be mistaken for real data later."""
    analysis = analyze_capture(capture, settings.signatures, settings.detection)
    result = analysis.to_dict()
    labels = {c.name: c.label for c in settings.channels}
    narrative = build_narrative({"t": capture.trigger_t, "channel": capture.trigger_channel,
                                 "z": capture.trigger_z},
                                result["chain"], result["verdict"], result["hypotheses"], labels)
    det_digest = hashlib.sha256(json.dumps(asdict(settings.detection), sort_keys=True)
                                .encode()).hexdigest()[:16]
    return {
        "schema": SCHEMA_ID,
        "machine": {"id": settings.machine_id, "name": settings.machine_name},
        "trigger": {"t": capture.trigger_t, "channel": capture.trigger_channel,
                    "z": capture.trigger_z},
        "window": {"start_t": capture.t[0], "end_t": capture.t[-1],
                   "pre_roll_s": settings.detection.pre_roll_s,
                   "post_roll_s": settings.detection.post_roll_s,
                   "sample_count": len(capture.t)},
        "channels": [{"name": c.name, "label": c.label, "unit": c.unit}
                     for c in settings.channels if c.name in capture.values],
        "baselines": capture.baselines,
        "t": capture.t, "values": capture.values, "z": capture.z,
        "data_quality": {"missing_samples": capture.missing,
                         "latched_at_capture_end": capture.latched},
        "analysis": result,
        "narrative": narrative,
        "provenance": {"software": f"precursor {__version__}", "source": source,
                       "detection_config_digest": det_digest},
        "sealed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
