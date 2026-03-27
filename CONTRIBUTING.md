# Contributing Guide

## Development Setup

```bash
# Clone and enter the project
cd sec-agent

# Install dependencies with uv
uv sync

# Copy environment config
cp .env.example .env
# Edit .env to configure your LLM provider (see README for options)

# Run the server locally
uv run uvicorn main:app --port 8090 --reload
```

### GCP Credentials

Backend services (securities-recommendation) call external APIs that require GCP S2S authentication. To run them locally:

```bash
# Option 1: Service account key (recommended)
export GOOGLE_APPLICATION_CREDENTIALS='/path/to/gcp-key-dev.json'

# Option 2: gcloud CLI
gcloud auth application-default login
```

Without this, backend services will return 500 errors when they try to fetch user portfolios or security data.

### Running Backend Services

The agent calls backend services at `API_BASE_URL` (default: `http://localhost:8089`). You can run individual services:

```bash
cd ../securities-recommendation

# Financial engine (no LLM dependency)
GOOGLE_APPLICATION_CREDENTIALS='/path/to/gcp-key-dev.json' \
API_BASE_URL='https://api.askmyfi.dev' \
uvicorn services.financial_engine.main:app --host 0.0.0.0 --port 8089

# ML recommendations (no LLM dependency)
GOOGLE_APPLICATION_CREDENTIALS='/path/to/gcp-key-dev.json' \
API_BASE_URL='https://api.askmyfi.dev' \
uvicorn services.ml_recommendations.main:app --host 0.0.0.0 --port 8089
```

> **Tip:** You only need to run the service(s) relevant to the tools you're testing. See README for which tools map to which service.

## Git Workflow

### Branch Naming

```
feature/<short-description>    # New features
fix/<short-description>        # Bug fixes
refactor/<short-description>   # Code refactoring
docs/<short-description>       # Documentation only
```

### Commit Messages

Use imperative mood, keep the first line under 72 characters:

```
Add multi-step planning for fund comparison queries
Fix JSON parsing when LLM returns markdown fences
Update render prompt with stricter anti-hallucination rules
```

### Pull Requests

1. Create a feature branch from `main`
2. Make your changes (keep PRs focused — one feature/fix per PR)
3. Test locally against the securities-recommendation services
4. Open a PR with a clear description of what changed and why
5. Request review from at least one teammate

### Git Rules

- **Never** use `git add -A` or `git add .` — always add files explicitly
- **Never** commit `.env` files or credentials
- **Never** force-push to `main`

## Project Conventions

### Code Style

- Python 3.12+ features are fine (`dict[str, Any]` instead of `Dict[str, Any]`, etc.)
- Use type annotations on all function signatures
- Use `async/await` for all I/O operations (HTTP calls, LLM calls)
- Keep functions short and focused — if a function does too much, split it

### File Responsibilities

Each file has a single responsibility. Don't blur the lines:

| File | Owns | Does NOT own |
|------|------|-------------|
| `tools.py` | Tool definitions, parameter schemas | HTTP calls, LLM calls |
| `api_client.py` | HTTP requests to microservices | Tool selection, response formatting |
| `prompts.py` | System prompt text | LLM client calls |
| `main.py` | Orchestration loop, FastAPI app | Tool schemas, prompt text |
| `config.py` | Settings and env loading | Business logic |
| `models.py` | Request/response Pydantic models | Validation logic beyond types |

### Adding a New Tool

1. **Define it in `tools.py`** — add an entry to the `TOOLS` dict with description, endpoint, method, and parameter schema
2. **That's it** — the planner prompt auto-generates from `TOOLS` via `get_tools_prompt()`, and `execute()` dispatches by looking up the endpoint

Example:
```python
# In tools.py, add to the TOOLS dict:
"new_tool_name": {
    "description": "What this tool does (shown to the LLM planner)",
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

### Modifying Prompts

- Planner prompt is in `prompts.py:get_planner_prompt()` — edit the rules/instructions there
- Render prompt is in `prompts.py:RENDER_PROMPT` — keep the anti-hallucination rules strict
- After changing prompts, test with diverse queries to catch regressions (the LLM may behave differently)

### Adding a New LLM Provider

The agent uses `openai.AsyncOpenAI` which supports any OpenAI-compatible API. To switch providers:

1. Update `.env` with the new base URL, API key, and model name
2. No code changes needed if the provider is OpenAI-compatible
3. If the provider has a different SDK, modify the LLM client initialization in `main.py`

## Testing

### Manual Testing

Start the agent and the relevant backend service(s), then test with curl:

```bash
# Portfolio analytics — financial engine (no self-hosted LLM needed)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show sector breakdown for user 1912650190"}' | python3 -m json.tool

curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the exposure to HDFC Bank for user 1912650190?"}' | python3 -m json.tool

curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show market cap breakdown for user 1912650190"}' | python3 -m json.tool

# Fund search — SRC service (requires self-hosted LLM for NER)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me top 3 large cap funds"}' | python3 -m json.tool

# Goal planning — model portfolio service (no self-hosted LLM needed)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "I want to save 50 lakhs for retirement in 20 years, investing 10000 per month via SIP"}' | python3 -m json.tool
```

### Test User IDs

| User ID | Has Portfolio Data | Notes |
|---------|-------------------|-------|
| `1912650190` | Yes | Verified working for all financial engine functions |

### What to Test After Changes

| Changed | Test |
|---------|------|
| `tools.py` | Verify the new/modified tool is called correctly with a relevant query |
| `prompts.py` | Test with 5+ diverse queries to check for regressions |
| `api_client.py` | Test with both reachable and unreachable services |
| `main.py` | Test single-step and multi-step queries |
| `config.py` | Test with different `.env` configurations |

### Checking the Debug Output

The `/ask` response includes a `debug` field with the raw plans and tool results. Use this to verify:
- The planner selected the right tool(s)
- The correct parameters were sent
- The API returned valid data
- Multi-step plans executed in the right order

```bash
# Pretty-print debug info
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "your query"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['debug'], indent=2))"
```

## Future Work

These are planned extensions — documented here so contributors can pick them up:

1. **Calculation context in render** — Inject explanation of how each API computes its results so the agent can answer "how did you calculate this?" follow-ups
2. **Pandas processing tool** — Add an in-process tool that takes API results into a DataFrame and runs LLM-generated pandas code for custom analysis (same pattern as Zara's `run_query()`)
3. **Conversation memory** — Support multi-turn conversations where the agent remembers previous queries and results
4. **Streaming responses** — Stream the render LLM output for better UX on long answers
