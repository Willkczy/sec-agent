"""
Securities Recommendation Agent — FastAPI app + Agent orchestrator.

Thin API orchestrator that uses native function calling to decide which
securities-recommendation endpoints to call, executes the HTTP calls,
and produces a natural language answer.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from openai import AsyncOpenAI
from dotenv import load_dotenv

from config import settings
from models import AskRequest, AskResponse
from tools import TOOLS, get_openai_tools
from prompts import SYSTEM_PROMPT
from api_client import APIClient
from reasoning_adapter import ReasoningAdapter
from session_store import SessionStore, SessionState
from logging_config import (
    log_footer,
    log_header,
    log_stage,
    request_id_var,
    session_id_var,
    setup_logging,
)

load_dotenv()

setup_logging(
    level=settings.LOG_LEVEL,
    fmt=settings.LOG_FORMAT,
    use_unicode=settings.LOG_USE_UNICODE,
)
logger = logging.getLogger("sec_agent")

# ---------------------------------------------------------------------------
# Clients (initialized once at module level)
# ---------------------------------------------------------------------------
llm_client = AsyncOpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
    timeout=120.0,
)

api_client = APIClient(
    base_url=settings.API_BASE_URL,
    enable_auth=settings.ENABLE_AUTH,
    local_mode=settings.LOCAL_MODE,
    service_base_urls={
        "fin-engine": settings.FIN_ENGINE_BASE_URL,
        "model-portfolio": settings.MODEL_PORTFOLIO_BASE_URL,
    },
)

reasoning_adapter = ReasoningAdapter()

# In-memory per-session conversation state (Phase 2 prototype).
# Production should swap this for Redis / Postgres / app session service
# (see session_store.py and integration plan §298).
session_store = SessionStore()

# Pre-build the OpenAI tools list (static across requests)
OPENAI_TOOLS = get_openai_tools()


# Backend pydantic models declare these as int. The LLM sometimes emits them
# as quoted strings; pydantic strict-mode rejects, fin-engine returns 500.
# Coerce here so tool-calling is deterministic regardless of LLM variance.
_INT_FIELDS = {"org_id", "max_stocks", "top_n"}
MISSING_USER_CONTEXT_ANSWER = (
    "I need a signed-in user context to answer portfolio-specific questions."
)


@dataclass(frozen=True)
class UserContext:
    """Trusted caller/session context, separate from the natural-language query."""
    user_id: str | None = None
    external_user_id: str | None = None
    org_id: str | None = None

    def has_any(self) -> bool:
        return any((self.user_id, self.external_user_id, self.org_id))


def _coerce_int_fields(obj: Any) -> Any:
    """Recursively cast known int fields from numeric-string to int."""
    if isinstance(obj, dict):
        return {
            k: (int(v) if k in _INT_FIELDS and isinstance(v, str) and v.lstrip("-").isdigit() else _coerce_int_fields(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_coerce_int_fields(x) for x in obj]
    return obj


def _clean_context_value(value: str | int | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _resolve_user_context(
    session: SessionState,
    *,
    user_id: str | int | None = None,
    external_user_id: str | int | None = None,
    org_id: str | int | None = None,
) -> UserContext:
    """Merge request context into session context and return the active values."""
    resolved_user_id = _clean_context_value(user_id) or session.user_id
    resolved_external_user_id = (
        _clean_context_value(external_user_id) or session.external_user_id
    )
    resolved_org_id = _clean_context_value(org_id) or session.org_id

    session.user_id = resolved_user_id
    session.external_user_id = resolved_external_user_id
    session.org_id = resolved_org_id

    return UserContext(
        user_id=resolved_user_id,
        external_user_id=resolved_external_user_id,
        org_id=resolved_org_id,
    )


def _build_user_context_message(context: UserContext) -> dict[str, str] | None:
    if not context.has_any():
        return None

    lines = [
        "Authenticated user context is trusted request/session metadata.",
        "Use these values for tool parameters when the user says 'my' or omits identifiers.",
    ]
    if context.user_id:
        lines.append(f"user_id: {context.user_id}")
    if context.external_user_id:
        lines.append(f"external_user_id: {context.external_user_id}")
    if context.org_id:
        lines.append(f"org_id: {context.org_id}")

    return {"role": "system", "content": "\n".join(lines)}


def _context_user_id_for_tool(tool_name: str, context: UserContext) -> str | int | None:
    if not context.user_id:
        return None
    tool_def = TOOLS.get(tool_name, {})
    param_def = tool_def.get("parameters", {}).get("user_id", {})
    if param_def.get("type") == "integer" and context.user_id.isdigit():
        return int(context.user_id)
    return context.user_id


def _inject_user_context(
    tool_name: str,
    params: dict[str, Any],
    context: UserContext,
) -> dict[str, Any]:
    """Fill omitted user/org identifiers from trusted context before API calls."""
    params = dict(params or {})
    tool_def = TOOLS.get(tool_name, {})
    tool_params = tool_def.get("parameters", {})

    if tool_name == "financial_engine":
        inner = params.get("parameters")
        if not isinstance(inner, dict):
            inner = {}
        else:
            inner = dict(inner)

        if context.user_id and not inner.get("user_id"):
            inner["user_id"] = context.user_id
        if context.external_user_id and not inner.get("external_user_id"):
            inner["external_user_id"] = context.external_user_id
        if context.org_id and not inner.get("org_id"):
            inner["org_id"] = context.org_id
        params["parameters"] = inner
        return params

    if "user_id" in tool_params and context.user_id and not params.get("user_id"):
        params["user_id"] = _context_user_id_for_tool(tool_name, context)
    if (
        "external_user_id" in tool_params
        and context.external_user_id
        and not params.get("external_user_id")
    ):
        params["external_user_id"] = context.external_user_id
    if "org_id" in tool_params and context.org_id and not params.get("org_id"):
        params["org_id"] = context.org_id
    return params


def _missing_user_context_error(tool_name: str, params: dict[str, Any]) -> str | None:
    """Return a user-facing error when a user-specific tool has no user ID."""
    tool_def = TOOLS.get(tool_name, {})
    tool_params = tool_def.get("parameters", {})

    if tool_name == "financial_engine":
        inner = params.get("parameters")
        if not isinstance(inner, dict) or not inner.get("user_id"):
            return "Missing user_id for this portfolio-specific query."
        return None

    user_schema = tool_params.get("user_id")
    if user_schema and user_schema.get("required") and not params.get("user_id"):
        return "Missing user_id for this user-specific query."
    return None


def _has_missing_user_context_error(tool_results: list[dict[str, Any]]) -> bool:
    for record in tool_results:
        result = record.get("result")
        if not isinstance(result, dict):
            continue
        error = result.get("error")
        if isinstance(error, str) and error.startswith("Missing user_id"):
            return True
    return False


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class Agent:
    """
    Tool-calling agent using native OpenAI function calling.

    Flow: send query → model calls tools → execute → feed results back →
    repeat until model responds with text (or max_iters reached).
    """

    def __init__(
        self,
        llm: AsyncOpenAI,
        api: APIClient,
        reasoner: ReasoningAdapter,
        sessions: SessionStore | None = None,
    ):
        self.llm = llm
        self.api = api
        self.reasoner = reasoner
        # If no store is supplied, the agent runs stateless (every call
        # gets a fresh ephemeral SessionState). Production callers pass
        # the module-level store; tests can pass their own isolated one.
        self.sessions = sessions

    # -- Execute a single tool call -----------------------------------------

    async def _call_tool(
        self,
        tool_name: str,
        params: dict,
        context: UserContext,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Look up the tool in the registry and make the HTTP call."""
        tool_def = TOOLS.get(tool_name)
        if tool_def is None:
            log_stage(
                logger, "tool", "warn", indent=1,
                name=tool_name, error="unknown_tool",
            )
            return params, {"error": f"Unknown tool: {tool_name}"}

        log_stage(
            logger, "tool", "info", indent=1,
            name=tool_name, endpoint=tool_def["endpoint"],
        )

        params = _inject_user_context(tool_name, params, context)
        missing_error = _missing_user_context_error(tool_name, params)
        if missing_error:
            log_stage(
                logger, "tool", "warn", indent=1,
                name=tool_name, abort="missing_user_context",
            )
            return params, {"error": missing_error}

        params = _coerce_int_fields(params)
        started = time.perf_counter()
        result = await self.api.call_tool(tool_def["endpoint"], params)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if isinstance(result, dict) and "error" in result:
            log_stage(
                logger, "tool", "err", indent=1,
                name=tool_name, status="error", elapsed=f"{elapsed_ms}ms",
            )
        else:
            log_stage(
                logger, "tool", "ok", indent=1,
                name=tool_name, status="ok", elapsed=f"{elapsed_ms}ms",
            )
        return params, result

    # -- Main orchestration loop --------------------------------------------

    def _load_session(self, session_id: str | None) -> SessionState:
        """Resolve the SessionState for this turn.

        - With a session_id and a store: persistent, follow-ups continue.
        - Without one: ephemeral state, no continuity (one-shot call).
        """
        if session_id and self.sessions is not None:
            return self.sessions.get_or_create(session_id)
        return SessionState()

    async def run(
        self,
        user_query: str,
        max_iters: int = 3,
        session_id: str | None = None,
        user_id: str | int | None = None,
        external_user_id: str | int | None = None,
        org_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Full orchestration loop using native function calling.

        The tool-calling LLM only chooses + executes tools. Once tool
        calls finish (model emits text or max_iters reached), the
        collected tool_results are converted to Glass-Box inputs,
        merged with prior session-cached api_keys/user_outputs, and
        handed to ReasoningAdapter for the Reasoner + Answerer pipeline.

        Follow-up branches:
          - Tool calls fired → reason over merged (new + cached) inputs.
          - No tool calls but the session has a prior cache (a follow-up
            like "how was that calculated?" that doesn't need fresh
            data) → reason over cached inputs alone.
          - No tool calls and no cache → return the assistant's text
            verbatim (out-of-scope query).

        Returns {"answer": str, "debug": {...}}.
        """
        session = self._load_session(session_id)
        user_context = _resolve_user_context(
            session,
            user_id=user_id,
            external_user_id=external_user_id,
            org_id=org_id,
        )
        log_stage(
            logger, "session", "info",
            turns=len(session.history) // 2,
            cached_keys=len(session.last_api_keys),
            user_ctx="yes" if user_context.has_any() else "no",
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        context_message = _build_user_context_message(user_context)
        if context_message:
            messages.append(context_message)
        # Inject prior user-facing turns so the tool-calling LLM
        # understands references like "how was that calculated?" and can
        # decide to skip a redundant tool call.
        messages.extend(session.history)
        messages.append({"role": "user", "content": user_query})

        debug: dict[str, Any] = {"iterations": [], "tool_results": []}
        last_assistant_text: str = ""

        for iteration in range(max_iters):
            log_stage(
                logger, "tool-llm", "info",
                **{"iter": f"{iteration + 1}/{max_iters}"},
                msgs=len(messages),
            )
            resp = await self.llm.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=OPENAI_TOOLS,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False}
                },
            )
            choice = resp.choices[0]
            assistant_msg = choice.message
            if assistant_msg.tool_calls:
                log_stage(
                    logger, "tool-llm", "info",
                    **{"iter": iteration + 1},
                    tool_calls=len(assistant_msg.tool_calls),
                )
            else:
                log_stage(
                    logger, "tool-llm", "info",
                    **{"iter": iteration + 1},
                    result="text-done",
                )

            # Append the assistant message to the conversation history.
            # We need to serialize it properly for the next API call.
            msg_dict: dict[str, Any] = {"role": "assistant"}
            if assistant_msg.content:
                msg_dict["content"] = assistant_msg.content
                last_assistant_text = assistant_msg.content
            if assistant_msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_msg.tool_calls
                ]
            messages.append(msg_dict)

            # Model is done planning tool calls.
            if not assistant_msg.tool_calls:
                break

            # Execute each tool call and feed results back.
            iter_results = []
            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.name
                try:
                    params = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    params = {}

                params, result = await self._call_tool(
                    tool_name,
                    params,
                    user_context,
                )

                tool_record = {
                    "tool": tool_name,
                    "params": params,
                    "result": result,
                }
                iter_results.append(tool_record)
                debug["tool_results"].append(tool_record)

                # Add the tool result to the conversation so the model
                # can see it on the next turn.
                result_str = json.dumps(
                    result, ensure_ascii=False, default=str
                )
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "... [truncated]"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            debug["iterations"].append({
                "iteration": iteration + 1,
                "tool_calls": [
                    {"tool": r["tool"], "params": r["params"]}
                    for r in iter_results
                ],
            })

        # Resolve which (api_keys, user_outputs) the Reasoner should see.
        new_keys, new_outputs, unmapped = ReasoningAdapter.build_inputs(
            debug["tool_results"]
        )
        log_stage(
            logger, "inputs", "info",
            api_keys=new_keys or "none",
            unmapped=unmapped or "none",
        )

        if _has_missing_user_context_error(debug["tool_results"]):
            log_stage(
                logger, "branch", "warn",
                path="abort", reason="missing_user_context",
            )
            return {
                "answer": MISSING_USER_CONTEXT_ANSWER,
                "debug": debug,
            }

        if not debug["tool_results"] and not session.last_api_keys:
            # No new tool call AND no prior session cache — nothing to
            # ground on. Return the assistant's text directly.
            log_stage(
                logger, "branch", "info",
                path="out_of_scope",
            )
            return {
                "answer": last_assistant_text or (
                    "No answer produced. This assistant covers Financial "
                    "Engine and Model Portfolio queries only."
                ),
                "debug": debug,
            }

        if not debug["tool_results"]:
            # Follow-up that did not need a fresh tool call. Reuse the
            # prior session cache so the Reasoner can answer from the
            # previous evidence (and prior history_traces).
            merged_keys = list(session.last_api_keys)
            merged_outputs = dict(session.last_user_outputs)
            debug["reused_session_cache"] = True
            log_stage(
                logger, "branch", "info",
                path="cache_reuse", keys=len(merged_keys),
            )
        else:
            # New tool calls collected — merge with any prior cache so a
            # follow-up that does fetch fresh data still has access to
            # earlier evidence.
            merged_keys = list(
                dict.fromkeys(list(session.last_api_keys) + new_keys)
            )
            merged_outputs = {**session.last_user_outputs, **new_outputs}
            log_stage(
                logger, "branch", "info",
                path="fresh+merge",
                new=len(new_keys),
                cached=len(session.last_api_keys),
                merged=len(merged_keys),
            )

        reasoning = await self.reasoner.answer(
            question=user_query,
            api_keys=merged_keys,
            user_outputs=merged_outputs,
            history=session.history,
            history_traces=session.history_traces,
            unmapped_tools=unmapped,
        )

        # Persist updated session cache for the next turn. The Reasoner
        # has already mutated session.history and session.history_traces
        # in place. Trim if a real store is backing this session.
        session.last_api_keys = merged_keys
        session.last_user_outputs = merged_outputs
        if session_id and self.sessions is not None:
            self.sessions.trim(session)

        debug["reasoning"] = {
            "api_keys": reasoning["api_keys"],
            "trace": reasoning["reasoning_trace"],
            "verifier_verdict": reasoning["verifier_verdict"],
            "verifier_retries": reasoning["verifier_retries"],
            "unmapped_tools": reasoning["unmapped_tools"],
        }
        return {"answer": reasoning["answer"], "debug": debug}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Securities Recommendation Agent")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sec-agent"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Main endpoint: takes a natural language query, returns an answer."""
    request_id_var.set(uuid4().hex[:8])
    session_id_var.set(request.session_id or "-")

    log_header(logger)
    log_stage(
        logger, "receive", "info",
        query_len=len(request.query),
        user_ctx="yes" if any([
            request.user_id, request.external_user_id, request.org_id,
        ]) else "no",
    )
    started = time.perf_counter()

    try:
        agent = Agent(
            llm=llm_client,
            api=api_client,
            reasoner=reasoning_adapter,
            sessions=session_store,
        )
        result = await agent.run(
            request.query,
            request.max_iters,
            session_id=request.session_id,
            user_id=request.user_id,
            external_user_id=request.external_user_id,
            org_id=request.org_id,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log_footer(
            logger,
            label="DONE",
            total=f"{elapsed_ms}ms",
            answer=f"{len(result['answer'])} chars",
        )
        return AskResponse(
            answer=result["answer"],
            session_id=request.session_id,
            debug=result["debug"],
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log_footer(
            logger,
            label="ERROR",
            total=f"{elapsed_ms}ms",
            error=type(e).__name__,
        )
        logger.exception("request failed")
        raise HTTPException(status_code=500, detail=str(e))
