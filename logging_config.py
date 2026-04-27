"""
Per-request stage logging for sec-agent.

Provides:
  - setup_logging()           — idempotent root-logger config.
  - request_id_var / session_id_var — ContextVars for correlation.
  - log_header() / log_footer() / log_stage() — call-site helpers.

PR 1 wires the formatter, ContextVars, and header/footer emission in /ask.
PR 2 will add the per-stage body lines across main / api_client /
reasoning_adapter / session_store.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any


# ---------------------------------------------------------------------------
# Correlation context — set by /ask, read by RequestContextFilter
# ---------------------------------------------------------------------------
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
session_id_var: ContextVar[str] = ContextVar("session_id", default="-")


# ---------------------------------------------------------------------------
# Glyph tables (unicode + ASCII fallback)
# ---------------------------------------------------------------------------
_GLYPHS_UNICODE = {
    "info": "▸",   # ▸
    "prog": "↻",   # ↻
    "ok":   "✓",   # ✓
    "warn": "⚠",   # ⚠
    "err":  "✗",   # ✗
    "empty": "∅",  # ∅
    "pipe": "│",   # │
    "tl":   "┌──",  # ┌──
    "bl":   "└──",  # └──
}
_GLYPHS_ASCII = {
    "info": ">",
    "prog": "..",
    "ok":   "OK",
    "warn": "!",
    "err":  "X",
    "empty": "none",
    "pipe": "|",
    "tl":   "--",
    "bl":   "--",
}

# Width of "HH:MM:SS.mmm  " — body lines pad this out so the box stays aligned.
_TS_PAD = " " * 14


# ---------------------------------------------------------------------------
# Filter — injects request_id / session_id from ContextVars onto every record
# ---------------------------------------------------------------------------
class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.session_id = session_id_var.get()
        return True


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------
class PrettyFormatter(logging.Formatter):
    """Stage-stream formatter.

    Reads optional record extras:
      - record.phase     : str  — phase column label (e.g. "tool-llm")
      - record.marker    : str  — one of info|prog|ok|warn|err
      - record.indent    : int  — sub-stage indent depth (default 0)
      - record.kv        : dict — key=value pairs rendered after the phase
      - record.is_header : bool — render per-request box header
      - record.is_footer : bool — render per-request box footer

    Records without those extras (e.g. a stray third-party log) fall back
    to a plain body line keyed by record.name and record.getMessage().
    """

    def __init__(self, use_unicode: bool = True) -> None:
        super().__init__()
        self.glyph = _GLYPHS_UNICODE if use_unicode else _GLYPHS_ASCII

    def _ts(self, record: logging.LogRecord) -> str:
        return f"{self.formatTime(record, '%H:%M:%S')}.{int(record.msecs):03d}"

    def _kv_str(self, kv: dict[str, Any]) -> str:
        return "  ".join(f"{k}={v}" for k, v in kv.items())

    def format(self, record: logging.LogRecord) -> str:
        is_header = getattr(record, "is_header", False)
        is_footer = getattr(record, "is_footer", False)
        req_id = getattr(record, "request_id", "-")
        sess_id = getattr(record, "session_id", "-")

        if is_header:
            return (
                f"{self._ts(record)}  {self.glyph['tl']} REQUEST {req_id}  "
                f"session={sess_id}"
            )

        kv: dict[str, Any] = dict(getattr(record, "kv", {}) or {})

        if is_footer:
            label = kv.pop("_label", "DONE")
            tail = self._kv_str(kv)
            tail = f"  {tail}" if tail else ""
            return f"{self._ts(record)}  {self.glyph['bl']} {label} {req_id}{tail}"

        # Body line — indented under the box pipe.
        phase = (getattr(record, "phase", None) or record.name)[:12].ljust(12)
        marker = self.glyph.get(
            getattr(record, "marker", "info"), self.glyph["info"]
        )
        indent_spaces = "  " * int(getattr(record, "indent", 0))
        body = self._kv_str(kv) if kv else record.getMessage()

        line = (
            f"{_TS_PAD}{self.glyph['pipe']} {indent_spaces}{marker} "
            f"{phase} {body}"
        )
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


class PlainFormatter(logging.Formatter):
    """Single-line fallback. No box drawing — useful for log aggregators."""

    def __init__(self) -> None:
        super().__init__(
            fmt=(
                "%(asctime)s %(levelname)-5s [%(name)s] "
                "[req=%(request_id)s sess=%(session_id)s] %(message)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def _select_formatter(fmt: str, use_unicode: bool) -> logging.Formatter:
    if fmt == "plain":
        return PlainFormatter()
    return PrettyFormatter(use_unicode=use_unicode)


# ---------------------------------------------------------------------------
# Setup — idempotent
# ---------------------------------------------------------------------------
_CONFIGURED = False


def setup_logging(
    level: str = "INFO",
    fmt: str = "pretty",
    use_unicode: bool = True,
) -> None:
    """Configure the root logger. Repeat calls are no-ops."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_select_formatter(fmt, use_unicode))
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Quiet noisy libs that don't carry our context — they'd render bare.
    for noisy in ("aiohttp.access", "openai", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel("WARNING")

    _CONFIGURED = True


def reset_logging_for_tests() -> None:
    """Test helper — drop the configured flag so setup_logging() reruns."""
    global _CONFIGURED
    _CONFIGURED = False


# ---------------------------------------------------------------------------
# Call-site helpers
# ---------------------------------------------------------------------------
def log_header(logger: logging.Logger) -> None:
    """Emit per-request box header. IDs come from ContextVars."""
    logger.info("", extra={"is_header": True})


def log_footer(logger: logging.Logger, label: str = "DONE", **kv: Any) -> None:
    """Emit per-request box footer with totals (e.g. total=Nms answer=N chars)."""
    payload: dict[str, Any] = {"_label": label, **kv}
    logger.info("", extra={"is_footer": True, "kv": payload})


def log_stage(
    logger: logging.Logger,
    phase: str,
    marker: str = "info",
    indent: int = 0,
    **kv: Any,
) -> None:
    """Emit one stage body line."""
    logger.info(
        "",
        extra={
            "phase": phase,
            "marker": marker,
            "indent": indent,
            "kv": kv,
        },
    )
