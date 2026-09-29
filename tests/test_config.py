import dataclasses
import shutil

import pytest

from precursor.config import (ConfigError, DetectionConfig, load_dotenv, load_settings,
                              parse_dotenv)


def test_default_config_loads(settings):
    assert len(settings.channels) == 6
    assert settings.detection.z_trigger > settings.detection.z_clear
    assert set(settings.signatures) <= set(settings.faults)
    assert settings.server.api_key == ""          # secrets never come from YAML


def test_env_overrides(tmp_path):
    env = {"PRECURSOR_PORT": "9999", "PRECURSOR_MODE": "ingest", "PRECURSOR_API_KEY": "abc"}
    s = load_settings(environ=env)
    assert s.server.port == 9999 and s.server.mode == "ingest" and s.server.api_key == "abc"


def test_invalid_mode_rejected():
    with pytest.raises(ConfigError):
        load_settings(environ={"PRECURSOR_MODE": "banana"})


def test_bad_detection_values_rejected():
    with pytest.raises(ConfigError):
        dataclasses.replace(DetectionConfig(), z_clear=9.0).validate()
    with pytest.raises(ConfigError):
        dataclasses.replace(DetectionConfig(), ring_capacity_s=100).validate()


def test_unknown_channel_in_signature_rejected(tmp_path, settings):
    cfg = tmp_path / "config"
    shutil.copytree(settings.config_dir, cfg)
    text = (cfg / "signatures.yaml").read_text().replace("vibration_g", "no_such_channel", 1)
    (cfg / "signatures.yaml").write_text(text)
    with pytest.raises(ConfigError, match="unknown channel"):
        load_settings(cfg, environ={})


def test_missing_config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("precursor.config.REPO_ROOT", tmp_path)   # hide the real config/
    with pytest.raises(ConfigError, match="config/default.yaml"):
        load_settings(tmp_path / "nowhere", environ={})


def test_parse_dotenv_handles_comments_and_quotes():
    text = "# comment\nA=1\nB = \"two words\"\nC='x'  \nD=val # trailing\n\nBAD LINE\n"
    assert parse_dotenv(text) == {"A": "1", "B": "two words", "C": "x", "D": "val"}


def test_load_dotenv_does_not_override(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A=from_file\nB=new\n")
    env = {"A": "already"}
    assert load_dotenv(f, env) is True
    assert env == {"A": "already", "B": "new"}
    assert load_dotenv(tmp_path / "missing.env", env) is False
