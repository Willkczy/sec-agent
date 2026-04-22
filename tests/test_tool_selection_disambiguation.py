"""
Negative-assertion tests: the LLM must NOT pick the wrong tool.

These cases don't come from the Glass-Box dataset — they capture
sec-agent-specific disambiguation edges where similarly-named tools can
be confused (get_risk_profile vs risk_profile_v2, single vs multi goal,
portfolio analysis vs fund discovery, chain-to-backtest traps).

Run:
    uv run pytest tests/test_tool_selection_disambiguation.py -m llm
"""

import pytest

from tests.conftest import majority_vote, tool_names


pytestmark = pytest.mark.llm

USER_ID = "1912650190"
ORG_ID = "2854263694"


class TestDisambiguation:

    @pytest.mark.anyio
    async def test_portfolio_does_not_chain_backtest(self, ask_llm):
        """Building a portfolio should NOT auto-chain into backtest_portfolio."""

        async def check():
            msg = await ask_llm(
                f"Build a medium risk portfolio for user 1018083528 with 20000 "
                f"monthly SIP."
            )
            return "backtest_portfolio" not in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_risk_lookup_not_v2(self, ask_llm):
        """Looking up an existing user's risk uses get_risk_profile, not v2."""

        async def check():
            msg = await ask_llm(f"What is user {USER_ID}'s risk profile?")
            names = tool_names(msg)
            return "get_risk_profile" in names and "risk_profile_v2" not in names

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_onboarding_risk_not_lookup(self, ask_llm):
        """Age/income/pin inputs should use risk_profile_v2, not get_risk_profile."""

        async def check():
            msg = await ask_llm(
                "Calculate risk for a 35-year-old with 20 lakh income, medium "
                "term horizon, can tolerate 25% loss, pin 110001."
            )
            names = tool_names(msg)
            return "risk_profile_v2" in names and "get_risk_profile" not in names

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_single_goal_not_multi(self, ask_llm):
        """A single goal should use single_goal_optimizer, not multi_goal."""

        async def check():
            msg = await ask_llm(
                "I want to save 50 lakh for a house in 10 years with 15000 "
                "monthly SIP. What are my chances?"
            )
            names = tool_names(msg)
            return (
                "single_goal_optimizer" in names
                and "multi_goal_optimizer" not in names
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_multi_goal_not_single(self, ask_llm):
        """Multiple goals should use multi_goal_optimizer, not single_goal."""

        async def check():
            msg = await ask_llm(
                "I have 10 lakh and 30000 SIP. Split between retirement "
                "(critical, 2 crore, 25 years) and child education "
                "(important, 50 lakh, 15 years)."
            )
            return "multi_goal_optimizer" in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_fund_search_not_portfolio_analysis(self, ask_llm):
        """Searching for new funds should NOT trigger financial_engine."""

        async def check():
            msg = await ask_llm(
                "Show me the best large cap mutual funds with low expense ratio."
            )
            names = tool_names(msg)
            return "search_funds" in names and "financial_engine" not in names

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_portfolio_analysis_not_fund_search(self, ask_llm):
        """Analyzing an existing portfolio should NOT trigger search_funds."""

        async def check():
            msg = await ask_llm(
                f"Show sector breakdown for user {USER_ID}'s portfolio. "
                f"Org {ORG_ID}."
            )
            names = tool_names(msg)
            return "financial_engine" in names and "search_funds" not in names

        assert await majority_vote(check)
