"""
Unit tests for sec-agent stage logging.

Verifies that:
  - setup_logging() is idempotent.
  - ContextVars (request_id, session_id) reach LogRecord via the filter.
  - log_header / log_footer / log_stage attach the expected extras.
  - PrettyFormatter renders unicode + ASCII fallback correctly.
  - Agent.run emits the expected phase sequence under stubbed dependencies.
"""

import logging

import anyio
import pytest

from logging_config import (
    PrettyFormatter,
    log_footer,
    log_header,
    log_stage,
    request_id_var,
    session_id_var,
    reset_logging_for_tests,
    setup_logging,
)

# Reuse the stub helpers from the existing agent unit suite.
from tests.test_agent_unit import (
    _build_agent,
    _make_stub_reasoner,
    _make_text_message,
    _make_tool_call_message,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

def test_setup_logging_idempotent():
    reset_logging_for_tests()
    setup_logging()
    root = logging.getLogger()
    handlers_before = len(root.handlers)
    setup_logging()
    assert len(root.handlers) == handlers_before


# ---------------------------------------------------------------------------
# Context propagation
# ---------------------------------------------------------------------------

def test_request_context_filter_injects_ids(caplog):
    request_id_var.set("abcd1234")
    session_id_var.set("sess-x")
    test_logger = logging.getLogger("sec_agent.tests")
    with caplog.at_level(logging.INFO):
        test_logger.info("hi")
    rec = caplog.records[-1]
    assert rec.request_id == "abcd1234"
    assert rec.session_id == "sess-x"


# ---------------------------------------------------------------------------
# Helper extras
# ---------------------------------------------------------------------------

def test_log_header_extras(caplog):
    sec_logger = logging.getLogger("sec_agent")
    with caplog.at_level(logging.INFO):
        log_header(sec_logger)
    rec = caplog.records[-1]
    assert getattr(rec, "is_header", False) is True


def test_log_footer_carries_label_and_kv(caplog):
    sec_logger = logging.getLogger("sec_agent")
    with caplog.at_level(logging.INFO):
        log_footer(sec_logger, label="DONE", total="100ms", answer="42 chars")
    rec = caplog.records[-1]
    assert getattr(rec, "is_footer", False) is True
    assert rec.kv["_label"] == "DONE"
    assert rec.kv["total"] == "100ms"


def test_log_stage_carries_phase_marker_indent_kv(caplog):
    sec_logger = logging.getLogger("sec_agent")
    with caplog.at_level(logging.INFO):
        log_stage(sec_logger, "tool-llm", "info", indent=0, msgs=3)
        log_stage(sec_logger, "http", "ok", indent=2, status=200)
    a, b = caplog.records[-2], caplog.records[-1]
    assert a.phase == "tool-llm" and a.marker == "info" and a.indent == 0
    assert a.kv == {"msgs": 3}
    assert b.phase == "http" and b.marker == "ok" and b.indent == 2


def test_log_stage_respects_level(caplog):
    """level=DEBUG records get filtered when root is INFO."""
    reset_logging_for_tests()
    setup_logging(level="INFO")
    sec_logger = logging.getLogger("sec_agent.session")
    with caplog.at_level(logging.INFO):
        log_stage(sec_logger, "session", "info", level=logging.DEBUG, event="x")
    debug_records = [
        r for r in caplog.records
        if getattr(r, "phase", None) == "session"
        and getattr(r, "kv", {}).get("event") == "x"
    ]
    assert debug_records == []


# ---------------------------------------------------------------------------
# Formatter rendering
# ---------------------------------------------------------------------------

def _make_record(**kwargs) -> logging.LogRecord:
    rec = logging.LogRecord(
        name="sec_agent", level=logging.INFO, pathname="", lineno=0,
        msg="", args=(), exc_info=None,
    )
    rec.request_id = "abc"
    rec.session_id = "s1"
    for k, v in kwargs.items():
        setattr(rec, k, v)
    return rec


def test_pretty_formatter_renders_unicode_header():
    fmt = PrettyFormatter(use_unicode=True)
    out = fmt.format(_make_record(is_header=True))
    assert "┌──" in out
    assert "REQUEST abc" in out
    assert "session=s1" in out


def test_pretty_formatter_ascii_fallback_strips_unicode():
    fmt = PrettyFormatter(use_unicode=False)
    out = fmt.format(_make_record(is_header=True))
    for ch in ("┌", "│", "▸", "✓", "↻", "⚠", "✗", "∅"):
        assert ch not in out
    assert "REQUEST abc" in out


def test_pretty_formatter_body_line_aligns_under_pipe():
    fmt = PrettyFormatter(use_unicode=True)
    rec = _make_record(phase="tool-llm", marker="info", indent=0,
                       kv={"iter": "1/3", "msgs": 3})
    out = fmt.format(rec)
    assert "│ ▸ tool-llm" in out
    assert "iter=1/3" in out and "msgs=3" in out


def test_pretty_formatter_indent_nests_subhase():
    fmt = PrettyFormatter(use_unicode=True)
    rec = _make_record(phase="http", marker="ok", indent=2,
                       kv={"status": 200, "elapsed": "412ms"})
    out = fmt.format(rec)
    assert "│     ✓ http" in out


# ---------------------------------------------------------------------------
# End-to-end stage sequence under Agent.run (stubbed)
# ---------------------------------------------------------------------------

def test_agent_run_emits_session_toolllm_tool_inputs_branch(caplog):
    reasoner = _make_stub_reasoner(
        answer="ok", api_keys=["asset_breakdown"],
    )
    agent = _build_agent(
        [
            _make_tool_call_message([
                ("financial_engine",
                 {"function": "asset_breakdown",
                  "parameters": {"user_id": "1"}}),
            ]),
            _make_text_message("ack"),
        ],
        api_results={"fin-engine": {"asset_breakdown": {"equity": 60}}},
        reasoner=reasoner,
    )
    with caplog.at_level(logging.INFO):
        anyio.run(agent.run, "show breakdown")
    phases = [
        getattr(r, "phase", None) for r in caplog.records
        if getattr(r, "phase", None)
    ]
    for required in ("session", "tool-llm", "tool", "inputs", "branch"):
        assert required in phases, f"missing phase {required!r} in {phases}"


def test_missing_user_context_emits_warn_branch(caplog):
    reasoner = _make_stub_reasoner()
    agent = _build_agent(
        [
            _make_tool_call_message([
                ("financial_engine",
                 {"function": "asset_breakdown", "parameters": {}}),
            ]),
            _make_text_message("ack"),
        ],
        api_results=None,
        reasoner=reasoner,
    )
    with caplog.at_level(logging.INFO):
        result = anyio.run(agent.run, "my breakdown")

    assert "signed-in user context" in result["answer"]
    branch_records = [
        r for r in caplog.records
        if getattr(r, "phase", None) == "branch"
    ]
    assert any(
        r.kv.get("reason") == "missing_user_context"
        and r.marker == "warn"
        for r in branch_records
    )
