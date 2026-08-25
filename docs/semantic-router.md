# Semantic router — the right bot for the right situation

Issue #103: put [vllm-project/semantic-router](https://github.com/vllm-project/semantic-router)
in front of the model roster so a request with model `vllm-sr/auto` lands on the model the
benchmarks say is right for that situation. The routing table **is** the skill matrix
([benchmarks/2026-08-22-skill-matrix.md](../benchmarks/2026-08-22-skill-matrix.md)) and
[model-fit.md](model-fit.md), rendered as config — every route cites a measured row, and the
tests pin the encoding to the evidence.

## The routes

| situation | model | rests on |
|---|---|---|
| battle | `laguna-xs-128k` | battle leg was 6/6 with near-identical rows — an execution baseline, so send the measured **Driver** (Haiku's cadence, reached the Gym first) |
| navigation | `qwen38-27b-128k` | 49 t / 36 HP on `mtmoon_1f_to_b1f` — dominates the nav column on both axes |
| puzzle | `kimi-k2.6:cloud` | deepest of six on the puzzle leg (B2F, 18 tiles); top puzzle screen score (0.55), and the screen ordered the expedition exactly |
| *default* | `qwen38-27b-128k` | best local operator score; the roster's proven investigator |

Change a route only with a run to point at. A verdict without a run behind it is an opinion.

## The wiring

```
pi (model vllm-sr/auto)
  → semantic-router :8899   classifies the request (keyword signals, priority strategy)
    → tapes proxy :42345    the same hop pi already uses — routed sessions stay captured
      → Ollama :11434       local models + Ollama cloud (kimi)
```

The router container reaches the tapes proxy at `host.docker.internal:42345` (the proxy binds
`0.0.0.0`, so no Ollama rebind is needed — Ollama stays on `127.0.0.1`).

## Setup

```bash
uv tool install vllm-sr                                   # once; CPU-only, drives Docker
uv run python scripts/semantic_router.py check            # config invariants
VLLM_SR_PORT_OFFSET=100 uv run python scripts/semantic_router.py serve
export SEMANTIC_ROUTER_URL=http://127.0.0.1:8999          # 8899 + the offset
uv run python scripts/semantic_router.py route --live \
    "the lane keeps bouncing on the spring, diagnose the warp anomaly"   # should say kimi
uv run python scripts/semantic_router.py register         # add vllm-sr/auto to ~/.pi/agent/models.json
```

`VLLM_SR_PORT_OFFSET=100` is required on this box: the stack wants Postgres on 5432, which
`tapes-local-postgres` owns. The offset shifts every published port, so the OpenAI endpoint
lands on **:8999** and the dashboard on :8800. First serve is slow: it pulls ~10 containers
(Milvus, Redis, Postgres, Envoy, Jaeger, Prometheus, Grafana, …) and the router downloads its
embedding classifier from HuggingFace before requests stop returning 500. Docker Hub 502s on
the Milvus pull happened once; `docker pull milvusdb/milvus:v2.3.3` and re-serve. The generated
runtime state lives in `references/.vllm-sr/` (gitignored).

Offline (no container needed): `route "text"` classifies with a mirror of the keyword signals,
and `missions` prints where each `docs/prompts/operator_prompt_skill_*.md` would land. The
container is the authority; the mirror exists for tests and dry runs.

**Verified end-to-end 2026-08-25**: all three probe texts routed to their measured winners and
returned completions from the real models; `x-vsr-selected-decision` / `x-vsr-selected-model`
response headers carry the decision trail. Two deployment findings, both encoded in the config:

- Decision conditions use `type: keyword` referencing a signal by name — accepted as guessed.
- The extproc sets the upstream request path to `chat_path` **verbatim**; a path prefix on
  `base_url` is only prepended to paths still starting with `/v1`, so it silently never applies
  when `chat_path` is custom. Hence `chat_path: /agents/pi/v1/chat/completions` with a bare
  `base_url` (found with a capture server after every upstream call 404'd).

## Benchmark discipline

A routed run carries knowledge from other runs (the matrix picked its model), so it is an
**assisted** row — label it like `ASSIST=fit` rows and never compare it against unassisted
tables (benchmarks/README.md). The interesting future row: `vllm-sr/auto` vs the best single
model over a mixed leg (e.g. `mtmoon_clear`, which contains all three situations).

## Registered surface

`register` adds provider `vllm-sr` with one model, `vllm-sr/auto` (ctx 131072 — the smallest
routed card, so a mission fits whichever model the classifier lands on). Launch a routed lane
the same way as any other model row, passing `vllm-sr/auto` as the model.
