"""
Unit tests for Agent.run() orchestration — mocked LLM, mocked APIClient,
and a stub ReasoningAdapter so no Glass-Box / network calls occur.
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

def _make_text_message(content: str | None):
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


def _make_stub_reasoner(
    answer: str = "REASONER_ANSWER",
    trace: str = "TRACE",
    api_keys: list[str] | None = None,
    verifier_verdict=None,
    verifier_retries: int = 0,
    unmapped: list[str] | None = None,
):
    """Stub ReasoningAdapter — returns predictable payload without invoking
    Glass-Box or any LLM. Records the (question, tool_results) it was called
    with on `.calls`."""
    stub = MagicMock()
    stub.calls = []

    async def _answer(*, question, tool_results, history, history_traces):
        stub.calls.append({
            "question": question,
            "tool_results": list(tool_results),
            "history": list(history),
            "history_traces": list(history_traces),
        })
        return {
            "answer": answer,
            "reasoning_trace": trace,
            "api_keys": api_keys if api_keys is not None else [],
            "verifier_verdict": verifier_verdict,
            "verifier_retries": verifier_retries,
            "unmapped_tools": unmapped if unmapped is not None else [],
        }

    stub.answer = _answer
    return stub


def _build_agent(
    llm_responses: list,
    api_results: dict | None = None,
    reasoner=None,
):
    """Build an Agent with mocked LLM, API client, and reasoner."""
    mock_llm = MagicMock()
    completions = [_make_completion(msg) for msg in llm_responses]
    mock_llm.chat.completions.create = AsyncMock(side_effect=completions)

    mock_api = MagicMock()
    if api_results:
        async def _call_tool(endpoint, params):
            for name, result in api_results.items():
                if name in endpoint:
                    return result
            return {"data": "mock"}

        mock_api.call_tool = AsyncMock(side_effect=_call_tool)
    else:
        mock_api.call_tool = AsyncMock(return_value={"data": "mock_result"})

    if reasoner is None:
        reasoner = _make_stub_reasoner()

    return Agent(llm=mock_llm, api=mock_api, reasoner=reasoner)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentTextResponse:
    """When the LLM emits text without calling any tool, the agent returns
    that text directly — the reasoner has nothing to ground on."""

    def test_returns_text_directly_when_no_tool_calls(self):
        reasoner = _make_stub_reasoner()
        agent = _build_agent(
            [_make_text_message("Out of scope: I cover FE/MP only.")],
            reasoner=reasoner,
        )

        result = anyio.run(agent.run, "What is the meaning of life?")

        assert result["answer"] == "Out of scope: I cover FE/MP only."
        assert result["debug"]["iterations"] == []
        assert result["debug"]["tool_results"] == []
        assert "reasoning" not in result["debug"]
        assert reasoner.calls == []  # reasoner never invoked

    def test_empty_content_returns_fallback_message(self):
        agent = _build_agent([_make_text_message(None)])

        result = anyio.run(agent.run, "test")

        assert "Financial Engine" in result["answer"]


class TestAgentToolCallingRoutesToReasoner:
    """When tools fire, the reasoner produces the final answer and the
    Glass-Box trace lands in debug.reasoning."""

    def test_single_tool_call_then_reasoner(self):
        reasoner = _make_stub_reasoner(
            answer="Asset breakdown summarized.",
            trace="EVIDENCE: equity=60%",
            api_keys=["asset_breakdown"],
        )
        agent = _build_agent(
            [
                _make_tool_call_message([
                    ("financial_engine",
                     {"function": "asset_breakdown",
                      "parameters": {"user_id": "1912650190"}}),
                ]),
                _make_text_message("ack"),
            ],
            api_results={
                "fin-engine": {"asset_breakdown": {"equity": 60.0, "debt": 40.0}}
            },
            reasoner=reasoner,
        )

        result = anyio.run(agent.run, "Show asset breakdown for 1912650190")

        assert result["answer"] == "Asset breakdown summarized."
        assert result["debug"]["reasoning"]["api_keys"] == ["asset_breakdown"]
        assert result["debug"]["reasoning"]["trace"] == "EVIDENCE: equity=60%"
        assert len(reasoner.calls) == 1
        assert reasoner.calls[0]["question"] == "Show asset breakdown for 1912650190"
        assert len(reasoner.calls[0]["tool_results"]) == 1

    def test_multiple_tool_calls_in_one_turn_pass_all_results_to_reasoner(self):
        reasoner = _make_stub_reasoner(api_keys=["asset_breakdown", "get_risk_profile"])
        agent = _build_agent(
            [
                _make_tool_call_message([
                    ("financial_engine",
                     {"function": "asset_breakdown",
                      "parameters": {"user_id": "1"}}),
                    ("get_risk_profile", {"user_id": 123}),
                ]),
                _make_text_message("ack"),
            ],
            reasoner=reasoner,
        )

        result = anyio.run(agent.run, "Asset breakdown and risk profile")

        assert len(result["debug"]["tool_results"]) == 2
        assert len(reasoner.calls[0]["tool_results"]) == 2

    def test_chained_tool_iterations_collected_and_reasoned_once(self):
        reasoner = _make_stub_reasoner()
        agent = _build_agent(
            [
                _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
                _make_tool_call_message([
                    ("financial_engine",
                     {"function": "asset_breakdown",
                      "parameters": {"user_id": "1"}}),
                ]),
                _make_text_message("ack"),
            ],
            reasoner=reasoner,
        )

        result = anyio.run(agent.run, "Profile then breakdown")

        assert len(result["debug"]["iterations"]) == 2
        assert len(result["debug"]["tool_results"]) == 2
        # Reasoner is called once with the full collected tool_results.
        assert len(reasoner.calls) == 1
        assert len(reasoner.calls[0]["tool_results"]) == 2


class TestAgentMaxIterationsHandsOffToReasoner:
    """When max_iters is exhausted with tool calls still pending, the agent
    no longer makes a forced LLM text call — it hands the collected
    tool_results to the reasoner."""

    def test_max_iters_exhausted_routes_collected_results_to_reasoner(self):
        reasoner = _make_stub_reasoner(answer="Reasoner final answer.")
        agent = _build_agent(
            [
                _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
                _make_tool_call_message([("get_risk_profile", {"user_id": 2})]),
                _make_tool_call_message([("get_risk_profile", {"user_id": 3})]),
            ],
            reasoner=reasoner,
        )

        result = anyio.run(agent.run, "test", 3)

        assert result["answer"] == "Reasoner final answer."
        assert len(result["debug"]["iterations"]) == 3
        assert len(reasoner.calls) == 1
        assert len(reasoner.calls[0]["tool_results"]) == 3


class TestAgentErrorHandling:

    def test_unknown_tool_returns_error_in_debug(self):
        agent = _build_agent([
            _make_tool_call_message([("nonexistent_tool", {})]),
            _make_text_message("ack"),
        ])

        result = anyio.run(agent.run, "test")

        error_result = result["debug"]["tool_results"][0]["result"]
        assert "error" in error_result
        assert "Unknown tool" in error_result["error"]

    def test_invalid_json_arguments_uses_empty_dict(self):
        msg = MagicMock()
        msg.content = None
        tc = MagicMock()
        tc.id = "call_0"
        tc.function.name = "get_risk_profile"
        tc.function.arguments = "{invalid json"
        msg.tool_calls = [tc]

        agent = _build_agent([msg, _make_text_message("ack")])

        result = anyio.run(agent.run, "test")

        assert result["debug"]["tool_results"][0]["params"] == {}


class TestAgentDebugOutput:

    def test_debug_has_iterations_tool_results_and_reasoning_when_tools_fire(self):
        agent = _build_agent([
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
        ])

        result = anyio.run(agent.run, "test")

        debug = result["debug"]
        assert "iterations" in debug
        assert "tool_results" in debug
        assert "reasoning" in debug
        for key in ("api_keys", "trace", "verifier_verdict",
                    "verifier_retries", "unmapped_tools"):
            assert key in debug["reasoning"]

        iteration = debug["iterations"][0]
        assert iteration["iteration"] == 1
        assert "tool_calls" in iteration

    def test_tool_result_record_structure(self):
        agent = _build_agent([
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
        ])

        result = anyio.run(agent.run, "test")

        record = result["debug"]["tool_results"][0]
        assert "tool" in record
        assert "params" in record
        assert "result" in record
