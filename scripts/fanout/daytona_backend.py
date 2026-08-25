"""Daytona backend — opt-in fan-out across one sandbox per variant.

Never the default. Selected with `--backend daytona`, and only then does this
module import the SDK, so neither the local path nor the test suite needs
`daytona` installed.

Shape: N variants become N sandboxes launched from one prebuilt snapshot. The
snapshot carries the repo, its deps, and the capture sidecar; it carries
neither the ROM nor any secret. The ROM is uploaded per sandbox and the DSN,
capture URL, and API keys are injected as env at create time, so the image
stays publishable and a rotated key needs no rebuild.

Teardown is the part that has to be right. Every sandbox is deleted in a
`finally`, a batch-level sweep catches anything a `KeyboardInterrupt` skipped,
and `ephemeral=True` plus `ttl_minutes` give the server its own reason to reap
a sandbox if this driver is killed outright. Leaking a sandbox costs money
silently, so all three layers exist on purpose.
"""

from __future__ import annotations

import json
import os
import shlex
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from fanout.backend import degraded_fitness

REMOTE_WORKDIR = "/workspace"
REMOTE_ROM = "/tmp/rom.gb"
REMOTE_FITNESS = "/tmp/fitness.json"
SIDECAR_PORT = 8080
SIDECAR_LOG = "/tmp/tapes-proxy.log"
DEFAULT_LLM_UPSTREAM = "https://api.anthropic.com"


@dataclass(frozen=True)
class DaytonaSettings:
    """Everything the backend needs that must not live in the snapshot."""

    snapshot: str
    cohort: str
    concurrency: int = 5
    run_timeout: int = 600
    create_timeout: int = 180
    # Wall-clock backstop: if this driver is SIGKILLed, the server still reaps.
    ttl_minutes: int = 30
    capture_base_url: str | None = None
    anthropic_api_key: str | None = None
    # When set, each sandbox runs its own tapes proxy writing to this ONE
    # central store. Injected at launch — baking a DSN into the image would
    # make the snapshot itself a credential.
    postgres_dsn: str | None = None
    llm_upstream: str = DEFAULT_LLM_UPSTREAM
    extra_env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, snapshot: str, cohort: str, **overrides) -> DaytonaSettings:
        """Build settings from the environment.

        Reads the DSN, capture proxy, and upstream key from the launching
        shell so they are injected per sandbox rather than baked into the
        image, and a rotated key never forces a snapshot rebuild.
        """
        return cls(
            snapshot=snapshot,
            cohort=cohort,
            capture_base_url=os.environ.get("FANOUT_CAPTURE_BASE_URL"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            postgres_dsn=os.environ.get("TAPES_POSTGRES_DSN"),
            llm_upstream=os.environ.get("FANOUT_LLM_UPSTREAM", DEFAULT_LLM_UPSTREAM),
            **overrides,
        )


def build_sidecar_command(dsn: str, cohort: str, upstream: str) -> str:
    """Start the in-sandbox tapes proxy, writing to the central store.

    `--project` is the cohort tag, so one fan-out is one queryable group. The
    proxy is backgrounded and its log kept: if capture fails, the race should
    still produce fitness, and the log is how that failure is diagnosed.
    """
    return (
        f"nohup tapes serve proxy "
        f"--postgres {shlex.quote(dsn)} "
        f"--project {shlex.quote(cohort)} "
        f"--provider anthropic "
        f"--upstream {shlex.quote(upstream)} "
        f"--listen :{SIDECAR_PORT} "
        f"> {SIDECAR_LOG} 2>&1 &"
    )


def build_heartbeat_command(cohort: str, label: str) -> str:
    """One tiny real /v1/messages call through the capture path, per arm.

    agent.py has no in-process LLM client (should_call_llm has no caller), so
    a race emits no capture traffic of its own yet. Until it does, this is how
    a fan-out proves its capture path end to end: one ~10-token request whose
    content carries the cohort and arm label. Content-addressing matters —
    tapes dedupes raw turns by request-body hash, so the body must be unique
    per arm or a whole race collapses into one row.

    The key and base URL come from the sandbox environment at exec time; they
    are never interpolated into this string, which gets logged.
    """
    body = json.dumps(
        {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 4,
            "messages": [{"role": "user", "content": f"capture-heartbeat {cohort} {label} — reply OK"}],
        }
    )
    return (
        'curl -sf --max-time 60 "$ANTHROPIC_BASE_URL/v1/messages" '
        '-H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" '
        f"-H 'content-type: application/json' -d {shlex.quote(body)} -o /dev/null"
    )


def build_agent_command(turns: int, params: dict, strategy: str, load_state: str | None = None) -> str:
    """The in-sandbox agent invocation, mirroring `evolve.run_agent`'s flags.

    `--no-self-heal` and `--no-in-run-heal` matter as much here as locally: a
    race child that spawned its own healer would recurse, and in a sandbox that
    recursion would be billed.
    """
    cmd = (
        f"EVOLVE_PARAMS={shlex.quote(json.dumps(params))} "
        f"uv run scripts/agent.py {shlex.quote(REMOTE_ROM)} "
        f"--max-turns {turns} --output-json {REMOTE_FITNESS} "
        f"--no-self-heal --no-in-run-heal --strategy {shlex.quote(strategy)}"
    )
    if load_state:
        cmd += f" --load-state {shlex.quote(load_state)}"
    return cmd


def parse_fitness(raw: str, turns: int) -> dict:
    """Parse the fitness JSON a run wrote, degrading rather than raising."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return degraded_fitness(turns)
    if not isinstance(parsed, dict) or "party_size" not in parsed:
        return degraded_fitness(turns)
    return parsed


class DaytonaBackend:
    """One sandbox per variant, launched from a prebuilt snapshot."""

    name = "daytona"

    def __init__(self, settings: DaytonaSettings, client=None):
        self.settings = settings
        self._client = client
        self._live: dict[str, object] = {}
        self._lock = threading.Lock()

    def _daytona(self):
        """Resolve the SDK client lazily so importing this module is free."""
        if self._client is None:
            from daytona import Daytona  # imported here: optional dependency

            self._client = Daytona()
        return self._client

    def _env_for(self, label: str) -> dict[str, str]:
        """Per-sandbox env. Secrets are injected, never baked into the image."""
        # Cohort tagging does NOT happen here. tapes reads no TAPES_PROJECT or
        # TAPES_AGENT_NAME env var (the binary's only such variable is
        # TAPES_CASSETTES) — the real tag is `--project` on the sidecar, see
        # build_sidecar_command, plus the Daytona labels set in _create.
        # These two are in-sandbox provenance only: they tell a human shelled
        # into an arm which cohort it belongs to.
        env = {
            "FANOUT_COHORT": self.settings.cohort,
            "FANOUT_VARIANT": label,
        }
        if self.settings.capture_base_url:
            # Capture-at-boundary: an already-running central proxy. This wins
            # over the DSN because a host commonly has BOTH — the DSN serves
            # host-side verification, while a loopback DSN inside a sandbox
            # would resolve to the sandbox's own empty database. An explicit
            # capture URL is always deliberate; a DSN in the env may not be.
            env["ANTHROPIC_BASE_URL"] = self.settings.capture_base_url
        elif self.settings.postgres_dsn:
            # Capture-in-image: the sandbox's own sidecar is the agent's
            # upstream, and it forwards to the real vendor while writing to
            # the central store. Requires a DSN that is reachable FROM the
            # sandbox, not just from this host.
            env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{SIDECAR_PORT}"
        if self.settings.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = self.settings.anthropic_api_key
        env.update(self.settings.extra_env)
        return env

    def _create(self, label: str):
        from daytona import CreateSandboxFromSnapshotParams

        params = CreateSandboxFromSnapshotParams(
            snapshot=self.settings.snapshot,
            env_vars=self._env_for(label),
            labels={"cohort": self.settings.cohort, "variant": label},
            ephemeral=True,
            ttl_minutes=self.settings.ttl_minutes,
        )
        return self._daytona().create(params, timeout=self.settings.create_timeout)

    def _delete(self, sandbox) -> None:
        """Best-effort delete. A teardown error must not mask a run's result."""
        try:
            self._daytona().delete(sandbox)
        except Exception:  # noqa: BLE001 - reaping is best-effort by design
            pass

    def _run_one(self, rom: str, turns: int, params: dict, label: str, strategy: str, load_state: str | None) -> dict:
        sandbox = None
        start = time.monotonic()

        def stamped(fitness: dict) -> dict:
            # Per-arm wall clock, for honest cost extrapolation. score() reads
            # its keys via .get, so an extra key never affects ranking.
            fitness["fanout_elapsed"] = round(time.monotonic() - start, 1)
            return fitness

        try:
            sandbox = self._create(label)
            with self._lock:
                self._live[label] = sandbox
            # The ROM is uploaded, never baked: it is not ours to redistribute.
            sandbox.fs.upload_file(rom, REMOTE_ROM)
            if self.settings.postgres_dsn and not self.settings.capture_base_url:
                # In-image mode only — with a central proxy there is nothing
                # to run in the sandbox. Start capture before the agent, so no
                # turn is missed. A
                # sidecar that fails to start must not fail the race — the
                # log stays in the sandbox only as long as the sandbox does,
                # so capture problems surface as an empty cohort, not a crash.
                sandbox.process.exec(
                    build_sidecar_command(self.settings.postgres_dsn, self.settings.cohort, self.settings.llm_upstream),
                    cwd=REMOTE_WORKDIR,
                    timeout=60,
                )
                # The proxy is nohup'd, so exec returns before it listens.
                # Without this wait the agent's opening LLM calls would race
                # the socket and fail — invisibly, as missing capture.
                sandbox.process.exec(
                    f"for i in $(seq 1 20); do "
                    f"curl -s -o /dev/null http://127.0.0.1:{SIDECAR_PORT} && exit 0; sleep 0.5; "
                    f"done; echo 'sidecar never came up' >> {SIDECAR_LOG}",
                    cwd=REMOTE_WORKDIR,
                    timeout=30,
                )
            sandbox.process.exec(
                build_agent_command(turns, params, strategy, load_state),
                cwd=REMOTE_WORKDIR,
                timeout=self.settings.run_timeout,
            )
            read = sandbox.process.exec(f"cat {REMOTE_FITNESS}", cwd=REMOTE_WORKDIR, timeout=60)
            fitness = degraded_fitness(turns) if read.exit_code != 0 else parse_fitness(read.result, turns)
            if (
                strategy != "low"
                and self.settings.anthropic_api_key
                and (self.settings.capture_base_url or self.settings.postgres_dsn)
            ):
                # Prove this arm's capture path with one real, uniquely-bodied
                # call. Failure is recorded, not raised: a race with broken
                # capture should still rank its variants.
                hb = sandbox.process.exec(
                    build_heartbeat_command(self.settings.cohort, label),
                    cwd=REMOTE_WORKDIR,
                    env=self._env_for(label),
                    timeout=90,
                )
                fitness["capture_heartbeat"] = "ok" if hb.exit_code == 0 else f"failed (exit {hb.exit_code})"
            return stamped(fitness)
        except Exception as exc:  # noqa: BLE001 - one bad variant must not abort a race
            # Degrade, but say why: without the error in the result, a quota
            # rejection at create time is indistinguishable from a crashed run,
            # and diagnosing it means forensics instead of reading the summary.
            fitness = degraded_fitness(turns)
            fitness["fanout_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            return stamped(fitness)
        finally:
            if sandbox is not None:
                self._delete(sandbox)
                with self._lock:
                    self._live.pop(label, None)

    def _sweep(self) -> None:
        """Delete anything still live — the interrupt and crash path."""
        with self._lock:
            stragglers = list(self._live.items())
            self._live.clear()
        for _, sandbox in stragglers:
            self._delete(sandbox)

    def run_batch(
        self,
        rom: str,
        turns: int,
        candidates: list[dict],
        load_state: str | None = None,
        strategy: str = "low",
    ) -> list[dict]:
        labels = [str(p.get("label", f"variant_{i}")) for i, p in enumerate(candidates)]
        try:
            with ThreadPoolExecutor(max_workers=self.settings.concurrency) as pool:
                return list(
                    pool.map(
                        lambda item: self._run_one(rom, turns, item[0], item[1], strategy, load_state),
                        zip(candidates, labels),
                    )
                )
        finally:
            self._sweep()
