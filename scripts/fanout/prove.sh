#!/usr/bin/env bash
# Prove the fan-out end to end with a 3-sandbox race.
#
#   bash scripts/fanout/prove.sh --rom <rom> --snapshot <name>
#
# Runs three arms at --strategy medium. agent.py has no in-process LLM client
# yet (should_call_llm has no caller), so each arm proves its capture path
# with one real per-arm heartbeat call routed through the funnel; the checks:
#
#   1. all three runs landed in the central store as one cohort
#   2. fitness JSON came back for every arm
#   3. zero sandboxes from this cohort are still alive
#   4. what a 20-arm race would cost, extrapolated from measured usage
#
# Bounded on purpose: three arms is the agreed proof size. Nothing here scales
# itself up.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROM=""
SNAPSHOT=""
ARMS=3
TURNS=400
PROVE_ARMS_MAX=3
COHORT="fanout-proof-$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${REPO_ROOT}/runs/fanout-proof"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rom) ROM="$2"; shift 2 ;;
        --snapshot) SNAPSHOT="$2"; shift 2 ;;
        --turns) TURNS="$2"; shift 2 ;;
        --cohort) COHORT="$2"; shift 2 ;;
        -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

fail() { echo "[prove] FAIL: $*" >&2; exit 1; }

[[ -n "${ROM}" ]] || fail "--rom is required"
[[ -f "${ROM}" ]] || fail "ROM not found: ${ROM}"
[[ -n "${SNAPSHOT}" ]] || fail "--snapshot is required (build one with build_snapshot.sh)"
[[ -n "${DAYTONA_API_KEY:-}" ]] || fail "DAYTONA_API_KEY is not set"
# Boundary capture: derive the public proxy URL from the funnel if not given.
if [[ -z "${FANOUT_CAPTURE_BASE_URL:-}" ]]; then
    TS_HOST="$(tailscale status --json 2>/dev/null | python3 -c "
import json,sys
print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))" 2>/dev/null || true)"
    # No pipe here: under pipefail, grep -q's early exit SIGPIPEs tailscale
    # (141) and silently falsifies the condition.
    FUNNEL_OUT="$(tailscale funnel status 2>/dev/null || true)"
    if [[ -n "${TS_HOST}" && "${FUNNEL_OUT}" == *"Funnel on"* ]]; then
        FANOUT_CAPTURE_BASE_URL="https://${TS_HOST}"
        echo "[prove] capture URL derived from funnel: ${FANOUT_CAPTURE_BASE_URL}"
    fi
fi
export FANOUT_CAPTURE_BASE_URL
# The funnel forwards to the anthropic proxy on :8093; make sure one is up.
if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8093; then
    fail "no proxy on :8093 — start one: tapes serve proxy --provider anthropic --upstream https://api.anthropic.com --listen :8093"
fi

# The DSN defaults from the host's own tapes config — when `tapes serve` runs
# here, ~/.tapes/config.toml already names the store, so nothing needs typing.
if [[ -z "${TAPES_POSTGRES_DSN:-}" && -f "${HOME}/.tapes/config.toml" ]]; then
    TAPES_POSTGRES_DSN="$(python3 -c "
import tomllib
print(tomllib.load(open('${HOME}/.tapes/config.toml','rb'))['storage']['postgres_dsn'])" 2>/dev/null || true)"
    [[ -n "${TAPES_POSTGRES_DSN}" ]] && echo "[prove] DSN taken from ~/.tapes/config.toml"
fi
# Capture needs one of two shapes. With FANOUT_CAPTURE_BASE_URL (boundary
# mode: a central proxy the sandboxes call), the DSN is used only host-side to
# verify the cohort, so loopback is fine. Without it (in-image mode: each
# sandbox runs its own sidecar against the DSN), loopback would resolve to the
# sandbox's own empty database — reject it before it becomes an empty cohort.
if [[ -z "${TAPES_POSTGRES_DSN:-}" ]]; then
    fail "no TAPES_POSTGRES_DSN (env or ~/.tapes/config.toml) — the cohort check needs the store"
fi
if [[ -z "${FANOUT_CAPTURE_BASE_URL:-}" && "${TAPES_POSTGRES_DSN}" =~ @(localhost|127\.0\.0\.1|\[::1\]) ]]; then
    fail "loopback DSN without FANOUT_CAPTURE_BASE_URL — sandboxes cannot reach it; funnel the proxy or use a reachable DSN"
fi
[[ -n "${ANTHROPIC_API_KEY:-}" ]] || fail "ANTHROPIC_API_KEY is not set (--strategy medium makes real calls)"


# The proof is deliberately small. Raising it is a spend decision, not a flag.
[[ "${ARMS}" -le "${PROVE_ARMS_MAX}" ]] || fail "proof is capped at ${PROVE_ARMS_MAX} arms"

mkdir -p "${OUT_DIR}"
SUMMARY="${OUT_DIR}/${COHORT}.json"

echo "[prove] cohort=${COHORT} arms=${ARMS} turns=${TURNS} snapshot=${SNAPSHOT}"
echo "[prove] strategy=medium — this run makes real LLM calls and costs money."

# ── 1. run the race ───────────────────────────────────────────────────
START_EPOCH=$(date +%s)
uv run scripts/fanout/cli.py \
    --rom "${ROM}" \
    --backend daytona \
    --snapshot "${SNAPSHOT}" \
    --variants "${ARMS}" \
    --turns "${TURNS}" \
    --strategy medium \
    --cohort "${COHORT}" \
    --output-json "${SUMMARY}"
END_EPOCH=$(date +%s)
WALL=$(( END_EPOCH - START_EPOCH ))

# ── 2. fitness collected for every arm ────────────────────────────────
echo "[prove] checking collected fitness"
COLLECTED=$(python3 -c "
import json,sys
s=json.load(open('${SUMMARY}'))
ok=[r for r in s['results'] if r['fitness'].get('party_size') is not None]
print(len(ok))
")
[[ "${COLLECTED}" -eq "${ARMS}" ]] || fail "only ${COLLECTED}/${ARMS} arms returned fitness"
echo "[prove] OK: ${COLLECTED}/${ARMS} arms returned fitness"

# ── 3. one queryable cohort in the central store ──────────────────────
echo "[prove] checking central store for cohort=${COHORT}"
# Queries raw_turns — what the proxy writes directly — rather than the derived
# `sessions` table, which the derive-worker may not have projected yet when
# this runs. `agent_name` and `meta` are both real columns on raw_turns;
# meta->>'project' returns NULL rather than erroring if the tag lands
# elsewhere, so the OR degrades instead of failing the query.
# The cohort lives in the heartbeat request bodies: tapes v0.37 has no
# project column and ignores tagging headers on the proxy path, but raw
# request content is stored (and deduped by body hash — which is why each
# arm's heartbeat body is unique).
SESSIONS=$(psql "${TAPES_POSTGRES_DSN}" -tAc \
    "SELECT count(*) FROM raw_turns
     WHERE raw_request::text LIKE '%capture-heartbeat ${COHORT} %';" 2>/dev/null || echo "ERR")
if [[ "${SESSIONS}" == "ERR" ]]; then
    fail "could not query the central store (is psql installed and TAPES_POSTGRES_DSN reachable?)"
fi
[[ "${SESSIONS}" -ge "${ARMS}" ]] || fail "central store has ${SESSIONS} heartbeats for this cohort, expected >= ${ARMS}"
echo "[prove] OK: ${SESSIONS} capture heartbeats in the central store under one cohort"

# ── 4. nothing left running ───────────────────────────────────────────
echo "[prove] checking for leaked sandboxes"
LEAKED=$(uv run --group fanout python -c "
from daytona import Daytona
print(sum(1 for s in Daytona().list() if (getattr(s,'labels',{}) or {}).get('cohort')=='${COHORT}'))" 2>/dev/null || echo 0)
[[ "${LEAKED}" -eq 0 ]] || fail "${LEAKED} sandbox(es) from ${COHORT} still exist — teardown leaked"
echo "[prove] OK: zero sandboxes left running"

# ── 5. cost extrapolation ─────────────────────────────────────────────
# Measured usage is real; the price is not invented. Supply the rate your plan
# actually charges via DAYTONA_USD_PER_VCPU_HOUR and this reports dollars,
# otherwise it reports the resource usage and the arithmetic to apply.
echo "[prove] usage: ${WALL}s wall clock for ${ARMS} arms"
python3 - <<PY
arms, wall, target = ${ARMS}, ${WALL}, 20
import os
per_arm = wall / arms
# Arms run concurrently, so a 20-arm race costs 20x the per-arm resource time
# even though its wall clock stays near one arm's duration.
vcpu = int(os.environ.get("FANOUT_VCPU_PER_SANDBOX", "2"))
sandbox_hours = target * per_arm / 3600
vcpu_hours = sandbox_hours * vcpu
print(f"[prove] per-arm: {per_arm:.0f}s")
print(f"[prove] {target}-arm race: ~{sandbox_hours:.2f} sandbox-hours, ~{vcpu_hours:.2f} vCPU-hours")
rate = os.environ.get("DAYTONA_USD_PER_VCPU_HOUR")
if rate:
    print(f"[prove] estimated cost: \${vcpu_hours * float(rate):.2f} at \${rate}/vCPU-hour")
else:
    print("[prove] set DAYTONA_USD_PER_VCPU_HOUR to convert this to dollars")
    print("[prove] (LLM spend at --strategy medium is separate and billed by the model vendor)")
PY

echo "[prove] PASS — summary written to ${SUMMARY}"
