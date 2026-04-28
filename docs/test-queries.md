# Test Queries Reference

This file is the source of truth for live `/ask` smoke-test queries. Query wording is based on `../Reasoning_LLM_TiFin/example_data/`, but adjusted where needed so the live agent has enough inputs to call the backend APIs.

Use a fresh `session_id` per test pair. For follow-ups, omit `user_id`; the agent should reuse the prior session cache and trusted context.

## Quick Checks

Expected response fields:

- First turn: `debug.tool_results` contains the expected tool calls.
- Follow-up: `debug.tool_results` is usually empty and `debug.reused_session_cache` is `true`.
- Two-layer reasoning: `debug.reasoning.verifier_verdict` is `null`.
- Three-layer reasoning: `debug.reasoning.verifier_verdict` is populated.

## Curl Templates

User-specific:

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"<QUERY>","user_id":"1912650190","session_id":"<SESSION>"}' \
  | python3 -m json.tool
```

Non-user:

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"<QUERY>","session_id":"<SESSION>"}' \
  | python3 -m json.tool
```

Follow-up:

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"<FOLLOW_UP>","session_id":"<SESSION>"}' \
  | python3 -m json.tool
```

## Financial Engine Smoke Pairs

All require request context `user_id: "1912650190"` on turn 1.

| Session | Turn 1 query | Turn 2 follow-up | Expected key(s) |
|---|---|---|---|
| `smoke-fe-asset` | `How is my money split across different asset types?` | `How did you calculate that?` | `asset_breakdown` |
| `smoke-fe-div` | `How diversified is my portfolio?` | `Why did it say N/A instead of High, Medium, or Low?` | `diversification` |
| `smoke-fe-sector` | `What are my top sectors?` | `How were those top sectors determined?` | `sector_breakdown` |
| `smoke-fe-cap` | `How is my portfolio split between large, mid, and small cap stocks?` | `How do you know Mid Cap is dominant?` | `market_cap_breakdown` |
| `smoke-fe-hdfc` | `What is my total exposure to HDFC Bank Ltd.?` | `How was that exposure figure calculated?` | `single_holding_exposure` |
| `smoke-fe-topstocks` | `Show me the top 5 individual stock exposures in my portfolio.` | `How did you rank those stocks?` | `total_stock_exposure` |
| `smoke-fe-amc` | `Which AMC am I most concentrated in?` | `How did you determine the AMC concentration?` | `amc_preference` |
| `smoke-fe-sector-pref` | `Which sectors am I overweight and underweight in versus the benchmark?` | `How were those active share numbers calculated?` | `sector_preference` |
| `smoke-fe-theme` | `Do I have a thematic investment focus?` | `How did you infer that there is a thematic focus?` | `theme_preference` |
| `smoke-fe-factor` | `Do I have any strong factor tilt?` | `Why was it classified as factor-neutral?` | `factor_preference` |

Good multi-tool FE checks:

| Session | Turn 1 query | Turn 2 follow-up | Expected key(s) |
|---|---|---|---|
| `smoke-fe-midcap-equity` | `How much of my total portfolio is in equity mid caps?` | `How did you calculate that combined number?` | `asset_breakdown` + `market_cap_breakdown` |
| `smoke-fe-aggressive` | `Would you describe this portfolio as aggressive rather than defensive?` | `How did you synthesize that view from the outputs?` | `asset_breakdown` + `market_cap_breakdown` + `sector_preference` + `factor_preference` |

## Model Portfolio User-Specific Smoke Pairs

All require request context `user_id: "1912650190"` on turn 1.

| Session | Turn 1 query | Turn 2 follow-up | Expected key(s) |
|---|---|---|---|
| `smoke-mpu-risk` | `What is my stored overall risk profile?` | `How was that risk label determined?` | `get_risk_profile` |
| `smoke-mpu-lump` | `What portfolio is recommended for me if I invest 50000 as a one-time lump sum?` | `How did it calculate those fund amounts?` | `get_portfolio_options_lumpsum` |
| `smoke-mpu-sip` | `What mutual fund portfolio would you recommend for me if I invest 10000 every month through an SIP?` | `How did you decide the split between those funds and calculate the monthly SIP amount for each one?` | `get_portfolio_options_sip` |
| `smoke-mpu-stockfund` | `Are there mutual fund alternatives that could replace my current stock holdings, and how does my exposure compare?` | `How did it derive that recommendation setup?` | `stock_to_fund` |
| `smoke-mpu-risk-vs-lump` | `Is the recommended portfolio style for a 50000 lump sum consistent with my stored risk profile?` | `Why is that a reasonable connection to make?` | `get_risk_profile` + `get_portfolio_options_lumpsum` |

Workflow-dependent tools:

- `portfolio_builder` can be smoked with `What does the custom-assembled portfolio look like for a 50000 lump sum?`, but it is semantically intended for user-selected funds.
- `backtest_portfolio` requires `selected_funds` in the tool arguments. Do not expect a clean one-shot natural-language test unless you include the selected fund IDs explicitly.

## Model Portfolio Non-User Smoke Pairs

Do not send `user_id` for these. The live query must include the inputs; fixture-style wording like "this onboarding-style assessment" is not enough by itself.

| Session | Turn 1 query | Turn 2 follow-up | Expected key(s) |
|---|---|---|---|
| `smoke-mpnu-risk` | `Assess risk for a 30 year old earning 12 lakhs annually, long term horizon, willing to lose 20%, pin code 400001.` | `How was that recommendation determined?` | `risk_profile_v2` |
| `smoke-mpnu-retire` | `For retirement, if I invest 10000 monthly SIP toward a 1 crore goal over 20 years, what allocation does the optimizer recommend?` | `How did it arrive at that recommendation?` | `single_goal_optimizer` |
| `smoke-mpnu-multigoal` | `I have 5 lakh corpus and 20000 monthly SIP. Split it across a critical house purchase goal of 50 lakh in 5 years and an important retirement goal of 2 crore in 30 years.` | `How was that split calculated?` | `multi_goal_optimizer` |
| `smoke-mpnu-defaults` | `What is the suggested default monthly SIP for reaching a 1 crore retirement corpus over 30 years?` | `How is that default generated?` | `goal_defaults` |
| `smoke-mpnu-compare-single` | `Which single-goal plan looks more achievable: retirement with 10000 monthly SIP toward 1 crore in 20 years, or a house purchase with 15000 monthly SIP toward 50 lakh in 5 years?` | `How did you compare those two results?` | `single_goal_optimizer` called twice |
| `smoke-mpnu-compare-defaults` | `Which goal requires a larger default monthly SIP: reaching a 1 crore retirement corpus over 30 years, or saving 50 lakh for a house purchase over 5 years?` | `How did you calculate that comparison?` | `goal_defaults` called twice |
| `smoke-mpnu-risk-vs-goal` | `For a 30 year old earning 12 lakhs, pin code 400001, long term horizon, willing to lose 20%, does the onboarding risk assessment look more aggressive than a retirement optimizer for 10000 monthly SIP toward 1 crore in 20 years?` | `Why can those two outputs disagree?` | `risk_profile_v2` + `single_goal_optimizer` |
| `smoke-mpnu-house-struggle` | `I have 5 lakh corpus and 20000 monthly SIP across a critical 50 lakh house goal in 5 years and an important 2 crore retirement goal in 30 years. Why is the house goal struggling? Also compare the house goal against its standalone default and single-goal optimizer result.` | `How did you infer that?` | `multi_goal_optimizer` + `goal_defaults` + `single_goal_optimizer` |

Unavailable fixture sessions:

- `data-v0-mp_nonuser_split.json` session 5 uses `build_stock_portfolio`, which is reserved because the backend currently returns HTTP 500.
- `data-v0-mp_nonuser_split.json` session 6 uses `sip_timeseries`, which is not exposed as a sec-agent tool.

## Disambiguation Tests

| Query | Should call | Should not call |
|---|---|---|
| `What is my stored overall risk profile?` with `user_id` | `get_risk_profile` | `risk_profile_v2` |
| `Assess risk for a 30 year old earning 12 lakhs annually, long term horizon, willing to lose 20%, pin code 400001.` | `risk_profile_v2` | `get_risk_profile` |
| `Build a medium risk portfolio with 20000 monthly SIP.` with `user_id` | `get_portfolio_options` | `backtest_portfolio` |
| `For retirement, if I invest 10000 monthly SIP toward a 1 crore goal over 20 years, what allocation does the optimizer recommend?` | `single_goal_optimizer` | `multi_goal_optimizer` |
| `I have 5 lakh corpus and 20000 monthly SIP. Split it across a house goal and a retirement goal.` | `multi_goal_optimizer` | `single_goal_optimizer` only |

## Missing Context Tests

User-specific query without request or session user context:

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"How is my money split across different asset types?"}' \
  | python3 -m json.tool
```

Expected answer: `I need a signed-in user context to answer portfolio-specific questions.`

Non-user fixture-style query without inputs:

```bash
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"What risk profile does this onboarding-style risk assessment recommend?","session_id":"bad-risk-v2"}' \
  | python3 -m json.tool
```

Expected behavior: the agent should ask for missing onboarding inputs or fail to call `risk_profile_v2`. This is not a valid live smoke query because `session_id` does not load fixture data.

## Full Example

```bash
# Turn 1
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"For a 30 year old earning 12 lakhs, pin code 400001, long term horizon, willing to lose 20%, does the onboarding risk assessment look more aggressive than a retirement optimizer for 10000 monthly SIP toward 1 crore in 20 years?","session_id":"smoke-mpnu-risk-vs-goal"}' \
  | python3 -m json.tool

# Turn 2
curl -s -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Why can those two outputs disagree?","session_id":"smoke-mpnu-risk-vs-goal"}' \
  | python3 -m json.tool
```
