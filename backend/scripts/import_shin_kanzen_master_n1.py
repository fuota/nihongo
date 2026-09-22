"""
Imports VocabCard rows from the Shin Kanzen Master Vocabulary JLPT N1
Anki deck (scripts/data/shin_kanzen_master_n1_vocab.apkg -- a single
flat deck, note type "Japanese ShinKanzenMasterVocabN1" with fields
Expression | Reading | Meaning | Notes). Every row is seeded at N1 --
there's no lesson/level structure to read instead (tags are just a
numeric item index, e.g. "0042").

Field layout and conventions match the Quartet Intermediate Complete
Edition deck (see import_quartet_complete_vol2.py): Expression holds
the kanji/kana surface form, Reading holds the same text with inline
per-kanji furigana (e.g. "几[き] 帳[ちょう] 面[めん]"), Meaning is
English, and the 4th "Notes" field (usage examples, cf. cross-refs) is
populated on ~3% of rows and folded into the meaning as a suffix note.

Usage (from backend/): PYTHONPATH=. uv run python scripts/import_shin_kanzen_master_n1.py
"""

import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app.database import SessionLocal
from app import models

APKG_PATH = Path(__file__).parent / "data" / "shin_kanzen_master_n1_vocab.apkg"
JLPT_LEVEL = "N1"

FURIGANA_RE = re.compile(r"[^\s\[\]]+\[([^\]]+)\]")
CJK_RE = re.compile(r"[一-鿿々]")  # kanji + 々

HTML_BREAK_RE = re.compile(r"<br\s*/?>|</p>|<p>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")

SEPARATOR_PLACEHOLDER = "\x00SEP\x00"
JP_CHAR = "぀-ヿ一-鿿ー々"
# A space between two Japanese characters is just a leftover token
# boundary from how the deck wrote bracketed furigana side by side
# (e.g. "几[き] 帳[ちょう]" -> "几 帳" once brackets are stripped) and
# needs to disappear; a space next to Latin text (cf., e.g.) is a real
# word gap and should survive as a single space.
JP_GAP_RE = re.compile(rf"(?<=[{JP_CHAR}])[ 　]+(?=[{JP_CHAR}])")


def clean_text(text: str) -> str:
    """Replaces 漢字[かな] with かな and strips whitespace. This deck has
    no optional-word or usage-hint brackets, so no bracket-stripping
    beyond furigana is needed."""
    cleaned = FURIGANA_RE.sub(lambda m: m.group(1), text)
    return re.sub(r"\s+", "", cleaned)


def clean_english_field(text: str) -> str:
    """Cleans an English-ish field (Meaning or Notes) that may embed
    <br>/<p> breaks and 漢字[ふりがな]-annotated Japanese fragments.
    Keeps kanji (not reading) for readability and turns <br>/<p> into a
    separator instead of dropping them silently, which would otherwise
    run two clauses together."""
    text = HTML_BREAK_RE.sub(SEPARATOR_PLACEHOLDER, text)
    text = HTML_TAG_RE.sub("", text)
    # keep kanji form: substitute "X[Y]" -> "X" (drop the furigana, keep the kanji)
    text = re.sub(r"([^\s\[\]]+)\[[^\]]+\]", lambda m: m.group(1), text)
    text = JP_GAP_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(f"\\s*({SEPARATOR_PLACEHOLDER})\\s*", "; ", text)
    return text.strip("; ")


def load_notes() -> list[tuple[str, str, str, str]]:
    with zipfile.ZipFile(APKG_PATH) as zf, tempfile.TemporaryDirectory() as tmp:
        # Newer-format .apkg: real data lives in collection.anki21, not
        # the legacy collection.anki2 stub kept alongside it.
        db_path = Path(tmp) / "collection.anki21"
        db_path.write_bytes(zf.read("collection.anki21"))
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT flds FROM notes").fetchall()
        finally:
            conn.close()

    notes = []
    for (flds,) in rows:
        parts = flds.split("\x1f")
        if len(parts) != 4:
            continue
        notes.append(tuple(parts))
    return notes


def main() -> None:
    notes = load_notes()
    print(f"Loaded {len(notes)} notes from {APKG_PATH.name}")

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
