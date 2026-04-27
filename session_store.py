"""
In-memory per-session store for the Glass-Box reasoning integration.

Each session_id maps to four pieces of state:
  - history          : Answerer-facing user/assistant pairs.
  - history_traces   : Reasoner-facing user/trace pairs.
  - last_api_keys    : api_keys reasoned over on the most recent turn.
  - last_user_outputs: {api_key: output} cache so a follow-up question
                       (e.g. "how was that calculated?") that triggers no
                       new tool call can still reach the Reasoner with
                       the prior data attached.

Phase 2 prototype: single-process, in-memory, dict-backed. Plan §298 calls
out Redis/Postgres/app-session-service as the production target — out of
scope here.

Concurrency: Python dict ops are GIL-protected for single statements but a
read-modify-write across multiple statements is not. We add a coarse Lock
around session creation only; same-session concurrent calls within a
single FastAPI request lifecycle are not expected (the agent processes
one turn at a time).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


DEFAULT_MAX_TURNS = 10


@dataclass
class SessionState:
    """Per-session state. Lists are mutated in place by the Reasoner."""
    history: list[dict[str, Any]] = field(default_factory=list)
    history_traces: list[dict[str, Any]] = field(default_factory=list)
    last_api_keys: list[str] = field(default_factory=list)
    last_user_outputs: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    """Dict-backed session store with history trimming."""

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS):
        self._sessions: dict[str, SessionState] = {}
        self._lock = Lock()
        self._max_turns = max_turns

    @property
    def max_turns(self) -> int:
        return self._max_turns

    def get_or_create(self, session_id: str) -> SessionState:
        """Return state for `session_id`, creating an empty entry if absent."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                state = SessionState()
                self._sessions[session_id] = state
            return state

    def trim(self, state: SessionState) -> None:
        """Cap history and history_traces at max_turns turns (2 msgs each).

        The Reasoner appends 2 messages per turn (user + assistant). We
        keep the most recent slice so the LLM sees recent context without
        unbounded prompt growth.
        """
        keep = self._max_turns * 2
        if len(state.history) > keep:
            state.history[:] = state.history[-keep:]
        if len(state.history_traces) > keep:
            state.history_traces[:] = state.history_traces[-keep:]

    def reset(self, session_id: str) -> None:
        """Drop all state for a session_id (test helper / explicit reset)."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        return len(self._sessions)
