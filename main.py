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
)

reasoning_adapter = ReasoningAdapter()

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
    ):
        self.llm = llm
        self.api = api
        self.reasoner = reasoner

    # -- Execute a single tool call -----------------------------------------

    async def _call_tool(self, tool_name: str, params: dict) -> dict[str, Any]:
        """Look up the tool in the registry and make the HTTP call."""
        tool_def = TOOLS.get(tool_name)
        if tool_def is None:
            return {"error": f"Unknown tool: {tool_name}"}
        params = _coerce_int_fields(params)
        return await self.api.call_tool(tool_def["endpoint"], params)

    # -- Main orchestration loop --------------------------------------------

    async def run(
        self, user_query: str, max_iters: int = 3
    ) -> dict[str, Any]:
        """
        Full orchestration loop using native function calling.

        The tool-calling LLM only chooses + executes tools. Once tool calls
        finish (model emits text or max_iters reached), the collected
        tool_results are handed to ReasoningAdapter, which runs the
        Glass-Box Reasoner+Answerer pipeline to produce the user-facing
        answer. The tool-calling LLM's text is only used as a fallback
        when no tools were called (out-of-scope queries).

        Returns {"answer": str, "debug": {...}}.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ]
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

        # No tool was ever called: assistant rejected the query as
        # out-of-scope (or returned text with no plan). Return its text
        # directly — the reasoner has nothing to ground on.
        if not debug["tool_results"]:
            return {
                "answer": last_assistant_text or (
                    "No answer produced. This assistant covers Financial "
                    "Engine and Model Portfolio queries only."
                ),
                "debug": debug,
            }

        # Tool calls collected — hand off to Glass-Box reasoner.
        reasoning = await self.reasoner.answer(
            question=user_query,
            tool_results=debug["tool_results"],
            history=[],
            history_traces=[],
        )
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
        agent = Agent(llm=llm_client, api=api_client, reasoner=reasoning_adapter)
        result = await agent.run(request.query, request.max_iters)
        return AskResponse(answer=result["answer"], debug=result["debug"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
