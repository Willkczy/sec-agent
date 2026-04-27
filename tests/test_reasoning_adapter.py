"""
Unit tests for reasoning_adapter.

Covers tool_record → Glass-Box api_key mapping, output unwrapping, error
envelope handling, description coverage for every active tool path, and
the empty-tool-results fallback path on the public adapter.
"""

import asyncio

import pytest

import reasoning_adapter as ra_module
from tools import ACTIVE_TOOLS
from reasoning_adapter import (
    ReasoningAdapter,
    _resolve_api_key,
    _unwrap_output,
    has_glass_box_description,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _resolve_api_key
# ---------------------------------------------------------------------------

class TestResolveApiKey:
    def test_financial_engine_uses_function_param(self):
        for fn in [
            "asset_breakdown",
            "diversification",
            "sector_breakdown",
            "market_cap_breakdown",
            "sector_preference",
            "amc_preference",
            "theme_preference",
            "factor_preference",
            "total_stock_exposure",
            "single_holding_exposure",
        ]:
            assert _resolve_api_key("financial_engine", {"function": fn}) == fn

    def test_get_portfolio_options_split_by_investment_type(self):
        assert (
            _resolve_api_key("get_portfolio_options", {"investment_type": "LUMP_SUM"})
            == "get_portfolio_options_lumpsum"
        )
        assert (
            _resolve_api_key("get_portfolio_options", {"investment_type": "SIP"})
            == "get_portfolio_options_sip"
        )

    def test_get_portfolio_options_missing_type_returns_none(self):
        assert _resolve_api_key("get_portfolio_options", {}) is None

    def test_backtest_portfolio_renames_to_glass_box_key(self):
        assert (
            _resolve_api_key("backtest_portfolio", {})
            == "backtest_selected_portfolio"
        )

    def test_direct_mp_tools_pass_through(self):
        for tool in [
            "portfolio_builder",
            "get_risk_profile",
            "risk_profile_v2",
            "multi_goal_optimizer",
            "stock_to_fund",
        ]:
            assert _resolve_api_key(tool, {}) == tool

    def test_goal_tools_use_base_key(self):
        # Plan §263-268: live data attaches under base key; Glass-Box
        # description JSON has only base entries.
        assert (
            _resolve_api_key("single_goal_optimizer", {"goal_type": "RETIREMENT"})
            == "single_goal_optimizer"
        )
        assert (
            _resolve_api_key("goal_defaults", {"goal_type": "HOUSE_PURCHASE"})
            == "goal_defaults"
        )

    def test_unknown_tool_returns_none(self):
        assert _resolve_api_key("search_funds", {}) is None
        assert _resolve_api_key("ml_fund_discovery", {}) is None


# ---------------------------------------------------------------------------
# _unwrap_output
# ---------------------------------------------------------------------------

class TestUnwrapOutput:
    def test_unwraps_single_key_envelope_matching_api_key(self):
        assert _unwrap_output("asset_breakdown", {"asset_breakdown": {"x": 1}}) == {"x": 1}

    def test_returns_raw_when_envelope_does_not_match(self):
        result = {"foo": 1, "bar": 2}
        assert _unwrap_output("asset_breakdown", result) == result

    def test_returns_raw_for_non_dict(self):
        assert _unwrap_output("anything", [1, 2, 3]) == [1, 2, 3]
        assert _unwrap_output("anything", "string") == "string"


# ---------------------------------------------------------------------------
# Description coverage — every active tool must produce an api_key with a
# matching Glass-Box description.
# ---------------------------------------------------------------------------

# Sample params per active tool that exercise every code path the resolver
# can take. financial_engine is expanded to all 10 FE functions. MP tools
# with branching params include both branches.
_SAMPLE_INVOCATIONS: dict[str, list[dict]] = {
    "financial_engine": [
        {"function": fn}
        for fn in [
            "asset_breakdown",
            "diversification",
            "sector_breakdown",
            "market_cap_breakdown",
            "sector_preference",
            "amc_preference",
            "theme_preference",
            "factor_preference",
            "total_stock_exposure",
            "single_holding_exposure",
        ]
    ],
    "get_portfolio_options": [
        {"investment_type": "LUMP_SUM"},
        {"investment_type": "SIP"},
    ],
    "backtest_portfolio": [{}],
    "portfolio_builder": [{}],
    "get_risk_profile": [{}],
    "risk_profile_v2": [{}],
    "single_goal_optimizer": [{"goal_type": "RETIREMENT"}],
    "multi_goal_optimizer": [{}],
    "goal_defaults": [{"goal_type": "RETIREMENT"}],
    "stock_to_fund": [{}],
}


class TestDescriptionCoverage:
    def test_every_active_tool_has_sample_invocation(self):
        missing = ACTIVE_TOOLS - set(_SAMPLE_INVOCATIONS.keys())
        assert not missing, (
            f"Sample invocation missing for active tools: {missing}. "
            "Update _SAMPLE_INVOCATIONS when enabling a new tool."
        )

    def test_every_active_tool_path_resolves_to_described_api_key(self):
        gaps = []
        for tool, samples in _SAMPLE_INVOCATIONS.items():
            if tool not in ACTIVE_TOOLS:
                continue
            for params in samples:
                api_key = _resolve_api_key(tool, params)
                if api_key is None:
                    gaps.append(f"{tool}({params}) -> None")
                    continue
                if not has_glass_box_description(api_key):
                    gaps.append(f"{tool}({params}) -> {api_key} (no description)")
        assert not gaps, "Active tools missing Glass-Box descriptions:\n" + "\n".join(gaps)


# ---------------------------------------------------------------------------
# ReasoningAdapter.build_inputs
# ---------------------------------------------------------------------------

class TestBuildInputs:
    def test_collects_api_keys_in_order(self):
        keys, outs, unmapped = ReasoningAdapter.build_inputs([
            {"tool": "financial_engine",
             "params": {"function": "asset_breakdown"},
             "result": {"asset_breakdown": {"equity": 60}}},
            {"tool": "get_portfolio_options",
             "params": {"investment_type": "SIP", "amount": 10000},
             "result": {"portfolio": {}}},
        ])
        assert keys == ["asset_breakdown", "get_portfolio_options_sip"]
        assert outs["asset_breakdown"] == {"equity": 60}
        assert outs["get_portfolio_options_sip"] == {"portfolio": {}}
        assert unmapped == []

    def test_skips_error_envelopes(self):
        keys, outs, unmapped = ReasoningAdapter.build_inputs([
            {"tool": "financial_engine",
             "params": {"function": "sector_breakdown"},
             "result": {"error": "HTTP 500", "status_code": 500}},
        ])
        assert keys == []
        assert outs == {}
        assert unmapped == []  # error result is silently dropped, not flagged

    def test_records_unmapped_tools(self):
        keys, outs, unmapped = ReasoningAdapter.build_inputs([
            {"tool": "search_funds", "params": {}, "result": {"hits": []}},
        ])
        assert keys == []
        assert "search_funds" in unmapped

    def test_dedupe_keeps_last_write(self):
        keys, outs, unmapped = ReasoningAdapter.build_inputs([
            {"tool": "financial_engine",
             "params": {"function": "asset_breakdown"},
             "result": {"asset_breakdown": {"v": 1}}},
            {"tool": "financial_engine",
             "params": {"function": "asset_breakdown"},
             "result": {"asset_breakdown": {"v": 2}}},
        ])
        assert keys == ["asset_breakdown"]
        assert outs["asset_breakdown"] == {"v": 2}


# ---------------------------------------------------------------------------
# ReasoningAdapter.answer — empty-input path (no LLM)
# ---------------------------------------------------------------------------

class TestAdapterAnswerEmptyInputs:
    def test_returns_out_of_scope_message_when_api_keys_empty(self):
        adapter = ReasoningAdapter()
        out = asyncio.run(adapter.answer(
            question="show me top funds",
            api_keys=[],
            user_outputs={},
            unmapped_tools=["search_funds"],
        ))
        assert out["api_keys"] == []
        assert out["reasoning_trace"] == ""
        assert out["verifier_verdict"] is None
        assert out["unmapped_tools"] == ["search_funds"]
        assert "Financial Engine" in out["answer"]

    def test_returns_out_of_scope_when_called_with_no_inputs_at_all(self):
        adapter = ReasoningAdapter()
        out = asyncio.run(adapter.answer(
            question="hi",
            api_keys=[],
            user_outputs={},
        ))
        assert out["api_keys"] == []
        assert out["unmapped_tools"] == []


# ---------------------------------------------------------------------------
# Verifier metadata propagation (Phase 3 — three-layer mode)
# ---------------------------------------------------------------------------

class _StubGlassBoxModel:
    """Stand-in for TwoLayer / ThreeLayer Glass-Box model.

    The real models do file IO + LLM calls at __init__ and ask(), neither
    of which we want in unit tests. This stub lets each test pre-program
    the (answer, trace, verifier_verdict, verifier_retries) returned and
    appends to history / history_traces in place the way the real model
    does.
    """

    def __init__(self, answer="STUB", trace="STUB_TRACE",
                 verifier_verdict=None, verifier_retries=0):
        self._answer = answer
        self._trace = trace
        self.last_verifier_verdict = verifier_verdict
        self.last_verifier_retries = verifier_retries

    def ask(self, question, api_keys, history, history_traces, user_outputs):
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": self._answer})
        history_traces.append({"role": "user", "content": question})
        history_traces.append({"role": "assistant", "content": self._trace})
        return self._answer, self._trace


@pytest.fixture
def patched_model(monkeypatch):
    """Helper to install a stub Glass-Box model and return a setter so each
    test can swap in its own pre-programmed instance."""
    def _install(stub):
        monkeypatch.setattr(ra_module, "_MODEL", stub)
        return stub
    yield _install
    # Clean up so other tests get a fresh singleton resolution.
    ra_module.reset_model_singleton()


class TestVerifierMetadataPropagation:
    def test_pass_verdict_with_zero_retries_propagates(self, patched_model):
        patched_model(_StubGlassBoxModel(
            answer="ANS", trace="TR",
            verifier_verdict="PASS", verifier_retries=0,
        ))
        adapter = ReasoningAdapter()
        out = asyncio.run(adapter.answer(
            question="q",
            api_keys=["asset_breakdown"],
            user_outputs={"asset_breakdown": {"equity": 60}},
        ))
        assert out["answer"] == "ANS"
        assert out["reasoning_trace"] == "TR"
        assert out["verifier_verdict"] == "PASS"
        assert out["verifier_retries"] == 0

    def test_fail_verdict_after_max_retries_still_returns_answer(self, patched_model):
        # Mirrors ThreeLayerGlassBoxModel.MAX_RETRIES exhaustion: the
        # answer is still returned, just flagged FAIL with retries=2.
        patched_model(_StubGlassBoxModel(
            answer="DEGRADED_ANS", trace="DEGRADED_TR",
            verifier_verdict="FAIL", verifier_retries=2,
        ))
        adapter = ReasoningAdapter()
        out = asyncio.run(adapter.answer(
            question="q",
            api_keys=["asset_breakdown"],
            user_outputs={"asset_breakdown": {"equity": 60}},
        ))
        assert out["answer"] == "DEGRADED_ANS"
        assert out["verifier_verdict"] == "FAIL"
        assert out["verifier_retries"] == 2

    def test_pass_after_one_retry_propagates_retry_count(self, patched_model):
        patched_model(_StubGlassBoxModel(
            answer="ANS", trace="TR",
            verifier_verdict="PASS", verifier_retries=1,
        ))
        adapter = ReasoningAdapter()
        out = asyncio.run(adapter.answer(
            question="q",
            api_keys=["asset_breakdown"],
            user_outputs={"asset_breakdown": {"equity": 60}},
        ))
        assert out["verifier_verdict"] == "PASS"
        assert out["verifier_retries"] == 1

    def test_two_layer_model_yields_none_verdict(self, patched_model):
        # TwoLayerGlassBoxModel does not define last_verifier_*; getattr
        # in the adapter must fall back to None / 0 — not raise.
        stub = _StubGlassBoxModel()
        # Strip the verifier attrs so getattr fallback is exercised.
        del stub.last_verifier_verdict
        del stub.last_verifier_retries
        patched_model(stub)
        adapter = ReasoningAdapter()
        out = asyncio.run(adapter.answer(
            question="q",
            api_keys=["asset_breakdown"],
            user_outputs={"asset_breakdown": {"equity": 60}},
        ))
        assert out["verifier_verdict"] is None
        assert out["verifier_retries"] == 0


class TestArchitectureSelection:
    def test_two_layer_is_default(self, monkeypatch):
        from config import settings as cfg
        monkeypatch.setattr(cfg, "REASONING_ARCHITECTURE", "two_layer")
        ra_module.reset_model_singleton()
        # _get_model would actually instantiate Glass-Box (heavy file IO),
        # so we patch the constructors to track which one was called.
        instantiated: list[str] = []
        monkeypatch.setattr(
            ra_module, "TwoLayerGlassBoxModel",
            lambda: instantiated.append("two") or _StubGlassBoxModel(),
        )
        monkeypatch.setattr(
            ra_module, "ThreeLayerGlassBoxModel",
            lambda: instantiated.append("three") or _StubGlassBoxModel(),
        )
        ra_module._get_model()
        assert instantiated == ["two"]
        ra_module.reset_model_singleton()

    def test_three_layer_selected_via_settings(self, monkeypatch):
        from config import settings as cfg
        monkeypatch.setattr(cfg, "REASONING_ARCHITECTURE", "three_layer")
        ra_module.reset_model_singleton()
        instantiated: list[str] = []
        monkeypatch.setattr(
            ra_module, "TwoLayerGlassBoxModel",
            lambda: instantiated.append("two") or _StubGlassBoxModel(),
        )
        monkeypatch.setattr(
            ra_module, "ThreeLayerGlassBoxModel",
            lambda: instantiated.append("three") or _StubGlassBoxModel(),
        )
        ra_module._get_model()
        assert instantiated == ["three"]
        ra_module.reset_model_singleton()

    def test_unknown_value_falls_back_to_two_layer(self, monkeypatch):
        from config import settings as cfg
        monkeypatch.setattr(cfg, "REASONING_ARCHITECTURE", "garbage")
        ra_module.reset_model_singleton()
        instantiated: list[str] = []
        monkeypatch.setattr(
            ra_module, "TwoLayerGlassBoxModel",
            lambda: instantiated.append("two") or _StubGlassBoxModel(),
        )
        monkeypatch.setattr(
            ra_module, "ThreeLayerGlassBoxModel",
            lambda: instantiated.append("three") or _StubGlassBoxModel(),
        )
        ra_module._get_model()
        assert instantiated == ["two"]
        ra_module.reset_model_singleton()
