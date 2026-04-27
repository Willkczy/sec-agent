# Demo Queries — Glass-Box Aligned

Focused showcase of sec-agent end-to-end, organized to mirror the Reasoning_LLM_TiFin Glass-Box eval dataset (`Reasoning_LLM_TiFin/example_data/`). Each query is labeled with its source session so the reasoning agent's outputs can be cross-referenced later.

The user-facing answer in every response is produced by the Glass-Box Answerer (running inside `Reasoning_LLM_TiFin`), not by the tool-calling LLM. The `debug.reasoning.trace` field is the Reasoner's structured trace; the `debug.reasoning.api_keys` field is the set of Glass-Box keys the Reasoner grounded against. See `README.md#glass-box-reasoning-integration` for the full handoff.

## Prerequisites

1. Backend services running through a deployed `API_BASE_URL`, or locally with `LOCAL_MODE=true`, `FIN_ENGINE_BASE_URL`, and `MODEL_PORTFOLIO_BASE_URL`
2. Two LLMs reachable: the **tool-calling LLM** (sec-agent's `LLM_BASE_URL`) and the **Glass-Box LLM** (configured inside `Reasoning_LLM_TiFin`). Both are typically the self-hosted GPU at `103.42.51.88:2205`, which requires VPN / GCP.
3. `Reasoning_LLM_TiFin` checked out at `../Reasoning_LLM_TiFin` (sibling path; sec-agent imports it via `sys.path` shim)
4. Agent running: `uv run uvicorn main:app --port 8090 --reload`

## Curl template

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "<QUERY>"}' | python3 -m json.tool

# With a session_id to chain follow-ups (the second turn typically reuses the
# cached api_keys/user_outputs and does NOT re-fire the tool)
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "<QUERY>", "session_id": "demo-1"}' | python3 -m json.tool
```

## Reference user

All user-specific queries target **user `1912650190`** — the user Glass-Box built its session evidence around. For current local smoke tests, omit `org_id` unless a specific endpoint requires it; passing an unvalidated org can make Financial Engine fetch an empty portfolio for this user.

---

## 1. Financial Engine — single-function (FE S1–S10)

Source: `data-fe.json` sessions 1–10. Every query should route to `financial_engine` with the `function` parameter set as shown.

| # | Query | Expected `function` |
|---|---|---|
| FE-S1 | `How is user 1912650190's money split across different asset types?` | `asset_breakdown` |
| FE-S2 | `How diversified is user 1912650190's portfolio?` | `diversification` |
| FE-S3 | `What are user 1912650190's top sectors?` | `sector_breakdown` |
| FE-S4 | `How is user 1912650190's portfolio split between large, mid, and small cap?` | `market_cap_breakdown` |
| FE-S5 | `What is user 1912650190's total exposure to HDFC Bank Ltd.?` | `single_holding_exposure` (param: `holding_name`) |
| FE-S6 | `Show me user 1912650190's top 5 individual stock exposures.` | `total_stock_exposure` (param: `top_n=5`) |
| FE-S7 | `Which AMC is user 1912650190 most concentrated in?` | `amc_preference` |
| FE-S8 | `Which sectors is user 1912650190 overweight or underweight versus the benchmark?` | `sector_preference` |
| FE-S9 | `Does user 1912650190 have a thematic investment focus?` | `theme_preference` |
| FE-S10 | `Does user 1912650190 have any strong factor tilt?` | `factor_preference` |

## 2. Financial Engine — multi-function (FE S11–S20)

Source: `data-fe.json` sessions 11–20. Each query should trigger two or more `financial_engine` calls (or at least the primary one) so the reasoning agent has the signals it needs for synthesis.

| # | Query | Expected functions |
|---|---|---|
| FE-S11 | `How much of user 1912650190's total portfolio is in equity mid caps?` | `asset_breakdown` + `market_cap_breakdown` |
| FE-S12 | `Do user 1912650190's top sector holdings match their overall investing preferences?` | `sector_breakdown` + `sector_preference` |
| FE-S13 | `Is user 1912650190's HDFC Bank exposure direct or mostly through funds, and which fund contributes most?` | `single_holding_exposure` + `amc_preference` |
| FE-S14 | `Does user 1912650190's portfolio look concentrated in a few stocks even though it is heavily tilted to one AMC?` | `total_stock_exposure` + `amc_preference` |
| FE-S15 | `Does user 1912650190's overall portfolio mix suggest they are leaning heavily towards equities?` | `asset_breakdown` + `factor_preference` |
| FE-S16 | `Is user 1912650190's dominant investment theme aligned with their biggest sector exposures?` | `theme_preference` + `sector_breakdown` |
| FE-S17 | `Does user 1912650190's sector bias line up with their market-cap profile?` | `sector_preference` + `market_cap_breakdown` |
| FE-S18 | `Are user 1912650190's top stock exposures enough to explain their strongest sector overweight?` | `total_stock_exposure` + `sector_preference` |
| FE-S19 | `Is user 1912650190's portfolio more concentrated by theme or by single-stock exposure?` | `theme_preference` + `total_stock_exposure` |
| FE-S20 | `Would you describe user 1912650190's portfolio as aggressive rather than defensive?` | `asset_breakdown` + `market_cap_breakdown` + `sector_preference` + `factor_preference` |

---

## 3. Model Portfolio — user-specific (MP-U S1–S11)

Source: `data-v0-mp_user_split.json`. All queries reference user `1912650190`.

| # | Query | Expected tool(s) |
|---|---|---|
| MP-U-S1 | `What is user 1912650190's stored overall risk profile?` | `get_risk_profile` |
| MP-U-S2 | `What portfolio is recommended for user 1912650190 if they invest 50000 as a one-time lump sum?` | `get_portfolio_options` (investment_type=LUMP_SUM) |
| MP-U-S3 | `What does the custom-assembled portfolio look like for user 1912650190 with a 50000 lump sum, and what were its backtest results?` | `portfolio_builder` |
| MP-U-S5 | `Are there mutual fund alternatives that could replace user 1912650190's current stock holdings?` | `stock_to_fund` |
| MP-U-S6 | `Is the recommended portfolio style consistent with user 1912650190's stored risk profile? Investment: 50000 lump sum.` | `get_risk_profile` + `get_portfolio_options` |
| MP-U-S7 | `Show both the standard portfolio recommendation and the custom-assembled portfolio for user 1912650190 with 50000 lump sum.` | `get_portfolio_options` + `portfolio_builder` |
| MP-U-S9 | `Is user 1912650190's current stock exposure narrower in scope compared to the mutual funds recommended for a 50000 lump sum investment?` | `get_portfolio_options` + `stock_to_fund` |
| MP-U-S11 | `What mutual fund portfolio would you recommend for user 1912650190 if they invest 10000 every month through a SIP?` | `get_portfolio_options` (investment_type=SIP) |

**Skipped from this suite:** MP-U-S4, S8, S10 are omitted from this compact demo list. `backtest_portfolio` is active, but backtest examples should use a concrete selected portfolio payload returned by a prior Model Portfolio call.

## 4. Model Portfolio — non-user (MP-NU S1–S10)

Source: `data-v0-mp_nonuser_split.json`. These don't reference any stored user.

| # | Query | Expected tool(s) |
|---|---|---|
| MP-NU-S1 | `Assess risk for a 30 year old earning 12 lakhs annually, long term horizon, willing to lose 20%, pin code 400001.` | `risk_profile_v2` |
| MP-NU-S2 | `I want to save 1 crore for retirement in 20 years with 10000 monthly SIP. What are my chances?` | `single_goal_optimizer` |
| MP-NU-S3 | `I have 50 lakhs and 20000 monthly SIP. Split across retirement in 20 years (critical, 1 crore) and house purchase in 5 years (important, 30 lakhs).` | `multi_goal_optimizer` |
| MP-NU-S4 | `What is the suggested default monthly SIP for reaching 1 crore over 30 years for retirement?` | `goal_defaults` |
| MP-NU-S7 | `Compare two goals: saving 1 crore for retirement in 20 years with 10000 SIP vs saving 30 lakhs for a house in 5 years with 15000 SIP. Which is more achievable?` | `single_goal_optimizer` (called twice) |
| MP-NU-S8 | `Which goal requires a larger monthly SIP: building a 1 crore retirement corpus over 30 years or saving 50 lakhs for a house in 10 years?` | `goal_defaults` (called twice) |
| MP-NU-S9 | `For a 30 year old earning 12 lakhs (pin 400001, long term, willing to lose 20%), does the risk assessment recommend something more aggressive or conservative than the retirement goal optimizer for 1 crore in 20 years with 10000 SIP?` | `risk_profile_v2` + `single_goal_optimizer` |
| MP-NU-S10 | `I have 50 lakhs and 20000 monthly SIP. Optimize across retirement (critical, 1 crore, 20 years) and house purchase (important, 30 lakhs, 5 years). Also show what the house goal would need on its own.` | `multi_goal_optimizer` + `single_goal_optimizer` (and optionally `goal_defaults`) |

**Skipped from this suite:** MP-NU-S5 uses `build_stock_portfolio`, which is reserved because the backend endpoint is currently broken. MP-NU-S6 requires `sip_timeseries`, which is not exposed as a sec-agent tool.

---

## 5. Loan-financed scenario (not in Glass-Box)

Exercises the `loan_financing_amount` parameter added to `goal_defaults` and `single_goal_optimizer`. Useful for showing that loan-financed goals are handled end-to-end.

| Query | Expected tool + params |
|---|---|
| `I need 50 lakhs for a house in 10 years, and 20 lakhs of that will come from a home loan. What's the default monthly SIP?` | `goal_defaults` with `loan_financing_amount=2000000` |
| `Optimize my retirement goal: 1 crore in 20 years, 10000 SIP, and I'll take a 25 lakh loan closer to the end.` | `single_goal_optimizer` with `loan_financing_amount=2500000` |

---

## How to read the response

Every `/ask` response includes:

- `answer` — the user-facing answer **produced by the Glass-Box Answerer** (not by the tool-calling LLM). Grounded in the Reasoner's trace.
- `session_id` — echoed back from the request (or `null` if none was supplied).
- `debug.iterations` — per-iteration tool plan from the tool-calling LLM.
- `debug.tool_results` — the tools that were called and the raw backend responses (the inputs the Reasoner grounded against).
- `debug.reasoning` — Glass-Box output:
  - `api_keys` — the Glass-Box description keys the Reasoner used (e.g. `["asset_breakdown"]`).
  - `trace` — the Reasoner's structured trace (EVIDENCE / CONCLUSION / CAVEATS, etc.).
  - `verifier_verdict` and `verifier_retries` — populated only when `REASONING_ARCHITECTURE=three_layer`.
  - `unmapped_tools` — tools that were called but had no Glass-Box mapping (should be empty for the demo queries below).
- `debug.reused_session_cache` — `true` when a follow-up turn reused the prior cache without re-firing any tool.

When validating against the Glass-Box eval dataset, compare `debug.reasoning.api_keys` against the session's `api_used_q1`, and compare `debug.reasoning.trace` against the corresponding entry in `Reasoning_LLM_TiFin/test_data/all_users_generated_sessions.json`.
