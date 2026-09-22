"""
Imports VocabCard rows from the Quartet 1 Vocab Anki deck
(scripts/data/quartet_1_vocab.apkg -- Lessons 1-6, note type
"Japanese (recognition&recall)" with fields Expression | Meaning | Reading).

Unlike the Minna no Nihongo deck, field naming here is reversed:
Expression already holds the plain-kana reading (e.g. "かんとく"), and
Reading holds the kanji form with inline furigana (e.g. "監督[かんとく]").
So the reading comes straight from Expression -- no furigana math needed
for it -- and kanji is derived from Reading by keeping the kanji/kana
written outside the [furigana] brackets and dropping the brackets.

~67 entries carry a leading usage-hint prefix using half-width brackets,
e.g. "[が] 得意[とくい]な" ("good at ~", used with が) -- identical in
both Expression and Reading fields. These aren't furigana (nothing
precedes them) and get folded into the meaning as "(used with: ...)"
instead of left in the word itself.

Quartet 1 is intermediate-level -- every row is seeded at N3 per the
user's instruction (the deck has no per-level field to read instead).

Usage (from backend/): PYTHONPATH=. uv run python scripts/import_quartet_apkg.py
"""

import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app.database import SessionLocal
from app import models

APKG_PATH = Path(__file__).parent / "data" / "quartet_1_vocab.apkg"
JLPT_LEVEL = "N3"

FURIGANA_TO_KANJI_RE = re.compile(r"([^\s\[\]]+)\[[^\]]+\]")
CJK_RE = re.compile(r"[一-鿿々]")  # kanji + 々

HTML_TAG_RE = re.compile(r"<[^>]+>")

# A leading "[が]" / "[~に]" / "[人に]" style bracket is a usage-context
# hint (which particle the word takes), not furigana -- nothing precedes
# it, whereas furigana always immediately follows a kanji/kana token.
PREFIX_HINT_RE = re.compile(r"^\s*\[([^\]]*)\]\s*")


def strip_html(text: str) -> str:
    return HTML_TAG_RE.sub("", text).replace("&nbsp;", "")


def extract_prefix_hint(text: str) -> tuple[str, str | None]:
    match = PREFIX_HINT_RE.match(text)
    if not match:
        return text, None
    hint = match.group(1).strip()
    return PREFIX_HINT_RE.sub("", text, count=1), (hint or None)


def kanji_from_reading_field(text: str) -> str:
    """"監督[かんとく]" -> "監督"; leaves kanji with no furigana untouched."""
    cleaned = FURIGANA_TO_KANJI_RE.sub(lambda m: m.group(1), text)
    return re.sub(r"\s+", "", cleaned)


def load_notes() -> list[tuple[str, str, str]]:
    with zipfile.ZipFile(APKG_PATH) as zf, tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "collection.anki2"
        db_path.write_bytes(zf.read("collection.anki2"))
        conn = sqlite3.connect(db_path)
        try:
            # This deck defines a second "Basic" note type, but it has
            # zero notes -- every row here is the 3-field
            # "Japanese (recognition&recall)" model, filtered below by
            # field count rather than joining on model id.
            rows = conn.execute("SELECT flds FROM notes").fetchall()
        finally:
            conn.close()

    notes = []
    for (flds,) in rows:
        parts = flds.split("\x1f")
        if len(parts) != 3:
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
        for expression, meaning_raw, reading_field in notes:
            expression = strip_html(expression)
            meaning_raw = strip_html(meaning_raw)
            reading_field = strip_html(reading_field)

            expr_core, expr_hint = extract_prefix_hint(expression)
            reading_core, reading_hint = extract_prefix_hint(reading_field)
            hint = reading_hint or expr_hint

            reading = re.sub(r"\s+", "", expr_core)
            kanji_candidate = kanji_from_reading_field(reading_core)

            kanji = kanji_candidate if CJK_RE.search(kanji_candidate) else None

            meaning = meaning_raw.strip()
            if hint:
                meaning = f"{meaning} (used with: {hint})"

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
