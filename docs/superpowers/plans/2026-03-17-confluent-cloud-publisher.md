# Confluent Cloud Publisher Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Confluent Cloud as an additive telemetry publisher alongside the existing JSONL backend, configurable through `config.toml`.

**Architecture:** Dual-publisher fan-out pattern. A new `FanoutPublisher` wraps both `JSONLPublisher` (always active) and `ConfluentPublisher` (opt-in via config). Config is loaded from a project-root `config.toml` with env var overrides. The `confluent-kafka` package is an optional dependency — the project works identically without it.

**Tech Stack:** Python 3.11+, `tomllib` (stdlib), `confluent-kafka` (optional), existing `Publisher` protocol.

**Spec:** `docs/superpowers/specs/2026-03-17-confluent-cloud-publisher-design.md`

---

### Task 1: Config loader (`scripts/config.py`)

**Files:**
- Create: `scripts/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test — defaults when no file exists**

```python
# tests/test_config.py
"""Tests for config loader."""

from pathlib import Path

from config import load_config


def test_load_config_defaults_when_no_file(tmp_path):
    """Returns defaults when config.toml does not exist."""
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg["telemetry"]["dir"] == "data/telemetry"
    assert cfg["telemetry"]["confluent"]["enabled"] is False
    assert cfg["telemetry"]["confluent"]["topic_prefix"] == "pokemon"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_load_config_defaults_when_no_file -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/config.py
"""Config loader — reads config.toml with env var overrides.

Precedence (highest wins):
1. Environment variables (CONFLUENT_ENABLED, CONFLUENT_BOOTSTRAP_SERVERS, etc.)
2. config.toml values
3. Defaults
"""

from __future__ import annotations

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
    import copy

    cfg = copy.deepcopy(_DEFAULTS)
    if config_path and config_path.is_file():
        with open(config_path, "rb") as f:
            toml_data = tomllib.load(f)
        cfg = _deep_merge(cfg, toml_data)
    return _apply_env_overrides(cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_load_config_defaults_when_no_file -v`
Expected: PASS

- [ ] **Step 5: Write failing test — TOML parsing**

```python
def test_load_config_parses_toml(tmp_path):
    """Parses config.toml and merges with defaults."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        '[telemetry.confluent]\n'
        'enabled = true\n'
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
```

- [ ] **Step 6: Run test to verify it passes** (implementation already handles this)

Run: `uv run pytest tests/test_config.py::test_load_config_parses_toml -v`
Expected: PASS

- [ ] **Step 7: Write failing test — env var overrides**

```python
def test_load_config_env_overrides(tmp_path, monkeypatch):
    """Environment variables override TOML values."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        '[telemetry.confluent]\n'
        'enabled = false\n'
        'bootstrap_servers = "from-toml:9092"\n'
    )
    monkeypatch.setenv("CONFLUENT_ENABLED", "1")
    monkeypatch.setenv("CONFLUENT_BOOTSTRAP_SERVERS", "from-env:9092")
    monkeypatch.setenv("CONFLUENT_TOPIC_PREFIX", "override")

    cfg = load_config(toml_file)
    assert cfg["telemetry"]["confluent"]["enabled"] is True
    assert cfg["telemetry"]["confluent"]["bootstrap_servers"] == "from-env:9092"
    assert cfg["telemetry"]["confluent"]["topic_prefix"] == "override"
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_load_config_env_overrides -v`
Expected: PASS

- [ ] **Step 9: Write failing test — CONFLUENT_ENABLED falsy values**

```python
def test_load_config_enabled_falsy(monkeypatch):
    """CONFLUENT_ENABLED with non-truthy value stays disabled."""
    monkeypatch.setenv("CONFLUENT_ENABLED", "no")
    cfg = load_config(None)
    assert cfg["telemetry"]["confluent"]["enabled"] is False
```

- [ ] **Step 10: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_load_config_enabled_falsy -v`
Expected: PASS

- [ ] **Step 11: Lint and commit**

```bash
uv run ruff check scripts/config.py tests/test_config.py
uv run ruff format --check scripts/config.py tests/test_config.py
git add scripts/config.py tests/test_config.py
git commit -m "feat: add config loader with TOML + env var support"
```

---

### Task 2: FanoutPublisher (`scripts/publisher.py`)

**Files:**
- Modify: `scripts/publisher.py:61-75`
- Test: `tests/test_publisher.py`

- [ ] **Step 1: Write failing test — FanoutPublisher distributes events**

Add to `tests/test_publisher.py`:

```python
def test_fanout_publisher_distributes_events():
    """FanoutPublisher sends each event to all inner publishers."""
    from publisher import FanoutPublisher

    events_a, events_b = [], []

    class RecorderA:
        def publish(self, event):
            events_a.append(event)
        def close(self):
            pass

    class RecorderB:
        def publish(self, event):
            events_b.append(event)
        def close(self):
            pass

    pub = FanoutPublisher([RecorderA(), RecorderB()])
    pub.publish({"type": "test", "n": 1})
    pub.publish({"type": "test", "n": 2})
    pub.close()

    assert len(events_a) == 2
    assert len(events_b) == 2
    assert events_a[0]["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publisher.py::test_fanout_publisher_distributes_events -v`
Expected: FAIL — `ImportError: cannot import name 'FanoutPublisher'`

- [ ] **Step 3: Write FanoutPublisher implementation**

Add to `scripts/publisher.py` after `NoopPublisher`:

```python
class FanoutPublisher:
    """Publishes events to multiple backends. One failing does not stop others."""

    def __init__(self, publishers: list[Publisher]):
        self._publishers = list(publishers)

    def publish(self, event: dict) -> None:
        for pub in self._publishers:
            try:
                pub.publish(event)
            except Exception as exc:
                print(f"[fanout] publisher {type(pub).__name__} failed: {exc}")

    def close(self) -> None:
        for pub in self._publishers:
            try:
                pub.close()
            except Exception as exc:
                print(f"[fanout] close {type(pub).__name__} failed: {exc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_fanout_publisher_distributes_events -v`
Expected: PASS

- [ ] **Step 5: Write failing test — FanoutPublisher tolerates inner failure**

```python
def test_fanout_publisher_tolerates_failure():
    """One inner publisher failing does not stop others."""
    from publisher import FanoutPublisher

    received = []

    class Broken:
        def publish(self, event):
            raise RuntimeError("boom")
        def close(self):
            pass

    class Recorder:
        def publish(self, event):
            received.append(event)
        def close(self):
            pass

    pub = FanoutPublisher([Broken(), Recorder()])
    pub.publish({"type": "test"})
    pub.close()

    assert len(received) == 1
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_fanout_publisher_tolerates_failure -v`
Expected: PASS

- [ ] **Step 7: Write failing test — FanoutPublisher close propagates to all**

```python
def test_fanout_publisher_close_propagates():
    """close() is called on all inner publishers."""
    from publisher import FanoutPublisher

    closed = []

    class Trackable:
        def __init__(self, name):
            self.name = name
        def publish(self, event):
            pass
        def close(self):
            closed.append(self.name)

    pub = FanoutPublisher([Trackable("a"), Trackable("b")])
    pub.close()

    assert closed == ["a", "b"]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_fanout_publisher_close_propagates -v`
Expected: PASS

- [ ] **Step 9: Lint and commit**

```bash
uv run ruff check scripts/publisher.py tests/test_publisher.py
uv run ruff format --check scripts/publisher.py tests/test_publisher.py
git add scripts/publisher.py tests/test_publisher.py
git commit -m "feat: add FanoutPublisher for multi-backend event distribution"
```

---

### Task 3: ConfluentPublisher (`scripts/publisher.py`)

**Files:**
- Modify: `scripts/publisher.py`
- Test: `tests/test_publisher.py`

- [ ] **Step 1: Write failing test — ConfluentPublisher routes by schema**

```python
from unittest.mock import MagicMock, patch


def test_confluent_publisher_routes_by_schema():
    """ConfluentPublisher routes events to correct topics based on schema field."""
    mock_producer_cls = MagicMock()
    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=mock_producer_cls)}):
        # Re-import to pick up the mock
        import importlib
        import publisher

        importlib.reload(publisher)

        pub = publisher.ConfluentPublisher(
            bootstrap_servers="test:9092",
            api_key="key",
            api_secret="secret",
            topic_prefix="pokemon",
        )
        pub.publish({"schema": "tapes.node.v1", "type": "fitness"})
        pub.publish({"schema": "pokemon.game.v1", "event_type": "battle"})

        calls = mock_producer.produce.call_args_list
        assert calls[0].kwargs["topic"] == "pokemon.telemetry.raw"
        assert calls[1].kwargs["topic"] == "pokemon.game.events"

        pub.close()
        mock_producer.flush.assert_called_once_with(timeout=10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publisher.py::test_confluent_publisher_routes_by_schema -v`
Expected: FAIL — `AttributeError: module 'publisher' has no attribute 'ConfluentPublisher'`

- [ ] **Step 3: Write ConfluentPublisher implementation**

Add to `scripts/publisher.py` after `NoopPublisher`, before `FanoutPublisher`:

```python
import json


# Schema → topic suffix mapping
_TOPIC_MAP: dict[str, str] = {
    "tapes.node.v1": "telemetry.raw",
    "pokemon.game.v1": "game.events",
}


class ConfluentPublisher:
    """Publishes events to Confluent Cloud via confluent-kafka Producer.

    Routes events to topics based on the ``schema`` field.
    Unknown schemas are logged and dropped.
    """

    def __init__(self, bootstrap_servers: str, api_key: str, api_secret: str, topic_prefix: str):
        from confluent_kafka import Producer

        self._topic_prefix = topic_prefix
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "security.protocol": "SASL_SSL",
                "sasl.mechanisms": "PLAIN",
                "sasl.username": api_key,
                "sasl.password": api_secret,
            }
        )

    @staticmethod
    def _delivery_callback(err, msg):
        if err is not None:
            print(f"[confluent] delivery failed: {err}")

    def publish(self, event: dict) -> None:
        schema = event.get("schema", "")
        suffix = _TOPIC_MAP.get(schema)
        if suffix is None:
            print(f"[confluent] unknown schema {schema!r}, dropping event")
            return
        topic = f"{self._topic_prefix}.{suffix}"
        key = schema.encode("utf-8")
        value = json.dumps(event).encode("utf-8")
        self._producer.produce(topic=topic, key=key, value=value, callback=self._delivery_callback)

    def close(self) -> None:
        self._producer.flush(timeout=10)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_confluent_publisher_routes_by_schema -v`
Expected: PASS

- [ ] **Step 5: Write failing test — unknown schema dropped**

```python
def test_confluent_publisher_drops_unknown_schema(capsys):
    """ConfluentPublisher drops events with unknown schema and logs warning."""
    mock_producer_cls = MagicMock()
    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=mock_producer_cls)}):
        import importlib
        import publisher

        importlib.reload(publisher)

        pub = publisher.ConfluentPublisher(
            bootstrap_servers="test:9092",
            api_key="key",
            api_secret="secret",
            topic_prefix="pokemon",
        )
        pub.publish({"schema": "unknown.v1", "data": "test"})

        mock_producer.produce.assert_not_called()
        assert "unknown schema" in capsys.readouterr().out
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_confluent_publisher_drops_unknown_schema -v`
Expected: PASS

- [ ] **Step 7: Write failing test — event with no schema dropped**

```python
def test_confluent_publisher_drops_missing_schema(capsys):
    """ConfluentPublisher drops events with no schema field."""
    mock_producer_cls = MagicMock()
    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=mock_producer_cls)}):
        import importlib
        import publisher

        importlib.reload(publisher)

        pub = publisher.ConfluentPublisher(
            bootstrap_servers="test:9092",
            api_key="key",
            api_secret="secret",
            topic_prefix="pokemon",
        )
        pub.publish({"type": "fitness"})

        mock_producer.produce.assert_not_called()
        assert "unknown schema" in capsys.readouterr().out
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_confluent_publisher_drops_missing_schema -v`
Expected: PASS

- [ ] **Step 9: Lint and commit**

```bash
uv run ruff check scripts/publisher.py tests/test_publisher.py
uv run ruff format --check scripts/publisher.py tests/test_publisher.py
git add scripts/publisher.py tests/test_publisher.py
git commit -m "feat: add ConfluentPublisher with schema-based topic routing"
```

---

### Task 4: Update `make_publisher()` to support config

**Files:**
- Modify: `scripts/publisher.py:71-75`
- Test: `tests/test_publisher.py`

- [ ] **Step 1: Write failing test — make_publisher returns FanoutPublisher when Confluent enabled**

```python
def test_make_publisher_returns_fanout_when_confluent_enabled(tmp_path):
    """make_publisher returns FanoutPublisher wrapping JSONL + Confluent."""
    mock_producer_cls = MagicMock()
    mock_producer_cls.return_value = MagicMock()

    with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=mock_producer_cls)}):
        import importlib
        import publisher

        importlib.reload(publisher)

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[telemetry.confluent]\n'
            'enabled = true\n'
            'bootstrap_servers = "test:9092"\n'
        )

        pub = publisher.make_publisher(telemetry_dir=str(tmp_path / "telemetry"), config_path=config_file)
        assert isinstance(pub, publisher.FanoutPublisher)
        pub.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publisher.py::test_make_publisher_returns_fanout_when_confluent_enabled -v`
Expected: FAIL — `TypeError: make_publisher() got an unexpected keyword argument 'config_path'`

- [ ] **Step 3: Update make_publisher implementation**

Replace the `make_publisher` function in `scripts/publisher.py`:

First, add `import os` to the top-level imports in `publisher.py` (after `from pathlib import Path`):

```python
import os
```

Then replace the `make_publisher` function:

```python
def make_publisher(telemetry_dir: str | None = None, config_path: Path | None = None) -> Publisher:
    """Factory: builds publisher stack from config.

    Always includes JSONLPublisher when telemetry_dir is set.
    Adds ConfluentPublisher when config enables it and confluent-kafka is installed.
    Returns FanoutPublisher if multiple backends, single publisher otherwise.
    """
    from config import load_config

    cfg = load_config(config_path)
    publishers: list[Publisher] = []

    if telemetry_dir:
        publishers.append(JSONLPublisher(telemetry_dir))

    confluent_cfg = cfg["telemetry"]["confluent"]
    if confluent_cfg["enabled"]:
        api_key = os.environ.get(confluent_cfg["api_key_env"], "")
        api_secret = os.environ.get(confluent_cfg["api_secret_env"], "")
        try:
            publishers.append(
                ConfluentPublisher(
                    bootstrap_servers=confluent_cfg["bootstrap_servers"],
                    api_key=api_key,
                    api_secret=api_secret,
                    topic_prefix=confluent_cfg["topic_prefix"],
                )
            )
        except Exception as exc:
            print(f"[publisher] confluent setup failed, continuing with JSONL only: {exc}")

    if not publishers:
        return NoopPublisher()
    if len(publishers) == 1:
        return publishers[0]
    return FanoutPublisher(publishers)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_make_publisher_returns_fanout_when_confluent_enabled -v`
Expected: PASS

- [ ] **Step 5: Write failing test — make_publisher without config returns JSONLPublisher (backward compat)**

```python
def test_make_publisher_without_config_returns_jsonl(tmp_path):
    """make_publisher with no config behaves like before — returns JSONLPublisher."""
    from publisher import JSONLPublisher, make_publisher

    pub = make_publisher(telemetry_dir=str(tmp_path))
    assert isinstance(pub, JSONLPublisher)
    pub.close()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_make_publisher_without_config_returns_jsonl -v`
Expected: PASS

- [ ] **Step 7: Write failing test — make_publisher graceful when confluent-kafka missing**

```python
def test_make_publisher_graceful_without_confluent_kafka(tmp_path, monkeypatch, capsys):
    """make_publisher falls back to JSONL when confluent-kafka is not installed."""
    import importlib
    import publisher

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[telemetry.confluent]\n'
        'enabled = true\n'
        'bootstrap_servers = "test:9092"\n'
    )
    monkeypatch.setenv("CONFLUENT_API_KEY", "key")
    monkeypatch.setenv("CONFLUENT_API_SECRET", "secret")

    # Setting a sys.modules entry to None causes ImportError on import
    with patch.dict("sys.modules", {"confluent_kafka": None}):
        importlib.reload(publisher)
        pub = publisher.make_publisher(telemetry_dir=str(tmp_path / "telemetry"), config_path=config_file)
        assert isinstance(pub, publisher.JSONLPublisher)
        assert "confluent setup failed" in capsys.readouterr().out
        pub.close()
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_publisher.py::test_make_publisher_graceful_without_confluent_kafka -v`
Expected: PASS

- [ ] **Step 9: Verify all existing tests still pass**

Run: `uv run pytest tests/test_publisher.py -v`
Expected: ALL PASS (existing + new tests)

- [ ] **Step 10: Lint and commit**

```bash
uv run ruff check scripts/publisher.py tests/test_publisher.py
uv run ruff format --check scripts/publisher.py tests/test_publisher.py
git add scripts/publisher.py tests/test_publisher.py
git commit -m "feat: wire make_publisher to config for Confluent Cloud support"
```

---

### Task 5: Agent CLI integration (`scripts/agent.py`)

**Files:**
- Modify: `scripts/agent.py:1192-1244`

- [ ] **Step 1: Add `--config` argument to argparser**

After line 1197 (`--telemetry-dir` arg), add:

```python
    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to config.toml (default: config.toml in cwd)",
    )
```

- [ ] **Step 2: Pass config_path to both make_publisher calls**

Replace lines 1211-1244 (both publisher blocks) with:

```python
    config_path = Path(args.config) if args.config else None

    if args.telemetry_dir:
        try:
            from publisher import make_publisher

            pub = make_publisher(telemetry_dir=args.telemetry_dir, config_path=config_path)
            pub.publish(
                {
                    "schema": "tapes.node.v1",
                    "type": "fitness",
                    "root_hash": f"local-{Path(args.rom).stem}",
                    "node": {
                        "bucket": {"role": "agent", "model": "pokemon-agent"},
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                        "project": "pokemon-kafka",
                    },
                    "fitness": fitness,
                    "params": json.loads(os.environ.get("EVOLVE_PARAMS", "{}")),
                }
            )
            pub.close()
        except Exception as exc:
            print(f"[agent] telemetry publish failed: {exc}")

    # Publish game events
    if args.telemetry_dir:
        try:
            from publisher import make_publisher as _make_pub

            game_pub = _make_pub(telemetry_dir=str(Path(args.telemetry_dir) / "game"), config_path=config_path)
            for event in agent.collector.events:
                game_pub.publish(event)
            game_pub.close()
        except Exception as exc:
            print(f"[agent] game event publish failed: {exc}")
```

- [ ] **Step 3: Verify agent still works without --config flag**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS (no regressions)

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check scripts/agent.py
uv run ruff format --check scripts/agent.py
git add scripts/agent.py
git commit -m "feat: add --config flag to agent for Confluent Cloud publisher"
```

---

### Task 6: Packaging and config files

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `config.toml.example`

- [ ] **Step 1: Add optional dependency to pyproject.toml**

Add after the `[dependency-groups]` section:

```toml
[project.optional-dependencies]
confluent = ["confluent-kafka>=2.3.0"]
```

- [ ] **Step 2: Add config.toml to .gitignore**

Add after the `.env` / `*.key` section:

```
# Config (may contain credential env var references)
config.toml
```

- [ ] **Step 3: Create config.toml.example**

```toml
# Pokemon-Kafka Configuration
# Copy to config.toml and customize. config.toml is gitignored.
#
# All [telemetry.confluent] values can be overridden by environment variables:
#   CONFLUENT_ENABLED=1
#   CONFLUENT_BOOTSTRAP_SERVERS=pkc-xxxxx.us-east-1.aws.confluent.cloud:9092
#   CONFLUENT_TOPIC_PREFIX=pokemon
#   CONFLUENT_API_KEY=<your-api-key>
#   CONFLUENT_API_SECRET=<your-api-secret>

version = 1

[telemetry]
dir = "data/telemetry"

[telemetry.confluent]
enabled = false
bootstrap_servers = "pkc-xxxxx.us-east-1.aws.confluent.cloud:9092"
topic_prefix = "pokemon"

# These name environment variables — not raw secrets.
# Set CONFLUENT_API_KEY and CONFLUENT_API_SECRET in your environment.
api_key_env = "CONFLUENT_API_KEY"
api_secret_env = "CONFLUENT_API_SECRET"
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `uv run pytest --cov --cov-report=term-missing`
Expected: ALL PASS, 100% coverage

- [ ] **Step 5: Lint check**

```bash
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore config.toml.example
git commit -m "feat: add confluent-kafka optional dep, config template, gitignore config.toml"
```

---

### Task 7: Full integration verification

- [ ] **Step 1: Run full test suite with coverage**

```bash
uv run pytest --cov --cov-report=term-missing
```

Expected: ALL PASS, coverage at 100%.

- [ ] **Step 2: Run lint checks**

```bash
uv run ruff check .
uv run ruff format --check .
```

Expected: No errors.

- [ ] **Step 3: Verify backward compatibility — no config.toml, no confluent-kafka**

```bash
uv run python -c "
from publisher import make_publisher
pub = make_publisher(telemetry_dir='/tmp/test-telemetry')
pub.publish({'schema': 'tapes.node.v1', 'type': 'test'})
pub.close()
print('OK: backward-compatible, no config needed')
"
```

Expected: Prints `OK` and writes to `/tmp/test-telemetry/*.jsonl`.

- [ ] **Step 4: Final commit if any fixups needed**

```bash
git add -A
git status
# Only commit if there are changes
```
