# Test Queries Reference

All queries for testing tool selection and API calls. Verified user IDs with portfolio data: `1018083528`, `1733307354`, `1515040473`, `1176384033`, `1724788267`. User `1133023930` has no holdings.

## Quick curl template

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "<QUERY>"}' | python3 -m json.tool
```

---

## SRC Service (Fund Search & Recommendations)

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

## Financial Engine (Portfolio Analytics)

All queries go through the `financial_engine` tool with different `function` sub-parameters.

| Query | Expected function |
|---|---|
| Show sector breakdown for user 1912650190 in org 2854263694 | `sector_breakdown` |
| Check diversification of portfolio for user 1912650190 org 2854263694 | `diversification` |
| What is the asset breakdown for user 1912650190 in org 2854263694? | `asset_breakdown` |
| Show market cap distribution for user 1912650190 org 2854263694 | `market_cap_breakdown` |
| What is my exposure to Reliance in user 1912650190's portfolio in org 2854263694? | `single_holding_exposure` |

---

## Model Portfolio Service

### get_portfolio_options
| Query | Expected Tool |
|---|---|
| Build me a portfolio with 50000 SIP investment, medium risk, user ID 100 | `get_portfolio_options` |
| I want to invest 5 lakhs as a lump sum with high risk. User ID 200. | `get_portfolio_options` |
| Build a medium risk portfolio for user 1018083528 with 20000 monthly SIP | `get_portfolio_options` |

**Critical routing test:** The last query above previously caused the agent to auto-chain into `backtest_portfolio`. After the description enrichment, it should call `get_portfolio_options` ONCE and stop.

### get_risk_profile
| Query | Expected Tool |
|---|---|
| What is the risk profile for user 12345? | `get_risk_profile` |
| What is the risk profile for user 1018083528? | `get_risk_profile` |

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
| Convert stock holdings of user 12345 to mutual fund recommendations | `stock_to_fund` |

### determine_income_sector
| Query | Expected Tool |
|---|---|
| Classify income sector for a household where one person is a software engineer at an IT company and spouse is a doctor | `determine_income_sector` |

### build_stock_portfolio
| Query | Expected Tool |
|---|---|
| Build me a large cap tech portfolio with up to 10 stocks | `build_stock_portfolio` |
| Construct a mid cap healthcare stock portfolio, max 8 positions | `build_stock_portfolio` |

**Params the LLM should extract:** `query` (natural-language description), and optionally `max_stocks`, `sectors`, `market_caps`. The endpoint takes an NL description and does its own sector/cap parsing — do NOT pass an explicit `stocks[{symbol, weight}]` list.

---

## ML Recommendations

### ml_fund_discovery
| Query | Expected Tool |
|---|---|
| Show ML-based personalized fund recommendations for user 1912650190 | `ml_fund_discovery` |
| What funds would similar investors recommend for user 100? | `ml_fund_discovery` |
| Give me collaborative filtering fund suggestions for user 1912650190 | `ml_fund_discovery` |

---

## Multi-Step / Ambiguous Queries

These queries may correctly trigger multiple tools or have multiple valid tool selections.

| Query | Acceptable Tools |
|---|---|
| Show me the peers of SBI Large Cap Fund | `search_funds`, `get_fund_peers`, or both |
| Find better alternatives to HDFC Mid Cap Fund based on cost | `search_funds`, `swap_recommendations`, or both |
| Determine my risk profile and build a portfolio. User 12345, 50000 SIP. | `get_portfolio_options`, `get_risk_profile`, or both |
| Analyze user 1912650190's portfolio in org 2854263694: show diversification and suggest better fund alternatives | `financial_engine`, `portfolio_swap_recommendations`, or both |

---

## Disambiguation Tests (should NOT trigger wrong tool)

These test that the enriched descriptions prevent common mis-routing:

| Query | Should Call | Should NOT Call |
|---|---|---|
| Build a medium risk portfolio for user 1018083528 with 20000 monthly SIP | `get_portfolio_options` | `backtest_portfolio` (response already has backtest) |
| What is user 1018083528's risk profile? | `get_risk_profile` | `risk_profile_v2` (that's for onboarding) |
| Build a portfolio with 50000 SIP, user 200 | `get_portfolio_options` | `get_risk_profile` (auto-fetched internally) |
| I have one goal: save 1 crore in 20 years | `single_goal_optimizer` | `multi_goal_optimizer` (single goal) |

---

## Full curl examples for live testing

```bash
# Risk profile lookup
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the risk profile for user 1018083528?"}'

# Build portfolio (the critical auto-chain test)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Build a medium risk portfolio for user 1018083528 with 20000 monthly SIP"}'

# Financial engine - sector breakdown
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show sector breakdown for user 1912650190 in org 2854263694"}'

# Fund search
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me the best large cap mutual funds"}'

# Goal planning
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "I want to save 1 crore in 20 years with 10000 monthly SIP for retirement"}'

# ML recommendations
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Show ML-based personalized fund recommendations for user 1912650190"}'
```
