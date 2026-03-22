# Confluent Cloud Publisher Design

**Date:** 2026-03-17
**Status:** Draft

## Problem

The pokemon-kafka project publishes telemetry to local JSONL files and a local
docker-compose Kafka broker. There is no path to Confluent Cloud for production
event streaming. The sweeper project is adding Confluent Cloud support through
`config.toml`; pokemon-kafka should follow the same pattern so both projects can
independently publish to their own Confluent Cloud clusters.

## Constraints

- **Must not break existing local demo workflow.** Presentations rely on the
  current JSONL + docker-compose Kafka setup working without cloud credentials.
- **Confluent Cloud is additive.** JSONL remains the always-on local backend.
  Confluent is an optional second publisher that runs alongside it.
- **Separate cluster from sweeper.** Each project manages its own Confluent
  Cloud environment.
- **No new required dependencies.** `confluent-kafka` is an optional extra.
  The project installs and runs identically to today without it.

## Design

### Config Layer

A `config.toml` at the project root controls Confluent Cloud settings. The file
is gitignored since it can hold references to credential env vars. A committed
`config.toml.example` documents the structure.

```toml
# config.toml
version = 1

[telemetry]
dir = "data/telemetry"

[telemetry.confluent]
enabled = false
bootstrap_servers = "pkc-xxxxx.us-east-1.aws.confluent.cloud:9092"
topic_prefix = "pokemon"
api_key_env = "CONFLUENT_API_KEY"
api_secret_env = "CONFLUENT_API_SECRET"
```

**Precedence** (highest wins):

1. Environment variables: `CONFLUENT_ENABLED` (truthy: `1`, `true`, `yes`),
   `CONFLUENT_BOOTSTRAP_SERVERS`, `CONFLUENT_API_KEY`, `CONFLUENT_API_SECRET`,
   `CONFLUENT_TOPIC_PREFIX`
2. `config.toml` values
3. Defaults (no Confluent, JSONL to `data/telemetry`)

If `config.toml` does not exist, behavior is identical to today. Setting
`CONFLUENT_ENABLED=1` plus the credential env vars is sufficient for CI/cloud
deployments that skip the TOML file entirely.

**Credential pattern** follows sweeper: `api_key_env` and `api_secret_env` name
environment variables rather than storing raw secrets.

### Config Loading

New module `scripts/config.py` exposes:

```python
def load_config(config_path: Path | None = None) -> dict
```

Uses `tomllib` (stdlib in Python 3.11+) to parse TOML, merges with env var
overrides, returns a dict with defaults filled in. No new dependencies.

### Publisher Architecture

Three new classes in `scripts/publisher.py`. Existing `JSONLPublisher` and
`NoopPublisher` are untouched.

**`ConfluentPublisher`**

Implements the existing `Publisher` protocol. Uses `confluent_kafka.Producer`
with SASL_SSL authentication. Routes events to topics based on the `schema`
field:

| Event schema       | Topic                          |
|--------------------|--------------------------------|
| `tapes.node.v1`    | `{topic_prefix}.telemetry.raw` |
| `pokemon.game.v1`  | `{topic_prefix}.game.events`   |
| unknown / missing  | Logged warning, event dropped  |

Events are serialized as `json.dumps(event).encode("utf-8")`. The Kafka message
key is the event's `schema` field (or `"unknown"` if absent), encoded as UTF-8.
This ensures events of the same type land on the same partition for ordered
consumption.

On publish failure, logs a warning via a delivery callback. Does not crash the
agent. `ConfluentPublisher.close()` calls `producer.flush(timeout=10)` to drain
buffered messages before shutdown.

**`FanoutPublisher`**

Wraps a list of `Publisher` instances. `publish()` calls each in order.
`close()` closes all. One publisher failing does not stop the others.

**Updated `make_publisher()`**

```
make_publisher(telemetry_dir, config_path=None)
  +-- always: JSONLPublisher(telemetry_dir)  [if dir set]
  +-- if config + confluent.enabled:
  |     ConfluentPublisher(bootstrap, key, secret, topic_prefix)
  +-- FanoutPublisher([...active publishers])
```

If `confluent-kafka` is not installed but config requests it, logs a clear
error message and continues with JSONL only.

### Agent Integration: Dual Publisher Pattern

Today `agent.py` calls `make_publisher()` twice (lines 1213-1230 and 1237-1242):
one for telemetry events (`data/telemetry`), one for game events
(`data/telemetry/game`). Both publishers are short-lived (create, publish, close).

With Confluent Cloud, `ConfluentPublisher` routes by schema field, so a single
Confluent producer handles both event types regardless of which `make_publisher`
call creates it. The design keeps the two `make_publisher` calls as-is:

- **Telemetry publisher**: JSONL writes to `data/telemetry` + Confluent routes
  `tapes.node.v1` events to `{prefix}.telemetry.raw`
- **Game publisher**: JSONL writes to `data/telemetry/game` + Confluent routes
  `pokemon.game.v1` events to `{prefix}.game.events`

Two short-lived Kafka producer instances are acceptable here. The agent runs
a single session, publishes a handful of events, then exits. Sharing a producer
across both call sites would require refactoring the agent's publish flow,
which is out of scope for this change.

### Dependency and Packaging

`confluent-kafka` is an optional dependency using `[project.optional-dependencies]`
(PEP 621). The existing `[dependency-groups]` section (PEP 735) is used for dev
tools. This is intentional: optional-dependencies is the standard mechanism for
extras that `uv sync --extra` understands, while dependency-groups is for
development tooling.

```toml
[project.optional-dependencies]
confluent = ["confluent-kafka>=2.3.0"]
```

- `uv sync` gives the same environment as today.
- `uv sync --extra confluent` opts into cloud publishing.

`ConfluentPublisher.__init__` does a lazy import. If the package is missing and
config asks for Confluent, it logs: "confluent-kafka not installed -- run
`uv sync --extra confluent`" and skips that publisher.

### Agent CLI Integration

`scripts/agent.py` gains a `--config` CLI argument (defaults to `config.toml`
in cwd). Passes the path to `make_publisher()`. Existing invocations without
`--config` work identically.

The `--telemetry-dir` CLI arg takes precedence over `telemetry.dir` in
config.toml. Config.toml provides a default; the CLI arg overrides it.

### Testing Strategy

All tests in `tests/`, following existing patterns. Coverage stays at 100%.

**`tests/test_config.py`** (new):

- Defaults returned when no config file exists
- TOML parsing produces correct dict structure
- Env vars override TOML values (including `CONFLUENT_ENABLED` toggle)
- Missing file handled gracefully (no crash, returns defaults)

**`tests/test_publisher.py`** (extended):

- `ConfluentPublisher`: mocked `confluent_kafka.Producer`, verify `produce()`
  called with correct topic routing by schema field, SASL config built correctly
- `FanoutPublisher`: all inner publishers receive every event, close propagates,
  one publisher failing does not stop others
- `make_publisher()`: returns `FanoutPublisher` when config enables Confluent,
  returns `JSONLPublisher` alone when no config (current behavior preserved)
- Graceful degradation: missing `confluent-kafka` package logs warning, falls
  back to JSONL only

No real Confluent Cloud connections in tests. `Producer` is mocked at the import
boundary.

## Files Changed

| File                     | Change                                              |
|--------------------------|-----------------------------------------------------|
| `scripts/config.py`      | New -- config loading with TOML + env var merge     |
| `scripts/publisher.py`   | Modified -- add ConfluentPublisher, FanoutPublisher  |
| `scripts/agent.py`       | Modified -- accept --config arg                     |
| `pyproject.toml`         | Modified -- add confluent-kafka optional dep         |
| `config.toml.example`    | New -- committed template                           |
| `.gitignore`             | Modified -- add config.toml                         |
| `tests/test_config.py`   | New -- config loading tests                         |
| `tests/test_publisher.py`| Modified -- Confluent, Fanout, degradation tests    |

## What Does Not Change

- `JSONLPublisher` and `NoopPublisher` implementations
- `docker-compose.yml` and all Docker services
- Kafka consumers (telemetry, game, alerts)
- Flink SQL analytics jobs
- Tapes proxy
- Any existing demo or presentation workflow

## Stretch Goal (Future Design)

Flink-powered Engineering Health Copilot on Confluent Cloud. Sweeper telemetry
and pokemon-kafka game events processed in managed Flink to derive real-time
code-health signals. This is a follow-on design after the core publisher lands.
