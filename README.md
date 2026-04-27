# sec-agent

A tool-calling agent that orchestrates the [securities-recommendation](../securities-recommendation) microservice APIs and hands the collected results to the [Reasoning_LLM_TiFin](../Reasoning_LLM_TiFin) Glass-Box reasoner to produce a grounded, explainable answer.

## Project Goal

The agent's job is not to relay numbers — it is to **explain the logic and assumptions behind those numbers**. A user who asks "what is my asset breakdown?" gets a concise answer; a follow-up "how was that calculated?" gets a real explanation grounded in the API's calculation logic, not a fabricated rationale.

This is achieved by splitting the work in two:

1. **sec-agent** decides which Financial Engine and Model Portfolio APIs to call, executes the HTTP calls, and gathers raw outputs. (This repo.)
2. **Reasoning_LLM_TiFin** Glass-Box pipeline (Reasoner → Answerer → optional Verifier) takes those outputs plus the matching API descriptions and produces the user-facing answer.

The tool-calling LLM never writes the final answer. The Glass-Box Reasoner does.

## Architecture

```
                     User Query (+ optional session_id)
                              │
                              ▼
         ┌────────────────────────────────────────────────────┐
         │ Agent.run() — main.py                              │
         │  1. Load SessionState (history + cache) by id      │
         │  2. Prepend prior turns to tool-LLM messages       │
         │  3. Tool-calling LLM picks FE/MP tool(s)           │
         │  4. APIClient executes HTTP POST per call          │
         │  5. Loop until LLM emits text or max_iters         │
         └────────────────────────────────────────────────────┘
                              │
                              │ tool_results
                              ▼
         ┌────────────────────────────────────────────────────┐
         │ ReasoningAdapter — reasoning_adapter.py            │
         │  - build_inputs: tool_results → (api_keys,         │
         │    user_outputs, unmapped) using static map        │
         │  - merge with SessionState cache                   │
         │  - asyncio.to_thread(model.ask, ...)               │
         └────────────────────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────────────────────┐
         │ Glass-Box (Reasoning_LLM_TiFin, sibling repo)      │
         │  TwoLayerGlassBoxModel       (default)             │
         │   Reasoner → Answerer                              │
         │  ThreeLayerGlassBoxModel     (REASONING_ARCH=…)    │
         │   Reasoner → Answerer → Verifier (≤2 retries)      │
         └────────────────────────────────────────────────────┘
                              │
                              ▼
                     answer + reasoning_trace
```

The tool-calling LLM only plans tool calls. The Glass-Box Reasoner+Answerer (and optional Verifier) produce the user-facing answer from the live tool outputs plus the static API descriptions in `Reasoning_LLM_TiFin/services/glass_box/data/all_api_descriptions.json`.

## Glass-Box Reasoning Integration

### What Reasoning_LLM_TiFin provides

- `TwoLayerGlassBoxModel` (`model_two_layer.py`) — Reasoner produces a structured trace; Answerer writes the user-facing reply from the trace.
- `ThreeLayerGlassBoxModel` (`model_three_layer.py`) — adds a Verifier that checks the answer against raw API outputs and retries the Reasoner up to 2 times on FAIL.
- `services/glass_box/data/all_api_descriptions.json` — calculation logic and field descriptions for every FE/MP API key the Reasoner is allowed to ground against.
- Bundled filtered outputs and prompt templates (used internally; sec-agent supplies live outputs at call time, not the bundled ones).

### How sec-agent uses it

`reasoning_adapter.py` is the bridge. It does not pip-install the Glass-Box repo — the sibling path `../Reasoning_LLM_TiFin` is prepended to `sys.path` at import time. The Glass-Box model classes are synchronous, so `Agent.run()` invokes them through `asyncio.to_thread` to avoid blocking the FastAPI event loop. A single Glass-Box model is lazy-instantiated as a module-level singleton.

The adapter exposes two public entry points:

```python
api_keys, user_outputs, unmapped = ReasoningAdapter.build_inputs(tool_results)
result = await adapter.answer(
    question=question,
    api_keys=api_keys,           # may be merged with session cache
    user_outputs=user_outputs,
    history=session.history,
    history_traces=session.history_traces,
)
```

`result` contains `answer`, `reasoning_trace`, `api_keys`, `verifier_verdict`, `verifier_retries`, `unmapped_tools`.

### Tool → Glass-Box api_key mapping

Each active sec-agent tool resolves to an api_key the Reasoner can ground against. Full logic in `reasoning_adapter.py::_resolve_api_key`; summary:

| sec-agent tool (params) | Glass-Box api_key |
|---|---|
| `financial_engine` (`function=<X>`) | `<X>` (e.g. `asset_breakdown`, `sector_breakdown`, …10 functions) |
| `get_portfolio_options` (`investment_type=LUMP_SUM`) | `get_portfolio_options_lumpsum` |
| `get_portfolio_options` (`investment_type=SIP`) | `get_portfolio_options_sip` |
| `backtest_portfolio` | `backtest_selected_portfolio` |
| `portfolio_builder`, `get_risk_profile`, `risk_profile_v2`, `multi_goal_optimizer`, `stock_to_fund` | same name |
| `single_goal_optimizer`, `goal_defaults` | base name (no scenario suffix) |

A pre-flight test (`tests/test_reasoning_adapter.py::TestDescriptionCoverage`) fails if any active tool maps to an api_key with no Glass-Box description.

### Architecture toggle

```env
REASONING_ARCHITECTURE=two_layer   # default — Reasoner + Answerer
REASONING_ARCHITECTURE=three_layer # Reasoner + Answerer + Verifier (≤2 retries)
```

Three-layer adds 1 LLM call per attempt and up to 2 full retries on FAIL — slower but stricter grounding. Verifier verdict and retry count are surfaced in `debug.reasoning`.

### Session memory and follow-ups

`session_store.py` is an in-memory dict keyed by `session_id`. Per session it holds:

- `history` — Answerer-facing user/assistant pairs
- `history_traces` — Reasoner-facing user/trace pairs
- `last_api_keys`, `last_user_outputs` — cache of the most recent reasoning inputs

When a follow-up turn arrives on the same `session_id`:

- Prior `history` is prepended to the tool-LLM messages so it understands references like "how was that calculated?".
- If the tool-LLM decides not to call any tool, the adapter still runs against the cached `api_keys`/`user_outputs` so the Reasoner can answer from the prior evidence and prior trace.
- If the tool-LLM does fire a fresh call, the new inputs are merged with the cache so the Reasoner sees both old and new evidence.

History is trimmed to `max_turns × 2` messages (default 10 turns). No `session_id` → ephemeral, no continuity. This is a Phase 2 prototype store; production should swap it for Redis / Postgres / app-session-service.

## Integration Progress

Tracking the [integration plan](../sec_agent_reasoning_llm_integration_plan.md):

| Phase | Scope | Status |
|---|---|---|
| 1 — Adapter prototype | Tool prune to FE/MP, `reasoning_adapter.py`, wire `main.py`, `session_id` field | **Done** |
| 2 — Session memory | `session_store.py`, history injection, follow-up cache reuse, trimming | **Done** |
| 3 — Three-layer verification | `REASONING_ARCHITECTURE` toggle, verifier metadata in `debug.reasoning` | **Done** |
| 4 — Description update pipeline | `update_api_descriptions.py`, JSON validation, GitHub Actions | **Pending** (handed off) |

Unit test coverage: 83 tests across `test_reasoning_adapter`, `test_session_store`, `test_agent_unit`, `test_agent_session`, `test_tools_registry`, `test_api_client`, `test_fastapi_app`.

Live verification (real GLM-4.7-Flash + backend round-trip) not yet run — same caveat as the original Phase 1 plan.

## Project Structure

```
sec-agent/
├── main.py                # FastAPI app + Agent orchestrator (tool loop + reasoner handoff)
├── tools.py               # TOOLS registry (20 entries) + ACTIVE_TOOLS allowlist + get_openai_tools()
├── prompts.py             # SYSTEM_PROMPT for the tool-calling LLM (FE/MP scope only)
├── models.py              # AskRequest / AskResponse Pydantic models (with session_id)
├── api_client.py          # Async HTTP client for backend microservice calls
├── reasoning_adapter.py   # Bridge to Reasoning_LLM_TiFin Glass-Box models
├── session_store.py       # In-memory per-session history + cache (Phase 2 prototype)
├── config.py              # Settings (env-based, includes REASONING_ARCHITECTURE)
├── tests/
│   ├── conftest.py
│   ├── test_agent_unit.py                    # Agent.run with stubbed LLM + reasoner
│   ├── test_agent_session.py                 # Session continuity, isolation, trimming
│   ├── test_agent_e2e.py                     # End-to-end against live LLM/backend
│   ├── test_reasoning_adapter.py             # Mapping, build_inputs, verifier propagation
│   ├── test_session_store.py                 # Per-session state semantics
│   ├── test_tools_registry.py                # Active vs reserved, schema validity
│   ├── test_api_client.py
│   ├── test_fastapi_app.py
│   ├── test_parameter_extraction.py
│   ├── test_tool_selection_single.py         # Glass-Box single-tool LLM cases
│   ├── test_tool_selection_multi.py          # Glass-Box multi-tool LLM cases
│   ├── test_tool_selection_disambiguation.py # Negative tool-routing assertions
│   ├── test_tool_selection_src.py            # SRC reference suite (tools currently reserved)
│   └── test_tool_selection_ml.py             # ML reference suite (tool currently reserved)
├── docs/
│   ├── demo-queries.md    # Glass-Box-aligned demo queries
│   └── test-queries.md    # Per-tool query reference
├── pyproject.toml
└── .env.example
```

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- `Reasoning_LLM_TiFin` checked out as a sibling directory (sec-agent imports it via `sys.path` — no pip install)
- An OpenAI-compatible LLM endpoint with native function calling and a context window large enough for ~10 tool schemas (self-hosted GLM-4.7-Flash recommended)
- Backend `securities-recommendation` services running locally or deployed
- **GCP service account key** if backends run locally (S2S auth to upstream APIs)

### Setup

```bash
cd sec-agent

# Install dependencies
uv sync

# Copy env template and configure
cp .env.example .env
# Edit .env — set LLM_BASE_URL, LLM_API_KEY, REASONING_ARCHITECTURE

# Start the agent
uv run uvicorn main:app --port 8090 --reload
```

### Test

```bash
# Asset breakdown — routes through financial_engine -> Reasoner -> Answerer
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show asset breakdown for user 1912650190", "session_id": "demo-1"}' \
  | python3 -m json.tool

# Follow-up on the same session — should NOT re-fire the tool;
# the cached outputs and prior trace are reused by the Reasoner.
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "How was that calculated?", "session_id": "demo-1"}' \
  | python3 -m json.tool
```

### Test User IDs

| User ID | Has Portfolio Data | Notes |
|---------|-------------------|-------|
| `1912650190` | Yes | Reference user that Glass-Box's session evidence was built around |

## Configuration

All config is via `.env` (or system env). See `.env.example` for the full list.

| Variable | Default | Description |
|---|---|---|
| `API_BASE_URL` | `http://localhost:8089` | securities-recommendation base URL |
| `LLM_BASE_URL` | `http://103.42.51.88:2205/` | OpenAI-compatible LLM endpoint |
| `LLM_API_KEY` | `anything works` | LLM key (dummy for self-hosted) |
| `LLM_MODEL` | `orchestrator` | Model name on the LLM endpoint |
| `LLM_TEMPERATURE` | `0.2` | Tool-calling LLM temperature |
| `LLM_MAX_TOKENS` | `16384` | Max tokens for tool-calling LLM |
| `ENABLE_AUTH` | `false` | Enable S2S auth for deployed backends |
| `LOCAL_MODE` | `false` | Strip `/cr/<service>` prefixes for direct local backends |
| `REASONING_ARCHITECTURE` | `two_layer` | Glass-Box pipeline: `two_layer` or `three_layer` |

### LLM Provider Notes

The tool-calling LLM uses any OpenAI-compatible API with native function calling. The active 10 tool schemas are small enough for most providers, but the Glass-Box Reasoner inside `Reasoning_LLM_TiFin` separately calls its own provider (controlled by Glass-Box's own `MODEL_PROVIDER` env). They can be the same endpoint or different.

**Self-hosted GPU (recommended — GLM-4.7-Flash via vLLM):**
```env
LLM_BASE_URL=http://103.42.51.88:2205/
LLM_API_KEY=anything works
LLM_MODEL=orchestrator
```

> The self-hosted GPU is reachable only from GCP infrastructure or company VPN.

## Available Tools

The full `TOOLS` registry holds 20 entries; only the 10 with matching Glass-Box descriptions are exposed to the LLM via `ACTIVE_TOOLS` (see `tools.py`). The rest stay in the registry as a reference / placeholder for re-enablement once descriptions exist.

### Active (10) — Financial Engine + Model Portfolio

| Tool | Service | Endpoint | Glass-Box api_key |
|---|---|---|---|
| `financial_engine` | Fin Engine | `/cr/fin-engine/financial_engine` | dispatches to 10 FE function names |
| `get_portfolio_options` | Model Portfolio | `/cr/model-portfolio/get_portfolio_options` | `get_portfolio_options_lumpsum` / `_sip` |
| `backtest_portfolio` | Model Portfolio | `/cr/model-portfolio/backtest_selected_portfolio` | `backtest_selected_portfolio` |
| `portfolio_builder` | Model Portfolio | `/cr/model-portfolio/portfolio_builder` | `portfolio_builder` |
| `get_risk_profile` | Model Portfolio | `/cr/model-portfolio/get_risk_profile` | `get_risk_profile` |
| `risk_profile_v2` | Model Portfolio | `/cr/model-portfolio/risk_profile_v2` | `risk_profile_v2` |
| `single_goal_optimizer` | Model Portfolio | `/cr/model-portfolio/single_goal_optimizer` | `single_goal_optimizer` |
| `multi_goal_optimizer` | Model Portfolio | `/cr/model-portfolio/multi_goal_optimizer` | `multi_goal_optimizer` |
| `goal_defaults` | Model Portfolio | `/cr/model-portfolio/goal_defaults` | `goal_defaults` |
| `stock_to_fund` | Model Portfolio | `/cr/model-portfolio/stock_to_fund` | `stock_to_fund` |

### Reserved (10) — registry entries not exposed to the LLM

These remain in `TOOLS` but are filtered out of the OpenAI schema. Excluded reasons:

- **No Glass-Box description** — Reasoner has nothing to ground against (SRC, ML, `determine_income_sector`).
- **Backend broken** — `build_stock_portfolio` always returns HTTP 500 (see `Reasoning_LLM_TiFin/CLAUDE.md`).

| Tool | Service | Reason reserved |
|---|---|---|
| `search_funds` | SRC | No Glass-Box description |
| `swap_recommendations` | SRC | No Glass-Box description |
| `portfolio_swap_recommendations` | SRC | No Glass-Box description |
| `get_fund_peers` | SRC | No Glass-Box description |
| `stock_research_data` | SRC | No Glass-Box description |
| `parse_query` | SRC | No Glass-Box description |
| `can_support` | SRC | No Glass-Box description |
| `ml_fund_discovery` | ML | No Glass-Box description |
| `determine_income_sector` | Model Portfolio | Utility, no Glass-Box description |
| `build_stock_portfolio` | Model Portfolio | Backend always 500s |

To re-enable a reserved tool: add a description to `Reasoning_LLM_TiFin/services/glass_box/data/all_api_descriptions.json`, add a mapping in `reasoning_adapter.py::_resolve_api_key` if the api_key differs, then add the tool name to `ACTIVE_TOOLS`. The `TestDescriptionCoverage` test will fail if any of those steps is missing.

### Financial Engine Functions

The `financial_engine` tool dispatches via the `function` param. All 10 functions have Glass-Box descriptions and are exercised by the active tool: `asset_breakdown`, `diversification`, `sector_breakdown`, `market_cap_breakdown`, `single_holding_exposure`, `total_stock_exposure`, `amc_preference`, `sector_preference`, `theme_preference`, `factor_preference`. See [CONTRIBUTING.md](CONTRIBUTING.md#financial-engine-test-payloads) for example payloads.

## API

### `POST /ask`

**Request:**
```json
{
  "query": "Show asset breakdown for user 1912650190",
  "max_iters": 3,
  "session_id": "demo-1"
}
```

`session_id` is optional. With it, follow-up turns reuse prior history and the Reasoner cache. Without it, each call is stateless.

**Response:**
```json
{
  "answer": "Your portfolio is almost entirely in equity at 99.14% ...",
  "session_id": "demo-1",
  "debug": {
    "iterations": [
      {"iteration": 1,
       "tool_calls": [{"tool": "financial_engine",
                       "params": {"function": "asset_breakdown",
                                  "parameters": {"user_id": "1912650190"}}}]}
    ],
    "tool_results": [
      {"tool": "financial_engine",
       "params": {"function": "asset_breakdown", "parameters": {"user_id": "1912650190"}},
       "result": {"asset_breakdown": {"equity": 99.14, "debt": 0.21, "...": "..."}}}
    ],
    "reasoning": {
      "api_keys": ["asset_breakdown"],
      "trace": "EVIDENCE: equity=99.14%, debt=0.21% ...\nCONCLUSION: ...",
      "verifier_verdict": null,
      "verifier_retries": 0,
      "unmapped_tools": []
    }
  }
}
```

On a follow-up turn that reuses the session cache, `debug.tool_results` is empty and `debug.reused_session_cache` is `true`. `verifier_verdict` and `verifier_retries` populate only when `REASONING_ARCHITECTURE=three_layer`.

### `GET /health`

Returns `{"status": "ok", "service": "sec-agent"}`.

## Relationship to Other Repos

| Repo | Relationship | How sec-agent uses it |
|---|---|---|
| [`securities-recommendation`](../securities-recommendation) | Backend microservices (sibling) | Pure HTTP consumer via `APIClient`. No code import. |
| [`Reasoning_LLM_TiFin`](../Reasoning_LLM_TiFin) | Glass-Box reasoning library (sibling) | Imported through `sys.path` shim in `reasoning_adapter.py`. The adapter calls the Glass-Box model classes directly; sec-agent supplies live tool outputs (not the bundled filtered ones) and per-session histories. |

For deeper detail on the Glass-Box internals (Reasoner / Answerer / Verifier prompts, retry loop, description JSON schema), see `Reasoning_LLM_TiFin/ARCHITECTURE.md`.
