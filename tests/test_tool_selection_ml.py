"""
LLM tool selection tests for ML Recommendations service.

Tool covered: ml_fund_discovery
"""

import pytest

from tests.conftest import majority_vote, tool_names


pytestmark = pytest.mark.llm


class TestMLFundDiscovery:

    @pytest.mark.anyio
    async def test_explicit_ml_request(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Show ML-based personalized fund recommendations for user 1912650190"
            )
            return tool_names(msg) == ["ml_fund_discovery"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_similar_investors_phrasing(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "What funds would similar investors recommend for user 100?"
            )
            return tool_names(msg) == ["ml_fund_discovery"]

        assert await majority_vote(check)

    @pytest.mark.anyio
    async def test_collaborative_filtering_phrasing(self, ask_llm):
        async def check():
            msg = await ask_llm(
                "Give me collaborative filtering fund suggestions for user 1912650190"
            )
            return tool_names(msg) == ["ml_fund_discovery"]

        assert await majority_vote(check)
