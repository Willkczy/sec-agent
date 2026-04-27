# Test Queries Reference

Queries for testing tool selection and API calls. Verified user IDs with portfolio data include `1912650190`, `1018083528`, `1733307354`, `1515040473`, `1176384033`, `1724788267`. User `1133023930` has no holdings.

Use verified users for live backend smoke tests. Synthetic IDs such as `100`, `200`, or `12345` are routing-only examples unless the target backend environment has matching data.

> **Active vs reserved tools.** Only the 10 Financial Engine + Model Portfolio tools listed in `tools.py::ACTIVE_TOOLS` are exposed to the LLM today. Sections below labeled **Reserved (currently disabled)** still have entries in the `TOOLS` registry but are filtered out of the OpenAI schema — they are kept here for the day they are re-enabled (per the steps in `CONTRIBUTING.md#adding-a-new-tool`). Queries against reserved tools will currently produce an out-of-scope reply from the agent.

## Quick curl template

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "<QUERY>"}' | python3 -m json.tool

# With a session_id to enable follow-up continuity
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "<QUERY>", "session_id": "smoke-1"}' | python3 -m json.tool
```

---

## Financial Engine (Portfolio Analytics) — ACTIVE

All queries go through the `financial_engine` tool with different `function` sub-parameters.

| Query | Expected function |
|---|---|
| Show sector breakdown for user 1912650190 | `sector_breakdown` |
| Check diversification of portfolio for user 1912650190 | `diversification` |
| What is the asset breakdown for user 1912650190? | `asset_breakdown` |
| Show market cap distribution for user 1912650190 | `market_cap_breakdown` |
| What is my exposure to Reliance in user 1912650190's portfolio? | `single_holding_exposure` |

---

## Model Portfolio Service — ACTIVE

The following Model Portfolio tools are in `ACTIVE_TOOLS`:

### get_portfolio_options
| Query | Expected Tool |
|---|---|
| Build me a portfolio with 50000 SIP investment, medium risk, user ID 100 | `get_portfolio_options` (routing-only unless user exists) |
| I want to invest 5 lakhs as a lump sum with high risk. User ID 200. | `get_portfolio_options` (routing-only unless user exists) |
| Build a medium risk portfolio for user 1018083528 with 20000 monthly SIP | `get_portfolio_options` |

**Critical routing test:** the last query previously caused the agent to auto-chain into `backtest_portfolio`. After the description enrichment, it should call `get_portfolio_options` ONCE and stop.

### get_risk_profile
| Query | Expected Tool |
|---|---|
| What is the risk profile for user 12345? | `get_risk_profile` (routing-only unless user exists) |
| What is the risk profile for user 1018083528? | `get_risk_profile` |

### portfolio_builder
| Query | Expected Tool |
|---|---|
| Build a custom portfolio for user 1018083528 with a 50000 lump sum after I select my own funds | `portfolio_builder` |

### backtest_portfolio
| Query | Expected Tool |
|---|---|
| I swapped funds in the recommended portfolio for user 1018083528. Re-run the backtest for a 50000 lump sum using my selected funds. | `backtest_portfolio` |

`backtest_portfolio` requires a concrete `selected_funds` payload from a prior portfolio-options response. It should not be auto-called immediately after `get_portfolio_options`, because that response already includes backtest metrics.

### risk_profile_v2
| Query | Expected Tool |
|---|---|
| Assess risk for a 30 year old earning 12 lakhs annually, medium term horizon, willing to lose 20%, pin code 400001 | `risk_profile_v2` |

### single_goal_optimizer
| Query | Expected Tool |
|---|---|
| I want to save 1 crore in 20 years with 10000 monthly SIP for retirement | `single_goal_optimizer` |
| Plan for buying a house worth 50 lakhs in 10 years, I can invest 15000 per month | `single_goal_optimizer` |

### multi_goal_optimizer
| Query | Expected Tool |
|---|---|
| I have 50 lakhs and 20000 monthly SIP. Optimize across retirement in 20 years (critical, 1 crore) and house in 5 years (important, 30 lakhs) | `multi_goal_optimizer` |

### goal_defaults
| Query | Expected Tool |
|---|---|
| What SIP amount should I target for a 50 lakh goal in 15 years? | `goal_defaults` |

### stock_to_fund
| Query | Expected Tool |
|---|---|
| Convert stock holdings of user 12345 to mutual fund recommendations | `stock_to_fund` (routing-only unless user exists) |

---

## SRC Service (Fund Search & Recommendations) — Reserved (currently disabled)

> Not in `ACTIVE_TOOLS`. No Glass-Box description — Reasoner has nothing to ground against. Queries here currently produce the out-of-scope reply. Re-enable by adding descriptions to `Reasoning_LLM_TiFin/services/glass_box/data/all_api_descriptions.json`, mappings in `reasoning_adapter.py`, and the tool name to `ACTIVE_TOOLS`.

### search_funds
| Query | Expected Tool |
|---|---|
| Show me the best large cap mutual funds | `search_funds` |
| Low expense ratio mid cap funds with high returns | `search_funds` |
| Show SBI large cap funds | `search_funds` |
| Top performing mid cap funds this year | `search_funds` |

### get_fund_peers
| Query | Expected Tool |
|---|---|
| Compare fund with ISIN INF209K01YY8 against its peers | `get_fund_peers` |
| Show peers for fund with internal security ID 130685 in org 2854263694 | `get_fund_peers` |

### swap_recommendations
| Query | Expected Tool |
|---|---|
| What are better alternatives to fund with ID 130685 based on returns? | `swap_recommendations` |
| Find cheaper alternatives for fund ID 130685 | `swap_recommendations` |

### portfolio_swap_recommendations
| Query | Expected Tool |
|---|---|
| Analyze the full portfolio of user 1912650190 in org 2854263694 and suggest swaps | `portfolio_swap_recommendations` |

### stock_research_data
| Query | Expected Tool |
|---|---|
| Get stock research data for ISIN INE002A01018 | `stock_research_data` |

### can_support
| Query | Expected Tool |
|---|---|
| Can the system handle a query about cryptocurrency trading? | `can_support` |

---

## Model Portfolio Utilities — Reserved (currently disabled)

> Not in `ACTIVE_TOOLS`. `determine_income_sector` is a utility with no Glass-Box description. `build_stock_portfolio` has a Glass-Box description, but live backend calls currently return HTTP 500 (see `Reasoning_LLM_TiFin/CLAUDE.md`).

### determine_income_sector
| Query | Expected Tool |
|---|---|
| Classify income sector for a household where one person is a software engineer at an IT company and spouse is a doctor | `determine_income_sector` |

### build_stock_portfolio
| Query | Expected Tool |
|---|---|
| Build me a large cap tech portfolio with up to 10 stocks | `build_stock_portfolio` |
| Construct a mid cap healthcare stock portfolio, max 8 positions | `build_stock_portfolio` |

**Params the LLM should extract:** `query` (NL description), and optionally `max_stocks`, `sectors`, `market_caps`. The endpoint takes an NL description and does its own sector/cap parsing — do NOT pass an explicit `stocks[{symbol, weight}]` list.

---

## ML Recommendations — Reserved (currently disabled)

> Not in `ACTIVE_TOOLS`. No Glass-Box description.

### ml_fund_discovery
| Query | Expected Tool |
|---|---|
| Show ML-based personalized fund recommendations for user 1912650190 | `ml_fund_discovery` |
| What funds would similar investors recommend for user 100? | `ml_fund_discovery` |
| Give me collaborative filtering fund suggestions for user 1912650190 | `ml_fund_discovery` |

---

## Multi-Step / Ambiguous Queries — ACTIVE

These may correctly trigger multiple tools or have multiple valid tool selections. All examples below use only active tools.

| Query | Acceptable Tools |
|---|---|
| Determine my risk profile and build a portfolio. User 12345, 50000 SIP. | `get_portfolio_options`, `get_risk_profile`, or both |
| Show diversification for user 1912650190 and break it down by sector | `financial_engine` (called twice with different `function` values) |
| What's the asset breakdown for user 1912650190, and is the portfolio concentrated? | `financial_engine` (`asset_breakdown` + `diversification`) |

---

## Disambiguation Tests (should NOT trigger wrong tool) — ACTIVE

These verify the description enrichment prevents common mis-routing.

| Query | Should Call | Should NOT Call |
|---|---|---|
| Build a medium risk portfolio for user 1018083528 with 20000 monthly SIP | `get_portfolio_options` | `backtest_portfolio` (response already has backtest) |
| What is user 1018083528's risk profile? | `get_risk_profile` | `risk_profile_v2` (that's for onboarding) |
| Build a portfolio with 50000 SIP, user 200 | `get_portfolio_options` | `get_risk_profile` (auto-fetched internally) |
| I have one goal: save 1 crore in 20 years | `single_goal_optimizer` | `multi_goal_optimizer` (single goal) |

---

## Follow-up continuity smoke (Phase 2)

Verifies `session_id` follow-ups reuse the prior cache without re-firing tools. The second call should return `debug.tool_results: []` and `debug.reused_session_cache: true`, with the answer grounded in the prior turn's reasoning trace.

```bash
# Turn 1 — fires financial_engine
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show asset breakdown for user 1912650190", "session_id": "smoke-followup"}' \
  | python3 -m json.tool

# Turn 2 — same session, no new tool call expected
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "How was that calculated?", "session_id": "smoke-followup"}' \
  | python3 -m json.tool
```

---

## Out-of-scope smoke

Verifies the no-tool-no-cache path returns the assistant's text directly without invoking the Reasoner.

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather today?"}' \
  | python3 -m json.tool
```

Expected: `debug.reasoning` is absent; the answer is the tool-LLM's plain text reply.

---

## Full curl examples for live testing

```bash
# Risk profile lookup (active)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the risk profile for user 1018083528?"}'

# Build portfolio (the critical auto-chain test)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Build a medium risk portfolio for user 1018083528 with 20000 monthly SIP"}'

# Financial engine — sector breakdown (active)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show sector breakdown for user 1912650190"}'

# Goal planning (active)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "I want to save 1 crore in 20 years with 10000 monthly SIP for retirement"}'

# Reserved (currently returns out-of-scope reply):
# curl -s -X POST http://localhost:8090/ask \
#   -H "Content-Type: application/json" \
#   -d '{"query": "Show me the best large cap mutual funds"}'
```
