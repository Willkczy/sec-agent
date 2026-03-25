# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Repository Overview

This is a simple tool-calling agent that orchestrates the securities-recommendation microservice APIs. It uses a self-hosted LLM (OpenAI-compatible) to plan which API endpoints to call, executes HTTP requests, and renders natural language answers.

## CRITICAL: Git Rules

**NEVER use `git add -A`, `git add .`, or `git add --all`.** Always add files explicitly by name. Never commit `.env` files or credentials.

## Common Commands

```bash
# Install dependencies
uv sync

# Run the server
uv run uvicorn main:app --port 8090 --reload

# Run with different port (if 8090 is occupied)
uv run uvicorn main:app --port 8091

# Quick syntax check
uv run python -c "from main import app; print('OK')"

# Test the endpoint
curl -s -X POST http://localhost:8090/ask -H "Content-Type: application/json" -d '{"query": "Show me top 3 large cap funds"}'
```

## Architecture

```
main.py    → Agent class (plan/execute/render loop) + FastAPI /ask endpoint
tools.py   → TOOLS dict (20 tools) + get_tools_prompt() helper
prompts.py → Planner prompt (with dynamic tool list) + render prompt
api_client.py → APIClient class (aiohttp POST to microservices)
config.py  → Settings from .env (API URL, LLM endpoint, auth toggle)
models.py  → AskRequest / AskResponse Pydantic models
```

**Data flow:** User query → planner LLM → JSON plan → HTTP calls to securities-recommendation → render LLM → answer

## Key Patterns

### Tool Registry (tools.py)
- Tools are defined as dicts in `TOOLS` with description, endpoint, method, parameters
- `get_tools_prompt()` auto-renders all tools into the planner system prompt
- Adding a tool = adding a dict entry. No other code changes needed.

### Agent Orchestration (main.py)
- `Agent.plan()` → sends query + system prompt to LLM, parses JSON response
- `Agent.execute()` → loops through `tool_calls`, calls `api_client.call_tool()` for each
- `Agent.render()` → sends query + all tool results to render LLM
- `Agent.run()` → full loop with optional multi-step (`next_step_required`)
- `extract_json_object()` → robust JSON extraction from LLM text (regex for ```json fences then fallback)

### Configuration
- All settings via `.env` file, loaded by pydantic-settings
- `ENABLE_AUTH=false` for local development, `true` for deployed services
- LLM defaults match Zara's cli.py (self-hosted GPU at 103.42.51.88:2205, dummy API key)

## Dependencies on Other Repos

- **securities-recommendation** (sibling directory): The 5 microservices this agent calls over HTTP. This agent does NOT import any code from it.
- **zara** (sibling directory): The complex agent this is modeled after. Referenced for patterns only.

## Upstream API Services

The agent calls these services (must be running for the agent to work):

| Service | Local URL | Deployed URL |
|---------|-----------|-------------|
| SRC | `http://localhost:8089/cr/src/` | `https://api.askmyfi.com/cr/src/` |
| Model Portfolio | `http://localhost:8089/cr/model-portfolio/` | `https://api.askmyfi.com/cr/model-portfolio/` |
| Financial Engine | `http://localhost:8089/cr/fin-engine/` | `https://api.askmyfi.com/cr/fin-engine/` |
| ML Recommendations | `http://localhost:8089/cr/mlr/` | `https://api.askmyfi.com/cr/mlr/` |

## LLM Access

- **Self-hosted GPU**: `http://103.42.51.88:2205/` (dev) or `http://103.42.51.60/` (prod)
- API key: `123-123-123` (dummy — the self-hosted endpoint doesn't validate keys)
- Model name: `orchestrator`
- **Note**: GPU endpoints are only reachable from GCP infrastructure or company VPN. For local development without VPN, use OpenAI or Ollama as alternatives.

## Important: What NOT to Do

- Do not add organization-specific routing (this agent is org-agnostic by design)
- Do not import code from securities-recommendation — communicate only via HTTP
- Do not add pandas/DataFrame processing in the MVP — this is planned as a future extension
- Do not hardcode API responses or mock data in production code
- Keep prompts in `prompts.py`, not scattered across other files
