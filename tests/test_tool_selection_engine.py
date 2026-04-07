"""
LLM tool selection tests for Financial Engine tool.

The financial_engine tool has a `function` sub-parameter that selects the
analytics operation. Tests validate both tool selection and function param.
"""

import json

import pytest

from tests.conftest import majority_vote, tool_names, extract_tool_calls


pytestmark = pytest.mark.llm

VALID_FUNCTIONS = {
    "diversification",
    "sector_breakdown",
    "asset_breakdown",
    "market_cap_breakdown",
    "single_holding_exposure",
    "total_stock_exposure",
    "amc_preference",
    "sector_preference",
    "theme_preference",
    "factor_preference",
}


class TestFinancialEngineToolSelection:

    @pytest.mark.anyio
    async def test_sector_breakdown(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Show sector breakdown for user 1912650190 in org 2854263694"
            )
            return tool_names(msg) == ["financial_engine"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_diversification(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Check diversification of portfolio for user 1912650190 org 2854263694"
            )
            return tool_names(msg) == ["financial_engine"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_asset_breakdown(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What is the asset breakdown for user 1912650190 in org 2854263694?"
            )
            return tool_names(msg) == ["financial_engine"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_market_cap_breakdown(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Show market cap distribution for user 1912650190 org 2854263694"
            )
            return tool_names(msg) == ["financial_engine"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_single_holding_exposure(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What is my exposure to Reliance in user 1912650190's portfolio in org 2854263694?"
            )
            return tool_names(msg) == ["financial_engine"]

        assert await majority_vote(check)


class TestFinancialEngineFunctionParam:
    """Validate the `function` sub-parameter matches the query intent."""

    @pytest.mark.anyio
    async def test_sector_breakdown_function_value(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Show sector breakdown for user 1912650190 in org 2854263694"
            )
            calls = extract_tool_calls(msg)
            if not calls or calls[0]["name"] != "financial_engine":
                return False
            fn = calls[0]["params"].get("function", "")
            return fn == "sector_breakdown"

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_diversification_function_value(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Check diversification of portfolio for user 1912650190 org 2854263694"
            )
            calls = extract_tool_calls(msg)
            if not calls or calls[0]["name"] != "financial_engine":
                return False
            fn = calls[0]["params"].get("function", "")
            return fn == "diversification"

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_function_value_is_valid_enum(self, ask_llm):
        """Any financial engine query should produce a valid function value."""

        async def check():
            msg = await ask_llm(
                "Show asset breakdown for user 1912650190 in org 2854263694"
            )
            calls = extract_tool_calls(msg)
            if not calls or calls[0]["name"] != "financial_engine":
                return False
            fn = calls[0]["params"].get("function", "")
            return fn in VALID_FUNCTIONS

        assert await majority_vote(check)
