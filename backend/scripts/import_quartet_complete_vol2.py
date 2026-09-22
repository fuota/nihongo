"""
Imports Volume 2 (Lessons 7-12) VocabCard rows from the Quartet
Intermediate Complete Edition Anki deck
(scripts/data/quartet_intermediate_complete.apkg -- a combined Volume
1+2 deck, note type "Japanese Quartet" with fields
Expression | Reading | Meaning | Notes).

Volume 1 (Lessons 1-6, N3) was already imported separately from the
dedicated Quartet_1_Vocab.apkg deck (see import_quartet_apkg.py) --
this script only pulls Volume 2 (Lessons 7-12, N2), identified via
Anki tags rather than a lesson field: each note carries one or more
"L##-..." tags (e.g. "L09-漢字", "L09-読1") for the lesson(s) it
appears in. A word's LOWEST tagged lesson number is treated as where
it's first introduced, so a word recurring in both volumes is only
ever imported once, at its true introduction level.

Notes lacking any "L##-" tag (~530 of 3034) are supplementary content
this deck bundles in -- "上級C#" advanced bonus columns, and
"漢字C##"/"読S##" kanji/reading supplements that don't map cleanly to
a single lesson -- and are intentionally left out of this Volume 2
import; only clearly-tagged L07-L12 material is in scope here.

Field layout matches Minna no Nihongo's, not the reversed layout of
the standalone Quartet_1_Vocab.apkg: Expression holds the kanji/kana
surface form, Reading holds the same text with inline per-kanji
furigana (e.g. "監[かん] 督[とく]"), and Meaning is English. There's a
4th "Notes" field (usage notes, antonyms, "e.g." examples) present on
~9% of rows -- folded into the meaning as a suffix note rather than
forced into example_sentence, since most of it isn't sentence-shaped
(antonym cross-refs, する-verb conversion notes, etc).

Usage (from backend/): PYTHONPATH=. uv run python scripts/import_quartet_complete_vol2.py
"""

import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app.database import SessionLocal
from app import models

APKG_PATH = Path(__file__).parent / "data" / "quartet_intermediate_complete.apkg"
JLPT_LEVEL = "N2"
VOLUME_2_LESSON_RANGE = range(7, 13)

LESSON_TAG_RE = re.compile(r"L(\d{2})-")
FURIGANA_RE = re.compile(r"[^\s\[\]]+\[([^\]]+)\]")
CJK_RE = re.compile(r"[一-鿿々]")  # kanji + 々

HTML_BREAK_RE = re.compile(r"<br\s*/?>|</p>|<p>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(text: str) -> str:
    """Replaces 漢字[かな] with かな and strips whitespace. This deck has
    neither the fullwidth optional-word brackets nor the usage-hint
    brackets the other two decks used, so no bracket-stripping needed."""
    cleaned = FURIGANA_RE.sub(lambda m: m.group(1), text)
    return re.sub(r"\s+", "", cleaned)


SEPARATOR_PLACEHOLDER = "\x00SEP\x00"
JP_CHAR = "぀-ヿ一-鿿ー々"
# A space between two Japanese characters is just a leftover token
# boundary from how the deck wrote bracketed furigana side by side
# (e.g. "意[い] 味[み]が" -> "意 味が" once brackets are stripped) and
# needs to disappear; a space next to Latin text (cf., e.g., する：)
# is a real word gap and should survive as a single space.
JP_GAP_RE = re.compile(rf"(?<=[{JP_CHAR}])[ 　]+(?=[{JP_CHAR}])")


def clean_english_field(text: str) -> str:
    """Cleans an English-ish field (Meaning or Notes) that may embed
    <br>/<p> breaks and 漢字[ふりがな]-annotated Japanese fragments
    (e.g. a meaning distinguishing two readings of the same kanji, or a
    Notes antonym/example). Keeps kanji (not reading) for readability
    and turns <br>/<p> into a separator instead of dropping them
    silently, which would otherwise run two clauses together."""
    text = HTML_BREAK_RE.sub(SEPARATOR_PLACEHOLDER, text)
    text = HTML_TAG_RE.sub("", text)
    # keep kanji form: substitute "X[Y]" -> "X" (drop the furigana, keep the kanji)
    text = re.sub(r"([^\s\[\]]+)\[[^\]]+\]", lambda m: m.group(1), text)
    text = JP_GAP_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(f"\\s*({SEPARATOR_PLACEHOLDER})\\s*", "; ", text)
    return text.strip("; ")


def load_volume2_notes() -> list[tuple[str, str, str, str]]:
    with zipfile.ZipFile(APKG_PATH) as zf, tempfile.TemporaryDirectory() as tmp:
        # This is a newer-format .apkg: the real data lives in
        # collection.anki21, not the legacy collection.anki2 stub kept
        # alongside it for backward compatibility.
        db_path = Path(tmp) / "collection.anki21"
        db_path.write_bytes(zf.read("collection.anki21"))
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT tags, flds FROM notes").fetchall()
        finally:
            conn.close()

    notes = []
    for tags, flds in rows:
        lessons = [int(n) for n in LESSON_TAG_RE.findall(tags)]
        if not lessons or min(lessons) not in VOLUME_2_LESSON_RANGE:
            continue
        parts = flds.split("\x1f")
        if len(parts) != 4:
            continue
        notes.append(tuple(parts))
    return notes


def main() -> None:
    notes = load_volume2_notes()
    print(f"Loaded {len(notes)} Volume 2 (Lessons 7-12) notes from {APKG_PATH.name}")

    db = SessionLocal()
    inserted = 0
    skipped_duplicate = 0
    seen_in_batch: set[tuple[str | None, str]] = set()

    try:
        for expression, reading_field, meaning_raw, notes_field in notes:
            expr_clean = clean_text(expression)
            reading_clean = clean_text(reading_field)

            if CJK_RE.search(expr_clean):
                kanji = expr_clean
                reading = reading_clean
            else:
                kanji = None
                reading = expr_clean

            meaning = clean_english_field(meaning_raw)
            note = clean_english_field(notes_field) if notes_field.strip() else ""
            if note:
                meaning = f"{meaning} (note: {note})"

            key = (kanji, reading)
            if key in seen_in_batch:
                skipped_duplicate += 1
                continue

            exists = (
                db.query(models.VocabCard)
                .filter(
                    models.VocabCard.reading == reading,
                    models.VocabCard.kanji == kanji,
                )
                .first()
            )
            if exists:
                skipped_duplicate += 1
                continue
            seen_in_batch.add(key)

            db.add(
                models.VocabCard(
                    kanji=kanji,
                    reading=reading,
                    meaning=meaning,
                    example_sentence=None,
                    jlpt_level=JLPT_LEVEL,
                    source="textbook",
                    topic=None,
                )
            )
            inserted += 1

        db.commit()
    finally:
        db.close()

    print(f"Inserted {inserted} new VocabCard rows at {JLPT_LEVEL}.")
    print(f"Skipped {skipped_duplicate} already-present (reading+kanji match).")


if __name__ == "__main__":
    main()
