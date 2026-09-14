"""
Seed WritingCharacter rows (kanji), sourced from scripts/data/n5_kanji_topics.json
(the list of characters to seed, grouped by topic -- numbers, time/calendar,
directions, etc, for later module-building) with per-character detail
(stroke count, meanings, on/kun readings) pulled from kanjiapi.dev, a
free public API.

kanjiapi.dev's own "jlpt-5" tier only has 79 characters. Characters
listed in scripts/data/n4_additions.json are seeded as jlpt_level=N4
instead of N5 -- these are unambiguously N5-equivalent content in
every standard textbook (e.g. 兄/姉/弟/妹), but this API's older,
coarser tier labeling files them one tier up, so they're labeled
honestly rather than force-relabeled.

"Compounds" per the build plan means: link each kanji to the vocab
words we've already seeded that contain it, via VocabCharacterLink --
there's no separate compounds column, the link table is the compounds
list.

stroke_paths (SVG stroke-order animation data) is NOT provided by
this API -- that's KanjiVG's job (Day 6). Seeded as an empty list here
and filled in properly later.

Usage:
    uv run python scripts/seed_kanji.py
"""

import json
import time
from pathlib import Path

import requests

from app.database import SessionLocal
from app import models

KANJI_DETAIL_URL = "https://kanjiapi.dev/v1/kanji/{kanji}"
TOPICS_PATH = Path(__file__).parent / "data" / "n5_kanji_topics.json"
N4_ADDITIONS_PATH = Path(__file__).parent / "data" / "n4_additions.json"


def seed() -> None:
    topics = json.loads(TOPICS_PATH.read_text())
    topic_by_char = {char: topic for topic, chars in topics.items() for char in chars}
    n4_chars = set(json.loads(N4_ADDITIONS_PATH.read_text()))

    db = SessionLocal()
    inserted = 0
    skipped = 0
    linked = 0
    try:
        for char, topic in topic_by_char.items():
            level = "N4" if char in n4_chars else "N5"

            character_row = (
                db.query(models.WritingCharacter)
                .filter(
                    models.WritingCharacter.character == char,
                    models.WritingCharacter.character_type == "kanji",
                )
                .first()
            )

            if character_row is not None:
                skipped += 1
            else:
                detail_response = requests.get(
                    KANJI_DETAIL_URL.format(kanji=char),
                    headers={"User-Agent": "nihongo-app-seed-script/1.0"},
                    timeout=10,
                )
                detail_response.raise_for_status()
                detail = detail_response.json()

                character_row = models.WritingCharacter(
                    character=char,
                    character_type="kanji",
                    meaning="; ".join(detail.get("meanings", [])[:3]) or None,
                    onyomi=detail.get("on_readings", []),
                    kunyomi=detail.get("kun_readings", []),
                    stroke_count=detail["stroke_count"],
                    stroke_paths=[],  # populated later from KanjiVG (Day 6)
                    jlpt_level=level,
                    topic=topic,
                )
                db.add(character_row)
                db.flush()  # need character_row.id for linking below
                inserted += 1
                time.sleep(0.2)  # be polite to the free public API

            # Link to any already-seeded vocab containing this kanji
            # ("compounds") -- VocabCard.kanji is nullable, and .contains()
            # against NULL is falsy in SQL, so kana-only words are skipped.
            for vocab in db.query(models.VocabCard).filter(
                models.VocabCard.kanji.contains(char)
            ):
                link_exists = (
                    db.query(models.VocabCharacterLink)
                    .filter(
                        models.VocabCharacterLink.vocab_card_id == vocab.id,
                        models.VocabCharacterLink.character_id == character_row.id,
                    )
                    .first()
                )
                if link_exists is None:
                    db.add(
                        models.VocabCharacterLink(
                            vocab_card_id=vocab.id, character_id=character_row.id
                        )
                    )
                    linked += 1

        db.commit()
    finally:
        db.close()

    print(f"{len(topic_by_char)} kanji across {len(topics)} topics in the source list.")
    print(f"Inserted {inserted} new WritingCharacter rows, skipped {skipped} already present.")
    print(f"Created {linked} vocab-character compound links.")


if __name__ == "__main__":
    seed()
