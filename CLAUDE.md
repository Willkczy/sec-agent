# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Repository Overview

This is a tool-calling agent that orchestrates the securities-recommendation microservice APIs. It uses an OpenAI-compatible LLM (Groq or self-hosted GPU) to plan which API endpoints to call, executes HTTP requests, and renders natural language answers.

## Project Goal

The agent's ultimate goal is to **explain the logic and assumptions behind API results**, not just relay numbers. Currently it can call APIs and render results, but cannot answer follow-up questions like "how was this calculated?" or "what assumptions does this use?". All work should be evaluated against this goal. See README.md for approaches being explored.

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

# Test the endpoint (use user 1912650190 — verified with portfolio data)
curl -s -X POST http://localhost:8090/ask -H "Content-Type: application/json" -d '{"query": "Show sector breakdown for user 1912650190"}'
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
- LLM provider is configurable: Groq or self-hosted GPU (see README for setup)
- Backend services need GCP credentials (`GOOGLE_APPLICATION_CREDENTIALS`) to call external APIs

## Dependencies on Other Repos

- **securities-recommendation** (sibling directory): The 5 microservices this agent calls over HTTP. This agent does NOT import any code from it.

## Upstream API Services

The agent calls these services (must be running for the agent to work):

| Service | Local URL | Deployed URL |
|---------|-----------|-------------|
| SRC | `http://localhost:8089/cr/src/` | `https://api.askmyfi.com/cr/src/` |
| Model Portfolio | `http://localhost:8089/cr/model-portfolio/` | `https://api.askmyfi.com/cr/model-portfolio/` |
| Financial Engine | `http://localhost:8089/cr/fin-engine/` | `https://api.askmyfi.com/cr/fin-engine/` |
| ML Recommendations | `http://localhost:8089/cr/mlr/` | `https://api.askmyfi.com/cr/mlr/` |

## LLM Access

The agent needs an LLM for planning and rendering. Any OpenAI-compatible endpoint works:

- **Groq** (recommended for local dev): `https://api.groq.com/openai/v1` with `llama-3.3-70b-versatile`
- **Self-hosted GPU** (company VPN/GCP only): `http://103.42.51.88:2205/` with `orchestrator`

> **Important distinction:** The agent's LLM (plan/render) is separate from the backend services' LLM dependencies. Some SRC and Model Portfolio endpoints call the self-hosted GPU for NER parsing — those won't work without VPN access regardless of which LLM the agent uses. Financial Engine and ML Recommendations have no LLM dependencies.

## GCP Credentials

Backend services call external APIs (portfolio data, security master) that require S2S authentication:

```bash
export GOOGLE_APPLICATION_CREDENTIALS='/path/to/gcp-key-dev.json'
```

Without this, running backend services locally will produce 500 errors.

## Important: What NOT to Do

- Do not add organization-specific routing (this agent is org-agnostic by design)
- Do not import code from securities-recommendation — communicate only via HTTP
- Do not hardcode API responses or mock data in production code
- Keep prompts in `prompts.py`, not scattered across other files
