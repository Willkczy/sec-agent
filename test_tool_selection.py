"""
Dry-run test: verify the LLM selects the correct tools for various queries.
Does NOT call backend APIs — only checks which tools the model picks.

Usage:
    uv run python test_tool_selection.py
"""

import asyncio
import json

from openai import AsyncOpenAI
from config import settings
from tools import get_openai_tools
from prompts import SYSTEM_PROMPT

OPENAI_TOOLS = get_openai_tools()

llm = AsyncOpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY)

# -- Test cases: (query, list of acceptable tool names) ---------------------
# Some queries have multiple valid approaches, so we accept alternatives.
# Based on actual API contracts in securities-recommendation.
TEST_CASES = [
    # --- SRC: Fund search (natural language → /get_query_data) ---
    (
        "Show me the best large cap mutual funds",
        [["search_funds"]],
    ),
    (
        "Low expense ratio mid cap funds with high returns",
        [["search_funds"]],
    ),
    # --- SRC: Peer comparison (needs security_id → /get_fund_peers) ---
    # get_fund_peers needs an internalSecurityId or ISIN, not a fund name.
    # The model should either call search_funds first to get the ID, or
    # call get_fund_peers directly if the user provides an ID.
    (
        "Compare fund with ISIN INF209K01YY8 against its peers",
        [["get_fund_peers"]],
    ),
    # --- SRC: Swap recommendations (needs internal_security_id_list) ---
    (
        "What are better alternatives to fund with ID 130685 based on returns?",
        [["swap_recommendations"]],
    ),
    # --- SRC: Portfolio swap (needs user_id + org_id) ---
    (
        "Analyze the full portfolio of user 1912650190 in org 2854263694 and suggest swaps",
        [["portfolio_swap_recommendations"]],
    ),
    # --- SRC: Stock research data (Axis org, needs ISINs) ---
    (
        "Get stock research data for ISIN INE002A01018",
        [["stock_research_data"]],
    ),
    # --- Financial Engine: portfolio analytics ---
    (
        "Show sector breakdown for user 1912650190 in org 2854263694",
        [["financial_engine"]],
    ),
    (
        "Check diversification of portfolio for user 1912650190 org 2854263694",
        [["financial_engine"]],
    ),
    # --- Model Portfolio: build portfolio ---
    (
        "Build me a portfolio with 50000 SIP investment, medium risk, user ID 100",
        [["get_portfolio_options"]],
    ),
    # --- Model Portfolio: single goal optimization ---
    (
        "I want to save 1 crore in 20 years with 10000 monthly SIP for retirement",
        [["single_goal_optimizer"]],
    ),
    # --- Model Portfolio: multi goal optimization ---
    (
        "I have 50 lakhs and 20000 monthly SIP. Optimize across retirement in 20 years (critical, 1 crore) and house in 5 years (important, 30 lakhs)",
        [["multi_goal_optimizer"]],
    ),
    # --- Model Portfolio: risk profile ---
    (
        "What is the risk profile for user 12345?",
        [["get_risk_profile"]],
    ),
    # --- Model Portfolio: goal defaults ---
    (
        "What SIP amount should I target for a 50 lakh goal in 15 years?",
        [["goal_defaults"]],
    ),
    # --- ML Recommendations: collaborative filtering ---
    (
        "Show ML-based personalized fund recommendations for user 1912650190",
        [["ml_fund_discovery"]],
    ),
    # --- Multi-step: fund name → need to search first, then use result ---
    # The model should recognize it needs search_funds first to resolve
    # the fund name to an ID before calling get_fund_peers.
    (
        "Show me the peers of SBI Large Cap Fund",
        [
            ["search_funds"],           # first call: resolve name to ID
            ["get_fund_peers"],         # acceptable if model assumes ID
            ["search_funds", "get_fund_peers"],  # both in one shot
        ],
    ),
]


async def test_one(query: str, acceptable: list[list[str]]) -> dict:
    """Send a query and check which tools the LLM selects."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    resp = await llm.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        tools=OPENAI_TOOLS,
        temperature=0.1,  # low temp for deterministic selection
        max_tokens=settings.LLM_MAX_TOKENS,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False}
        },
    )
    choice = resp.choices[0]
    msg = choice.message

    if not msg.tool_calls:
        selected = []
        text = msg.content or "(empty)"
        params_list = []
    else:
        selected = [tc.function.name for tc in msg.tool_calls]
        params_list = []
        for tc in msg.tool_calls:
            try:
                params_list.append(json.loads(tc.function.arguments))
            except json.JSONDecodeError:
                params_list.append({})
        text = None

    # Check if selected tools match any of the acceptable options
    match = any(sorted(selected) == sorted(option) for option in acceptable)

    return {
        "query": query,
        "acceptable": acceptable,
        "selected": selected,
        "params": params_list,
        "match": match,
        "text_response": text,
    }


async def main():
    print(f"LLM: {settings.LLM_MODEL} @ {settings.LLM_BASE_URL}")
    print(f"Tools loaded: {len(OPENAI_TOOLS)}")
    print(f"Running {len(TEST_CASES)} test cases...\n")
    print("=" * 80)

    passed = 0
    failed = 0

    for query, acceptable in TEST_CASES:
        try:
            result = await test_one(query, acceptable)
        except Exception as e:
            print(f"  QUERY:  {query}")
            print(f"  ERROR:  {e}")
            print("=" * 80)
            failed += 1
            continue

        status = "PASS" if result["match"] else "FAIL"
        if result["match"]:
            passed += 1
        else:
            failed += 1

        print(f"  [{status}] {query}")
        print(f"  Expected (any of): {acceptable}")
        print(f"  Selected:          {result['selected']}")
        if result["params"]:
            for i, p in enumerate(result["params"]):
                print(f"  Params[{i}]:         {json.dumps(p, ensure_ascii=False)}")
        if result["text_response"]:
            print(f"  Text:              {result['text_response'][:200]}")
        print("=" * 80)

    print(f"\nResults: {passed}/{passed + failed} passed")


if __name__ == "__main__":
    asyncio.run(main())
