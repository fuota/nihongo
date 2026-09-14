"""
SessionBuilderAgent.

Runs a real tool-use loop: the model decides which of the 4 tools to
call (and with what arguments), we execute the matching real Python
function against the database, feed the result back, and repeat until
the model returns a final structured session plan.

The underlying model/vendor is swappable -- see app/agents/llm.py --
via the LLM_PROVIDER env var ("anthropic" | "openai" | "deepseek").
"""

import json

from sqlalchemy.orm import Session

from app.agents import tools as agent_tools
from app.agents.llm import ToolResult, get_llm_provider
from app.utils.retry import call_with_retry

AGENT_NAME = "SessionBuilderAgent"

TOOL_SCHEMAS = [
    {
        "name": "get_weak_areas",
        "description": "Returns specific content items the user has struggled with (each with its real content_id and a human-readable display_label), most frequent first. Use this to bring back the EXACT items the user struggled with -- e.g. the specific kanji they got wrong -- rather than just generic practice of the same category.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "get_due_reviews",
        "description": "Returns SRS-scheduled items that are due (or overdue) for review today for this user, soonest-due first.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "fetch_new_content",
        "description": "Returns new (never-seen) content the user can learn, at a given JLPT level. Use this to fill remaining session slots after weak areas and due reviews are accounted for.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "description": "JLPT level, e.g. 'N5'"},
                "content_type": {
                    "type": "string",
                    "enum": ["vocab", "writing", "grammar"],
                },
                "exclude_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs to exclude (content the user has already seen)",
                },
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["level", "content_type", "exclude_ids"],
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

SYSTEM_PROMPT = """You are SessionBuilderAgent, part of a Japanese learning app called Nihongo.

Your job: build today's personalized learning session for a user, by
calling the available tools to understand their current state, then
deciding what the session should contain.

Use the tools to gather context (you can call multiple tools before
deciding). Prioritize, in this order:
1. Items due for SRS review (these come first -- spaced repetition only
   works if reviews happen on schedule)
2. Specific items the user has struggled with -- get_weak_areas returns
   the EXACT content_id of each struggling item (e.g. a specific kanji
   or grammar pattern), not just a category. Include those exact items
   directly in the session using their real content_id, with
   reason="weak_area". Only fall back to fetch_new_content for the same
   content_type if you need to fill additional slots beyond the
   specific weak items returned.
3. New content to fill any remaining session slots

Aim for a session of 8-12 items total. Once you've gathered enough
context, respond with ONLY a JSON object (no markdown fences, no prose)
in this exact shape:

{
  "reasoning": "a short paragraph explaining what you decided and why, written for the user to read",
  "items": [
    {"content_type": "vocab" | "writing" | "grammar", "content_id": "...", "reason": "due_review" | "weak_area" | "new_content"}
  ]
}
"""


def _execute_tool(db: Session, user_id: str, tool_name: str, tool_input: dict) -> dict:
    if tool_name == "get_weak_areas":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.get_weak_areas(db, user_id),
            fallback={"weak_areas": []},  # treat as "no weak areas known yet"
        )
    elif tool_name == "get_due_reviews":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.get_due_reviews(db, user_id),
            fallback={"due_count": 0, "due_items": []},  # treat as "nothing due"
        )
    elif tool_name == "fetch_new_content":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.fetch_new_content(
                db,
                level=tool_input["level"],
                content_type=tool_input["content_type"],
                exclude_ids=tool_input.get("exclude_ids", []),
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


def run_session_builder_agent(db: Session, user_id: str) -> dict:
    provider = get_llm_provider()
    provider.start_conversation(
        system=SYSTEM_PROMPT,
        user_message=f"Build today's session for user_id={user_id}.",
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
    Claude to respond with ONLY JSON, it sometimes adds a preamble
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
