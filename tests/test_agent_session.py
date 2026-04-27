"""
Phase 2 integration tests — session memory + follow-up continuity.

Uses the same stub-LLM / stub-ReasoningAdapter pattern as
test_agent_unit.py so no Glass-Box or network calls happen. Each test
constructs its own isolated SessionStore.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import anyio

from main import Agent
from session_store import SessionStore


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers (mirrors test_agent_unit.py — kept local so tests stay readable)
# ---------------------------------------------------------------------------

def _make_text_message(content: str | None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def _make_tool_call_message(calls: list[tuple[str, dict]], content=None):
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
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = message
    return resp


def _make_recording_llm(messages_per_turn: list):
    """Mock LLM that records each `messages=` kwarg it received and returns
    `messages_per_turn[i]` as the assistant message on call i."""
    completions = [_make_completion(m) for m in messages_per_turn]
    captured: list[list[dict]] = []

    async def _create(**kwargs):
        captured.append(list(kwargs["messages"]))
        return completions.pop(0)

    llm = MagicMock()
    llm.chat.completions.create = _create
    llm.captured_messages = captured  # type: ignore[attr-defined]
    return llm


def _make_recording_reasoner(answers: list[str]):
    """Stub reasoner that pulls the next answer off `answers` per call and
    appends 2 messages to history / history_traces in place (mimicking
    Glass-Box's TwoLayerGlassBoxModel.ask side-effect)."""
    stub = MagicMock()
    stub.calls = []
    queue = list(answers)

    async def _answer(
        *,
        question,
        api_keys,
        user_outputs,
        history=None,
        history_traces=None,
        unmapped_tools=None,
    ):
        history = history if history is not None else []
        history_traces = history_traces if history_traces is not None else []
        next_answer = queue.pop(0) if queue else "STUB_ANSWER"
        next_trace = f"TRACE[{next_answer}]"

        stub.calls.append({
            "question": question,
            "api_keys": list(api_keys),
            "user_outputs": dict(user_outputs),
            "history_in": list(history),
            "history_traces_in": list(history_traces),
            "unmapped_tools": list(unmapped_tools or []),
        })

        # Mimic Glass-Box's in-place mutation of both histories.
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": next_answer})
        history_traces.append({"role": "user", "content": question})
        history_traces.append({"role": "assistant", "content": next_trace})

        return {
            "answer": next_answer,
            "reasoning_trace": next_trace,
            "api_keys": list(api_keys),
            "verifier_verdict": None,
            "verifier_retries": 0,
            "unmapped_tools": list(unmapped_tools or []),
        }

    stub.answer = _answer
    return stub


def _build_agent(llm, reasoner, sessions, api_results: dict | None = None):
    mock_api = MagicMock()
    if api_results:
        async def _call_tool(endpoint, params):
            for name, result in api_results.items():
                if name in endpoint:
                    return result
            return {"data": "mock"}
        mock_api.call_tool = AsyncMock(side_effect=_call_tool)
    else:
        mock_api.call_tool = AsyncMock(return_value={"data": "mock"})
    return Agent(llm=llm, api=mock_api, reasoner=reasoner, sessions=sessions)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFollowUpContinuity:
    """Plan §457: a follow-up question reuses the prior topic without
    re-running irrelevant tools."""

    def test_followup_with_no_new_tool_call_reuses_session_cache(self):
        sessions = SessionStore()
        reasoner = _make_recording_reasoner(
            answers=["Equity 60%, debt 40%.", "It came from your holdings split."]
        )
        # Turn 1: tool call -> reasoner. Turn 2: no tool call -> reuse cache.
        llm = _make_recording_llm([
            _make_tool_call_message([
                ("financial_engine",
                 {"function": "asset_breakdown",
                  "parameters": {"user_id": "1912650190"}}),
            ]),
            _make_text_message("ack"),
            _make_text_message(None),  # no tool call on turn 2
        ])
        agent = _build_agent(
            llm,
            reasoner,
            sessions,
            api_results={"fin-engine": {"asset_breakdown": {"equity": 60, "debt": 40}}},
        )

        out1 = anyio.run(
            agent.run, "Show asset breakdown for 1912650190", 3, "sess-A"
        )
        assert out1["answer"] == "Equity 60%, debt 40%."

        out2 = anyio.run(
            agent.run, "How was that calculated?", 3, "sess-A"
        )
        assert out2["answer"] == "It came from your holdings split."
        assert out2["debug"]["tool_results"] == [], (
            "Follow-up should not have triggered a fresh tool call"
        )
        assert out2["debug"].get("reused_session_cache") is True

        # Reasoner saw the same api_keys + outputs from cache on turn 2.
        assert reasoner.calls[1]["api_keys"] == ["asset_breakdown"]
        assert reasoner.calls[1]["user_outputs"] == {
            "asset_breakdown": {"equity": 60, "debt": 40}
        }
        # And it received the prior turn's history_traces (Reasoner ctx).
        assert any(
            "TRACE[Equity 60%, debt 40%.]" in m["content"]
            for m in reasoner.calls[1]["history_traces_in"]
            if isinstance(m["content"], str)
        )

    def test_prior_history_is_injected_into_tool_llm_messages(self):
        sessions = SessionStore()
        reasoner = _make_recording_reasoner(answers=["A1", "A2"])
        llm = _make_recording_llm([
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
            _make_text_message("ack"),  # turn 2: no tool call
        ])
        agent = _build_agent(llm, reasoner, sessions)

        anyio.run(agent.run, "What's my risk profile?", 3, "sess-B")
        anyio.run(agent.run, "Why?", 3, "sess-B")

        # The first LLM call on turn 2 should contain the prior turn's
        # user/assistant pair before the new user query.
        turn2_first_call_messages = llm.captured_messages[2]
        # System + prior user + prior assistant + new user = 4
        assert len(turn2_first_call_messages) == 4
        assert turn2_first_call_messages[0]["role"] == "system"
        assert turn2_first_call_messages[1] == {
            "role": "user", "content": "What's my risk profile?"
        }
        assert turn2_first_call_messages[2] == {
            "role": "assistant", "content": "A1"
        }
        assert turn2_first_call_messages[3] == {
            "role": "user", "content": "Why?"
        }

    def test_followup_with_new_tool_call_merges_with_session_cache(self):
        """When a follow-up DOES fetch fresh data, the Reasoner sees both
        the new keys and the cached ones (so it can compare across them)."""
        sessions = SessionStore()
        reasoner = _make_recording_reasoner(answers=["A1", "A2"])
        llm = _make_recording_llm([
            _make_tool_call_message([
                ("financial_engine",
                 {"function": "asset_breakdown",
                  "parameters": {"user_id": "1"}}),
            ]),
            _make_text_message("ack"),
            _make_tool_call_message([
                ("financial_engine",
                 {"function": "sector_breakdown",
                  "parameters": {"user_id": "1"}}),
            ]),
            _make_text_message("ack"),
        ])
        agent = _build_agent(
            llm,
            reasoner,
            sessions,
            api_results={
                "fin-engine": {
                    # Both calls hit the same envelope; the unwrap logic
                    # picks the matching key per call.
                    "asset_breakdown": {"equity": 60},
                    "sector_breakdown": {"tech": 40},
                }
            },
        )

        anyio.run(agent.run, "Asset breakdown?", 3, "sess-C")
        anyio.run(agent.run, "Now sector breakdown?", 3, "sess-C")

        # Turn 2 reasoner gets both keys merged (cache + new).
        assert reasoner.calls[1]["api_keys"] == [
            "asset_breakdown", "sector_breakdown",
        ]
        assert "asset_breakdown" in reasoner.calls[1]["user_outputs"]
        assert "sector_breakdown" in reasoner.calls[1]["user_outputs"]


class TestSessionIsolation:
    """Plan §457: two session IDs do not share history."""

    def test_different_session_ids_have_independent_caches(self):
        sessions = SessionStore()
        reasoner = _make_recording_reasoner(
            answers=["A-from-sess1", "A-from-sess2"]
        )
        llm = _make_recording_llm([
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
            _make_tool_call_message([("get_risk_profile", {"user_id": 2})]),
            _make_text_message("ack"),
        ])
        agent = _build_agent(llm, reasoner, sessions)

        anyio.run(agent.run, "Profile for user 1?", 3, "sess-1")
        anyio.run(agent.run, "Profile for user 2?", 3, "sess-2")

        # Sess-2's reasoner call must not see sess-1's history.
        assert reasoner.calls[1]["history_in"] == []
        assert reasoner.calls[1]["history_traces_in"] == []

        # And the store has both as separate states.
        s1 = sessions.get_or_create("sess-1")
        s2 = sessions.get_or_create("sess-2")
        assert s1 is not s2
        assert s1.history != s2.history

    def test_no_session_id_is_stateless_between_calls(self):
        sessions = SessionStore()
        reasoner = _make_recording_reasoner(answers=["A1", "A2"])
        llm = _make_recording_llm([
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
            _make_tool_call_message([("get_risk_profile", {"user_id": 2})]),
            _make_text_message("ack"),
        ])
        agent = _build_agent(llm, reasoner, sessions)

        anyio.run(agent.run, "Q1", 3, None)
        anyio.run(agent.run, "Q2", 3, None)

        # No session in the store after two stateless calls.
        assert sessions.session_count() == 0
        # Second call's reasoner saw no prior history.
        assert reasoner.calls[1]["history_in"] == []


class TestHistoryTrimming:
    """Plan §448: max history trimming."""

    def test_trim_caps_history_after_max_turns(self):
        sessions = SessionStore(max_turns=2)
        reasoner = _make_recording_reasoner(
            answers=["A1", "A2", "A3", "A4"]
        )
        llm = _make_recording_llm([
            # Turn 1
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
            # Turn 2
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
            # Turn 3
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
            # Turn 4
            _make_tool_call_message([("get_risk_profile", {"user_id": 1})]),
            _make_text_message("ack"),
        ])
        agent = _build_agent(llm, reasoner, sessions)

        for i in range(1, 5):
            anyio.run(agent.run, f"Q{i}", 3, "sess-trim")

        state = sessions.get_or_create("sess-trim")
        # max_turns=2 -> 2 turns × 2 messages = 4 messages kept.
        assert len(state.history) == 4
        assert state.history[0]["content"] == "Q3"
        assert state.history[-1]["content"] == "A4"
        assert len(state.history_traces) == 4


class TestNoCacheNoToolsPath:
    """Out-of-scope query with no prior session — return assistant text."""

    def test_returns_assistant_text_when_no_tools_and_no_cache(self):
        sessions = SessionStore()
        reasoner = _make_recording_reasoner(answers=[])
        llm = _make_recording_llm([
            _make_text_message("Out of scope: I cover FE/MP only."),
        ])
        agent = _build_agent(llm, reasoner, sessions)

        out = anyio.run(agent.run, "What's the weather?", 3, "sess-oos")

        assert out["answer"] == "Out of scope: I cover FE/MP only."
        assert "reasoning" not in out["debug"]
        assert reasoner.calls == []
