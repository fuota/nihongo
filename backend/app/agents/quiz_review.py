"""
QuizReviewAgent -- on-demand "AI Detailed Feedback" for a completed
Drill run or Reading comprehension check.

Formerly DrillReviewAgent, Drill-only. Renamed and generalized when
Reading grew the same "show me what I got wrong and why" need: the
transcript shape (question asked, user's answer, correct answer,
right/wrong) is identical for a Drill question and a Reading
comprehension question, so this is genuinely the same reasoning task,
not two similar-looking ones.

Needs no tool loop: by the time a user asks for detailed feedback, the
whole Q&A transcript is already known -- there's nothing left in the
database worth looking up mid-conversation. It's a single one-shot
call: hand the transcript to the model, get back a written review.
Deliberately on-demand (its own endpoint, not run automatically on
completion) -- an LLM call on every run whether or not the user reads
it would be wasted cost and latency most of the time.
"""

import json
from typing import List

from sqlalchemy.orm import Session

from app.agents.llm import get_llm_provider
from app.utils.retry import call_with_retry

AGENT_NAME = "QuizReviewAgent"

# Drill items are independent flashcard-style facts -- a quick "here's
# what you got right, here's what you got wrong and why" recap is all
# that's useful, since each item stands alone.
DRILL_SYSTEM_PROMPT = """You are QuizReviewAgent, giving a quick review of a
just-completed Drill session in a Japanese learning app called Nihongo.

You'll be given the full transcript: for each question, what was asked,
what the user answered, the correct answer, and whether they got it right.

Format, exactly:
1. One line listing what they got correct, e.g. "Correct: 寒い, 洋服".
   If nothing was correct, skip this line entirely.
2. If anything was incorrect, a line "Incorrect:" followed by each
   wrong item numbered on its own line: the item, then one short,
   specific reason the answer was wrong (not just restating the
   correct answer). One sentence per item, no more.
3. If everything was correct, skip step 2 and add one short line of
   genuine encouragement instead.

Rules:
- Never use an em dash ("—") or a double hyphen ("--") anywhere in the
  text. Use a comma, colon, or a new sentence instead.
- Be brief. No filler, no restating the question, no long explanations.
- Plain text only, no markdown (no #, no *, no backticks).

Respond with ONLY a JSON object (no markdown fences, no prose outside it):
{"review": "the full review text"}
"""

# Reading comprehension questions are all about ONE passage, so a
# right/wrong recap isn't as useful as a real answer key: the point is
# understanding the passage, not just knowing which answers were picked.
READING_SYSTEM_PROMPT = """You are QuizReviewAgent, giving an answer key for a
just-completed Reading comprehension check in a Japanese learning app
called Nihongo.

You'll be given the full transcript: for each question, what was asked,
what the user answered, the correct answer, and whether they got it right.

Format, exactly: one numbered line per question, in order, covering
ALL questions (not just the ones missed) -- a real answer key, not a
right/wrong recap:
1. [question]: one short, concrete sentence explaining why the correct
   answer is right, grounded in what the passage actually says.
Do NOT add a "Correct: ..." summary line, and do not skip questions
the user got right -- every question gets its own explanation line.

Rules:
- Never use an em dash ("—") or a double hyphen ("--") anywhere in the
  text. Use a comma, colon, or a new sentence instead.
- Be brief. One sentence per question, no filler, no restating the
  full question text back.
- Plain text only, no markdown (no #, no *, no backticks).

Respond with ONLY a JSON object (no markdown fences, no prose outside it):
{"review": "the full review text"}
"""


def run_quiz_review_agent(
    db: Session, user_id: str, items: List[dict], session_label: str = "practice"
) -> dict:
    """
    items: [{"content_type", "prompt", "user_answer", "correct_answer", "is_correct"}],
    already human-readable strings. This agent does no DB lookups of
    its own -- the caller hydrates from SessionItem (Drill) or the
    stored session payload (Reading) first.

    session_label: "Drill" or "Reading" -- selects the format (see the
    two prompts above) as well as labeling the transcript's intro line.
    """
    system_prompt = READING_SYSTEM_PROMPT if session_label.lower() == "reading" else DRILL_SYSTEM_PROMPT
    provider = get_llm_provider()

    transcript = "\n".join(
        f"{i + 1}. [{item['content_type']}] asked={item['prompt']!r} "
        f"user_answered={item['user_answer']!r} correct_answer={item['correct_answer']!r} "
        f"correct={item['is_correct']}"
        for i, item in enumerate(items)
    )

    def call():
        provider.start_conversation(
            system=system_prompt,
            user_message=f"{session_label} session transcript:\n{transcript}",
        )
        turn = provider.step([])
        return _parse_review(turn.text)

    return call_with_retry(
        db,
        user_id=user_id,
        agent_name=AGENT_NAME,
        tool_name="generate_review",
        fn=call,
        fallback={
            "review": "Nice work finishing this session! Detailed feedback isn't available right now. Try again in a bit."
        },
    )


def _parse_review(text: str) -> dict:
    cleaned = text.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or start > end:
        return {"review": cleaned}
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {"review": cleaned}
