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

_JLPT_RANK = {"n5": 0, "n4": 1, "n3": 2, "n2": 3, "n1": 4}


def _pick_best_entry(data: list) -> dict:
    """
    Jisho's own ranking doesn't track word commonality for bare-kana
    queries -- e.g. searching "ここ" ranks 個々 ("individual", N1) above
    此処 ("here", N5). Since this app is JLPT-focused, prefer whichever
    result has the easiest JLPT tag (most likely the everyday word a
    learner actually meant); entries with no JLPT tag sort last, and
    Python's sort is stable so Jisho's original order still breaks ties.
    """

    def rank(entry: dict) -> tuple:
        tags = entry.get("jlpt") or []
        levels = [_JLPT_RANK[t.split("-")[-1]] for t in tags if t.split("-")[-1] in _JLPT_RANK]
        return (0, min(levels)) if levels else (1, 99)

    return sorted(data, key=rank)[0]


def _card_to_result(db: Session, card: models.VocabCard, status: str) -> dict:
    links = (
        db.query(models.WritingCharacter)
        .join(models.VocabCharacterLink, models.VocabCharacterLink.character_id == models.WritingCharacter.id)
        .filter(models.VocabCharacterLink.vocab_card_id == card.id)
        .all()
    )

    return {
        "status": status,
        "id": card.id,
        "kanji": card.kanji,
        "reading": card.reading,
        "meaning": card.meaning,
        "example_sentence": card.example_sentence,
        "example_sentence_en": card.example_sentence_en,
        "example_sentence_furigana": card.example_sentence_furigana,
        "jlpt_level": card.jlpt_level,
        "topic": card.topic,
        "source": card.source,
        "characters": [{"id": c.id, "character": c.character} for c in links],
    }


def _unavailable(word: str, reason: str) -> dict:
    return {"status": "unavailable", "word": word, "reason": reason}


def _extract_jlpt_level(entry: dict) -> Optional[str]:
    tags = entry.get("jlpt") or []
    levels = [t.split("-")[-1] for t in tags if t.split("-")[-1] in _JLPT_RANK]
    if not levels:
        return None
    # A word can carry multiple tags (e.g. "here" is both n5 and n3
    # depending on the dictionary source) -- report the easiest one.
    return min(levels, key=lambda l: _JLPT_RANK[l]).upper()


def get_or_fetch_word(db: Session, word: str) -> dict:
    existing = (
        db.query(models.VocabCard)
        .filter(or_(models.VocabCard.kanji == word, models.VocabCard.reading == word))
        .first()
    )
    if existing is not None:
        return _card_to_result(db, existing, status="found_in_db")

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

    entry = _pick_best_entry(data)
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

    return _card_to_result(db, new_card, status="fetched_from_api")
