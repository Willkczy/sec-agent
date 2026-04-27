"""
Bridge between sec-agent tool execution and Reasoning_LLM_TiFin Glass-Box models.

Converts sec-agent tool_result records into the (api_keys, user_outputs) shape
that TwoLayerGlassBoxModel / ThreeLayerGlassBoxModel expect, runs the
Reasoner+Answerer (and optionally Verifier) pipeline, and returns the
user-facing answer plus the reasoning trace and metadata.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Import Glass-Box from the sibling Reasoning_LLM_TiFin repo
# ---------------------------------------------------------------------------
_REASONING_REPO = Path(__file__).resolve().parent.parent / "Reasoning_LLM_TiFin"
if str(_REASONING_REPO) not in sys.path:
    sys.path.insert(0, str(_REASONING_REPO))

from model_two_layer import TwoLayerGlassBoxModel, API_DESCRIPTIONS  # noqa: E402
from model_three_layer import ThreeLayerGlassBoxModel  # noqa: E402


# ---------------------------------------------------------------------------
# sec-agent tool name → Glass-Box api_key resolver
# ---------------------------------------------------------------------------

# Direct one-to-one mappings (no parameter inspection needed).
_DIRECT_TOOL_TO_KEY: dict[str, str] = {
    "portfolio_builder": "portfolio_builder",
    "get_risk_profile": "get_risk_profile",
    "risk_profile_v2": "risk_profile_v2",
    "multi_goal_optimizer": "multi_goal_optimizer",
    "stock_to_fund": "stock_to_fund",
    # backtest_portfolio's sec-agent tool name differs from its Glass-Box key.
    "backtest_portfolio": "backtest_selected_portfolio",
    # single_goal_optimizer + goal_defaults: live data attaches under the base
    # key (no _retirement/_house split) so the Glass-Box description (single
    # entry per base name) lines up.
    "single_goal_optimizer": "single_goal_optimizer",
    "goal_defaults": "goal_defaults",
}


def _resolve_api_key(tool_name: str, params: dict[str, Any]) -> str | None:
    """Map a sec-agent tool call to a Glass-Box api_key.

    Returns None if the tool has no Glass-Box mapping (unsupported in the
    reasoning pipeline). Caller is expected to drop these from api_keys.
    """
    if tool_name == "financial_engine":
        # FE tool dispatches via the `function` param; that name IS the api_key.
        return params.get("function")

    if tool_name == "get_portfolio_options":
        # Glass-Box splits this into _lumpsum / _sip variants. Description
        # lookup strips the suffix back to the base entry.
        investment_type = (params.get("investment_type") or "").upper()
        if investment_type == "LUMP_SUM":
            return "get_portfolio_options_lumpsum"
        if investment_type == "SIP":
            return "get_portfolio_options_sip"
        return None

    return _DIRECT_TOOL_TO_KEY.get(tool_name)


def _unwrap_output(api_key: str, result: Any) -> Any:
    """Return the inner output payload Glass-Box expects.

    Some backends wrap responses in an envelope keyed by the function name
    (e.g. financial_engine → {"asset_breakdown": {...}}). Glass-Box stores
    user_outputs[api_key] as the inner dict, so unwrap when the envelope
    matches the api_key. Otherwise return the raw result unchanged.
    """
    if isinstance(result, dict) and api_key in result and len(result) == 1:
        return result[api_key]
    return result


def _description_key(api_key: str) -> str:
    """Glass-Box strips _lumpsum/_sip when looking up descriptions; mirror it
    so we can validate that an api_key has a matching description."""
    return api_key.replace("_lumpsum", "").replace("_sip", "")


def has_glass_box_description(api_key: str) -> bool:
    return _description_key(api_key) in API_DESCRIPTIONS


# ---------------------------------------------------------------------------
# Glass-Box model singleton
# ---------------------------------------------------------------------------

_MODEL: TwoLayerGlassBoxModel | None = None


def _get_model() -> TwoLayerGlassBoxModel:
    """Lazy-init the Glass-Box model. Two- or three-layer per env var."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    arch = os.getenv("REASONING_ARCHITECTURE", "two_layer").lower()
    if arch == "three_layer":
        _MODEL = ThreeLayerGlassBoxModel()
    else:
        _MODEL = TwoLayerGlassBoxModel()
    return _MODEL


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_MESSAGE = (
    "No supported tool outputs were available to reason over. "
    "This assistant covers Financial Engine and Model Portfolio "
    "queries only."
)


class ReasoningAdapter:
    """Stateless wrapper around the Glass-Box reasoning models.

    Two-step usage so the caller (main.py) can merge live tool results
    with prior session-cached api_keys/user_outputs before reasoning:

        api_keys, user_outputs, unmapped = ReasoningAdapter.build_inputs(tool_results)
        # ... merge with session cache ...
        result = await adapter.answer(
            question=...,
            api_keys=api_keys,
            user_outputs=user_outputs,
            history=...,
            history_traces=...,
        )

    History lists are mutated in place by the underlying Glass-Box model
    (one user/assistant pair appended per call), so the caller's session
    store sees the new turn automatically.
    """

    @staticmethod
    def build_inputs(
        tool_results: list[dict[str, Any]],
    ) -> tuple[list[str], dict[str, Any], list[str]]:
        """Convert tool_results → (api_keys, user_outputs, unmapped_tool_names).

        - Skips tool calls that returned an error envelope (no signal for
          the Reasoner; would pollute the trace).
        - Last-write-wins if the same api_key is produced twice (later
          call presumed more relevant).
        """
        api_keys: list[str] = []
        user_outputs: dict[str, Any] = {}
        unmapped: list[str] = []

        for record in tool_results:
            tool_name = record.get("tool")
            params = record.get("params") or {}
            result = record.get("result")

            if isinstance(result, dict) and "error" in result:
                continue

            api_key = _resolve_api_key(tool_name, params)
            if api_key is None:
                unmapped.append(tool_name)
                continue

            if not has_glass_box_description(api_key):
                # Reasoner would have nothing to ground against; treat as
                # unmapped so callers can surface the gap.
                unmapped.append(f"{tool_name}:{api_key}")
                continue

            user_outputs[api_key] = _unwrap_output(api_key, result)
            if api_key not in api_keys:
                api_keys.append(api_key)

        return api_keys, user_outputs, unmapped

    async def answer(
        self,
        *,
        question: str,
        api_keys: list[str],
        user_outputs: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
        history_traces: list[dict[str, Any]] | None = None,
        unmapped_tools: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run the Glass-Box pipeline with already-resolved inputs.

        Returns the answer + trace + verifier metadata. Forwards
        unmapped_tools through unchanged so callers can include the gap
        in debug output.
        """
        history = history if history is not None else []
        history_traces = history_traces if history_traces is not None else []
        unmapped_tools = unmapped_tools if unmapped_tools is not None else []

        if not api_keys:
            return {
                "answer": OUT_OF_SCOPE_MESSAGE,
                "reasoning_trace": "",
                "api_keys": [],
                "verifier_verdict": None,
                "verifier_retries": 0,
                "unmapped_tools": unmapped_tools,
            }

        model = _get_model()
        answer, trace = await asyncio.to_thread(
            model.ask,
            question,
            api_keys,
            history,
            history_traces,
            user_outputs,
        )

        verifier_verdict = getattr(model, "last_verifier_verdict", None)
        verifier_retries = getattr(model, "last_verifier_retries", 0)

        return {
            "answer": answer,
            "reasoning_trace": trace,
            "api_keys": api_keys,
            "verifier_verdict": verifier_verdict,
            "verifier_retries": verifier_retries,
            "unmapped_tools": unmapped_tools,
        }
