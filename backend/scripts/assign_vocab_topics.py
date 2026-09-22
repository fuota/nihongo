"""
Assigns a `topic` to every N5/N4 VocabCard that doesn't have one yet.

Two passes, both idempotent (only touch rows where topic IS NULL):

1. Deterministic: if a word is linked (via VocabCharacterLink) to a kanji
   that already has a topic from the Day 2 kanji seeding, inherit it.
2. LLM: everything left over gets classified in small batches by the
   configured LLM provider (LLM_PROVIDER env var) into one of the same
   10 topics used for kanji, or "other" if nothing fits.

Usage (from backend/): PYTHONPATH=. .venv/bin/python scripts/assign_vocab_topics.py
"""
import json
from collections import Counter
from pathlib import Path

from app.database import SessionLocal
from app import models
from app.agents.llm import get_llm_provider

TOPICS_FILE = Path(__file__).parent / "data" / "n5_kanji_topics.json"
TOPICS = list(json.loads(TOPICS_FILE.read_text()).keys())
ALLOWED_TOPICS = TOPICS + ["other"]

BATCH_SIZE = 40

SYSTEM_PROMPT = f"""You are classifying Japanese JLPT vocabulary words into topics
for a language-learning app, so words can be browsed by theme.

Allowed topics (use exactly these strings, nothing else): {ALLOWED_TOPICS}

Pick the single best-fitting topic per word. If genuinely nothing fits,
use "other". Respond with ONLY a JSON array (no markdown fences, no prose),
one object per word, in this exact shape:
[{{"index": 0, "topic": "..."}}, {{"index": 1, "topic": "..."}}]
"""


def assign_from_kanji_links(db) -> int:
    cards = (
        db.query(models.VocabCard)
        .filter(models.VocabCard.topic.is_(None))
        .all()
    )

    assigned = 0
    for card in cards:
        topics = [
            link.character.topic
            for link in card.character_links
            if link.character.topic is not None
        ]
        if not topics:
            continue
        card.topic = Counter(topics).most_common(1)[0][0]
        assigned += 1

    db.commit()
    return assigned


def assign_via_llm(db) -> tuple[int, int]:
    cards = (
        db.query(models.VocabCard)
        .filter(models.VocabCard.topic.is_(None))
        .all()
    )

    assigned = 0
    failed = 0

    for batch_start in range(0, len(cards), BATCH_SIZE):
        batch = cards[batch_start : batch_start + BATCH_SIZE]
        word_list = "\n".join(
            f"{i}. kanji={card.kanji!r} reading={card.reading!r} meaning={card.meaning!r}"
            for i, card in enumerate(batch)
        )

        provider = get_llm_provider()
        provider.start_conversation(system=SYSTEM_PROMPT, user_message=word_list)
        turn = provider.step(tools=[])

        try:
            cleaned = turn.text.strip()
            start, end = cleaned.find("["), cleaned.rfind("]")
            results = json.loads(cleaned[start : end + 1])
        except (ValueError, json.JSONDecodeError):
            print(f"  batch {batch_start}: could not parse LLM response, skipping")
            failed += len(batch)
            continue

        by_index = {r["index"]: r["topic"] for r in results}
        for i, card in enumerate(batch):
            topic = by_index.get(i)
            if topic not in ALLOWED_TOPICS:
                failed += 1
                continue
            card.topic = topic
            assigned += 1

        db.commit()
        print(f"  batch {batch_start}: assigned {len(batch) - failed} so far")

    return assigned, failed


def main():
    db = SessionLocal()

    kanji_linked = assign_from_kanji_links(db)
    print(f"Assigned via kanji-link inheritance: {kanji_linked}")

    llm_assigned, llm_failed = assign_via_llm(db)
    print(f"Assigned via LLM classification: {llm_assigned} (failed: {llm_failed})")

    remaining = (
        db.query(models.VocabCard).filter(models.VocabCard.topic.is_(None)).count()
    )
    print(f"Still untagged: {remaining}")


if __name__ == "__main__":
    main()
