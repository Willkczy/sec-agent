"""
Unit tests for the FastAPI endpoints — Agent is mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest
import anyio
import httpx

from main import app


pytestmark = pytest.mark.unit


class TestHealthEndpoint:

    def test_health_returns_ok(self):
        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get("/health")

        resp = anyio.run(_run)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "sec-agent"


class TestAskEndpoint:

    def test_ask_returns_answer(self):
        mock_result = {
            "answer": "Here are the top funds.",
            "debug": {"iterations": [], "tool_results": []},
        }

        async def _run():
            with patch("main.Agent") as MockAgent:
                instance = MockAgent.return_value
                instance.run = AsyncMock(return_value=mock_result)

                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.post(
                        "/ask",
                        json={"query": "Show me large cap funds"},
                    )

        resp = anyio.run(_run)
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Here are the top funds."
        assert "debug" in data

    def test_ask_missing_query_returns_422(self):
        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post("/ask", json={})

        resp = anyio.run(_run)
        assert resp.status_code == 422

    def test_ask_agent_exception_returns_500(self):
        async def _run():
            with patch("main.Agent") as MockAgent:
                instance = MockAgent.return_value
                instance.run = AsyncMock(side_effect=RuntimeError("LLM failed"))

                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.post(
                        "/ask",
                        json={"query": "test query"},
                    )

        resp = anyio.run(_run)
        assert resp.status_code == 500
