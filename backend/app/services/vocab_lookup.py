"""
get_or_fetch_word: the hybrid DB/API vocab lookup path.

1. Check VocabCard first (by kanji or reading match).
2. If not found, look the word up on Jisho's public API.
3. On success, persist it as a new VocabCard with source='api_fetched'
   so it's available locally next time (and so Tool 3/SRS always has
   something to schedule once a word has been looked up once).
4. On any failure (network error, bad response, word not found),
   return a typed "unavailable" result -- callers (including an LLM
   agent) should treat this as "no data", never invent a definition.
"""

from typing import Optional

import requests
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models

JISHO_SEARCH_URL = "https://jisho.org/api/v1/search/words"


def _card_to_result(card: models.VocabCard, status: str) -> dict:
    return {
        "status": status,
        "id": card.id,
        "kanji": card.kanji,
        "reading": card.reading,
        "meaning": card.meaning,
        "example_sentence": card.example_sentence,
        "jlpt_level": card.jlpt_level,
        "source": card.source,
    }


def _unavailable(word: str, reason: str) -> dict:
    return {"status": "unavailable", "word": word, "reason": reason}


def _extract_jlpt_level(entry: dict) -> Optional[str]:
    tags = entry.get("jlpt") or []
    if not tags:
        return None
    # tags look like "jlpt-n4" -> "N4"
    return tags[0].split("-")[-1].upper()


def get_or_fetch_word(db: Session, word: str) -> dict:
    existing = (
        db.query(models.VocabCard)
        .filter(or_(models.VocabCard.kanji == word, models.VocabCard.reading == word))
        .first()
    )
    if existing is not None:
        return _card_to_result(existing, status="found_in_db")

    try:
        response = requests.get(
            JISHO_SEARCH_URL,
            params={"keyword": word},
            headers={"User-Agent": "nihongo-app/1.0"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
    except requests.RequestException as e:
        return _unavailable(word, f"Jisho API request failed: {e}")
    except ValueError as e:
        return _unavailable(word, f"Jisho API returned invalid JSON: {e}")

    if not data:
        return _unavailable(word, "word not found on Jisho")

    entry = data[0]
    jp = entry["japanese"][0]
    kanji = jp.get("word")
    reading = jp["reading"]
    if kanji == reading:
        kanji = None

    meanings = entry.get("senses", [{}])[0].get("english_definitions", [])
    if not meanings:
        return _unavailable(word, "Jisho result had no definitions")

    new_card = models.VocabCard(
        kanji=kanji,
        reading=reading,
        meaning="; ".join(meanings[:2]),
        example_sentence=None,
        jlpt_level=_extract_jlpt_level(entry),
        source="api_fetched",
    )
    db.add(new_card)
    db.commit()
    db.refresh(new_card)

    return _card_to_result(new_card, status="fetched_from_api")
