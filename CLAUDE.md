# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Repository Overview

sec-agent is a tool-calling agent for the `securities-recommendation` Financial Engine and Model Portfolio APIs. The tool-calling LLM only **plans** and **executes** tool calls; the user-facing answer is produced by the Glass-Box reasoner in the sibling [`Reasoning_LLM_TiFin`](../Reasoning_LLM_TiFin) repo. This split is the integration described in `../sec_agent_reasoning_llm_integration_plan.md`.

## Project Goal

Explain the logic and assumptions behind API results — not just relay numbers. The Glass-Box Reasoner+Answerer (and optional Verifier) take live tool outputs plus the static API descriptions in `Reasoning_LLM_TiFin/services/glass_box/data/all_api_descriptions.json` and produce a grounded answer. Follow-up questions ("how was that calculated?") reuse the prior cache and trace via the per-`session_id` `SessionStore`.

Integration progress (full table in `README.md#integration-progress`):

| Phase | Scope | Status |
|---|---|---|
| 1 | Adapter prototype + tool prune | Done |
| 2 | Session memory + follow-up cache reuse | Done |
| 3 | Three-layer verifier toggle | Done |
| 4 | Description update pipeline + GitHub Actions | Pending (handed off) |

## CRITICAL: Git Rules

- **NEVER** use `git add -A`, `git add .`, or `git add --all`. Always add files explicitly by name.
- **NEVER** commit `.env` files or credentials.
- **NEVER** force-push to `main`.

## Common Commands

```bash
# Install dependencies
uv sync

# Run the server (default REASONING_ARCHITECTURE=two_layer)
uv run uvicorn main:app --port 8090 --reload

# Run with the three-layer verifier pipeline
REASONING_ARCHITECTURE=three_layer uv run uvicorn main:app --port 8090 --reload

# Quick syntax / import check
uv run python -c "from main import app; print('OK')"

# Pure unit tests (no LLM, no backend)
uv run pytest tests/ -m "unit and not llm and not e2e"

# LLM tool-selection regressions (needs LLM endpoint)
uv run pytest tests/ -m llm

# Deterministic single-shot instead of 3-run majority vote
STRICT_MODE=1 uv run pytest tests/ -m llm

# End-to-end smoke against the live backend + LLM (use the reference user)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show asset breakdown for user 1912650190", "session_id": "smoke-1"}'

# Follow-up on the same session — should NOT re-fire the tool
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "How was that calculated?", "session_id": "smoke-1"}'
```

## Architecture

```
main.py                → Agent class (tool-call loop + reasoner handoff) + FastAPI /ask endpoint
tools.py               → TOOLS dict (20 entries) + ACTIVE_TOOLS allowlist (10) + get_openai_tools()
prompts.py             → SYSTEM_PROMPT for the tool-calling LLM (FE/MP scope only; out-of-scope handler)
api_client.py          → APIClient class (aiohttp POST to backend microservices)
config.py              → Settings (env-based, includes REASONING_ARCHITECTURE)
models.py              → AskRequest / AskResponse Pydantic models (with session_id)
reasoning_adapter.py   → Bridge to Reasoning_LLM_TiFin: tool->api_key mapping, build_inputs,
                         model singleton, asyncio.to_thread wrap of sync Glass-Box ask()
session_store.py       → In-memory per-session history + last_api_keys/user_outputs cache + trim
                         (Phase 2 prototype; production should swap for Redis/Postgres)

tests/
├── conftest.py
├── test_agent_unit.py                    → Agent.run with stubbed LLM + reasoner
├── test_agent_session.py                 → Session continuity, isolation, trimming
├── test_agent_e2e.py                     → End-to-end against live LLM/backend
├── test_reasoning_adapter.py             → Mapping, build_inputs, verifier metadata propagation
├── test_session_store.py                 → Per-session state semantics
├── test_tools_registry.py                → Active vs reserved, schema validity, no SRC/ML active
├── test_api_client.py
├── test_fastapi_app.py
├── test_parameter_extraction.py
├── test_tool_selection_single.py         → Glass-Box-aligned single-tool LLM cases
├── test_tool_selection_multi.py          → Glass-Box-aligned multi-tool LLM cases
├── test_tool_selection_disambiguation.py → Negative tool-routing assertions
├── test_tool_selection_src.py            → SRC reference suite (tools currently reserved)
└── test_tool_selection_ml.py             → ML reference suite (tool currently reserved)
```

**Data flow:**
```
User query (+ session_id?)
  → Agent.run loads SessionState, prepends prior history
  → Tool-calling LLM picks FE/MP tool(s)
  → APIClient executes HTTP POST per call
  → Loop until LLM emits text or max_iters
  → ReasoningAdapter.build_inputs(tool_results) → (api_keys, user_outputs, unmapped)
  → Merge with SessionState cache
  → asyncio.to_thread(model.ask, ...)  ← Glass-Box Reasoner+Answerer (and optional Verifier)
  → Persist updated cache, trim history
  → AskResponse(answer, session_id, debug={iterations, tool_results, reasoning})
```

If no tool was called AND the session has no prior cache, the assistant's text reply is returned directly (out-of-scope path) and the reasoner is skipped.

## Key Patterns

### Tool Registry + Active Allowlist (`tools.py`)

- `TOOLS` holds 20 entries (FE, MP, SRC, ML, utilities). Adding an entry makes it dispatchable but NOT visible to the LLM.
- `ACTIVE_TOOLS` is the allowlist filtered by `get_openai_tools()`. Currently the 10 FE/MP tools that have a matching Glass-Box description.
- Reserved tools (SRC, ML, `determine_income_sector`, `build_stock_portfolio`) stay in `TOOLS` for re-enablement but are not exposed to the LLM.
- `tests/test_tools_registry.py::test_no_src_or_ml_tools_active` enforces this gating.

### Adapter Mapping (`reasoning_adapter.py`)

- `_resolve_api_key(tool_name, params)` is the single source of truth for tool→Glass-Box api_key mapping. `financial_engine` dispatches via `params["function"]`; `get_portfolio_options` splits into `_lumpsum`/`_sip` based on `investment_type`; `backtest_portfolio` renames to `backtest_selected_portfolio`; goal optimizers use base names.
- `build_inputs` is a public static — main.py calls it explicitly so it can merge with the SessionStore cache before calling `answer`.
- `_get_model()` lazy-instantiates `TwoLayerGlassBoxModel` or `ThreeLayerGlassBoxModel` based on `settings.REASONING_ARCHITECTURE`. The model is a module-level singleton; `reset_model_singleton()` is a test helper.

### Agent Orchestration (`main.py`)

- `Agent.run(user_query, max_iters, session_id)` loads SessionState, prepends prior history into tool-LLM messages, runs the tool loop, then routes to the reasoner.
- Three post-loop branches:
  1. Tool calls fired → `build_inputs` → merge with cache → reasoner.
  2. No tool calls + cache exists → reasoner over cached inputs (follow-up).
  3. No tool calls + no cache → return assistant text directly (out-of-scope).
- After reasoning, the merged `api_keys` and `user_outputs` replace the session cache; history is trimmed.
- The Glass-Box `model.ask` mutates `history` and `history_traces` in place — the SessionStore lists are passed by reference so the new turn lands in the store automatically.

### Session Store (`session_store.py`)

- Dict-backed, keyed by `session_id`. `SessionState` holds `history`, `history_traces`, `last_api_keys`, `last_user_outputs`.
- `trim(state)` mutates `state.history[:]` and `state.history_traces[:]` in place — DO NOT replace the list objects, the Reasoner holds references.
- `max_turns` defaults to 10 (= 20 messages each).
- Production should replace with Redis / Postgres / app session service (plan §298).

### Configuration

- All settings via `.env` (loaded by pydantic-settings).
- `extra=ignore` in `Settings.model_config` so the same `.env` can hold Glass-Box vars (`MODEL_PROVIDER`, `GPU_BASE_URL`, etc.) without breaking sec-agent startup.
- `ENABLE_AUTH=false` for local dev, `true` for deployed services.
- `REASONING_ARCHITECTURE=two_layer|three_layer` selects the Glass-Box pipeline.
- Self-hosted GPU is the recommended LLM (Groq context window is too small for the historical 20-tool schema; with 10 active tools it could fit, but not validated).

## Dependencies on Other Repos

- **`securities-recommendation`** (sibling) — backend microservices the agent calls over HTTP. No code import.
- **`Reasoning_LLM_TiFin`** (sibling) — Glass-Box reasoner. Imported via `sys.path` shim in `reasoning_adapter.py`. The repo MUST exist at `../Reasoning_LLM_TiFin` or `reasoning_adapter` import will fail. sec-agent uses the model classes directly (`TwoLayerGlassBoxModel`, `ThreeLayerGlassBoxModel`), supplies live tool outputs (not the bundled `filtered_outputs_*.json`), and owns the per-session history that the model mutates in place.

## Upstream API Services

The agent calls these services (must be running):

| Service | Local URL | Deployed URL |
|---|---|---|
| Financial Engine | `http://localhost:8089/cr/fin-engine/` | `https://api.askmyfi.com/cr/fin-engine/` |
| Model Portfolio | `http://localhost:8089/cr/model-portfolio/` | `https://api.askmyfi.com/cr/model-portfolio/` |
| SRC | `http://localhost:8089/cr/src/` | `https://api.askmyfi.com/cr/src/` (reserved) |
| ML Recommendations | `http://localhost:8089/cr/mlr/` | `https://api.askmyfi.com/cr/mlr/` (reserved) |

SRC and ML are listed because their tool entries still exist in `TOOLS`, but `ACTIVE_TOOLS` does not expose them to the LLM today (no Glass-Box descriptions).

## LLM Access

Two separate LLMs are involved:

1. **Tool-calling LLM** (sec-agent's `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`). Needs native function calling. Default: self-hosted GLM-4.7-Flash via vLLM at `http://103.42.51.88:2205/`. Reachable from GCP / company VPN only.
2. **Glass-Box LLM** (configured inside `Reasoning_LLM_TiFin` via `MODEL_PROVIDER`, `GPU_BASE_URL`, `OPENAI_API_KEY`). Used by the Reasoner / Answerer / Verifier. Can be the same endpoint as #1 or different.

The agent's LLM is separate from the backend services' own LLM dependencies. Some SRC and Model Portfolio endpoints call the self-hosted GPU for NER parsing — those won't work without VPN access regardless of which LLM the agent uses. Financial Engine and ML Recommendations have no backend-side LLM dependencies.

## GCP Credentials

Backend services call external APIs (portfolio data, security master) that require S2S authentication:

```bash
export GOOGLE_APPLICATION_CREDENTIALS='/path/to/gcp-key-dev.json'
```

Without this, running backend services locally produces 500s.

## Important: What NOT to Do

- Do not let the tool-calling LLM write the user-facing answer. Final answers come from the Glass-Box Answerer. `prompts.py::SYSTEM_PROMPT` explicitly tells the LLM to acknowledge tool outputs only.
- Do not add a tool to `ACTIVE_TOOLS` without also adding (a) an adapter mapping in `reasoning_adapter.py::_resolve_api_key`, (b) a Glass-Box description in `Reasoning_LLM_TiFin/services/glass_box/data/all_api_descriptions.json`, and (c) a sample invocation in `tests/test_reasoning_adapter.py::_SAMPLE_INVOCATIONS`.
- Do not edit Glass-Box prompts (Reasoner / Answerer / Verifier) from this repo — they live in `Reasoning_LLM_TiFin/services/glass_box/data/system_prompt_*.md`.
- Do not import code from `securities-recommendation` — communicate only via HTTP through `APIClient`.
- Do not hardcode API responses or mock data in production code.
- Do not replace `state.history` with a new list inside the SessionStore (the Reasoner already holds a reference); mutate with `state.history[:] = ...`.
- Do not assume `session_id` is supplied — the agent must run statelessly when it's omitted.
- Do not add organization-specific routing (this agent is org-agnostic by design).
