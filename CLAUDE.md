# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Repository Overview

This is a tool-calling agent that orchestrates the securities-recommendation microservice APIs. It uses native OpenAI function calling via a self-hosted GLM-4.7-Flash model (vLLM) to decide which API endpoints to call, executes HTTP requests, and synthesizes natural language answers in a single conversation loop.

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

# Run tool selection tests (dry-run, no backend needed)
uv run python test_tool_selection.py

# Test the endpoint (use user 1912650190 — verified with portfolio data)
curl -s -X POST http://localhost:8090/ask -H "Content-Type: application/json" -d '{"query": "Show sector breakdown for user 1912650190"}'
```

## Architecture

```
main.py                → Agent class (conversation loop with native function calling) + FastAPI /ask endpoint
tools.py               → TOOLS dict (20 tools) + get_openai_tools() for OpenAI schema conversion
prompts.py             → Unified SYSTEM_PROMPT (tool-use guidelines + rendering rules)
api_client.py          → APIClient class (aiohttp POST to microservices)
config.py              → Settings from .env (API URL, LLM endpoint, auth toggle)
models.py              → AskRequest / AskResponse Pydantic models
test_tool_selection.py → Dry-run tool selection tests (15 cases, no backend needed)
```

**Data flow:** User query + tool schemas → LLM returns tool_calls → HTTP calls to backend → results fed back → LLM responds with text

## Key Patterns

### Tool Registry (tools.py)
- Tools are defined as dicts in `TOOLS` with description, endpoint, method, parameters
- `get_openai_tools()` converts the registry into OpenAI function-calling schema (passed via `tools` API parameter)
- Adding a tool = adding a dict entry. No other code changes needed.

### Agent Orchestration (main.py)
- `Agent.run()` → single conversation loop using native function calling
- LLM receives tool schemas via `tools` parameter, returns `tool_calls` when it wants to call a tool
- `Agent._call_tool()` → looks up the tool in the registry and makes the HTTP call
- Loop continues until LLM responds with text (no tool_calls) or max iterations (3) reached
- If max iterations exhausted, a final LLM call without tools forces a text response

### Configuration
- All settings via `.env` file, loaded by pydantic-settings
- `ENABLE_AUTH=false` for local development, `true` for deployed services
- Self-hosted GPU is recommended (Groq context window too small for 20 tool schemas)
- `extra_body: {"chat_template_kwargs": {"enable_thinking": False}}` required for GLM chat template
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

The agent needs an LLM with native function calling support and a large enough context window for 20 tool schemas (~3,800 tokens).

- **Self-hosted GPU** (recommended): `http://103.42.51.88:2205/` with `orchestrator` (GLM-4.7-Flash via vLLM, company VPN/GCP only)
- **Groq** (NOT recommended): context window too small for 20 tool schemas

> **Important distinction:** The agent's LLM is separate from the backend services' LLM dependencies. Some SRC and Model Portfolio endpoints call the self-hosted GPU for NER parsing — those won't work without VPN access regardless of which LLM the agent uses. Financial Engine and ML Recommendations have no LLM dependencies.

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
