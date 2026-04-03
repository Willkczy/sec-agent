# sec-agent

A lightweight tool-calling agent that orchestrates the [securities-recommendation](../securities-recommendation) microservice APIs via natural language queries.

## Project Goal

The ultimate goal of this project is to build an agent that can **explain the logic and assumptions behind its answers**, not just relay API results. Currently the agent can call backend APIs and render results as natural language, but when users ask follow-up questions like "how was this calculated?" or "what assumptions does the diversification score use?", the agent has no understanding of the computation behind the APIs.

The key challenge is: **how do we give the agent understanding of the backend computation so it can answer "why" and "how" questions?**

Possible approaches being explored:
- **Calculation context from APIs** — Have backend endpoints return metadata explaining the computation alongside results
- **Code documentation injection** — Extract logic summaries from backend source code and inject into prompts
- **RAG over source code** — Index the backend codebase and retrieve relevant snippets for "how" questions
- **Static knowledge base per tool** — Write markdown explanations for each function, loaded into prompts

## Architecture

```
User Query
    │
    ▼
┌───────────────────────────────────────────────────┐
│              Agent (conversation loop)             │
│                                                   │
│  1. Send query + tool schemas to LLM              │
│  2. LLM returns tool_calls (native function call) │
│  3. Execute HTTP calls to backend services        │
│  4. Feed results back to LLM                      │
│  5. Repeat until LLM responds with text           │
└───────────────────────────────────────────────────┘
        │                           │
        │ HTTP POST                 │ Final Answer
        ▼                           ▼
┌─────────────────────────┐
│ securities-recommendation│
│  microservices (5 svc)   │
└─────────────────────────┘
```

**Native function calling loop:**
- The LLM receives all 20 tool schemas via the OpenAI `tools` API parameter
- It decides which tool(s) to call using native function calling (no JSON parsing needed)
- The agent executes the HTTP calls and feeds results back as `tool` messages
- The loop repeats until the LLM responds with text (or max 3 iterations)

## Project Structure

```
sec-agent/
├── main.py                # FastAPI app + Agent orchestrator (conversation loop)
├── tools.py               # Tool registry (20 tools) + get_openai_tools()
├── prompts.py             # System prompt (unified tool-use + rendering rules)
├── models.py              # Pydantic request/response models
├── api_client.py          # Async HTTP client for microservice calls
├── config.py              # Settings (env-based configuration)
├── test_tool_selection.py # Dry-run tool selection tests (15 cases)
├── pyproject.toml         # uv project dependencies
└── .env.example           # Environment variable template
```

## Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- An OpenAI-compatible LLM endpoint (self-hosted GPU recommended; Groq context window is too small for 20 tool schemas)
- securities-recommendation services running (locally or deployed)
- **GCP service account key** (required if running backend services locally — they call external APIs that need S2S auth)

### Setup

```bash
cd sec-agent

# Install dependencies
uv sync

# Copy env template and configure your LLM provider
cp .env.example .env
# Edit .env — see "LLM Provider Options" below

# Start the agent
uv run uvicorn main:app --port 8090 --reload
```

### Running Backend Services Locally

The agent calls securities-recommendation services over HTTP. You can either point at deployed services or run them locally.

**Running a single service locally** (e.g., financial engine):
```bash
cd ../securities-recommendation

# Set GCP credentials for S2S auth to external APIs
export GOOGLE_APPLICATION_CREDENTIALS='/path/to/gcp-key-dev.json'

# Start with dev API target
API_BASE_URL='https://api.askmyfi.dev' \
uvicorn services.financial_engine.main:app --host 0.0.0.0 --port 8089
```

> **Important:** Most backend services depend on external APIs (portfolio data, security master, etc.) via `API_BASE_URL`. They need GCP credentials to authenticate these calls. Without credentials, you'll get 500 errors.

### Test

```bash
# Portfolio analytics (financial engine)
curl -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me the sector breakdown for user 1912650190"}'

# Fund search (requires SRC service + self-hosted LLM)
curl -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me top 3 large cap funds with low expense ratio"}'
```

### Test User IDs

| User ID | Has Portfolio Data | Notes |
|---------|-------------------|-------|
| `1912650190` | Yes | Use this for financial engine testing |

## Configuration

All config is via environment variables (`.env` file or system env). See `.env.example` for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `http://localhost:8089` | securities-recommendation base URL |
| `LLM_BASE_URL` | `http://103.42.51.88:2205/` | Self-hosted GPU endpoint |
| `LLM_API_KEY` | `anything works` | GPU API key (dummy key for self-hosted) |
| `LLM_MODEL` | `orchestrator` | Model name on the GPU endpoint |
| `LLM_TEMPERATURE` | `0.2` | LLM temperature |
| `LLM_MAX_TOKENS` | `16384` | Max tokens for LLM responses |
| `ENABLE_AUTH` | `false` | Enable S2S auth for deployed environments |

### LLM Provider Options

The agent uses any OpenAI-compatible API with native function calling support. The 20 tool schemas consume ~3,800 tokens per request, so the LLM needs a sufficiently large context window.

**Self-hosted GPU (recommended — GLM-4.7-Flash via vLLM):**
```env
LLM_BASE_URL=http://103.42.51.88:2205/
LLM_API_KEY=anything works
LLM_MODEL=orchestrator
```

> **Note:** The self-hosted GPU is only reachable from GCP infrastructure or company VPN.

**Groq (NOT recommended — context window too small for 20 tool schemas):**
Groq's free tier has a ~12K TPM limit which is exceeded by the tool schemas alone. If you need Groq, you'd need to reduce the number of tools or implement category-based routing.

### Targeting deployed services

```env
API_BASE_URL=https://api.askmyfi.com
ENABLE_AUTH=true
```

## Available Tools (20)

| Tool | Service | Endpoint | Description |
|------|---------|----------|-------------|
| `search_funds` | SRC | `/cr/src/get_query_data` | NL fund discovery |
| `swap_recommendations` | SRC | `/cr/src/swap_recommendations` | Fund alternatives |
| `portfolio_swap_recommendations` | SRC | `/cr/src/portfolio_swap_recommendations` | Portfolio-level analysis |
| `get_fund_peers` | SRC | `/cr/src/get_fund_peers` | Peer comparison |
| `stock_research_data` | SRC | `/cr/src/stock_research_data` | Research data lookup |
| `parse_query` | SRC | `/cr/src/parser` | Raw NER parsing |
| `can_support` | SRC | `/cr/src/canSupport` | Capability check |
| `get_portfolio_options` | Model Portfolio | `/cr/model-portfolio/get_portfolio_options` | Portfolio construction |
| `backtest_portfolio` | Model Portfolio | `/cr/model-portfolio/backtest_selected_portfolio` | Custom backtest |
| `portfolio_builder` | Model Portfolio | `/cr/model-portfolio/portfolio_builder` | Legacy portfolio builder |
| `get_risk_profile` | Model Portfolio | `/cr/model-portfolio/get_risk_profile` | Risk profile v1 |
| `risk_profile_v2` | Model Portfolio | `/cr/model-portfolio/risk_profile_v2` | Enhanced risk profile |
| `single_goal_optimizer` | Model Portfolio | `/cr/model-portfolio/single_goal_optimizer` | Goal planning |
| `multi_goal_optimizer` | Model Portfolio | `/cr/model-portfolio/multi_goal_optimizer` | Multi-goal optimization |
| `goal_defaults` | Model Portfolio | `/cr/model-portfolio/goal_defaults` | Goal defaults |
| `build_stock_portfolio` | Model Portfolio | `/cr/model-portfolio/build_stock_portfolio` | Stock portfolio |
| `stock_to_fund` | Model Portfolio | `/cr/model-portfolio/stock_to_fund` | Stock-to-MF mapping |
| `determine_income_sector` | Model Portfolio | `/cr/model-portfolio/determine_income_sector` | Income classification |
| `financial_engine` | Fin Engine | `/cr/fin-engine/financial_engine` | Portfolio analytics |
| `ml_fund_discovery` | ML Recs | `/cr/mlr/fund_discovery` | CF-based discovery |

### Backend LLM Dependencies

The **agent itself** always needs an LLM (for planning and rendering), but the **backend services** have varying LLM requirements. This matters when deciding which tools you can test without the company's self-hosted GPU:

| Service | Tools that need self-hosted LLM | Tools that do NOT need LLM |
|---------|--------------------------------|---------------------------|
| **SRC** | `search_funds`, `parse_query`, `can_support` | `swap_recommendations`, `portfolio_swap_recommendations`, `get_fund_peers`, `stock_research_data` |
| **Model Portfolio** | `determine_income_sector`, `risk_profile_v2` (conditional) | `get_portfolio_options`, `backtest_portfolio`, `portfolio_builder`, `get_risk_profile`, `single_goal_optimizer`, `multi_goal_optimizer`, `goal_defaults`, `build_stock_portfolio`, `stock_to_fund` |
| **Financial Engine** | — | `financial_engine` (all functions) |
| **ML Recommendations** | — | `ml_fund_discovery` |

> **Note:** "Self-hosted LLM" refers to the company GPU endpoint (`orchestrator` / `ner-v2` models). The agent's own LLM (for plan/render) can be any provider (Groq, etc.).

### Financial Engine Functions

The `financial_engine` tool supports 10 functions: `diversification`, `asset_breakdown`, `sector_breakdown`, `market_cap_breakdown`, `single_holding_exposure`, `total_stock_exposure`, `amc_preference`, `sector_preference`, `theme_preference`, `factor_preference`.

See [CONTRIBUTING.md](CONTRIBUTING.md#financial-engine-test-payloads) for full example payloads.

## API

### `POST /ask`

**Request:**
```json
{
  "query": "Compare SBI Large Cap Fund with its peers",
  "max_iters": 3
}
```

**Response:**
```json
{
  "answer": "Here are the peer funds for SBI Large Cap Fund...",
  "debug": {
    "iterations": [{"iteration": 1, "tool_calls": [{"tool": "get_fund_peers", "params": {...}}]}],
    "tool_results": [{"tool": "get_fund_peers", "params": {...}, "result": {...}}]
  }
}
```

### `GET /health`

Returns `{"status": "ok", "service": "sec-agent"}`.

## Relationship to Other Repos

- **[securities-recommendation](../securities-recommendation)** — The 5 microservices this agent calls. This agent is a pure HTTP consumer; it does NOT import any code from securities-recommendation.
