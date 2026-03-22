"""Config loader — reads config.toml with env var overrides.

Precedence (highest wins):
1. Environment variables (CONFLUENT_ENABLED, CONFLUENT_BOOTSTRAP_SERVERS, etc.)
2. config.toml values
3. Defaults
"""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

_DEFAULTS: dict = {
    "version": 1,
    "telemetry": {
        "dir": "data/telemetry",
        "confluent": {
            "enabled": False,
            "bootstrap_servers": "",
            "topic_prefix": "pokemon",
            "api_key_env": "CONFLUENT_API_KEY",
            "api_secret_env": "CONFLUENT_API_SECRET",
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively. Returns a new dict."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _is_truthy(val: str) -> bool:
    return val.lower() in ("1", "true", "yes")


def _apply_env_overrides(cfg: dict) -> dict:
    """Apply CONFLUENT_* env vars over config values."""
    confluent = cfg["telemetry"]["confluent"]
    if env := os.environ.get("CONFLUENT_ENABLED"):
        confluent["enabled"] = _is_truthy(env)
    if env := os.environ.get("CONFLUENT_BOOTSTRAP_SERVERS"):
        confluent["bootstrap_servers"] = env
    if env := os.environ.get("CONFLUENT_TOPIC_PREFIX"):
        confluent["topic_prefix"] = env
    # Direct credential env vars override the indirection pattern
    if os.environ.get("CONFLUENT_API_KEY"):
        confluent["api_key_env"] = "CONFLUENT_API_KEY"
    if os.environ.get("CONFLUENT_API_SECRET"):
        confluent["api_secret_env"] = "CONFLUENT_API_SECRET"
    return cfg


def load_config(config_path: Path | None = None) -> dict:
    """Load config from TOML file with env var overrides.

    If config_path is None or the file does not exist, returns defaults.
    """
    cfg = copy.deepcopy(_DEFAULTS)
    if config_path and config_path.is_file():
        with open(config_path, "rb") as f:
            toml_data = tomllib.load(f)
        cfg = _deep_merge(cfg, toml_data)
    return _apply_env_overrides(cfg)
