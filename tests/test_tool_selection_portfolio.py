"""
LLM tool selection tests for Model Portfolio service tools.

Tools covered: get_portfolio_options, backtest_portfolio, portfolio_builder,
get_risk_profile, risk_profile_v2, single_goal_optimizer, multi_goal_optimizer,
goal_defaults, build_stock_portfolio, stock_to_fund, determine_income_sector
"""

import pytest

from tests.conftest import majority_vote, tool_names


pytestmark = pytest.mark.llm


class TestGetPortfolioOptions:

    @pytest.mark.anyio
    async def test_build_portfolio_sip(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Build me a portfolio with 50000 SIP investment, medium risk, user ID 100"
            )
            return tool_names(msg) == ["get_portfolio_options"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_build_portfolio_lumpsum(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "I want to invest 5 lakhs as a lump sum with high risk. User ID 200."
            )
            return tool_names(msg) == ["get_portfolio_options"]

        assert await majority_vote(check)


class TestSingleGoalOptimizer:

    @pytest.mark.anyio
    async def test_retirement_goal(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "I want to save 1 crore in 20 years with 10000 monthly SIP for retirement"
            )
            return tool_names(msg) == ["single_goal_optimizer"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_house_purchase_goal(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Plan for buying a house worth 50 lakhs in 10 years, I can invest 15000 per month"
            )
            return tool_names(msg) == ["single_goal_optimizer"]

        assert await majority_vote(check)


class TestMultiGoalOptimizer:

    @pytest.mark.anyio
    async def test_multiple_goals(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "I have 50 lakhs and 20000 monthly SIP. Optimize across retirement "
                "in 20 years (critical, 1 crore) and house in 5 years (important, 30 lakhs)"
            )
            return tool_names(msg) == ["multi_goal_optimizer"]

        assert await majority_vote(check)


class TestGetRiskProfile:

    @pytest.mark.anyio
    async def test_risk_profile_by_user_id(self, ask_llm):
        async def check():
            msg = await ask_llm("What is the risk profile for user 12345?")
            return tool_names(msg) == ["get_risk_profile"]

        assert await majority_vote(check)


class TestRiskProfileV2:

    @pytest.mark.anyio
    async def test_detailed_risk_assessment(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Assess risk for a 30 year old earning 12 lakhs annually, "
                "medium term horizon, willing to lose 20%, pin code 400001"
            )
            return tool_names(msg) == ["risk_profile_v2"]

        assert await majority_vote(check)


class TestGoalDefaults:

    @pytest.mark.anyio
    async def test_goal_defaults(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What SIP amount should I target for a 50 lakh goal in 15 years?"
            )
            return tool_names(msg) == ["goal_defaults"]

        assert await majority_vote(check)


class TestBuildStockPortfolio:

    @pytest.mark.anyio
    async def test_stock_portfolio(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Build a stock portfolio with TCS 40%, Infosys 30%, HDFC Bank 30%"
            )
            return tool_names(msg) == ["build_stock_portfolio"]

        assert await majority_vote(check)


class TestStockToFund:

    @pytest.mark.anyio
    async def test_convert_stocks_to_funds(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Convert stock holdings of user 12345 to mutual fund recommendations"
            )
            return tool_names(msg) == ["stock_to_fund"]

        assert await majority_vote(check)


class TestDetermineIncomeSector:

    @pytest.mark.anyio
    async def test_income_sector_classification(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Classify income sector for a household where one person is a "
                "software engineer at an IT company and spouse is a doctor"
            )
            return tool_names(msg) == ["determine_income_sector"]

        assert await majority_vote(check)
