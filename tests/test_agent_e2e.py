"""
End-to-end tests — real LLM + real backend APIs.

These tests are slow, require VPN and backend services running.
Run with: uv run pytest -m e2e
"""

import pytest
import anyio
from openai import AsyncOpenAI

from config import settings
from api_client import APIClient
from main import Agent


pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def real_agent():
    """Create an Agent with real LLM and API clients."""
    llm = AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        timeout=120.0,
    )
    api = APIClient(
        base_url=settings.API_BASE_URL,
        enable_auth=settings.ENABLE_AUTH,
    )
    return Agent(llm=llm, api=api)


async def _run_query(agent, query, max_iters=3):
    return await agent.run(query, max_iters=max_iters)


class TestEndToEnd:

    @pytest.mark.anyio
    async def test_search_funds_returns_answer(self, real_agent):
        result = await _run_query(real_agent, "Show me top large cap direct mutual funds")

        assert result["answer"]
        assert "error" not in result["answer"].lower() or "no data" not in result["answer"].lower()
        assert len(result["debug"]["tool_results"]) >= 1

    @pytest.mark.anyio
    async def test_financial_engine_sector_breakdown(self, real_agent):
        result = await _run_query(
            real_agent,
            "Show sector breakdown for user 1912650190 in org 2854263694",
        )

        assert result["answer"]
        assert len(result["debug"]["tool_results"]) >= 1
        # The tool should have been financial_engine
        tool_used = result["debug"]["tool_results"][0]["tool"]
        assert tool_used == "financial_engine"

    @pytest.mark.anyio
    async def test_goal_optimizer_returns_projection(self, real_agent):
        result = await _run_query(
            real_agent,
            "I want to save 1 crore in 20 years with 10000 monthly SIP for retirement",
        )

        assert result["answer"]
        assert len(result["debug"]["tool_results"]) >= 1

    @pytest.mark.anyio
    async def test_agent_handles_error_gracefully(self, real_agent):
        """Query with invalid data should not crash the agent."""
        result = await _run_query(
            real_agent,
            "Show sector breakdown for user 99999999 in org 0000000000",
        )

        # Should return some answer (possibly an error message), not crash
        assert result["answer"]
        assert isinstance(result["answer"], str)

    @pytest.mark.anyio
    async def test_ml_fund_discovery(self, real_agent):
        result = await _run_query(
            real_agent,
            "Show ML-based personalized fund recommendations for user 1912650190",
        )

        assert result["answer"]
        assert len(result["debug"]["tool_results"]) >= 1

    @pytest.mark.anyio
    async def test_debug_output_populated(self, real_agent):
        result = await _run_query(real_agent, "What is the risk profile for user 12345?")

        debug = result["debug"]
        assert "iterations" in debug
        assert "tool_results" in debug
        assert len(debug["iterations"]) >= 1
