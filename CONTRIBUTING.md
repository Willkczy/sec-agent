# Contributing Guide

## Project Goal

The agent's job is not to relay numbers — it is to **explain the logic and assumptions behind those numbers**. This is achieved by handing the live tool outputs to the [Reasoning_LLM_TiFin](../Reasoning_LLM_TiFin) Glass-Box reasoner; the tool-calling LLM never writes the final answer.

When evaluating a contribution, ask: "does this preserve the boundary between tool selection (this repo) and answer reasoning (Glass-Box)?" See [README.md](README.md#glass-box-reasoning-integration) for the integration overview and [README's Integration Progress table](README.md#integration-progress) for what's done and what's pending.

## Development Setup

```bash
# Clone the sibling repos so sys.path can find Reasoning_LLM_TiFin
# Layout expected:
#   Capstone/
#     sec-agent/
#     Reasoning_LLM_TiFin/
#     securities-recommendation/

cd sec-agent

# Install dependencies with uv
uv sync

# Copy environment config
cp .env.example .env
# Edit .env — at minimum set LLM_BASE_URL, LLM_API_KEY, REASONING_ARCHITECTURE.
# For separate local backend services, also set:
# LOCAL_MODE=true
# FIN_ENGINE_BASE_URL=http://localhost:8080
# MODEL_PORTFOLIO_BASE_URL=http://localhost:8081

# Run the server locally
uv run uvicorn main:app --port 8090 --reload
```

`reasoning_adapter.py` adds `../Reasoning_LLM_TiFin` to `sys.path` at import time — there is no pip install. The Glass-Box repo must exist at the sibling path or the agent will fail at startup.

### GCP Credentials

Backend services (`securities-recommendation`) call external APIs that require GCP S2S authentication. To run them locally:

```bash
# Option 1: Service account key (recommended)
export GOOGLE_APPLICATION_CREDENTIALS='/path/to/gcp-key-dev.json'

# Option 2: gcloud CLI
gcloud auth application-default login
```

Without this, backend services return 500s when fetching user portfolios or security data.

### Running Backend Services

You only need to run the service(s) relevant to the tools you're testing.

For deployed backends, point `API_BASE_URL` at the gateway and leave `LOCAL_MODE=false`:

```env
API_BASE_URL=https://api.askmyfi.dev
LOCAL_MODE=false
```

For local backend services on separate ports, use the service-specific base URLs:

```env
LOCAL_MODE=true
API_BASE_URL=http://localhost:8089
FIN_ENGINE_BASE_URL=http://localhost:8080
MODEL_PORTFOLIO_BASE_URL=http://localhost:8081
```

Then start the backend services in separate terminals:

```bash
cd ../securities-recommendation

# Financial Engine
python3 run_service.py fin-engine --env dev --port 8080

# Model Portfolio
python3 run_service.py model-portfolio --env dev --port 8081
```

`APIClient` routes `/cr/fin-engine/...` to `FIN_ENGINE_BASE_URL` and `/cr/model-portfolio/...` to `MODEL_PORTFOLIO_BASE_URL` when `LOCAL_MODE=true`. `API_BASE_URL` remains the fallback.

Only Financial Engine and Model Portfolio are exercised by `ACTIVE_TOOLS`. SRC and ML services are reserved (see README).

## Git Workflow

### Branch Naming

```
feature/<short-description>    # New features
fix/<short-description>        # Bug fixes
refactor/<short-description>   # Code refactoring
docs/<short-description>       # Documentation only
```

### Commit Messages

Imperative mood, first line under 72 chars:

```
Add session_id field to AskRequest
Fix verifier feedback not propagated on retry
Update reasoning adapter mapping for goal_defaults
```

### Pull Requests

1. Branch from `main`
2. Keep PRs focused — one feature/fix per PR
3. Test locally against `securities-recommendation` services and the Glass-Box reasoner
4. Open a PR with a clear description of what changed and why
5. Request review from at least one teammate

### Git Rules

- **Never** `git add -A` or `git add .` — always add files explicitly
- **Never** commit `.env` files or credentials
- **Never** force-push to `main`

## Project Conventions

### Code Style

- Python 3.12+ features (`dict[str, Any]`, `X | None`, etc.)
- Type annotations on all function signatures
- `async/await` for I/O (HTTP calls, LLM calls); sync Glass-Box calls go through `asyncio.to_thread` in the adapter
- Keep functions short and focused

### File Responsibilities

| File | Owns | Does NOT own |
|---|---|---|
| `tools.py` | `TOOLS` registry, `ACTIVE_TOOLS` allowlist, OpenAI schema conversion | HTTP calls, LLM calls, api_key resolution |
| `api_client.py` | HTTP requests to backend microservices | Tool selection, response formatting |
| `prompts.py` | System prompt for the **tool-calling LLM only** (not the Reasoner/Answerer) | Reasoner/Answerer prompts (those live in `Reasoning_LLM_TiFin`) |
| `main.py` | Tool-call loop, session loading, hand-off to reasoner, FastAPI app | Tool schemas, prompt text, mapping logic |
| `config.py` | Settings + env loading (includes `REASONING_ARCHITECTURE`) | Business logic |
| `models.py` | `AskRequest` / `AskResponse` Pydantic models | Validation logic beyond types |
| `reasoning_adapter.py` | sec-agent ↔ Glass-Box bridge: tool→api_key mapping, output unwrap, model singleton, `build_inputs` + `answer` | Glass-Box prompts or model internals |
| `session_store.py` | Per-`session_id` history + cache + trimming | Reasoning, tool calls, persistence |

### Adding a New Tool

A new active tool needs five touchpoints. The validation tests will fail until all required pieces are in place.

1. **Add to `TOOLS` in `tools.py`** — description, endpoint, method, parameter schema. This makes it dispatchable.

   ```python
   "new_tool_name": {
       "description": "What this tool does (visible to the LLM)",
       "endpoint": "/cr/service-name/endpoint-path",
       "method": "POST",
       "parameters": {
           "param_name": {
               "type": "string",
               "required": True,
               "description": "What this param is for",
           },
       },
   },
   ```

2. **Add to `ACTIVE_TOOLS` in `tools.py`** — the allowlist filters which tools are exposed to the LLM via `get_openai_tools()`.

3. **Add adapter mapping in `reasoning_adapter.py`** — if the tool name matches the Glass-Box api_key, just add to `_DIRECT_TOOL_TO_KEY`. If the tool dispatches via a parameter (like `financial_engine` does on `function`), or splits into multiple api_keys (like `get_portfolio_options` does on `investment_type`), add a branch in `_resolve_api_key`.

4. **Add a description in `Reasoning_LLM_TiFin/services/glass_box/data/all_api_descriptions.json`** — the Reasoner needs `name`, `service`, `description`, `parameters`, `calculation_logic`, `response`. Without this entry, `tests/test_reasoning_adapter.py::TestDescriptionCoverage` will fail.

5. **Add a sample invocation in `_SAMPLE_INVOCATIONS`** in `tests/test_reasoning_adapter.py` so the description-coverage test exercises the new branch.

### Modifying Prompts

- `prompts.py::SYSTEM_PROMPT` is for the **tool-calling LLM only**. It controls tool selection and the out-of-scope handler. It does NOT write the user-facing answer.
- Reasoner / Answerer / Verifier prompts live in `Reasoning_LLM_TiFin/services/glass_box/data/system_prompt_*.md`. To change how the Glass-Box reasons, edit those files in that repo, not here.
- After changing `SYSTEM_PROMPT`, run the LLM-marked tool-selection tests to check for routing regressions:

  ```bash
  uv run pytest tests/test_tool_selection_single.py tests/test_tool_selection_multi.py tests/test_tool_selection_disambiguation.py -m llm
  ```

### Switching LLM Provider

- The **tool-calling LLM** is set in sec-agent's `.env` (`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`). Any OpenAI-compatible API with native function calling works.
- The **Glass-Box LLM** is set independently inside `Reasoning_LLM_TiFin` (`MODEL_PROVIDER`, `GPU_BASE_URL`, `OPENAI_API_KEY`). Both can point at the same endpoint or different ones.

### Reasoning Architecture Toggle

```env
REASONING_ARCHITECTURE=two_layer   # default — Reasoner + Answerer
REASONING_ARCHITECTURE=three_layer # adds Verifier with up to 2 retries
```

Three-layer is slower but stricter. `debug.reasoning.verifier_verdict` and `verifier_retries` populate when the three-layer pipeline is active. The model is lazy-instantiated as a module-level singleton; restart the process to pick up a new architecture value.

## Testing

### Test Layout

```
tests/
├── conftest.py
├── test_agent_unit.py                    # Agent.run with stubbed LLM + reasoner
├── test_agent_session.py                 # Session continuity, isolation, trimming
├── test_agent_e2e.py                     # End-to-end against live LLM/backend
├── test_reasoning_adapter.py             # Mapping, build_inputs, verifier metadata
├── test_session_store.py                 # Per-session state semantics
├── test_tools_registry.py                # Active vs reserved, schema validity
├── test_api_client.py
├── test_fastapi_app.py
├── test_parameter_extraction.py
├── test_tool_selection_single.py         # Glass-Box-aligned single-tool LLM cases
├── test_tool_selection_multi.py          # Glass-Box-aligned multi-tool LLM cases
├── test_tool_selection_disambiguation.py # Negative tool-routing assertions
├── test_tool_selection_src.py            # SRC reference suite (tools currently reserved)
└── test_tool_selection_ml.py             # ML reference suite (tool currently reserved)
```

Tests with `@pytest.mark.unit` run with no external dependencies. Tests with `@pytest.mark.llm` need an LLM endpoint reachable. Tests with `@pytest.mark.e2e` need both LLM and backend.

### Common Test Commands

```bash
# Pure unit tests (no LLM, no backend)
uv run pytest tests/ -m "unit and not llm and not e2e"

# LLM tool-selection regressions (needs LLM endpoint)
uv run pytest tests/ -m llm

# Single deterministic shot instead of 3-run majority vote
STRICT_MODE=1 uv run pytest tests/ -m llm
```

The SRC and ML tool-selection suites stay in the repo as a reference for the day those tools come back into `ACTIVE_TOOLS`. They are not run by default.

### What to Test After Changes

| Changed | Test |
|---|---|
| `tools.py` (registry) | `uv run pytest tests/test_tools_registry.py` |
| `tools.py` (`ACTIVE_TOOLS`) | `tests/test_tools_registry.py` + `tests/test_reasoning_adapter.py::TestDescriptionCoverage` |
| `reasoning_adapter.py` | `tests/test_reasoning_adapter.py` + `tests/test_agent_session.py` |
| `session_store.py` | `tests/test_session_store.py` + `tests/test_agent_session.py` |
| `main.py` (Agent loop) | `tests/test_agent_unit.py` + `tests/test_agent_session.py` |
| `prompts.py` | `tests/ -m llm` then test 5+ diverse e2e queries |
| `api_client.py` | `tests/test_api_client.py` + a real backend smoke |
| `config.py` | All unit tests (config touches everything) |

### Manual Testing

```bash
# First turn — fires a tool
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show sector breakdown for user 1912650190", "session_id": "smoke-1"}' \
  | python3 -m json.tool

# Follow-up — should NOT re-fire the tool; cache is reused
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "How was that calculated?", "session_id": "smoke-1"}' \
  | python3 -m json.tool

# Out-of-scope (no tool fires, no cache) — assistant text returned directly
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather today?"}' \
  | python3 -m json.tool
```

Inspect `debug.reasoning.trace` to see the Reasoner output, and `debug.reasoning.api_keys` to confirm the right Glass-Box keys were used.

### Financial Engine Test Payloads

The `financial_engine` tool dispatches to 10 functions. All use `user_id: 1912650190` as the reference test user.

```json
{"function": "diversification", "parameters": {"user_id": 1912650190}}
{"function": "asset_breakdown", "parameters": {"user_id": 1912650190}}
{"function": "sector_breakdown", "parameters": {"user_id": 1912650190}}
{"function": "market_cap_breakdown", "parameters": {"user_id": 1912650190}}
{"function": "single_holding_exposure", "parameters": {"holding_name": "HDFC Bank", "user_id": 1912650190}}
{"function": "total_stock_exposure", "parameters": {"user_id": 1912650190, "top_n": 5}}
{"function": "amc_preference", "parameters": {"user_id": 1912650190}}
{"function": "sector_preference", "parameters": {"user_id": 1912650190}}
{"function": "theme_preference", "parameters": {"user_id": 1912650190}}
{"function": "factor_preference", "parameters": {"user_id": 1912650190}}
```

Direct backend call:
```bash
curl -X POST http://localhost:8080/financial_engine \
  -H "Content-Type: application/json" \
  -d '{"function": "sector_breakdown", "parameters": {"user_id": "1912650190"}}'
```

Through the agent (the answer comes from the Glass-Box Answerer):
```bash
curl -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the exposure to HDFC Bank for user 1912650190?"}'
```

## Future Work

The integration plan in `../sec_agent_reasoning_llm_integration_plan.md` defines four phases. Phases 1-3 are done. Remaining work:

### Phase 4 — API description update pipeline (handed off)

- Extraction script in `Reasoning_LLM_TiFin/scripts/update_api_descriptions.py` that walks `securities-recommendation` source and regenerates `all_api_descriptions.json`.
- JSON validation tests asserting every active tool has a description and every entry has the required fields.
- GitHub Actions workflow that runs the script + validation and fails (or opens a PR) when committed JSON differs from generated.
- Human-review docs for the regeneration process (per plan §423: no LLM-driven rewrite of descriptions).

### Production hardening (post-Phase 4)

- Move `session_store` from in-memory dict to Redis / Postgres / app session service.
- Stream the Answerer output for better UX on long answers.
- Per-request Glass-Box model instances (or locking) to remove the verifier-metadata race when concurrent same-session requests arrive.
- Re-enable reserved tools (SRC, ML, etc.) by adding their Glass-Box descriptions and adapter mappings.
