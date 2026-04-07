"""
Unit tests for Agent.run() orchestration — mocked LLM + mocked APIClient.
No network calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import anyio

from main import Agent


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers to build mock LLM responses
# ---------------------------------------------------------------------------

def _make_text_message(content: str):
    """Mock a completion message with text only (no tool calls)."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def _make_tool_call_message(calls: list[tuple[str, dict]], content=None):
    """Mock a completion message with tool_calls.

    calls: list of (tool_name, params_dict)
    """
    msg = MagicMock()
    msg.content = content
    tool_calls = []
    for i, (name, params) in enumerate(calls):
        tc = MagicMock()
        tc.id = f"call_{i}"
        tc.function.name = name
        tc.function.arguments = json.dumps(params)
        tool_calls.append(tc)
    msg.tool_calls = tool_calls
    return msg


def _make_completion(message):
    """Wrap a message into a mock completion response."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = message
    return resp


def _build_agent(llm_responses: list, api_results: dict | None = None):
    """Build an Agent with mocked LLM and API clients.

    llm_responses: list of messages the LLM returns in order.
    api_results: dict mapping tool_name -> result dict.
    """
    mock_llm = MagicMock()
    completions = [_make_completion(msg) for msg in llm_responses]
    mock_llm.chat.completions.create = AsyncMock(side_effect=completions)

    mock_api = MagicMock()
    if api_results:
        async def _call_tool(endpoint, params):
            # Match endpoint to tool name via a simple lookup
            for name, result in api_results.items():
                if name in endpoint:
                    return result
            return {"data": "mock"}

        mock_api.call_tool = AsyncMock(side_effect=_call_tool)
    else:
        mock_api.call_tool = AsyncMock(return_value={"data": "mock_result"})

    return Agent(llm=mock_llm, api=mock_api)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentTextResponse:
    """Agent should return immediately when LLM gives text (no tool calls)."""

    def test_returns_text_directly(self):
        agent = _build_agent([_make_text_message("The answer is 42.")])

        result = anyio.run(agent.run, "What is the answer?")

        assert result["answer"] == "The answer is 42."
        assert result["debug"]["iterations"] == []
        assert result["debug"]["tool_results"] == []

    def test_empty_content_returns_fallback(self):
        agent = _build_agent([_make_text_message(None)])

        result = anyio.run(agent.run, "test")

        assert result["answer"] == "No answer produced."


class TestAgentToolCalling:
    """Agent should execute tool calls and feed results back."""

    def test_single_tool_call_then_text(self):
        agent = _build_agent([
            _make_tool_call_message([("search_funds", {"query": "large cap"})]),
            _make_text_message("Found 3 large cap funds."),
        ])

        result = anyio.run(agent.run, "Show me large cap funds")

        assert result["answer"] == "Found 3 large cap funds."
        assert len(result["debug"]["tool_results"]) == 1
        assert result["debug"]["tool_results"][0]["tool"] == "search_funds"
        assert len(result["debug"]["iterations"]) == 1

    def test_multiple_tool_calls_in_one_turn(self):
        agent = _build_agent([
            _make_tool_call_message([
                ("search_funds", {"query": "large cap"}),
                ("get_risk_profile", {"user_id": 123}),
            ]),
            _make_text_message("Here are funds and your risk profile."),
        ])

        result = anyio.run(agent.run, "Funds and risk profile")

        assert len(result["debug"]["tool_results"]) == 2
        tool_names = [r["tool"] for r in result["debug"]["tool_results"]]
        assert "search_funds" in tool_names
        assert "get_risk_profile" in tool_names

    def test_two_iteration_chain(self):
        """Tool call -> result -> another tool call -> result -> text."""
        agent = _build_agent([
            _make_tool_call_message([("search_funds", {"query": "SBI"})]),
            _make_tool_call_message([("get_fund_peers", {"security_id": "123"})]),
            _make_text_message("Peers found."),
        ])

        result = anyio.run(agent.run, "Peers of SBI Large Cap")

        assert result["answer"] == "Peers found."
        assert len(result["debug"]["iterations"]) == 2
        assert len(result["debug"]["tool_results"]) == 2


class TestAgentMaxIterations:
    """Agent should force a final answer when max_iters is exhausted."""

    def test_max_iterations_forces_text(self):
        # 3 iterations of tool calls + 1 forced text response
        agent = _build_agent([
            _make_tool_call_message([("search_funds", {"query": "a"})]),
            _make_tool_call_message([("search_funds", {"query": "b"})]),
            _make_tool_call_message([("search_funds", {"query": "c"})]),
            _make_text_message("Forced final answer."),
        ])

        result = anyio.run(agent.run, "test", 3)

        assert result["answer"] == "Forced final answer."
        assert len(result["debug"]["iterations"]) == 3

    def test_max_iterations_empty_content(self):
        agent = _build_agent([
            _make_tool_call_message([("search_funds", {"query": "a"})]),
            _make_tool_call_message([("search_funds", {"query": "b"})]),
            _make_tool_call_message([("search_funds", {"query": "c"})]),
            _make_text_message(None),
        ])

        result = anyio.run(agent.run, "test", 3)

        assert result["answer"] == "Max iterations reached with no answer."


class TestAgentErrorHandling:

    def test_unknown_tool_returns_error(self):
        agent = _build_agent([
            _make_tool_call_message([("nonexistent_tool", {})]),
            _make_text_message("Tool not found."),
        ])

        result = anyio.run(agent.run, "test")

        error_result = result["debug"]["tool_results"][0]["result"]
        assert "error" in error_result
        assert "Unknown tool" in error_result["error"]

    def test_invalid_json_arguments_uses_empty_dict(self):
        """When LLM returns malformed JSON in arguments, agent should use {}."""
        msg = MagicMock()
        msg.content = None
        tc = MagicMock()
        tc.id = "call_0"
        tc.function.name = "search_funds"
        tc.function.arguments = "{invalid json"
        msg.tool_calls = [tc]

        agent = _build_agent([msg, _make_text_message("Done.")])

        result = anyio.run(agent.run, "test")

        # Should not crash; params should be {}
        assert result["debug"]["tool_results"][0]["params"] == {}


class TestAgentDebugOutput:

    def test_debug_structure(self):
        agent = _build_agent([
            _make_tool_call_message([("search_funds", {"query": "test"})]),
            _make_text_message("Answer."),
        ])

        result = anyio.run(agent.run, "test")

        debug = result["debug"]
        assert "iterations" in debug
        assert "tool_results" in debug
        assert isinstance(debug["iterations"], list)
        assert isinstance(debug["tool_results"], list)

        iteration = debug["iterations"][0]
        assert "iteration" in iteration
        assert iteration["iteration"] == 1
        assert "tool_calls" in iteration

    def test_tool_result_record_structure(self):
        agent = _build_agent([
            _make_tool_call_message([("search_funds", {"query": "test"})]),
            _make_text_message("Answer."),
        ])

        result = anyio.run(agent.run, "test")

        record = result["debug"]["tool_results"][0]
        assert "tool" in record
        assert "params" in record
        assert "result" in record
