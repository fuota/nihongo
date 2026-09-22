"""
ReadingGeneratorAgent -- powers Learn > Reading (Day 11).

Runs the same real tool-use loop pattern as SessionBuilderAgent: the
model calls tools to learn what the user actually knows, reasons about
how to constrain a passage to that, then generates the passage itself
in the same turn (no separate "generation" API call -- the tool loop's
final answer IS the passage, same as SessionBuilderAgent's final answer
is the session plan).

Content words (nouns, verbs, adjectives) and any grammar pattern used
must come from the user's known lists -- but basic structural particles
(は, が, を, に, で, と, か, ...) and the copula (です/だ) are always
allowed, since a passage literally cannot be built without them and
they aren't "content" the user is being taught here.
"""

import json

from sqlalchemy.orm import Session

from app.agents import tools as agent_tools
from app.agents.llm import ToolResult, get_llm_provider
from app.utils.retry import call_with_retry

AGENT_NAME = "ReadingGeneratorAgent"

# Used only as a call_with_retry fallback if get_known_vocab/get_known_grammar
# themselves fail (e.g. a DB hiccup) -- lets the agent still produce a
# passage instead of failing the whole request, per the Day 11 plan.
FALLBACK_VOCAB = [
    {"kanji": "食べる", "reading": "たべる", "meaning": "to eat"},
    {"kanji": "飲む", "reading": "のむ", "meaning": "to drink"},
    {"kanji": "行く", "reading": "いく", "meaning": "to go"},
    {"kanji": "学校", "reading": "がっこう", "meaning": "school"},
    {"kanji": "友達", "reading": "ともだち", "meaning": "friend"},
    {"kanji": "今日", "reading": "きょう", "meaning": "today"},
    {"kanji": "本", "reading": "ほん", "meaning": "book"},
    {"kanji": "水", "reading": "みず", "meaning": "water"},
]
FALLBACK_GRAMMAR = [
    {"pattern": "〜ます", "explanation": "Polite present/future tense."},
    {"pattern": "〜でした", "explanation": "Polite past tense of です."},
]

TOOL_SCHEMAS = [
    {
        "name": "get_known_vocab",
        "description": "Returns vocab words this user has explicitly marked Learnt.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "get_known_grammar",
        "description": "Returns grammar patterns this user has explicitly marked Learnt.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
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

SYSTEM_PROMPT = """You are ReadingGeneratorAgent, generating a short Japanese
reading passage for a language-learning app called Nihongo.

Call get_known_vocab, get_known_grammar, and get_user_profile to see
exactly which words and grammar patterns this specific user already
knows, and their JLPT level.

Then write a 4-6 sentence Japanese passage:
- Every content word (noun, verb, adjective) MUST come from the known
  vocab list. Do not use any vocabulary the user hasn't learnt.
- Any grammar pattern you use beyond basic sentence structure MUST come
  from the known grammar list.
- Basic particles (は, が, を, に, で, と, か, も, の) and です/だ and
  their conjugations are always allowed -- a sentence can't be built
  without them, and they aren't being tested here.
- Keep it simple and coherent: a short story or description, not a
  disconnected list of sentences just to use vocabulary.
- Calibrate length/complexity to how much the user actually knows (a
  user with only 10-15 known words gets a shorter, simpler passage than
  one with 100+).

Then write exactly 3 multiple-choice comprehension questions about the
passage, each answerable using ONLY the passage itself (not outside
knowledge). Each question has exactly 4 options, one correct.

Respond with ONLY a JSON object (no markdown fences, no prose):
{
  "reasoning": "one sentence on how you calibrated this passage",
  "passage": "the full Japanese passage as plain text",
  "passage_furigana": [{"surface": "...", "reading": "..." or null}, ...],
  "questions": [
    {"question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "..."}
  ]
}

passage_furigana MUST be an ordered list of chunks whose "surface"
fields concatenate to reconstruct "passage" EXACTLY, character for
character (including all punctuation and spaces). A kanji-bearing word
(with its okurigana) is one chunk with "reading" = its hiragana
reading; a chunk with no kanji (particles, punctuation, kana-only
words) has "reading": null.
"""


def _execute_tool(db: Session, user_id: str, tool_name: str, tool_input: dict) -> dict:
    if tool_name == "get_known_vocab":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.get_known_vocab(db, user_id),
            fallback={"count": len(FALLBACK_VOCAB), "items": FALLBACK_VOCAB},
        )
    elif tool_name == "get_known_grammar":
        return call_with_retry(
            db,
            user_id=user_id,
            agent_name=AGENT_NAME,
            tool_name=tool_name,
            fn=lambda: agent_tools.get_known_grammar(db, user_id),
            fallback={"count": len(FALLBACK_GRAMMAR), "items": FALLBACK_GRAMMAR},
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


def run_reading_generator_agent(db: Session, user_id: str) -> dict:
    provider = get_llm_provider()
    provider.start_conversation(
        system=SYSTEM_PROMPT,
        user_message=f"Generate a reading passage for user_id={user_id}.",
    )

    tool_call_log = []
    MAX_ROUNDS = 6

    for _ in range(MAX_ROUNDS):
        turn = provider.step(TOOL_SCHEMAS)

        if turn.is_final:
            plan = _parse_plan(turn.text)
            return {"plan": plan, "tool_calls": tool_call_log}

        results = []
        for call in turn.tool_calls:
            output = _execute_tool(db, user_id, call.name, call.input)
            tool_call_log.append({"tool_name": call.name, "input": call.input, "result": output})
            results.append(ToolResult(id=call.id, name=call.name, output=output))

        provider.submit_tool_results(results)

    raise RuntimeError(f"ReadingGeneratorAgent exceeded {MAX_ROUNDS} tool-use rounds without a final answer")


def _parse_plan(text: str) -> dict:
    cleaned = text.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or start > end:
        raise ValueError(f"ReadingGeneratorAgent returned non-JSON output: {text!r}")
    return json.loads(cleaned[start : end + 1])
