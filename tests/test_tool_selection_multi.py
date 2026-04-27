"""
Multi-tool LLM selection tests.

Queries adapted from the Glass-Box eval dataset where a single question
needs TWO OR MORE tool calls (or a single tool fired with multiple
function-param values) to answer:

  Reasoning_LLM_TiFin/example_data/
    - data-fe.json                sessions S11-S20  (financial_engine multi-function)
    - data-v0-mp_user_split.json   S6-S10           (cross-tool, user-specific)
    - data-v0-mp_nonuser_split.json S7-S10          (cross-tool, non-user)

Plus a handful of NL-to-ID SRC chains (search_funds -> get_fund_peers /
swap_recommendations) that the old test_tool_selection_multistep.py covered.

Matching notes
--------------
- The agent loops for up to 3 iterations; the LLM may emit these tools in
  parallel (one iteration, many calls) or serially (wait for each result).
  This harness only sees the FIRST message, so we accept "at least one of
  the expected tools on iteration 1" for most cases.
- For financial_engine we look at the set of `function` params, not just
  the tool name, since the same tool wraps 10 sub-operations.

Run:
    uv run pytest tests/test_tool_selection_multi.py -m llm
"""

import pytest

from tests.conftest import (
    majority_vote,
    tool_names,
    get_fe_functions,
)


pytestmark = pytest.mark.llm

USER_ID = "1912650190"
ORG_ID = "2854263694"


def _fe_ctx(q1: str) -> str:
    return f"{q1} (user {USER_ID}, org {ORG_ID})"


def _user_ctx(q1: str) -> str:
    return f"{q1} (user {USER_ID})"


# ==========================================================================
# data-fe.json S11-S20  —  financial_engine multi-function synthesis
# Each query needs 2+ FE sub-functions. We pass if the LLM hits at least
# one expected function on iteration 1 (chained iterations may add others).
# ==========================================================================


class TestFEMultiFunction:

    @pytest.mark.anyio
    async def test_s11_equity_midcap_cross(self, ask_llm):
        """Needs asset_breakdown + market_cap_breakdown."""

        async def check():
            msg = await ask_llm(
                _fe_ctx("How much of my total portfolio is in equity mid caps?")
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"asset_breakdown", "market_cap_breakdown"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s12_sector_vs_preference(self, ask_llm):
        """Needs sector_breakdown + sector_preference."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Do my top sector holdings match my overall investing preferences?"
                )
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"sector_breakdown", "sector_preference"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s13_hdfc_exposure_vs_amc(self, ask_llm):
        """Needs single_holding_exposure + amc_preference."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Is my HDFC Bank exposure direct or mostly through funds, and "
                    "which fund contributes the most?"
                )
            )
            fns = set(get_fe_functions(msg))
            return "single_holding_exposure" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s14_stock_concentration_vs_amc(self, ask_llm):
        """Needs total_stock_exposure + amc_preference."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Does my portfolio look concentrated in a few stocks even "
                    "though it seems heavily tilted to one AMC?"
                )
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"total_stock_exposure", "amc_preference"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s15_equity_heavy_vs_factor(self, ask_llm):
        """Needs asset_breakdown + factor_preference."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Does my overall portfolio mix suggest I am leaning heavily "
                    "towards equities across asset classes and factor styles?"
                )
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"asset_breakdown", "factor_preference"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s16_theme_vs_sector(self, ask_llm):
        """Needs theme_preference + sector_breakdown."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Is my dominant investment theme aligned with my biggest "
                    "sector exposures?"
                )
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"theme_preference", "sector_breakdown"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s17_sector_bias_vs_marketcap(self, ask_llm):
        """Needs sector_preference + market_cap_breakdown."""

        async def check():
            msg = await ask_llm(
                _fe_ctx("Does my sector bias line up with my market-cap profile?")
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"sector_preference", "market_cap_breakdown"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s18_stock_exposure_vs_sector_overweight(self, ask_llm):
        """Needs total_stock_exposure + sector_preference."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Are my top stock exposures enough to explain my strongest "
                    "sector overweight?"
                )
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"total_stock_exposure", "sector_preference"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s19_theme_vs_stock_concentration(self, ask_llm):
        """Needs theme_preference + total_stock_exposure."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Is my portfolio more concentrated by theme or by single-"
                    "stock exposure?"
                )
            )
            fns = set(get_fe_functions(msg))
            return bool(fns & {"theme_preference", "total_stock_exposure"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s20_aggressive_vs_defensive(self, ask_llm):
        """Needs asset_breakdown + market_cap_breakdown + sector_preference +
        factor_preference. Accept >= 2 of the 4 on iteration 1."""

        async def check():
            msg = await ask_llm(
                _fe_ctx(
                    "Would you describe this portfolio as aggressive rather than "
                    "defensive? Look at asset mix, market-cap tilt, sector bets, "
                    "and factor tilts."
                )
            )
            fns = set(get_fe_functions(msg))
            expected = {
                "asset_breakdown",
                "market_cap_breakdown",
                "sector_preference",
                "factor_preference",
            }
            return len(fns & expected) >= 2

        assert await majority_vote(check)


# ==========================================================================
# data-v0-mp_user_split.json S6-S10  —  cross-tool, user-specific
# Each session pairs get_portfolio_options/portfolio_builder with another
# user-scoped tool. First iteration may pick either side of the pair.
# ==========================================================================


class TestMPUserMultiTool:

    @pytest.mark.anyio
    async def test_s6_risk_plus_portfolio(self, ask_llm):
        """Needs get_risk_profile + get_portfolio_options (LUMP_SUM)."""

        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "Is the recommended portfolio style for a 50000 lump-sum "
                    "consistent with this user's stored risk profile?"
                )
            )
            names = set(tool_names(msg))
            return bool(names & {"get_portfolio_options", "get_risk_profile"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s7_portfolio_vs_builder(self, ask_llm):
        """Needs get_portfolio_options + portfolio_builder."""

        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "Between the standard portfolio recommendation and the "
                    "custom-assembled version for a 50000 lump-sum, which looks "
                    "better?"
                )
            )
            names = set(tool_names(msg))
            return bool(names & {"get_portfolio_options", "portfolio_builder"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s8_portfolio_vs_backtest(self, ask_llm):
        """Needs get_portfolio_options + backtest_portfolio."""

        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "After backtesting the recommended 50000 lump-sum fund "
                    "selection, did the projected performance change "
                    "significantly from the initial recommendation?"
                )
            )
            names = set(tool_names(msg))
            return bool(names & {"get_portfolio_options", "backtest_portfolio"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s9_stock_exposure_vs_funds(self, ask_llm):
        """Needs get_portfolio_options + stock_to_fund."""

        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "Is my current stock exposure narrower in scope compared to "
                    "the mutual funds recommended for my 50000 lump-sum investment?"
                )
            )
            names = set(tool_names(msg))
            return bool(names & {"get_portfolio_options", "stock_to_fund"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s10_builder_vs_backtest(self, ask_llm):
        """Needs portfolio_builder + backtest_portfolio."""

        async def check():
            msg = await ask_llm(
                _user_ctx(
                    "Comparing the custom-assembled 50000 lump-sum portfolio "
                    "against the modified fund selection, which shows better "
                    "historical performance?"
                )
            )
            names = set(tool_names(msg))
            return bool(names & {"portfolio_builder", "backtest_portfolio"})

        assert await majority_vote(check)


# ==========================================================================
# data-v0-mp_nonuser_split.json S7-S10  —  cross-tool, non-user
# ==========================================================================


class TestMPNonUserMultiTool:

    @pytest.mark.anyio
    async def test_s7_compare_single_goals(self, ask_llm):
        """Needs single_goal_optimizer (called twice with different scenarios)."""

        async def check():
            msg = await ask_llm(
                "Compare two goals: saving 1 crore for retirement in 20 years "
                "with 10000 monthly SIP vs saving 30 lakh for a house in 5 years "
                "with 15000 monthly SIP. Which is more achievable?"
            )
            return "single_goal_optimizer" in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s8_compare_goal_defaults(self, ask_llm):
        """Needs goal_defaults (called twice with different scenarios)."""

        async def check():
            msg = await ask_llm(
                "Which goal requires a larger monthly SIP: building a 1 crore "
                "retirement corpus over 30 years or saving 50 lakh for a house "
                "in 10 years?"
            )
            return "goal_defaults" in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s9_risk_vs_optimizer(self, ask_llm):
        """Needs risk_profile_v2 + single_goal_optimizer."""

        async def check():
            msg = await ask_llm(
                "Does the standalone retirement optimizer look more conservative "
                "than the onboarding risk assessment? Onboarding inputs: age 30, "
                "pretax income 1500000, pin 400001, long-term horizon, 15% "
                "willingness to lose. Retirement goal: 1 crore in 20 years with "
                "10000 monthly SIP."
            )
            names = set(tool_names(msg))
            return bool(names & {"risk_profile_v2", "single_goal_optimizer"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s10_multi_goal_struggling(self, ask_llm):
        """Needs multi_goal_optimizer + goal_defaults + single_goal_optimizer."""

        async def check():
            msg = await ask_llm(
                "Why is the house goal struggling in the multi-goal plan? "
                "Goals: house 50 lakh in 5 years, retirement 1 crore in 20 years. "
                "Total corpus 50 lakh, SIP 20000. Compare the multi-goal "
                "allocation against the standalone single-goal optimizer and the "
                "goal defaults for the house goal."
            )
            names = set(tool_names(msg))
            return bool(
                names
                & {"multi_goal_optimizer", "single_goal_optimizer", "goal_defaults"}
            )

        assert await majority_vote(check)


# ==========================================================================
# NL-to-ID SRC chains (not in Glass-Box; covered by old _multistep file).
# Fund name -> resolve via search_funds -> peers / swap_recommendations.
# ==========================================================================


class TestSRCMultiStep:

    @pytest.mark.anyio
    async def test_fund_name_to_peers(self, ask_llm):
        """Fund name query may need search_funds first to resolve the ID."""

        async def check():
            msg = await ask_llm("Show me the peers of SBI Large Cap Fund.")
            names = set(tool_names(msg))
            return bool(names & {"search_funds", "get_fund_peers"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_fund_name_swap(self, ask_llm):
        """Swap by fund name may need search_funds first."""

        async def check():
            msg = await ask_llm(
                "Find better alternatives to HDFC Mid Cap Fund based on cost."
            )
            names = set(tool_names(msg))
            return bool(names & {"search_funds", "swap_recommendations"})

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_portfolio_analysis_with_swaps(self, ask_llm):
        """Full portfolio analysis + swap suggestions."""

        async def check():
            msg = await ask_llm(
                f"Analyze user {USER_ID}'s portfolio in org {ORG_ID}: show "
                f"diversification and suggest better fund alternatives."
            )
            names = set(tool_names(msg))
            return bool(
                names & {"financial_engine", "portfolio_swap_recommendations"}
            )

        assert await majority_vote(check)
