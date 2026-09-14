"""
Applies a plain ordered list of example sentences (scripts/data/*.json)
to VocabCard rows at a given level that still have example_sentence
IS NULL, in created_at order -- the same order the list must be
written against. Refuses to apply if the counts don't match, to
avoid silently misaligning sentences with the wrong words.

Usage:
    uv run python scripts/apply_vocab_examples.py --level N5 --file n5_vocab_examples.json
    uv run python scripts/apply_vocab_examples.py --level N4 --file n4_vocab_examples.json
"""

import argparse
import json
from pathlib import Path

from app.database import SessionLocal
from app import models

DATA_DIR = Path(__file__).parent / "data"


def apply(level: str, filename: str) -> None:
    sentences = json.loads((DATA_DIR / filename).read_text())

    db = SessionLocal()
    try:
        rows = (
            db.query(models.VocabCard)
            .filter(
                models.VocabCard.jlpt_level == level.upper(),
                models.VocabCard.example_sentence.is_(None),
            )
            .order_by(models.VocabCard.created_at)
            .all()
        )

        if len(rows) != len(sentences):
            raise SystemExit(
                f"Mismatch: {len(rows)} rows need sentences but {len(sentences)} "
                "sentences provided -- refusing to apply out of order."
            )

        for row, sentence in zip(rows, sentences):
            row.example_sentence = sentence

        db.commit()
        print(f"Updated {len(rows)} rows.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", required=True, help="JLPT level, e.g. N5")
    parser.add_argument("--file", required=True, help="filename under scripts/data/")
    args = parser.parse_args()

    apply(args.level, args.file)
