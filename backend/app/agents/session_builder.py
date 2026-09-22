"""
SessionBuilderAgent -- powers Learn > For You (Day 9.5).

Runs a real tool-use loop: the model decides which tool to call (and
with what arguments), we execute the matching real Python function
against the database, feed the result back, and repeat until the model
returns a final structured session plan.

The underlying model/vendor is swappable -- see app/agents/llm.py --
via the LLM_PROVIDER env var ("anthropic" | "openai" | "deepseek").

CHANGED (Day 9.5): this agent originally also handled due reviews and
weak-area targeting for a combined new+review session. In the
redesigned IA, Drill owns all review -- SessionBuilderAgent's only job
now is picking a small batch of not-yet-learnt vocab/grammar for the
For You screen. get_weak_areas and get_due_reviews were dropped from
its toolset (they still exist in tools.py for reuse by other agents,
e.g. Day 12's ProgressEvaluatorAgent).
"""

import json

from sqlalchemy.orm import Session

from app.agents import tools as agent_tools
from app.agents.llm import ToolResult, get_llm_provider
from app.utils.retry import call_with_retry

AGENT_NAME = "SessionBuilderAgent"

TOOL_SCHEMAS = [
    {
        "name": "fetch_new_content",
        "description": "Returns content the user hasn't learnt yet, at a given JLPT level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "description": "JLPT level, e.g. 'N5'"},
                "content_type": {
                    "type": "string",
                    "enum": ["vocab", "grammar"],
                },
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["level", "content_type"],
        },
    },
    {
        "name": "get_user_profile",
        "description": "Returns the user's current JLPT level, streak count, and days since their last session.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        },
    },
]

SYSTEM_PROMPT = """You are SessionBuilderAgent, powering the "For You" tab of a
Japanese learning app called Nihongo -- an agent-curated batch of new
content for a user who doesn't want to browse Vocab/Grammar manually.

Use get_user_profile to check the user's JLPT level, then
fetch_new_content (vocab and/or grammar) to gather candidates -- it
already excludes anything the user has marked Learnt, so everything it
returns is genuinely new to them.

You'll be told exactly how many items to include -- pick that many
total, mixing vocab and grammar. Once you've gathered enough context,
respond with ONLY a JSON object (no markdown fences, no prose) in this
exact shape:

{
  "reasoning": "a short paragraph explaining what you picked and why, written for the user to read",
  "items": [
    {"content_type": "vocab" | "grammar", "content_id": "..."}
  ]
}
"""


def _execute_tool(db: Session, user_id: str, tool_name: str, tool_input: dict) -> dict:
    if tool_name == "fetch_new_content":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.fetch_new_content(
                db,
                user_id=user_id,
                level=tool_input["level"],
                content_type=tool_input["content_type"],
                limit=tool_input.get("limit", 5),
            ),
            # fetch_new_content only ever reads the seeded DB today (no
            # external API call yet), so failure just means an empty slot.
            fallback={"content_type": tool_input.get("content_type"), "items": []},
        )
    elif tool_name == "get_user_profile":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.get_user_profile(db, user_id),
            fallback={"jlpt_level": "N5", "streak_count": 0, "days_since_last_session": None},
        )
    else:
        return {"error": f"unknown tool: {tool_name}"}


def run_session_builder_agent(db: Session, user_id: str, item_count: int = 10) -> dict:
    provider = get_llm_provider()
    provider.start_conversation(
        system=SYSTEM_PROMPT,
        user_message=(
            f"Build today's For You session for user_id={user_id}. "
            f"Target exactly {item_count} items total."
        ),
    )

    tool_call_log = []

    MAX_ROUNDS = 6

    for _ in range(MAX_ROUNDS):
        turn = provider.step(TOOL_SCHEMAS)

        if turn.is_final:
            session_plan = _parse_session_plan(turn.text)
            return {
                "session_plan": session_plan,
                "tool_calls": tool_call_log,
                "raw_reasoning_text": turn.text,
            }

        results = []
        for call in turn.tool_calls:
            output = _execute_tool(db, user_id, call.name, call.input)

            tool_call_log.append(
                {
                    "tool_name": call.name,
                    "input": call.input,
                    "result": output,
                }
            )
            results.append(ToolResult(id=call.id, name=call.name, output=output))

        provider.submit_tool_results(results)

    raise RuntimeError(
        f"SessionBuilderAgent exceeded {MAX_ROUNDS} tool-use rounds without a final answer"
    )


def _parse_session_plan(text: str) -> dict:
    """
    Defensive JSON extraction. Despite the system prompt instructing
    the model to respond with ONLY JSON, it sometimes adds a preamble
    sentence or wraps the JSON in markdown fences anyway. Rather than
    assume the whole string is clean JSON, we find the first '{' and
    the last '}' and parse just that slice -- this tolerates leading/
    trailing prose without needing it to match an exact format.
    """
    cleaned = text.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or start > end:
        raise ValueError(f"No JSON object found in agent response: {text!r}")

    json_slice = cleaned[start:end + 1]

    return json.loads(json_slice)
