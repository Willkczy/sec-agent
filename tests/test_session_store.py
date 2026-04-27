"""
Unit tests for session_store.

Covers session isolation, get-or-create semantics, trimming behaviour,
reset, and that the same session_id returns the same mutable state object
(so in-place mutation by the Reasoner is observed on the next call).
"""

import pytest

from session_store import SessionStore, SessionState, DEFAULT_MAX_TURNS


pytestmark = pytest.mark.unit


class TestGetOrCreate:
    def test_creates_empty_state_on_first_access(self):
        store = SessionStore()
        state = store.get_or_create("s1")
        assert isinstance(state, SessionState)
        assert state.history == []
        assert state.history_traces == []
        assert state.last_api_keys == []
        assert state.last_user_outputs == {}

    def test_returns_same_object_on_repeated_access(self):
        store = SessionStore()
        a = store.get_or_create("s1")
        b = store.get_or_create("s1")
        assert a is b

    def test_in_place_mutation_persists(self):
        store = SessionStore()
        state = store.get_or_create("s1")
        state.history.append({"role": "user", "content": "hi"})
        state.last_api_keys.append("asset_breakdown")
        state.last_user_outputs["asset_breakdown"] = {"equity": 60}

        again = store.get_or_create("s1")
        assert again.history == [{"role": "user", "content": "hi"}]
        assert again.last_api_keys == ["asset_breakdown"]
        assert again.last_user_outputs == {"asset_breakdown": {"equity": 60}}


class TestSessionIsolation:
    def test_two_session_ids_have_independent_state(self):
        store = SessionStore()
        a = store.get_or_create("s1")
        b = store.get_or_create("s2")
        assert a is not b

        a.history.append({"role": "user", "content": "for s1 only"})
        a.last_api_keys.append("asset_breakdown")
        a.last_user_outputs["asset_breakdown"] = {"x": 1}

        assert b.history == []
        assert b.last_api_keys == []
        assert b.last_user_outputs == {}

    def test_session_count_tracks_unique_ids(self):
        store = SessionStore()
        store.get_or_create("s1")
        store.get_or_create("s2")
        store.get_or_create("s1")  # repeat
        assert store.session_count() == 2


class TestTrim:
    def test_trim_keeps_last_max_turns_pairs(self):
        store = SessionStore(max_turns=2)
        state = store.get_or_create("s1")
        for i in range(5):
            state.history.append({"role": "user", "content": f"q{i}"})
            state.history.append({"role": "assistant", "content": f"a{i}"})
            state.history_traces.append({"role": "user", "content": f"q{i}"})
            state.history_traces.append({"role": "assistant", "content": f"trace{i}"})

        store.trim(state)

        # max_turns=2 → keep last 4 messages (2 turns × 2 msgs)
        assert len(state.history) == 4
        assert state.history[0] == {"role": "user", "content": "q3"}
        assert state.history[-1] == {"role": "assistant", "content": "a4"}
        assert len(state.history_traces) == 4
        assert state.history_traces[-1] == {"role": "assistant", "content": "trace4"}

    def test_trim_is_noop_under_limit(self):
        store = SessionStore(max_turns=10)
        state = store.get_or_create("s1")
        state.history.append({"role": "user", "content": "q"})
        state.history.append({"role": "assistant", "content": "a"})

        store.trim(state)

        assert len(state.history) == 2

    def test_trim_mutates_in_place_so_caller_references_stay_valid(self):
        """The Reasoner holds a reference to history and mutates it; trim
        must not replace the list object (or the Reasoner would lose its
        handle). Verify by id()."""
        store = SessionStore(max_turns=1)
        state = store.get_or_create("s1")
        for i in range(3):
            state.history.append({"role": "user", "content": f"q{i}"})
            state.history.append({"role": "assistant", "content": f"a{i}"})

        history_id_before = id(state.history)
        traces_id_before = id(state.history_traces)
        store.trim(state)
        assert id(state.history) == history_id_before
        assert id(state.history_traces) == traces_id_before


class TestReset:
    def test_reset_drops_state(self):
        store = SessionStore()
        state = store.get_or_create("s1")
        state.history.append({"role": "user", "content": "hi"})
        store.reset("s1")

        new_state = store.get_or_create("s1")
        assert new_state is not state
        assert new_state.history == []

    def test_reset_unknown_session_is_noop(self):
        store = SessionStore()
        store.reset("never-seen")  # must not raise


class TestDefaults:
    def test_default_max_turns(self):
        store = SessionStore()
        assert store.max_turns == DEFAULT_MAX_TURNS
