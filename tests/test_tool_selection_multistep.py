"""
LLM tool selection tests for multi-step queries that may require 2+ tools.

These tests use relaxed matching: any of several acceptable tool combinations
is considered a pass.
"""

import pytest

from tests.conftest import majority_vote, tool_names


pytestmark = pytest.mark.llm


def _matches_any(selected: list[str], acceptable: list[list[str]]) -> bool:
    """Check if selected tools match any of the acceptable options."""
    return any(sorted(selected) == sorted(option) for option in acceptable)


class TestMultiStepToolSelection:

    @pytest.mark.anyio
    async def test_fund_name_to_peers(self, ask_llm):
        """Fund name query may need search_funds first to resolve the ID."""
        acceptable = [
            ["search_funds"],
            ["get_fund_peers"],
            ["get_fund_peers", "search_funds"],
        ]

        async def check():
            msg = await ask_llm("Show me the peers of SBI Large Cap Fund")
            return _matches_any(tool_names(msg), acceptable)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_fund_name_swap(self, ask_llm):
        """Swap by fund name may need search_funds first."""
        acceptable = [
            ["search_funds"],
            ["swap_recommendations"],
            ["search_funds", "swap_recommendations"],
        ]

        async def check():
            msg = await ask_llm(
                "Find better alternatives to HDFC Mid Cap Fund based on cost"
            )
            return _matches_any(tool_names(msg), acceptable)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_risk_then_portfolio(self, ask_llm):
        """Risk profile + portfolio build could be combined or sequential."""
        acceptable = [
            ["get_portfolio_options"],
            ["get_risk_profile"],
            ["get_portfolio_options", "get_risk_profile"],
        ]

        async def check():
            msg = await ask_llm(
                "Determine my risk profile and build a portfolio. User 12345, 50000 SIP."
            )
            return _matches_any(tool_names(msg), acceptable)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_portfolio_analysis_with_swaps(self, ask_llm):
        """Full portfolio analysis + swap suggestions."""
        acceptable = [
            ["portfolio_swap_recommendations"],
            ["financial_engine"],
            ["financial_engine", "portfolio_swap_recommendations"],
        ]

        async def check():
            msg = await ask_llm(
                "Analyze user 1912650190's portfolio in org 2854263694: "
                "show diversification and suggest better fund alternatives"
            )
            return _matches_any(tool_names(msg), acceptable)

        assert await majority_vote(check)
