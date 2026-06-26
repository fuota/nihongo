"""
SessionBuilderAgent.

Runs a real Anthropic tool-use loop: Claude decides which of the 4
tools to call (and with what arguments), we execute the matching real
Python function against the database, feed the result back, and repeat
until Claude returns a final structured session plan.
"""

import json
import os

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.agents import tools as agent_tools

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-6"

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
        return agent_tools.get_weak_areas(db, user_id)
    elif tool_name == "get_due_reviews":
        return agent_tools.get_due_reviews(db, user_id)
    elif tool_name == "fetch_new_content":
        return agent_tools.fetch_new_content(
            db,
            level=tool_input["level"],
            content_type=tool_input["content_type"],
            exclude_ids=tool_input.get("exclude_ids", []),
            limit=tool_input.get("limit", 5),
        )
    elif tool_name == "get_user_profile":
        return agent_tools.get_user_profile(db, user_id)
    else:
        return {"error": f"unknown tool: {tool_name}"}


def run_session_builder_agent(db: Session, user_id: str) -> dict:
    messages = [
        {
            "role": "user",
            "content": f"Build today's session for user_id={user_id}.",
        }
    ]

    tool_call_log = []
    raw_text_fragments = []

    MAX_ROUNDS = 6

    for _ in range(MAX_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        for block in response.content:
            if block.type == "text" and block.text.strip():
                raw_text_fragments.append(block.text.strip())

        if response.stop_reason != "tool_use":
            final_text = "".join(raw_text_fragments) if raw_text_fragments else ""
            for block in response.content:
                if block.type == "text":
                    final_text = block.text.strip()

            session_plan = _parse_session_plan(final_text)

            return {
                "session_plan": session_plan,
                "tool_calls": tool_call_log,
                "raw_reasoning_text": final_text,
            }

        messages.append({"role": "assistant", "content": response.content})
        
        '''
        CLAUDE EXAMPLE RESPONSE FOR TOOL USE:
            {
                "content": [
                    {"type": "tool_use", "id": "toolu_01ABC", "name": "get_due_reviews", "input": {...}},
                    {"type": "tool_use", "id": "toolu_02XYZ", "name": "get_weak_areas", "input": {...}}
                ]
            }
        '''
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            result = _execute_tool(db, user_id, block.name, block.input)

            tool_call_log.append(
                {
                    "tool_name": block.name,
                    "input": block.input,
                    "result": result,
                }
            )

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )

        messages.append({"role": "user", "content": tool_results})

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
