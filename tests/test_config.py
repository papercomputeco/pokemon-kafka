"""Tests for config loader."""

from config import load_config


def test_load_config_defaults_when_no_file(tmp_path):
    """Returns defaults when config.toml does not exist."""
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg["telemetry"]["dir"] == "data/telemetry"
    assert cfg["telemetry"]["confluent"]["enabled"] is False
    assert cfg["telemetry"]["confluent"]["topic_prefix"] == "pokemon"


def test_load_config_parses_toml(tmp_path):
    """Parses config.toml and merges with defaults."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        "[telemetry.confluent]\n"
        "enabled = true\n"
        'bootstrap_servers = "pkc-test.us-east-1.aws.confluent.cloud:9092"\n'
        'topic_prefix = "myapp"\n'
    )
    cfg = load_config(toml_file)
    assert cfg["telemetry"]["confluent"]["enabled"] is True
    assert cfg["telemetry"]["confluent"]["bootstrap_servers"] == "pkc-test.us-east-1.aws.confluent.cloud:9092"
    assert cfg["telemetry"]["confluent"]["topic_prefix"] == "myapp"
    # Defaults still filled in
    assert cfg["telemetry"]["dir"] == "data/telemetry"
    assert cfg["telemetry"]["confluent"]["api_key_env"] == "CONFLUENT_API_KEY"


def test_load_config_env_overrides(tmp_path, monkeypatch):
    """Environment variables override TOML values."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('[telemetry.confluent]\nenabled = false\nbootstrap_servers = "from-toml:9092"\n')
    monkeypatch.setenv("CONFLUENT_ENABLED", "1")
    monkeypatch.setenv("CONFLUENT_BOOTSTRAP_SERVERS", "from-env:9092")
    monkeypatch.setenv("CONFLUENT_TOPIC_PREFIX", "override")

    cfg = load_config(toml_file)
    assert cfg["telemetry"]["confluent"]["enabled"] is True
    assert cfg["telemetry"]["confluent"]["bootstrap_servers"] == "from-env:9092"
    assert cfg["telemetry"]["confluent"]["topic_prefix"] == "override"


def test_load_config_enabled_falsy(monkeypatch):
    """CONFLUENT_ENABLED with non-truthy value stays disabled."""
    monkeypatch.setenv("CONFLUENT_ENABLED", "no")
    cfg = load_config(None)
    assert cfg["telemetry"]["confluent"]["enabled"] is False
