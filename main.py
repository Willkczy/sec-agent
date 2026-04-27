"""
Securities Recommendation Agent — FastAPI app + Agent orchestrator.

Thin API orchestrator that uses native function calling to decide which
securities-recommendation endpoints to call, executes the HTTP calls,
and produces a natural language answer.
"""

import json
from typing import Any

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

load_dotenv()

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

    async def _call_tool(self, tool_name: str, params: dict) -> dict[str, Any]:
        """Look up the tool in the registry and make the HTTP call."""
        tool_def = TOOLS.get(tool_name)
        if tool_def is None:
            return {"error": f"Unknown tool: {tool_name}"}
        params = _coerce_int_fields(params)
        return await self.api.call_tool(tool_def["endpoint"], params)

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

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        # Inject prior user-facing turns so the tool-calling LLM
        # understands references like "how was that calculated?" and can
        # decide to skip a redundant tool call.
        messages.extend(session.history)
        messages.append({"role": "user", "content": user_query})

        debug: dict[str, Any] = {"iterations": [], "tool_results": []}
        last_assistant_text: str = ""

        for iteration in range(max_iters):
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

                result = await self._call_tool(tool_name, params)

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

        if not debug["tool_results"] and not session.last_api_keys:
            # No new tool call AND no prior session cache — nothing to
            # ground on. Return the assistant's text directly.
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
        else:
            # New tool calls collected — merge with any prior cache so a
            # follow-up that does fetch fresh data still has access to
            # earlier evidence.
            merged_keys = list(
                dict.fromkeys(list(session.last_api_keys) + new_keys)
            )
            merged_outputs = {**session.last_user_outputs, **new_outputs}

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
        )
        return AskResponse(
            answer=result["answer"],
            session_id=request.session_id,
            debug=result["debug"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
