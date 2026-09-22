"""
TutorAgent -- kanji handwriting feedback (Day 9, partial).

Runs after POST /kanji/recognize: given the target character and what
the vision model recognized, reasons about specific, contextual
feedback using the user's own history with this character, rather than
generic praise or criticism.

Honest scope note: Day 8's recognition pipeline (a vision-capable LLM,
since no Google Cloud Vision credentials exist for this project) only
returns a recognized character + confidence, not stroke-level analysis.
So this agent's error classification is coarser than the original
plan's illustrative example ("previous mistakes were stroke order") --
it can only tell "wrong_character" (drew something unrecognizable or
different) from "low_confidence" (right character, messy execution),
not identify which specific stroke went wrong.
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.agents import tools as agent_tools
from app.agents.llm import ToolResult, get_llm_provider
from app.utils.retry import call_with_retry

AGENT_NAME = "TutorAgent"

BASE_TOOL_SCHEMAS = [
    {
        "name": "get_kanji_data",
        "description": "Returns the target kanji's meaning, stroke count, and readings.",
        "input_schema": {
            "type": "object",
            "properties": {"kanji_id": {"type": "string"}},
            "required": ["kanji_id"],
        },
    },
    {
        "name": "get_user_kanji_history",
        "description": "Returns this user's past logged mistakes on this specific kanji (count + error types), oldest first.",
        "input_schema": {
            "type": "object",
            "properties": {"kanji_id": {"type": "string"}},
            "required": ["kanji_id"],
        },
    },
]

LOG_MISTAKE_SCHEMA = {
    "name": "log_mistake",
    "description": "Logs a mistake for this attempt. Only call this if the attempt was NOT a correct, high-confidence match.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kanji_id": {"type": "string"},
            "error_type": {
                "type": "string",
                "enum": ["wrong_character", "low_confidence"],
            },
        },
        "required": ["kanji_id", "error_type"],
    },
}

SYSTEM_PROMPT = """You are TutorAgent, giving feedback on a user's handwritten kanji
practice in a Japanese learning app called Nihongo.

You'll be told: the target kanji, what a vision model recognized from
the user's drawing, its confidence, and whether it matched the target.

Use get_kanji_data and get_user_kanji_history to understand the
character and the user's past attempts at it, so your feedback can
reference real history (e.g. "you've mixed this up before") instead of
being generic.

If a log_mistake tool is available to you AND the attempt was NOT a
correct, high-confidence match, call it with error_type
"wrong_character" (recognized a different character, or none at all)
or "low_confidence" (right character, but low confidence -- likely a
messy or incomplete drawing). Do not log a mistake for a correct,
high-confidence attempt. If no log_mistake tool is offered to you,
this is just free practice -- give feedback without logging anything.

Keep feedback to exactly ONE short sentence -- this renders on a small
mobile card, not a paragraph.
- Correct: brief, simple praise ("Nice work!", "Perfect!") -- don't
  restate the meaning/reading/stroke count unless the history genuinely
  makes it worth a quick callout (e.g. a first success after repeated
  mistakes).
- Incorrect: ONE concrete, actionable tip about what likely went wrong
  (e.g. "Try making the top stroke longer" or "That looks like 本, not
  木 -- keep the bottom clear"), not a lecture.

Once you're done, respond with ONLY a JSON object (no markdown fences,
no prose):
{"feedback": "exactly one short sentence"}
"""


def _execute_tool(db: Session, user_id: str, kanji_id: str, tool_name: str, tool_input: dict) -> dict:
    # tool_input.get("kanji_id", kanji_id): the model is given kanji_id
    # in its prompt and should pass it back, but fall back to the
    # actual target id if it ever omits it.
    if tool_name == "get_kanji_data":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.get_kanji_data(db, tool_input.get("kanji_id", kanji_id)),
            fallback={
                "character": None,
                "meaning": None,
                "stroke_count": None,
                "onyomi": [],
                "kunyomi": [],
            },
        )
    elif tool_name == "get_user_kanji_history":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.get_user_kanji_history(
                db, user_id, tool_input.get("kanji_id", kanji_id)
            ),
            # fail closed: if history can't be read, the agent gives
            # generic (not history-aware) feedback instead of erroring out
            fallback={"past_mistake_count": 0, "past_error_types": []},
        )
    elif tool_name == "log_mistake":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.log_mistake(
                db, user_id, tool_input.get("kanji_id", kanji_id), tool_input["error_type"]
            ),
            fallback={"logged": False},
        )
    else:
        return {"error": f"unknown tool: {tool_name}"}


def run_tutor_agent(
    db: Session,
    user_id: str,
    kanji_id: str,
    target_character: str,
    recognized_character: Optional[str],
    confidence: float,
    is_correct: bool,
    mode: str = "practice",
) -> dict:
    """
    mode="practice" (Learn > Writing, Day 8/9): mistakes are NOT logged.
    Early, exploratory attempts shouldn't flood get_weak_areas /
    UserMistake before the user has even decided to review this
    character -- that would overwhelm the weak-areas signal with noise
    from the learning phase.

    mode="drill" (Day 10, once built): mistakes ARE logged, since a
    Drill attempt is against an item the user explicitly opted into
    spaced review for -- that's exactly the signal get_weak_areas
    should reflect.
    """
    provider = get_llm_provider()
    provider.start_conversation(
        system=SYSTEM_PROMPT,
        user_message=(
            f"Target kanji: {target_character} (kanji_id={kanji_id}). "
            f"Vision model recognized: {recognized_character!r} with confidence {confidence:.2f}. "
            f"Matched target: {is_correct}."
        ),
    )

    tool_schemas = BASE_TOOL_SCHEMAS + ([LOG_MISTAKE_SCHEMA] if mode == "drill" else [])

    tool_call_log = []
    MAX_ROUNDS = 5

    for _ in range(MAX_ROUNDS):
        turn = provider.step(tool_schemas)

        if turn.is_final:
            parsed = _parse_feedback(turn.text)
            return {"feedback": parsed.get("feedback", turn.text.strip()), "tool_calls": tool_call_log}

        results = []
        for call in turn.tool_calls:
            output = _execute_tool(db, user_id, kanji_id, call.name, call.input)
            tool_call_log.append({"tool_name": call.name, "input": call.input, "result": output})
            results.append(ToolResult(id=call.id, name=call.name, output=output))

        provider.submit_tool_results(results)

    raise RuntimeError(f"TutorAgent exceeded {MAX_ROUNDS} tool-use rounds without a final answer")


def _parse_feedback(text: str) -> dict:
    cleaned = text.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or start > end:
        return {"feedback": cleaned}
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {"feedback": cleaned}
