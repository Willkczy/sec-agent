"""
LLM tool selection tests for SRC service tools.

Tools covered: search_funds, swap_recommendations, portfolio_swap_recommendations,
get_fund_peers, stock_research_data, parse_query, can_support
"""

import pytest

from tests.conftest import majority_vote, tool_names


pytestmark = pytest.mark.llm


class TestSearchFunds:

    @pytest.mark.anyio
    async def test_basic_large_cap_query(self, ask_llm):
        async def check():
            msg = await ask_llm("Show me the best large cap mutual funds")
            return tool_names(msg) == ["search_funds"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_complex_filter_query(self, ask_llm):
        async def check():
            msg = await ask_llm("Low expense ratio mid cap funds with high returns")
            return tool_names(msg) == ["search_funds"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_amc_specific_query(self, ask_llm):
        async def check():
            msg = await ask_llm("Show SBI large cap funds")
            return tool_names(msg) == ["search_funds"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_top_performing_query(self, ask_llm):
        async def check():
            msg = await ask_llm("Top performing mid cap funds this year")
            return tool_names(msg) == ["search_funds"]

        assert await majority_vote(check)


class TestGetFundPeers:

    @pytest.mark.anyio
    async def test_peer_comparison_with_isin(self, ask_llm):
        async def check():
            msg = await ask_llm("Compare fund with ISIN INF209K01YY8 against its peers")
            return tool_names(msg) == ["get_fund_peers"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_peer_comparison_with_security_id(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Show peers for fund with internal security ID 130685 in org 2854263694"
            )
            return tool_names(msg) == ["get_fund_peers"]

        assert await majority_vote(check)


class TestSwapRecommendations:

    @pytest.mark.anyio
    async def test_swap_by_returns(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What are better alternatives to fund with ID 130685 based on returns?"
            )
            return tool_names(msg) == ["swap_recommendations"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_swap_by_cost(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Find cheaper alternatives for fund ID 130685"
            )
            return tool_names(msg) == ["swap_recommendations"]

        assert await majority_vote(check)


class TestPortfolioSwapRecommendations:

    @pytest.mark.anyio
    async def test_full_portfolio_swap(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Analyze the full portfolio of user 1912650190 in org 2854263694 and suggest swaps"
            )
            return tool_names(msg) == ["portfolio_swap_recommendations"]

        assert await majority_vote(check)


class TestStockResearchData:

    @pytest.mark.anyio
    async def test_stock_research_by_isin(self, ask_llm):
        async def check():
            msg = await ask_llm("Get stock research data for ISIN INE002A01018")
            return tool_names(msg) == ["stock_research_data"]

        assert await majority_vote(check)


class TestCanSupport:

    @pytest.mark.anyio
    async def test_unsupported_query(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Can the system handle a query about cryptocurrency trading?"
            )
            return tool_names(msg) == ["can_support"]

        assert await majority_vote(check)
