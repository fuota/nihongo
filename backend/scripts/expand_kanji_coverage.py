"""
Expands WritingCharacter coverage beyond the original curated 100
(scripts/seed_kanji.py) to every kanji actually used in seeded N5/N4
vocab. The original 100 were hand-grouped into topics for module
browsing; that browsing UI doesn't exist in the current IA (kanji is
only reached via a word's "Practice" button or the Writing screen), so
these get topic=None -- there's nothing that reads it for them.

For each missing character: fetch meaning/readings/stroke_count from
kanjiapi.dev, stroke_paths from KanjiVG (same as seed_kanji.py /
seed_kanji_strokes.py), and link to every vocab word that contains it
(VocabCharacterLink). jlpt_level is assigned from our own vocab data
(N5 if the character appears in any seeded N5 word, else N4) rather
than kanjiapi.dev's coarser tiers, since our own labeling is already
the source of truth the rest of the app uses.

Idempotent: only processes characters not already in WritingCharacter.

Usage (from backend/): PYTHONPATH=. .venv/bin/python scripts/expand_kanji_coverage.py
"""
import re
import time

import requests

from app.database import SessionLocal
from app import models

KANJI_DETAIL_URL = "https://kanjiapi.dev/v1/kanji/{kanji}"
KANJIVG_URL = "https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/{codepoint}.svg"
STROKE_PATH_RE = re.compile(r'<path\b[^>]*\bd="([^"]+)"')

CJK_RANGE = ("一", "鿿")


def codepoint_for(character: str) -> str:
    return format(ord(character), "05x")


def fetch_stroke_paths(character: str) -> list:
    url = KANJIVG_URL.format(codepoint=codepoint_for(character))
    response = requests.get(url, timeout=10)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return STROKE_PATH_RE.findall(response.text)


def find_missing_characters(db) -> dict:
    """Returns {character: "N5" | "N4"} for every kanji used in N5/N4
    vocab that isn't in WritingCharacter yet."""
    cards = (
        db.query(models.VocabCard)
        .filter(
            models.VocabCard.kanji.isnot(None),
            models.VocabCard.jlpt_level.in_(["N5", "N4"]),
        )
        .all()
    )

    level_by_char = {}
    for card in cards:
        for ch in card.kanji:
            if not (CJK_RANGE[0] <= ch <= CJK_RANGE[1]):
                continue
            if card.jlpt_level == "N5" or ch not in level_by_char:
                level_by_char[ch] = card.jlpt_level
            elif level_by_char[ch] != "N5":
                level_by_char[ch] = card.jlpt_level

    existing = {c.character for c in db.query(models.WritingCharacter).all()}
    return {ch: level for ch, level in level_by_char.items() if ch not in existing}


def link_compounds(db, character_row) -> int:
    linked = 0
    for vocab in db.query(models.VocabCard).filter(
        models.VocabCard.kanji.contains(character_row.character)
    ):
        exists = (
            db.query(models.VocabCharacterLink)
            .filter(
                models.VocabCharacterLink.vocab_card_id == vocab.id,
                models.VocabCharacterLink.character_id == character_row.id,
            )
            .first()
        )
        if exists is None:
            db.add(
                models.VocabCharacterLink(vocab_card_id=vocab.id, character_id=character_row.id)
            )
            linked += 1
    return linked


def main():
    db = SessionLocal()
    missing = find_missing_characters(db)
    print(f"Expanding coverage for {len(missing)} characters")

    inserted = 0
    linked_total = 0
    no_stroke_data = []
    failed = []

    for i, (char, level) in enumerate(missing.items()):
        try:
            detail_response = requests.get(
                KANJI_DETAIL_URL.format(kanji=char),
                headers={"User-Agent": "nihongo-app-seed-script/1.0"},
                timeout=10,
            )
            detail_response.raise_for_status()
            detail = detail_response.json()

            stroke_paths = fetch_stroke_paths(char)
            if not stroke_paths:
                no_stroke_data.append(char)

            character_row = models.WritingCharacter(
                character=char,
                character_type="kanji",
                meaning="; ".join(detail.get("meanings", [])[:3]) or None,
                onyomi=detail.get("on_readings", []),
                kunyomi=detail.get("kun_readings", []),
                stroke_count=detail.get("stroke_count") or len(stroke_paths) or 1,
                stroke_paths=stroke_paths,
                jlpt_level=level,
                topic=None,
            )
            db.add(character_row)
            db.flush()
            linked_total += link_compounds(db, character_row)
            db.commit()
            inserted += 1
        except requests.RequestException as e:
            print(f"  {char}: failed ({e}), skipping")
            failed.append(char)
            db.rollback()
            continue

        time.sleep(0.15)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(missing)} processed")

    print(f"Inserted {inserted} characters, {linked_total} compound links.")
    if no_stroke_data:
        print(f"No KanjiVG stroke data for {len(no_stroke_data)}: {''.join(no_stroke_data)}")
    if failed:
        print(f"Failed (kanjiapi.dev error) for {len(failed)}: {''.join(failed)}")


if __name__ == "__main__":
    main()
