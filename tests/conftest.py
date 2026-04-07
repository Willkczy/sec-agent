"""
Shared fixtures for sec-agent tests.

Provides LLM client, tool schemas, and helpers for non-deterministic LLM tests.
"""

import json
import os
import sys

import pytest
from openai import AsyncOpenAI

# Allow imports from the project root (sec-agent/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from tools import get_openai_tools
from prompts import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Majority-vote helper for non-deterministic LLM tests
# ---------------------------------------------------------------------------

STRICT_MODE = os.environ.get("STRICT_MODE", "0") == "1"


async def majority_vote(check_fn, n=3, threshold=2):
    """Run check_fn() n times, return True if >= threshold succeed.

    In STRICT_MODE (env STRICT_MODE=1), runs only once (no retries).
    """
    if STRICT_MODE:
        return await check_fn()

    successes = 0
    for _ in range(n):
        try:
            if await check_fn():
                successes += 1
                if successes >= threshold:
                    return True
        except Exception:
            pass
    return successes >= threshold


# ---------------------------------------------------------------------------
# Helper to extract tool calls from an LLM response message
# ---------------------------------------------------------------------------


def extract_tool_calls(message):
    """Extract tool names and parsed params from a chat completion message.

    Returns:
        list[dict] with keys: name, params
    """
    if not message.tool_calls:
        return []
    results = []
    for tc in message.tool_calls:
        try:
            params = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            params = {}
        results.append({"name": tc.function.name, "params": params})
    return results


def tool_names(message):
    """Return sorted list of tool names from a chat completion message."""
    return sorted(tc["name"] for tc in extract_tool_calls(message))


# ---------------------------------------------------------------------------
# Session-scoped fixtures (created once per test session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def openai_tools():
    """Pre-built OpenAI tools list (static, no LLM needed)."""
    return get_openai_tools()


@pytest.fixture(scope="session")
def llm_client():
    """AsyncOpenAI client pointed at the self-hosted LLM.

    Skips all dependent tests if the LLM is unreachable.
    """
    client = AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        timeout=30.0,
    )
    return client


@pytest.fixture(scope="session")
def system_prompt():
    """The agent system prompt."""
    return SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Function-scoped fixture: ask_llm
# ---------------------------------------------------------------------------


@pytest.fixture
def ask_llm(llm_client, openai_tools, system_prompt):
    """Returns an async callable: ask_llm(query) -> message.

    Sends a single query to the LLM with the system prompt and tool schemas,
    returns the raw assistant message (with .tool_calls and .content).
    """

    async def _ask(query: str, temperature: float = 0.1):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        resp = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=openai_tools,
            temperature=temperature,
            max_tokens=settings.LLM_MAX_TOKENS,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return resp.choices[0].message

    return _ask
