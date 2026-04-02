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

load_dotenv()

# ---------------------------------------------------------------------------
# Clients (initialized once at module level)
# ---------------------------------------------------------------------------
llm_client = AsyncOpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
)

api_client = APIClient(
    base_url=settings.API_BASE_URL,
    enable_auth=settings.ENABLE_AUTH,
)

# Pre-build the OpenAI tools list (static across requests)
OPENAI_TOOLS = get_openai_tools()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class Agent:
    """
    Tool-calling agent using native OpenAI function calling.

    Flow: send query → model calls tools → execute → feed results back →
    repeat until model responds with text (or max_iters reached).
    """

    def __init__(self, llm: AsyncOpenAI, api: APIClient):
        self.llm = llm
        self.api = api

    # -- Execute a single tool call -----------------------------------------

    async def _call_tool(self, tool_name: str, params: dict) -> dict[str, Any]:
        """Look up the tool in the registry and make the HTTP call."""
        tool_def = TOOLS.get(tool_name)
        if tool_def is None:
            return {"error": f"Unknown tool: {tool_name}"}
        return await self.api.call_tool(tool_def["endpoint"], params)

    # -- Main orchestration loop --------------------------------------------

    async def run(
        self, user_query: str, max_iters: int = 3
    ) -> dict[str, Any]:
        """
        Full orchestration loop using native function calling.

        The model decides when it's done by returning a text response
        instead of more tool calls. No explicit ``next_step_required``
        flag is needed.

        Returns {"answer": str, "debug": {...}}.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ]
        debug: dict[str, Any] = {"iterations": [], "tool_results": []}

        for iteration in range(max_iters):
            resp = await self.llm.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=OPENAI_TOOLS,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
            choice = resp.choices[0]
            assistant_msg = choice.message

            # Append the assistant message to the conversation history.
            # We need to serialize it properly for the next API call.
            msg_dict: dict[str, Any] = {"role": "assistant"}
            if assistant_msg.content:
                msg_dict["content"] = assistant_msg.content
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

            # If the model returned text with no tool calls, we're done.
            if not assistant_msg.tool_calls:
                return {
                    "answer": assistant_msg.content or "No answer produced.",
                    "debug": debug,
                }

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

        # Exhausted max_iters — ask the model for a final answer without tools
        # so it synthesizes whatever data it has.
        resp = await self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )
        return {
            "answer": resp.choices[0].message.content or "Max iterations reached with no answer.",
            "debug": debug,
        }


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
        agent = Agent(llm=llm_client, api=api_client)
        result = await agent.run(request.query, request.max_iters)
        return AskResponse(answer=result["answer"], debug=result["debug"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
