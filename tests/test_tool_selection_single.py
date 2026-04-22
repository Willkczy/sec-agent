"""
Single-tool LLM selection tests.

Queries are adapted from the Glass-Box eval dataset:
  Reasoning_LLM_TiFin/example_data/
    - data-fe.json                sessions S1-S10   (financial_engine sub-functions)
    - data-v0-mp_user_split.json   S1-S5, S11       (user-specific MP tools)
    - data-v0-mp_nonuser_split.json S1-S5           (non-user MP tools)

Each test asks the LLM for exactly ONE tool call. For financial_engine we
also assert the `function` sub-param, since the single tool wraps 10 distinct
operations.

Run:
    uv run pytest tests/test_tool_selection_single.py -m llm
"""

import pytest

from tests.conftest import (
    majority_vote,
    tool_names,
    extract_tool_calls,
    get_fe_functions,
)


pytestmark = pytest.mark.llm

# Standard identity used across the Glass-Box sessions
USER_ID = "1912650190"
ORG_ID = "2854263694"


def _fe_ctx(q1: str) -> str:
    """Append user + org suffix expected by financial_engine tools."""
    return f"{q1} (user {USER_ID}, org {ORG_ID})"


def _user_ctx(q1: str) -> str:
    """Append user-only suffix for model-portfolio user-specific tools."""
    return f"{q1} (user {USER_ID})"


# ==========================================================================
# data-fe.json S1-S10  —  financial_engine single-function cases
# ==========================================================================


class TestFESingleFunction:

    @pytest.mark.anyio
    async def test_s1_asset_breakdown(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _fe_ctx("How is my money split across different asset types?")
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["asset_breakdown"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_diversification(self, ask_llm):
        async def check():
            msg = await ask_llm(_fe_ctx("How diversified is my portfolio?"))
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["diversification"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s3_sector_breakdown(self, ask_llm):
        async def check():
            msg = await ask_llm(_fe_ctx("What are my top sectors?"))
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["sector_breakdown"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s4_market_cap_breakdown(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "How is my portfolio split between large, mid, and small cap stocks?"
                )
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["market_cap_breakdown"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s5_single_holding_exposure(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _fe_ctx("What is my total exposure to HDFC Bank Ltd.?")
            )
            calls = extract_tool_calls(msg)
            if not calls or calls[0]["name"] != "financial_engine":
                return False
            params = calls[0]["params"]
            return (
                params.get("function") == "single_holding_exposure"
                and "HDFC" in params.get("parameters", {}).get("holding_name", "")
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s6_total_stock_exposure(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _fe_ctx("Show me the top 5 individual stock exposures in my portfolio.")
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["total_stock_exposure"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s7_amc_preference(self, ask_llm):
        async def check():
            msg = await ask_llm(_fe_ctx("Which AMC am I most concentrated in?"))
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["amc_preference"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s8_sector_preference(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Which sectors am I overweight and underweight in versus the benchmark?"
                )
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["sector_preference"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s9_theme_preference(self, ask_llm):
        async def check():
            msg = await ask_llm(_fe_ctx("Do I have a thematic investment focus?"))
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["theme_preference"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s10_factor_preference(self, ask_llm):
        async def check():
            msg = await ask_llm(_fe_ctx("Do I have any strong factor tilt?"))
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["factor_preference"]
            )

        assert await majority_vote(check)


# ==========================================================================
# data-v0-mp_user_split.json S1-S5, S11  —  user-specific model portfolio
# ==========================================================================


class TestMPUserSingleTool:

    @pytest.mark.anyio
    async def test_s1_risk_profile(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _user_ctx("What is this user's stored overall risk profile?")
            )
            return tool_names(msg) == ["get_risk_profile"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_portfolio_lumpsum(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "What portfolio is recommended for me if I invest 50000 as a "
                    "one-time lump sum?"
                )
            )
            return tool_names(msg) == ["get_portfolio_options"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_investment_type_lumpsum(self, ask_llm):
        """Lump-sum query must carry investment_type=LUMP_SUM."""

        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "Show me the portfolio options for a 50000 one-time lump sum."
                )
            )
            for c in extract_tool_calls(msg):
                if c["name"] == "get_portfolio_options":
                    return c["params"].get("investment_type") == "LUMP_SUM"
            return False

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s3_portfolio_builder(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "What does the custom-assembled portfolio look like for a 50000 "
                    "lump sum, and what were its backtest results?"
                )
            )
            return tool_names(msg) == ["portfolio_builder"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s5_stock_to_fund(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "Are there mutual fund alternatives that could replace my "
                    "current stock holdings, and how does my exposure compare?"
                )
            )
            return tool_names(msg) == ["stock_to_fund"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s11_portfolio_sip(self, ask_llm):
        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "What mutual fund portfolio would you recommend for me if I "
                    "invest 10000 every month through an SIP?"
                )
            )
            return tool_names(msg) == ["get_portfolio_options"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s11_investment_type_sip(self, ask_llm):
        """Monthly SIP query must carry investment_type=SIP."""

        async def check():
            msg = await ask_llm(
                _user_ctx("Build an SIP portfolio of 10000 per month for me.")
            )
            for c in extract_tool_calls(msg):
                if c["name"] == "get_portfolio_options":
                    return c["params"].get("investment_type") == "SIP"
            return False

        assert await majority_vote(check)


# ==========================================================================
# data-v0-mp_nonuser_split.json S1-S5  —  non-user model portfolio
# (S6 sip_timeseries has no sec-agent tool; skipped.)
# ==========================================================================


class TestMPNonUserSingleTool:

    @pytest.mark.anyio
    async def test_s1_risk_profile_v2(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What risk profile does an onboarding risk assessment recommend "
                "for a 30-year-old earning 1500000 per year, pin code 400001, "
                "long-term horizon, willing to lose 15%?"
            )
            return tool_names(msg) == ["risk_profile_v2"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_single_goal_optimizer(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What allocation does a single-goal optimizer recommend for a "
                "retirement goal of 1 crore in 20 years with 10000 monthly SIP?"
            )
            return tool_names(msg) == ["single_goal_optimizer"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s3_multi_goal_optimizer(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "How is a multi-goal optimizer splitting money across a house goal "
                "in 5 years (50 lakh) and a retirement goal in 20 years (1 crore), "
                "given 50 lakh starting corpus and 20000 monthly SIP?"
            )
            return tool_names(msg) == ["multi_goal_optimizer"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s4_goal_defaults(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What is the suggested default monthly SIP for reaching a 1 crore "
                "retirement corpus over 30 years?"
            )
            return tool_names(msg) == ["goal_defaults"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s5_build_stock_portfolio(self, ask_llm):
        """Pass the NL description through `query`; honour max_stocks."""

        async def check():
            msg = await ask_llm(
                "Build me a large-cap stock portfolio with up to 10 stocks."
            )
            calls = extract_tool_calls(msg)
            if not calls or calls[0]["name"] != "build_stock_portfolio":
                return False
            params = calls[0]["params"]
            return (
                isinstance(params.get("query"), str)
                and params["query"].strip() != ""
                and params.get("max_stocks") == 10
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_loan_financed_goal(self, ask_llm):
        """A loan-financed goal should surface loan_financing_amount so the
        backend can subtract it from the target corpus."""

        async def check():
            msg = await ask_llm(
                "I need 50 lakhs for a house in 10 years, and 20 lakhs of that "
                "will come from a home loan. What's the default monthly SIP?"
            )
            for c in extract_tool_calls(msg):
                if c["name"] in ("goal_defaults", "single_goal_optimizer"):
                    amt = c["params"].get("loan_financing_amount")
                    if isinstance(amt, (int, float)) and amt > 0:
                        return True
            return False

        assert await majority_vote(check)


# ==========================================================================
# Non-Glass-Box coverage
# determine_income_sector is a sec-agent tool not referenced in the eval set.
# ==========================================================================


class TestDetermineIncomeSector:

    @pytest.mark.anyio
    async def test_income_sector_classification(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Classify income sector for a household where one person is a "
                "software engineer at an IT company and spouse is a doctor."
            )
            return tool_names(msg) == ["determine_income_sector"]

        assert await majority_vote(check)
