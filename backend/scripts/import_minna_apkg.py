"""
Imports VocabCard rows from the Minna no Nihongo 1 & 2 Anki deck
(scripts/data/minna_no_nihongo.apkg -- Lessons 1-50, one flat note type
with fields Expression | Meaning | Reading | Lesson Number).

The deck has no separate grammar-explanation notes -- it's vocab words
plus ~221 fixed expressions/phrases per lesson (e.g. どういうふうに
なさいますか. "How would you like it done? (respectful)"). Both fit
VocabCard directly: phrases just use a longer kanji/reading string.
Phrase-like entries get topic="expressions" so they're browsable as
their own category; plain words are left topic=None for the existing
assign_vocab_topics.py LLM pass to classify thematically.

Lesson -> level: 1-25 = N5 (Book 1), 26-50 = N4 (Book 2).

Usage (from backend/): PYTHONPATH=. uv run python scripts/import_minna_apkg.py
"""

import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app.database import SessionLocal
from app import models

APKG_PATH = Path(__file__).parent / "data" / "minna_no_nihongo.apkg"

FURIGANA_RE = re.compile(r"[^\s\[\]（）［］]+\[([^\]]+)\]")
FULLWIDTH_BRACKETS = str.maketrans("", "", "［］")
CJK_RE = re.compile(r"[一-鿿々]")  # kanji + 々

# A handful of rows carry leftover HTML formatting (<div>, <br>, <b>,
# &nbsp;) and stray control characters from however this deck was
# authored/exported. Strip both before any other processing.
HTML_TAG_RE = re.compile(r"<[^>]+>")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1a]")

# The deck author left exactly one entry self-flagged as unresolved
# (葛飾北斉 <b>(FIX)</b> -- its furigana is also wrong, splitting the
# painter's name 北斎/ほくさい into 北[きた]斉[ひとし]). Skip anything
# carrying that marker rather than guess at a fix.
FIX_MARKER = "(FIX)"


def strip_html(text: str) -> str:
    text = HTML_TAG_RE.sub("", text).replace("&nbsp;", "")
    return CONTROL_CHAR_RE.sub("", text)


# ［友達に〜］-style brackets are usage-context notes (how the word is used
# in a sentence, e.g. "合います［サイズが〜］" = "to fit, as in サイズが合います"),
# NOT droppable optional words like ［どうぞ］. They must be cut out
# entirely rather than unwrapped, or they get concatenated onto the word
# itself as garbage (e.g. "間に合います［時間に〜］" -> "まにあいますじかんに〜").
USAGE_NOTE_RE = re.compile(r"［([^］]*〜[^］]*)］")


def extract_usage_notes(text: str) -> tuple[str, list[str]]:
    """Removes ［...〜...］ usage-note segments from text, returning the
    remaining text and the list of note contents found (still containing
    furigana brackets -- run clean_text on each before display)."""
    notes = USAGE_NOTE_RE.findall(text)
    return USAGE_NOTE_RE.sub("", text), notes


def clean_text(text: str) -> str:
    """Replaces 漢字[かな] with かな, strips optional-word brackets and
    whitespace. Leaves any kanji that wasn't inside a furigana bracket
    untouched -- callers that expect a pure-kana result (readings) are
    responsible for checking for and handling leftover kanji themselves.
    """
    cleaned = FURIGANA_RE.sub(lambda m: m.group(1), text)
    cleaned = cleaned.translate(FULLWIDTH_BRACKETS)
    return re.sub(r"\s+", "", cleaned)


def clean_reading(text: str) -> tuple[str, bool]:
    """Like clean_text, but the result must be pure kana. Returns
    (cleaned_reading, had_leftover_kanji) -- the second value flags rows
    where the source deck's furigana bracketing was incomplete (kanji
    left over with no [reading] attached), so they can be reviewed
    manually instead of guessed at. Any leftover kanji is stripped from
    the returned reading so it doesn't end up mixed into kana text.
    """
    cleaned = clean_text(text)
    had_leftover_kanji = bool(CJK_RE.search(cleaned))
    if had_leftover_kanji:
        cleaned = CJK_RE.sub("", cleaned)
    return cleaned, had_leftover_kanji


def is_expression(expression_field: str) -> bool:
    return "。" in expression_field or "　" in expression_field.strip()


def load_notes() -> list[tuple[str, str, str, str]]:
    with zipfile.ZipFile(APKG_PATH) as zf, tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "collection.anki2"
        db_path.write_bytes(zf.read("collection.anki2"))
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
    skipped_empty_lesson = 0
    skipped_self_flagged = 0
    flagged_for_review: list[tuple[str, str]] = []
    seen_in_batch: set[tuple[str | None, str]] = set()

    try:
        for expression, meaning_raw, reading_raw, lesson_str in notes:
            if not lesson_str.strip():
                skipped_empty_lesson += 1
                continue
            if FIX_MARKER in expression:
                skipped_self_flagged += 1
                continue
            lesson = int(lesson_str)

            expression = strip_html(expression)
            meaning_raw = strip_html(meaning_raw)
            reading_raw = strip_html(reading_raw)

            expression_core, _ = extract_usage_notes(expression)
            reading_core, usage_notes_raw = extract_usage_notes(reading_raw)

            expr_clean = clean_text(expression_core)
            reading_clean, reading_flagged = clean_reading(reading_core)
            if reading_flagged:
                flagged_for_review.append((expression, reading_raw))

            if CJK_RE.search(expr_clean):
                kanji = expr_clean
                reading = reading_clean
            else:
                kanji = None
                reading = expr_clean

            meaning = meaning_raw.replace("`", "'")
            if usage_notes_raw:
                hints = "; ".join(clean_text(note) for note in usage_notes_raw)
                meaning = f"{meaning} (used as: {hints})"

            jlpt_level = "N5" if 1 <= lesson <= 25 else "N4"
            topic = "expressions" if is_expression(expression_core) else None

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
                    jlpt_level=jlpt_level,
                    source="textbook",
                    topic=topic,
                )
            )
            inserted += 1

        db.commit()
    finally:
        db.close()

    print(f"Inserted {inserted} new VocabCard rows.")
    print(f"Skipped {skipped_duplicate} already-present (reading+kanji match).")
    print(f"Skipped {skipped_empty_lesson} row(s) with no Lesson Number.")
    print(f"Skipped {skipped_self_flagged} row(s) the deck author marked {FIX_MARKER}.")
    print(f"Flagged {len(flagged_for_review)} row(s) with incomplete furigana bracketing in the source deck:")
    for expression, reading_raw in flagged_for_review:
        print(f"  {expression!r} (reading field: {reading_raw!r})")


if __name__ == "__main__":
    main()
