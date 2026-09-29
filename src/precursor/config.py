"""Configuration loading and validation.

Settings come from three YAML files (``default.yaml``, ``faults.yaml``,
``signatures.yaml``) plus a small set of ``PRECURSOR_*`` environment variables.
No secret is ever read from YAML; the optional API key comes from the
environment only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VALID_MODES = ("simulate", "ingest")
VALID_DIRECTIONS = ("up", "down")


class ConfigError(ValueError):
    """Raised when configuration is missing or inconsistent."""


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    label: str
    unit: str
    min_sigma: float
    nominal: float = 0.0   # simulator only
    noise_sd: float = 0.0  # simulator only


@dataclass(frozen=True)
class DetectionConfig:
    warmup_samples: int = 240
    z_trigger: float = 4.0
    persist_samples: int = 5
    z_clear: float = 2.0
    clear_samples: int = 30
    adapt_alpha: float = 0.002
    pre_roll_s: float = 300.0
    post_roll_s: float = 180.0
    ring_capacity_s: float = 900.0
    cusum_k: float = 1.5
    cusum_h: float = 12.0
    onset_tolerance_s: float = 4.0
    min_confidence: float = 0.55
    ambiguity_margin: float = 0.10

    def validate(self) -> None:
        positive = ("warmup_samples", "z_trigger", "persist_samples", "z_clear",
                    "clear_samples", "pre_roll_s", "post_roll_s", "cusum_h")
        for name in positive:
            if getattr(self, name) <= 0:
                raise ConfigError(f"detection.{name} must be > 0")
        if not 0 <= self.adapt_alpha < 1:
            raise ConfigError("detection.adapt_alpha must be in [0, 1)")
        if self.z_clear >= self.z_trigger:
            raise ConfigError("detection.z_clear must be smaller than z_trigger")
        if self.ring_capacity_s < self.pre_roll_s + self.post_roll_s + 30:
            raise ConfigError(
                "detection.ring_capacity_s must be >= pre_roll_s + post_roll_s + 30")
        if not 0 < self.min_confidence <= 1:
            raise ConfigError("detection.min_confidence must be in (0, 1]")


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "data/precursor.db"
    api_key: str = ""          # from environment only, never from YAML
    mode: str = "simulate"
    sim_speed: float = 20.0
    sim_seed: int = 42
    sim_auto_faults: bool = True


@dataclass(frozen=True)
class Effect:
    channel: str
    delta: float
    lag_s: float
    ramp_s: float


@dataclass(frozen=True)
class FaultSpec:
    name: str
    description: str
    effects: tuple[Effect, ...]


@dataclass(frozen=True)
class SignatureStep:
    channel: str
    direction: str


@dataclass(frozen=True)
class Signature:
    name: str
    title: str
    summary: str
    sequence: tuple[SignatureStep, ...]
    checks: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    machine_id: str
    machine_name: str
    channels: tuple[ChannelSpec, ...]
    detection: DetectionConfig
    server: ServerConfig
    faults: Mapping[str, FaultSpec]
    signatures: Mapping[str, Signature]
    config_dir: Path

    @property
    def channel_names(self) -> list[str]:
        return [c.name for c in self.channels]


# ---------------------------------------------------------------- helpers

def parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines. Supports comments and simple quoting."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            result[key] = value
    return result


def load_dotenv(path: str | Path = ".env", environ: Optional[dict] = None) -> bool:
    """Load a .env file into ``environ`` (default ``os.environ``) without
    overriding variables that are already set. Returns True if a file was read."""
    env = os.environ if environ is None else environ
    p = Path(path)
    if not p.is_file():
        return False
    for key, value in parse_dotenv(p.read_text(encoding="utf-8")).items():
        env.setdefault(key, value)
    return True


def resolve_config_dir(explicit: Optional[str | Path] = None,
                       environ: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if environ is None else environ
    candidates = [explicit, env.get("PRECURSOR_CONFIG_DIR"),
                  Path.cwd() / "config", REPO_ROOT / "config"]
    for cand in candidates:
        if cand and (Path(cand) / "default.yaml").is_file():
            return Path(cand)
    raise ConfigError("Could not find config/default.yaml. "
                      "Run from the repository root or set PRECURSOR_CONFIG_DIR.")


def resolve_app_dir(environ: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    env = os.environ if environ is None else environ
    for cand in (env.get("PRECURSOR_APP_DIR"), Path.cwd() / "app", REPO_ROOT / "app"):
        if cand and (Path(cand) / "index.html").is_file():
            return Path(cand)
    return None


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _build_channels(raw: list[Mapping[str, Any]]) -> tuple[ChannelSpec, ...]:
    channels = []
    for item in raw:
        try:
            sim = item.get("sim", {}) or {}
            channels.append(ChannelSpec(
                name=str(item["name"]), label=str(item.get("label", item["name"])),
                unit=str(item.get("unit", "")), min_sigma=float(item["min_sigma"]),
                nominal=float(sim.get("nominal", 0.0)),
                noise_sd=float(sim.get("noise_sd", 0.0))))
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid channel definition {item!r}: {exc}") from exc
    names = [c.name for c in channels]
    if not names:
        raise ConfigError("machine.channels must define at least one channel")
    if len(set(names)) != len(names):
        raise ConfigError("machine.channels contains duplicate names")
    return tuple(channels)


def _build_faults(raw: Mapping[str, Any], names: set[str]) -> dict[str, FaultSpec]:
    faults: dict[str, FaultSpec] = {}
    for name, body in (raw or {}).items():
        effects = []
        for e in body.get("effects", []):
            if e["channel"] not in names:
                raise ConfigError(f"Fault '{name}' uses unknown channel '{e['channel']}'")
            effects.append(Effect(e["channel"], float(e["delta"]),
                                  float(e.get("lag_s", 0)), float(e["ramp_s"])))
        if not effects:
            raise ConfigError(f"Fault '{name}' has no effects")
        faults[name] = FaultSpec(name, str(body.get("description", "")), tuple(effects))
    return faults


def _build_signatures(raw: Mapping[str, Any], names: set[str]) -> dict[str, Signature]:
    signatures: dict[str, Signature] = {}
    for name, body in (raw or {}).items():
        steps = []
        for s in body.get("sequence", []):
            if s["channel"] not in names:
                raise ConfigError(f"Signature '{name}' uses unknown channel '{s['channel']}'")
            if s["direction"] not in VALID_DIRECTIONS:
                raise ConfigError(f"Signature '{name}': direction must be up or down")
            steps.append(SignatureStep(s["channel"], s["direction"]))
        if len(steps) < 2:
            raise ConfigError(f"Signature '{name}' needs at least two steps")
        signatures[name] = Signature(name, str(body.get("title", name)),
                                     str(body.get("summary", "")), tuple(steps),
                                     tuple(str(c) for c in body.get("checks", [])))
    return signatures


def load_settings(config_dir: Optional[str | Path] = None,
                  environ: Optional[Mapping[str, str]] = None) -> Settings:
    """Load and validate all settings. ``PRECURSOR_*`` variables override YAML."""
    env = os.environ if environ is None else environ
    cdir = resolve_config_dir(config_dir, env)
    default = _read_yaml(cdir / "default.yaml")
    faults_raw = _read_yaml(cdir / "faults.yaml").get("faults", {})
    sigs_raw = _read_yaml(cdir / "signatures.yaml").get("signatures", {})

    machine = default.get("machine") or {}
    channels = _build_channels(machine.get("channels", []))
    names = {c.name for c in channels}

    try:
        detection = DetectionConfig(**(default.get("detection") or {}))
    except TypeError as exc:
        raise ConfigError(f"Unknown key in detection section: {exc}") from exc
    detection.validate()

    srv = dict(default.get("server") or {})
    overrides = {"host": "PRECURSOR_HOST", "port": "PRECURSOR_PORT",
                 "db_path": "PRECURSOR_DB_PATH", "mode": "PRECURSOR_MODE",
                 "sim_speed": "PRECURSOR_SIM_SPEED", "sim_seed": "PRECURSOR_SIM_SEED",
                 "sim_auto_faults": "PRECURSOR_SIM_AUTO_FAULTS"}
    for key, var in overrides.items():
        if env.get(var):
            srv[key] = env[var]
    try:
        server = ServerConfig(
            host=str(srv.get("host", "127.0.0.1")), port=int(srv.get("port", 8000)),
            db_path=str(srv.get("db_path", "data/precursor.db")),
            api_key=env.get("PRECURSOR_API_KEY", ""),
            mode=str(srv.get("mode", "simulate")),
            sim_speed=float(srv.get("sim_speed", 20)), sim_seed=int(srv.get("sim_seed", 42)),
            sim_auto_faults=_as_bool(srv.get("sim_auto_faults", True)))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid server setting: {exc}") from exc
    if server.mode not in VALID_MODES:
        raise ConfigError(f"server.mode must be one of {VALID_MODES}")
    if server.sim_speed <= 0:
        raise ConfigError("server.sim_speed must be > 0")

    return Settings(
        machine_id=str(machine.get("id", "machine-01")),
        machine_name=str(machine.get("name", "Machine")),
        channels=channels, detection=detection, server=server,
        faults=_build_faults(faults_raw, names),
        signatures=_build_signatures(sigs_raw, names), config_dir=cdir)
