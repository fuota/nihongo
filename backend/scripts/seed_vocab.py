"""
Seed VocabCard rows from Jisho's public JLPT tag search
(https://jisho.org/api/v1/search/words?keyword=%23jlpt-n5).

Jisho doesn't return example sentences, so this script leaves
example_sentence null -- add those separately once the word list
itself is confirmed good.

Usage:
    uv run python scripts/seed_vocab.py --level N5 --count 100
"""

import argparse
import time

import requests

from app.database import SessionLocal
from app import models

JISHO_SEARCH_URL = "https://jisho.org/api/v1/search/words"
PAGE_SIZE = 20


def fetch_jlpt_words(level: str, count: int) -> list[dict]:
    """Paginates Jisho's tag search until `count` unique words are collected."""
    tag = f"jlpt-{level.lower()}"
    words = []
    seen = set()
    page = 1

    while len(words) < count:
        response = requests.get(
            JISHO_SEARCH_URL,
            params={"keyword": f"#{tag}", "page": page},
            headers={"User-Agent": "nihongo-app-seed-script/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json().get("data", [])

        if not data:
            break  # ran out of pages before hitting `count`

        for entry in data:
            jp = entry["japanese"][0]
            word = jp.get("word") or jp["reading"]
            reading = jp["reading"]

            key = (word, reading)
            if key in seen:
                continue
            seen.add(key)

            meanings = entry["senses"][0]["english_definitions"][:2]

            words.append(
                {
                    "kanji": word if word != reading else None,
                    "reading": reading,
                    "meaning": "; ".join(meanings),
                }
            )
            if len(words) >= count:
                break

        page += 1
        time.sleep(0.3)  # be polite to the free public API

    return words


def seed(level: str, count: int) -> None:
    words = fetch_jlpt_words(level, count)
    db = SessionLocal()

    inserted = 0
    skipped = 0
    try:
        for word in words:
            exists = (
                db.query(models.VocabCard)
                .filter(
                    models.VocabCard.reading == word["reading"],
                    models.VocabCard.kanji == word["kanji"],
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(
                models.VocabCard(
                    kanji=word["kanji"],
                    reading=word["reading"],
                    meaning=word["meaning"],
                    example_sentence=None,
                    jlpt_level=level.upper(),
                    source="seeded",
                )
            )
            inserted += 1

        db.commit()
    finally:
        db.close()

    print(f"Fetched {len(words)} words from Jisho (#{level.lower()}-tagged).")
    print(f"Inserted {inserted} new VocabCard rows, skipped {skipped} already present.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", default="N5")
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()

    seed(args.level, args.count)
