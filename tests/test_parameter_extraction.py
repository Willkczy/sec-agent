"""
LLM tests for parameter extraction — validates types, required fields,
enum values, and value extraction from natural language.
"""

import json

import pytest

from tests.conftest import majority_vote, extract_tool_calls
from tools import TOOLS


pytestmark = pytest.mark.llm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_first_call(msg, expected_tool=None):
    """Extract the first tool call's params. Optionally assert tool name."""
    calls = extract_tool_calls(msg)
    if not calls:
        return None
    if expected_tool and calls[0]["name"] != expected_tool:
        return None
    return calls[0]["params"]


# ---------------------------------------------------------------------------
# Required parameters present
# ---------------------------------------------------------------------------


class TestRequiredParams:

    @pytest.mark.anyio
    async def test_search_funds_has_query(self, ask_llm):
        async def check():
            msg = await ask_llm("Show me best large cap mutual funds")
            params = _get_first_call(msg, "search_funds")
            if params is None:
                return False
            return "query" in params and isinstance(params["query"], str)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_swap_recommendations_required(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Find better alternatives to fund ID 130685 based on returns"
            )
            params = _get_first_call(msg, "swap_recommendations")
            if params is None:
                return False
            return (
                "recommendation_type" in params
                and "internal_security_id_list" in params
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_financial_engine_required(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Show sector breakdown for user 1912650190 in org 2854263694"
            )
            params = _get_first_call(msg, "financial_engine")
            if params is None:
                return False
            return "function" in params and "parameters" in params

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_single_goal_optimizer_required(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Save 1 crore in 20 years with 10000 monthly SIP for retirement"
            )
            params = _get_first_call(msg, "single_goal_optimizer")
            if params is None:
                return False
            required = {"investment_type", "amount", "target_amount", "time_horizon_months"}
            return required.issubset(set(params.keys()))

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_get_portfolio_options_required(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Build a portfolio with 50000 SIP, medium risk, user ID 100"
            )
            params = _get_first_call(msg, "get_portfolio_options")
            if params is None:
                return False
            return (
                "amount" in params
                and "user_id" in params
                and "investment_type" in params
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_stock_research_data_required(self, ask_llm):
        async def check():
            msg = await ask_llm("Get stock research data for ISIN INE002A01018")
            params = _get_first_call(msg, "stock_research_data")
            if params is None:
                return False
            return "ids" in params and "id_type" in params

        assert await majority_vote(check)


# ---------------------------------------------------------------------------
# Enum validation
# ---------------------------------------------------------------------------


class TestEnumValues:

    RECOMMENDATION_TYPES = {"returns", "risk", "cost"}
    INVESTMENT_TYPES_PORTFOLIO = {"LUMP_SUM", "SIP"}
    INVESTMENT_TYPES_GOAL = {"SIP", "LUMPSUM"}
    FIN_ENGINE_FUNCTIONS = {
        "diversification", "sector_breakdown", "asset_breakdown",
        "market_cap_breakdown", "single_holding_exposure", "total_stock_exposure",
        "amc_preference", "sector_preference", "theme_preference", "factor_preference",
    }
    RISK_PREFERENCES = {"VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"}

    @pytest.mark.anyio
    async def test_recommendation_type_enum(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Find better alternatives to fund ID 130685 based on returns"
            )
            params = _get_first_call(msg, "swap_recommendations")
            if params is None:
                return False
            return params.get("recommendation_type") in self.RECOMMENDATION_TYPES

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_investment_type_enum_portfolio(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Build a portfolio with 50000 SIP investment, user ID 100"
            )
            params = _get_first_call(msg, "get_portfolio_options")
            if params is None:
                return False
            return params.get("investment_type") in self.INVESTMENT_TYPES_PORTFOLIO

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_investment_type_enum_goal(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Save 1 crore in 20 years with 10000 monthly SIP for retirement"
            )
            params = _get_first_call(msg, "single_goal_optimizer")
            if params is None:
                return False
            return params.get("investment_type") in self.INVESTMENT_TYPES_GOAL

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_financial_engine_function_enum(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Show sector breakdown for user 1912650190 in org 2854263694"
            )
            params = _get_first_call(msg, "financial_engine")
            if params is None:
                return False
            return params.get("function") in self.FIN_ENGINE_FUNCTIONS

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_risk_preference_enum(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Build a portfolio with 50000 SIP, medium risk, user ID 100"
            )
            params = _get_first_call(msg, "get_portfolio_options")
            if params is None:
                return False
            pref = params.get("portfolio_risk_preference")
            # Optional param — if present, must be valid
            if pref is None:
                return True
            return pref in self.RISK_PREFERENCES

        assert await majority_vote(check)


# ---------------------------------------------------------------------------
# Value extraction from natural language
# ---------------------------------------------------------------------------


class TestValueExtraction:

    @pytest.mark.anyio
    async def test_extracts_amount(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Build a portfolio with 50000 SIP investment, user ID 100"
            )
            params = _get_first_call(msg, "get_portfolio_options")
            if params is None:
                return False
            amount = params.get("amount")
            return amount == 50000 or amount == "50000"

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_extracts_user_id(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What is the risk profile for user 12345?"
            )
            params = _get_first_call(msg, "get_risk_profile")
            if params is None:
                return False
            uid = params.get("user_id")
            return uid == 12345 or uid == "12345"

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_extracts_time_horizon_months(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Save 1 crore in 20 years with 10000 monthly SIP for retirement"
            )
            params = _get_first_call(msg, "single_goal_optimizer")
            if params is None:
                return False
            months = params.get("time_horizon_months")
            # 20 years = 240 months, allow some tolerance
            return months is not None and 230 <= int(months) <= 250

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_extracts_target_amount_crore(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Save 1 crore in 20 years with 10000 monthly SIP for retirement"
            )
            params = _get_first_call(msg, "single_goal_optimizer")
            if params is None:
                return False
            target = params.get("target_amount")
            # 1 crore = 10000000
            return target is not None and int(target) == 10_000_000

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_extracts_security_id_list(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Find better alternatives to fund ID 130685 based on returns"
            )
            params = _get_first_call(msg, "swap_recommendations")
            if params is None:
                return False
            ids = params.get("internal_security_id_list")
            if not isinstance(ids, list) or len(ids) == 0:
                return False
            # Should contain 130685 in some form
            return any(str(i) == "130685" for i in ids)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_extracts_isin(self, ask_llm):
        async def check():
            msg = await ask_llm("Get stock research data for ISIN INE002A01018")
            params = _get_first_call(msg, "stock_research_data")
            if params is None:
                return False
            ids = params.get("ids", [])
            return "INE002A01018" in ids

        assert await majority_vote(check)
