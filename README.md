# sec-agent

A lightweight tool-calling agent that orchestrates the [securities-recommendation](../securities-recommendation) microservice APIs via natural language queries. Inspired by [Zara](../zara)'s orchestration pattern but simplified to a thin HTTP-based API orchestrator.

## Architecture

```
User Query
    │
    ▼
┌─────────┐   JSON plan    ┌──────────┐   HTTP POST    ┌─────────────────────────┐
│ Planner │ ─────────────► │ Executor │ ─────────────► │ securities-recommendation│
│  (LLM)  │                │          │                │  microservices (5 svc)   │
└─────────┘                └──────────┘                └─────────────────────────┘
                                │                                │
                                │ results                        │
                                ▼                                │
                           ┌──────────┐                          │
                           │ Renderer │ ◄────────────────────────┘
                           │  (LLM)   │
                           └──────────┘
                                │
                                ▼
                          Final Answer
```

**Three-phase loop (plan → execute → render):**
1. **Plan** — LLM decides which API endpoints to call, outputs a JSON plan
2. **Execute** — Agent makes async HTTP calls to the securities-recommendation services
3. **Render** — LLM synthesizes API responses into a natural language answer

Multi-step queries are supported via `next_step_required` flag (max 3 iterations).

## Project Structure

```
sec-agent/
├── main.py            # FastAPI app + Agent orchestrator class
├── tools.py           # Tool registry (20 tools across 5 services)
├── prompts.py         # Planner + render system prompts
├── models.py          # Pydantic request/response models
├── api_client.py      # Async HTTP client for microservice calls
├── config.py          # Settings (env-based configuration)
├── pyproject.toml     # uv project dependencies
└── .env.example       # Environment variable template
```

## Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Access to the self-hosted GPU endpoint (or an OpenAI API key)
- securities-recommendation services running (locally or deployed)

### Setup

```bash
cd sec-agent

# Install dependencies
uv sync

# Copy env template (defaults work for local development)
cp .env.example .env

# Start the agent
uv run uvicorn main:app --port 8090
```

### Test

```bash
curl -X POST http://localhost:8090/ask -H "Content-Type: application/json" -d '{"query": "Show me top 3 large cap funds with low expense ratio"}'
```

## Configuration

All config is via environment variables (`.env` file or system env). See `.env.example` for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `http://localhost:8089` | securities-recommendation base URL |
| `LLM_BASE_URL` | `http://103.42.51.88:2205/` | Self-hosted GPU endpoint |
| `LLM_API_KEY` | `123-123-123` | GPU API key (dummy key for self-hosted) |
| `LLM_MODEL` | `orchestrator` | Model name on the GPU endpoint |
| `LLM_TEMPERATURE` | `0.2` | LLM temperature for planning |
| `LLM_MAX_TOKENS` | `8192` | Max tokens for LLM responses |
| `ENABLE_AUTH` | `false` | Enable S2S auth for deployed environments |

### Using OpenAI instead of self-hosted GPU

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-key
LLM_MODEL=gpt-4o
```

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

## API

### `POST /ask`

**Request:**
```json
{
  "query": "Compare SBI Large Cap Fund with its peers",
  "max_iters": 3,
  "org_id": null
}
```

**Response:**
```json
{
  "answer": "Here are the peer funds for SBI Large Cap Fund...",
  "debug": {
    "plans": [{"reasoning": "...", "tool_calls": [...], "next_step_required": false}],
    "tool_results": [{"tool": "get_fund_peers", "params": {...}, "result": {...}}]
  }
}
```

### `GET /health`

Returns `{"status": "ok", "service": "sec-agent"}`.

## Relationship to Other Repos

- **[securities-recommendation](../securities-recommendation)** — The 5 microservices this agent calls. This agent is a pure HTTP consumer; it does NOT import any code from securities-recommendation.
- **[Zara](../zara)** — The more complex agent this is modeled after. Zara imports analyzer classes and runs pandas code in-process. This agent is simpler: HTTP calls only, no data processing.
