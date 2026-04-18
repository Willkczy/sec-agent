"""
Tool selection tests based on Glass-Box eval dataset (41 query -> API mappings).

Source: Reasoning_LLM_TiFin/example_data/
  - data-fe.json (20 Financial Engine sessions)
  - data-v0-mp_user_split.json (11 Model Portfolio user-specific sessions)
  - data-v0-mp_nonuser_split.json (10 Model Portfolio non-user sessions)

Glass-Box queries are adapted for sec-agent by:
  - Adding user IDs and org IDs (Glass-Box assumes logged-in user)
  - Mapping FE function names to financial_engine tool + function param
  - Mapping MP API names to sec-agent tool names
  - Skipping sip_timeseries (no sec-agent tool for this)

Tests are dry-run only — they check which tools the LLM selects,
NOT whether the API call succeeds.
"""

import pytest

from tests.conftest import (
    majority_vote,
    tool_names,
    extract_tool_calls,
    get_fe_functions,
    matches_any,
)


pytestmark = pytest.mark.llm

# Reference user ID and org used across FE and MP user-specific tests
USER_ID = "1912650190"
ORG_ID = "2854263694"


# ==========================================================================
# Financial Engine — Single-function sessions (S1–S10)
# All should select tool=financial_engine with the correct function param
# ==========================================================================


class TestFESingleFunction:
    """FE S1–S10: each query maps to exactly one financial_engine function."""

    @pytest.mark.anyio
    async def test_s1_asset_breakdown(self, ask_llm):
        """FE-S1: How is my money split across different asset types?"""

        async def check():
            msg = await ask_llm(
                f"How is user {USER_ID}'s money split across different asset types? "
                f"Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["asset_breakdown"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_diversification(self, ask_llm):
        """FE-S2: How diversified is my portfolio?"""

        async def check():
            msg = await ask_llm(
                f"How diversified is user {USER_ID}'s portfolio? Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["diversification"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s3_sector_breakdown(self, ask_llm):
        """FE-S3: What are my top sectors?"""

        async def check():
            msg = await ask_llm(
                f"What are the top sectors for user {USER_ID}? Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["sector_breakdown"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s4_market_cap_breakdown(self, ask_llm):
        """FE-S4: How is my portfolio split between large, mid, and small cap?"""

        async def check():
            msg = await ask_llm(
                f"How is user {USER_ID}'s portfolio split between large, mid, "
                f"and small cap stocks? Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["market_cap_breakdown"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s5_single_holding_exposure(self, ask_llm):
        """FE-S5: What is my total exposure to HDFC Bank Ltd.?"""

        async def check():
            msg = await ask_llm(
                f"What is user {USER_ID}'s total exposure to HDFC Bank Ltd.? "
                f"Org {ORG_ID}."
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
        """FE-S6: Show me the top 5 individual stock exposures."""

        async def check():
            msg = await ask_llm(
                f"Show me the top 5 individual stock exposures in user "
                f"{USER_ID}'s portfolio. Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["total_stock_exposure"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s7_amc_preference(self, ask_llm):
        """FE-S7: Which AMC am I most concentrated in?"""

        async def check():
            msg = await ask_llm(
                f"Which AMC is user {USER_ID} most concentrated in? Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["amc_preference"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s8_sector_preference(self, ask_llm):
        """FE-S8: Which sectors am I overweight/underweight vs benchmark?"""

        async def check():
            msg = await ask_llm(
                f"Which sectors is user {USER_ID} overweight and underweight in "
                f"versus the benchmark? Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["sector_preference"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s9_theme_preference(self, ask_llm):
        """FE-S9: Do I have a thematic investment focus?"""

        async def check():
            msg = await ask_llm(
                f"Does user {USER_ID} have a thematic investment focus? Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["theme_preference"]
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s10_factor_preference(self, ask_llm):
        """FE-S10: Do I have any strong factor tilt?"""

        async def check():
            msg = await ask_llm(
                f"Does user {USER_ID} have any strong factor tilt in their "
                f"portfolio? Org {ORG_ID}."
            )
            return (
                tool_names(msg) == ["financial_engine"]
                and get_fe_functions(msg) == ["factor_preference"]
            )

        assert await majority_vote(check)


# ==========================================================================
# Financial Engine — Multi-function sessions (S11–S20)
# Each query needs financial_engine called with 2+ different functions.
# We accept either multiple calls or at least one correct function.
# ==========================================================================


class TestFEMultiFunction:
    """FE S11–S20: queries that need 2+ financial_engine function calls."""

    @pytest.mark.anyio
    async def test_s11_equity_midcap_cross(self, ask_llm):
        """FE-S11: How much of my total portfolio is in equity mid caps?
        Needs: asset_breakdown + market_cap_breakdown"""

        async def check():
            msg = await ask_llm(
                f"How much of user {USER_ID}'s total portfolio is in equity "
                f"mid caps? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "asset_breakdown" in fns or "market_cap_breakdown" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s12_sector_vs_preference(self, ask_llm):
        """FE-S12: Do my top sector holdings match my investing preferences?
        Needs: sector_breakdown + sector_preference"""

        async def check():
            msg = await ask_llm(
                f"Do user {USER_ID}'s top sector holdings match their overall "
                f"investing preferences? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "sector_breakdown" in fns or "sector_preference" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s13_hdfc_exposure_vs_amc(self, ask_llm):
        """FE-S13: Is HDFC Bank exposure direct or through funds? Which fund contributes most?
        Needs: single_holding_exposure + amc_preference"""

        async def check():
            msg = await ask_llm(
                f"Is user {USER_ID}'s HDFC Bank exposure direct or mostly through "
                f"funds, and which fund contributes the most? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "single_holding_exposure" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s14_stock_concentration_vs_amc(self, ask_llm):
        """FE-S14: Concentrated in a few stocks but tilted to one AMC?
        Needs: total_stock_exposure + amc_preference"""

        async def check():
            msg = await ask_llm(
                f"Does user {USER_ID}'s portfolio look concentrated in a few "
                f"stocks even though it seems heavily tilted to one AMC? "
                f"Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "total_stock_exposure" in fns or "amc_preference" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s15_equity_heavy_vs_factor(self, ask_llm):
        """FE-S15: Does portfolio mix suggest leaning heavily towards equities?
        Needs: asset_breakdown + factor_preference"""

        async def check():
            msg = await ask_llm(
                f"Does user {USER_ID}'s overall portfolio mix suggest they are "
                f"leaning heavily towards equities? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "asset_breakdown" in fns or "factor_preference" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s16_theme_vs_sector(self, ask_llm):
        """FE-S16: Is dominant theme aligned with biggest sector exposures?
        Needs: theme_preference + sector_breakdown"""

        async def check():
            msg = await ask_llm(
                f"Is user {USER_ID}'s dominant investment theme aligned with "
                f"their biggest sector exposures? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "theme_preference" in fns or "sector_breakdown" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s17_sector_bias_vs_marketcap(self, ask_llm):
        """FE-S17: Does sector bias line up with market-cap profile?
        Needs: sector_preference + market_cap_breakdown"""

        async def check():
            msg = await ask_llm(
                f"Does user {USER_ID}'s sector bias line up with their "
                f"market-cap profile? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "sector_preference" in fns or "market_cap_breakdown" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s18_stock_exposure_vs_sector_overweight(self, ask_llm):
        """FE-S18: Are top stock exposures enough to explain strongest sector overweight?
        Needs: total_stock_exposure + sector_preference"""

        async def check():
            msg = await ask_llm(
                f"Are user {USER_ID}'s top stock exposures enough to explain "
                f"their strongest sector overweight? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "total_stock_exposure" in fns or "sector_preference" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s19_theme_vs_stock_concentration(self, ask_llm):
        """FE-S19: More concentrated by theme or by single-stock exposure?
        Needs: theme_preference + total_stock_exposure"""

        async def check():
            msg = await ask_llm(
                f"Is user {USER_ID}'s portfolio more concentrated by theme "
                f"or by single-stock exposure? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            return "theme_preference" in fns or "total_stock_exposure" in fns

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s20_aggressive_vs_defensive(self, ask_llm):
        """FE-S20: Would you describe this portfolio as aggressive?
        Needs: asset_breakdown + market_cap_breakdown + sector_preference + factor_preference"""

        async def check():
            msg = await ask_llm(
                f"Would you describe user {USER_ID}'s portfolio as aggressive "
                f"rather than defensive? Org {ORG_ID}."
            )
            fns = get_fe_functions(msg)
            # Should call at least 2 of the 4 needed functions
            expected = {"asset_breakdown", "market_cap_breakdown",
                        "sector_preference", "factor_preference"}
            return len(set(fns) & expected) >= 2

        assert await majority_vote(check)


# ==========================================================================
# Model Portfolio — User-specific sessions (S1–S11)
# ==========================================================================


class TestMPUserSingleTool:
    """MP User S1–S5, S11: single-tool queries."""

    @pytest.mark.anyio
    async def test_s1_risk_profile(self, ask_llm):
        """MP-S1: What is user's stored overall risk profile?"""

        async def check():
            msg = await ask_llm(
                f"What is user {USER_ID}'s stored overall risk profile?"
            )
            return tool_names(msg) == ["get_risk_profile"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_portfolio_lumpsum(self, ask_llm):
        """MP-S2: Portfolio recommended for 50000 lump-sum?"""

        async def check():
            msg = await ask_llm(
                f"What portfolio is recommended for user {USER_ID} if they "
                f"invest 50000 as a one-time lump sum?"
            )
            names = tool_names(msg)
            return names == ["get_portfolio_options"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_no_backtest_chaining(self, ask_llm):
        """MP-S2 anti-chain: get_portfolio_options should NOT be followed by backtest."""

        async def check():
            msg = await ask_llm(
                f"Build a medium risk portfolio for user {USER_ID} with "
                f"50000 lump sum investment."
            )
            names = tool_names(msg)
            return "backtest_portfolio" not in names

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s3_portfolio_builder(self, ask_llm):
        """MP-S3: Custom-assembled portfolio with backtest results."""

        async def check():
            msg = await ask_llm(
                f"Build a custom portfolio for user {USER_ID} with 50000 "
                f"lump sum and show the backtest results."
            )
            names = tool_names(msg)
            return matches_any(names, [
                ["portfolio_builder"],
                ["get_portfolio_options"],
            ])

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s5_stock_to_fund(self, ask_llm):
        """MP-S5: Mutual fund alternatives for current stock holdings."""

        async def check():
            msg = await ask_llm(
                f"Are there mutual fund alternatives that could replace user "
                f"{USER_ID}'s current stock holdings?"
            )
            return tool_names(msg) == ["stock_to_fund"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s11_portfolio_sip(self, ask_llm):
        """MP-S11: Portfolio recommended for 10000 monthly SIP.
        LLM may pick get_portfolio_options or portfolio_builder — both valid."""

        async def check():
            msg = await ask_llm(
                f"What mutual fund portfolio would you recommend for user "
                f"{USER_ID} if they invest 10000 every month through a SIP?"
            )
            names = tool_names(msg)
            return matches_any(names, [
                ["get_portfolio_options"],
                ["portfolio_builder"],
            ])

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s11_sip_investment_type(self, ask_llm):
        """MP-S11: SIP query should pass investment_type=SIP."""

        async def check():
            msg = await ask_llm(
                f"Build a SIP portfolio of 10000 per month for user {USER_ID}."
            )
            calls = extract_tool_calls(msg)
            if not calls:
                return False
            for c in calls:
                if c["name"] == "get_portfolio_options":
                    return c["params"].get("investment_type") == "SIP"
            return False

        assert await majority_vote(check)


class TestMPUserMultiTool:
    """MP User S6–S10: queries that may need 2 tools."""

    @pytest.mark.anyio
    async def test_s6_risk_plus_portfolio(self, ask_llm):
        """MP-S6: Is portfolio style consistent with stored risk profile?
        Needs: get_risk_profile + get_portfolio_options
        Accept either or both since get_portfolio_options auto-fetches risk."""

        async def check():
            msg = await ask_llm(
                f"Is the recommended portfolio style consistent with user "
                f"{USER_ID}'s stored risk profile? Investment: 50000 lump sum."
            )
            names = tool_names(msg)
            return matches_any(names, [
                ["get_portfolio_options"],
                ["get_risk_profile"],
                ["get_portfolio_options", "get_risk_profile"],
            ])

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s7_portfolio_vs_builder(self, ask_llm):
        """MP-S7: Compare standard recommendation vs custom-assembled.
        Needs: get_portfolio_options + portfolio_builder.
        LLM may pick either or both — all are valid first steps."""

        async def check():
            msg = await ask_llm(
                f"Show me both the standard portfolio recommendation and the "
                f"custom-assembled portfolio for user {USER_ID} with 50000 "
                f"lump sum."
            )
            names = tool_names(msg)
            return (
                "get_portfolio_options" in names
                or "portfolio_builder" in names
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s9_stock_exposure_vs_funds(self, ask_llm):
        """MP-S9: Is current stock exposure narrower than recommended funds?
        Needs: get_portfolio_options + stock_to_fund"""

        async def check():
            msg = await ask_llm(
                f"Is user {USER_ID}'s current stock exposure narrower in scope "
                f"compared to the mutual funds recommended for a 50000 lump sum "
                f"investment?"
            )
            names = tool_names(msg)
            return "get_portfolio_options" in names or "stock_to_fund" in names

        assert await majority_vote(check)


# ==========================================================================
# Model Portfolio — Non-user-specific sessions (S1–S10, skipping S6)
# ==========================================================================


class TestMPNonUserSingleTool:
    """MP Non-User S1–S5: single-tool queries (no user_id needed)."""

    @pytest.mark.anyio
    async def test_s1_risk_profile_v2(self, ask_llm):
        """MP-NU-S1: Onboarding-style risk assessment."""

        async def check():
            msg = await ask_llm(
                "Assess risk for a 30 year old earning 12 lakhs annually, "
                "long term horizon, willing to lose 20%, pin code 400001."
            )
            return tool_names(msg) == ["risk_profile_v2"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s1_not_get_risk_profile(self, ask_llm):
        """MP-NU-S1 disambiguation: onboarding inputs should NOT call get_risk_profile."""

        async def check():
            msg = await ask_llm(
                "Calculate risk profile for age 28, income 15 lakhs, "
                "medium term, willing to lose 15%, pin code 560001."
            )
            return "get_risk_profile" not in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s2_single_goal_retirement(self, ask_llm):
        """MP-NU-S2: Single-goal optimizer for retirement."""

        async def check():
            msg = await ask_llm(
                "I want to save 1 crore for retirement in 20 years with "
                "10000 monthly SIP. What are my chances?"
            )
            return tool_names(msg) == ["single_goal_optimizer"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s3_multi_goal(self, ask_llm):
        """MP-NU-S3: Multi-goal optimizer across house and retirement."""

        async def check():
            msg = await ask_llm(
                "I have 50 lakhs and 20000 monthly SIP. Split across "
                "retirement in 20 years (critical, 1 crore) and house "
                "purchase in 5 years (important, 30 lakhs)."
            )
            return tool_names(msg) == ["multi_goal_optimizer"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s4_goal_defaults(self, ask_llm):
        """MP-NU-S4: Default SIP for a 1 crore retirement corpus over 30 years."""

        async def check():
            msg = await ask_llm(
                "What is the suggested default monthly SIP for reaching "
                "1 crore over 30 years for retirement?"
            )
            return tool_names(msg) == ["goal_defaults"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s5_build_stock_portfolio_avoided(self, ask_llm):
        """MP-NU-S5: build_stock_portfolio is marked broken (HTTP 500).
        The LLM should NOT call it. It may fall back to search_funds or
        respond with text explaining the limitation."""

        async def check():
            msg = await ask_llm(
                "Build me a large cap stock portfolio with up to 10 stocks."
            )
            return "build_stock_portfolio" not in tool_names(msg)

        assert await majority_vote(check)


class TestMPNonUserMultiTool:
    """MP Non-User S7–S10: queries that reference multiple tools."""

    @pytest.mark.anyio
    async def test_s7_compare_single_goals(self, ask_llm):
        """MP-NU-S7: Which single-goal plan is more achievable: retirement or house?
        Needs: single_goal_optimizer (called for two scenarios)"""

        async def check():
            msg = await ask_llm(
                "Compare two goals: saving 1 crore for retirement in 20 years "
                "with 10000 SIP vs saving 30 lakhs for a house in 5 years "
                "with 15000 SIP. Which is more achievable?"
            )
            return "single_goal_optimizer" in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s8_compare_goal_defaults(self, ask_llm):
        """MP-NU-S8: Which goal requires a larger SIP?
        Needs: goal_defaults (called for two scenarios)"""

        async def check():
            msg = await ask_llm(
                "Which goal requires a larger monthly SIP: building a 1 crore "
                "retirement corpus over 30 years or saving 50 lakhs for a "
                "house in 10 years?"
            )
            return "goal_defaults" in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s9_risk_vs_optimizer(self, ask_llm):
        """MP-NU-S9: Compare onboarding risk assessment vs goal optimizer.
        Needs: risk_profile_v2 + single_goal_optimizer"""

        async def check():
            msg = await ask_llm(
                "For a 30 year old earning 12 lakhs (pin 400001, long term, "
                "willing to lose 20%), does the risk assessment recommend "
                "something more aggressive or conservative than the retirement "
                "goal optimizer for 1 crore in 20 years with 10000 SIP?"
            )
            names = tool_names(msg)
            return "risk_profile_v2" in names or "single_goal_optimizer" in names

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_s10_multi_goal_struggling(self, ask_llm):
        """MP-NU-S10: Why is the house goal struggling in the multi-goal plan?
        Needs: multi_goal_optimizer + goal_defaults + single_goal_optimizer.
        LLM may pick any combination of these, or just one as a starting point."""

        async def check():
            msg = await ask_llm(
                "I have 50 lakhs and 20000 monthly SIP. Optimize across "
                "retirement (critical, 1 crore, 20 years) and house purchase "
                "(important, 30 lakhs, 5 years). Also show what the house "
                "goal would need on its own."
            )
            names = tool_names(msg)
            return (
                "multi_goal_optimizer" in names
                or "single_goal_optimizer" in names
                or "goal_defaults" in names
            )

        assert await majority_vote(check)


# ==========================================================================
# Disambiguation tests — verify enriched descriptions prevent mis-routing
# ==========================================================================


class TestDisambiguation:
    """Tests that the LLM does NOT pick the wrong tool."""

    @pytest.mark.anyio
    async def test_portfolio_does_not_chain_backtest(self, ask_llm):
        """Building a portfolio should NOT auto-chain into backtest_portfolio."""

        async def check():
            msg = await ask_llm(
                f"Build a medium risk portfolio for user 1018083528 "
                f"with 20000 monthly SIP."
            )
            return "backtest_portfolio" not in tool_names(msg)

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_risk_lookup_not_v2(self, ask_llm):
        """Looking up an existing user's risk should use get_risk_profile, not v2."""

        async def check():
            msg = await ask_llm(
                f"What is user {USER_ID}'s risk profile?"
            )
            names = tool_names(msg)
            return "get_risk_profile" in names and "risk_profile_v2" not in names

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_onboarding_risk_not_lookup(self, ask_llm):
        """Providing age/income/pin should use risk_profile_v2, not get_risk_profile."""

        async def check():
            msg = await ask_llm(
                "Calculate risk for a 35-year-old with 20 lakh income, "
                "medium term horizon, can tolerate 25% loss, pin 110001."
            )
            names = tool_names(msg)
            return "risk_profile_v2" in names and "get_risk_profile" not in names

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_single_goal_not_multi(self, ask_llm):
        """A single goal should use single_goal_optimizer, not multi_goal."""

        async def check():
            msg = await ask_llm(
                "I want to save 50 lakhs for a house in 10 years with "
                "15000 monthly SIP. What are my chances?"
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
                "I have 10 lakhs and 30000 SIP. Split between retirement "
                "(critical, 2 crore, 25 years) and child education "
                "(important, 50 lakhs, 15 years)."
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
            return (
                "search_funds" in tool_names(msg)
                and "financial_engine" not in tool_names(msg)
            )

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_portfolio_analysis_not_fund_search(self, ask_llm):
        """Analyzing existing portfolio should NOT trigger search_funds."""

        async def check():
            msg = await ask_llm(
                f"Show sector breakdown for user {USER_ID}'s portfolio. "
                f"Org {ORG_ID}."
            )
            return (
                "financial_engine" in tool_names(msg)
                and "search_funds" not in tool_names(msg)
            )

        assert await majority_vote(check)
