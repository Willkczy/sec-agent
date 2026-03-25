"""
Securities Recommendation Agent — FastAPI app + Agent orchestrator.

Thin API orchestrator that plans which securities-recommendation endpoints to call,
executes the HTTP calls, and renders a natural language answer.
"""

import json
import re
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from openai import AsyncOpenAI
from dotenv import load_dotenv

from config import settings
from models import AskRequest, AskResponse
from tools import TOOLS
from prompts import get_planner_prompt, RENDER_PROMPT
from api_client import APIClient

load_dotenv()

# ---------------------------------------------------------------------------
# Clients (initialized once at module level, same pattern as Zara main.py)
# ---------------------------------------------------------------------------
llm_client = AsyncOpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
)

api_client = APIClient(
    base_url=settings.API_BASE_URL,
    enable_auth=settings.ENABLE_AUTH,
)

# Cache the planner prompt (static across requests)
PLANNER_PROMPT = get_planner_prompt()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class Agent:
    """
    Simple tool-calling agent inspired by Zara's FinancialDataOrchestrator.

    Flow: plan() → execute() → [loop if next_step_required] → render()
    """

    def __init__(
        self,
        llm: AsyncOpenAI,
        api: APIClient,
    ):
        self.llm = llm
        self.api = api

    # -- Utilities ----------------------------------------------------------

    @staticmethod
    def extract_json_object(text: str) -> dict[str, Any]:
        """
        Robustly extract a single JSON object from arbitrary LLM text.
        Same approach as Zara main.py:188-198.
        """
        # Try fenced ```json blocks first
        fence = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S | re.I)
        if fence:
            return json.loads(fence.group(1))
        # Fallback: first {...} block
        brace = re.search(r"\{.*\}", text, flags=re.S)
        if brace:
            return json.loads(brace.group(0))
        raise ValueError("No JSON object found in planner response")

    # -- Plan ---------------------------------------------------------------

    async def plan(self, user_query: str) -> dict[str, Any]:
        """
        Send the user query to the planner LLM.
        Returns parsed JSON plan: {reasoning, tool_calls, next_step_required}
        """
        messages = [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": user_query},
        ]

        resp = await self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        text = resp.choices[0].message.content
        return self.extract_json_object(text)

    # -- Execute ------------------------------------------------------------

    async def execute(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Execute each tool call in the plan by making HTTP requests.
        Returns list of {tool, params, result} dicts.
        """
        results = []
        for step in plan.get("tool_calls", []):
            tool_name = step.get("tool")
            params = step.get("params", {})

            tool_def = TOOLS.get(tool_name)
            if tool_def is None:
                results.append({
                    "tool": tool_name,
                    "params": params,
                    "result": {"error": f"Unknown tool: {tool_name}"},
                })
                continue

            endpoint = tool_def["endpoint"]
            result = await self.api.call_tool(endpoint, params)
            results.append({
                "tool": tool_name,
                "params": params,
                "result": result,
            })

        return results

    # -- Next-step context --------------------------------------------------

    @staticmethod
    def build_next_step_prompt(
        user_query: str, previous_results: list[dict[str, Any]]
    ) -> str:
        """
        Build a follow-up prompt with truncated previous results as context.
        Same pattern as Zara main.py:315-327.
        """
        summaries = []
        for r in previous_results:
            result_str = json.dumps(r.get("result", {}), ensure_ascii=False, default=str)
            summaries.append(
                f"Tool '{r.get('tool')}': {result_str[:2000]}"
            )
        preview = "\n".join(summaries)
        return (
            f"User query: {user_query}\n\n"
            f"Here are the previous tool output summaries:\n{preview}\n\n"
            f"Please plan the next tool steps (same strict JSON schema)."
        )

    # -- Render -------------------------------------------------------------

    async def render(
        self, user_query: str, all_results: list[dict[str, Any]]
    ) -> str:
        """
        Send tool results to the render LLM to produce the final answer.
        """
        # Format tool outputs with step labels
        step_outputs = []
        for i, r in enumerate(all_results, 1):
            tool_name = r.get("tool", "unknown")
            result_str = json.dumps(
                r.get("result", {}), ensure_ascii=False, default=str
            )
            # Truncate very large results to avoid token overflow
            if len(result_str) > 8000:
                result_str = result_str[:8000] + "... [truncated]"
            step_outputs.append(f"=== Step {i}: {tool_name} ===\n{result_str}")

        tool_output_text = "\n\n".join(step_outputs) if step_outputs else "(no results)"

        messages = [
            {"role": "system", "content": RENDER_PROMPT},
            {
                "role": "user",
                "content": f"User query: {user_query}\n\nTool output:\n{tool_output_text}",
            },
        ]

        resp = await self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )
        return resp.choices[0].message.content

    # -- Main orchestration loop --------------------------------------------

    async def run(
        self, user_query: str, max_iters: int = 3
    ) -> dict[str, Any]:
        """
        Full orchestration loop: plan → execute → (loop if needed) → render.
        Returns {"answer": str, "debug": {...}}.
        """
        debug: dict[str, Any] = {"plans": [], "tool_results": []}

        # Step 1: Initial plan
        plan = await self.plan(user_query)
        debug["plans"].append(plan)

        # Step 2: Execute
        results = await self.execute(plan)
        debug["tool_results"].extend(results)

        # Step 3: Multi-step loop (if next_step_required)
        iters = 1
        while plan.get("next_step_required") and iters < max_iters:
            iters += 1
            next_prompt = self.build_next_step_prompt(user_query, results)
            plan = await self.plan(next_prompt)
            debug["plans"].append(plan)
            results = await self.execute(plan)
            debug["tool_results"].extend(results)
            if not plan.get("next_step_required"):
                break

        # Step 4: Render final answer
        answer = await self.render(user_query, debug["tool_results"])

        return {"answer": answer, "debug": debug}


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
