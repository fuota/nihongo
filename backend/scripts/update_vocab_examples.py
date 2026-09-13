"""
Fills in VocabCard.example_sentence from a hand-written {id: sentence}
JSON map (scripts/data/n5_vocab_examples.json). Jisho's API has no
example sentences, so seed_vocab.py leaves them null; this fills the
gap for rows that were seeded from that script.

Usage:
    uv run python scripts/update_vocab_examples.py
"""

import json
from pathlib import Path

from app.database import SessionLocal
from app import models

EXAMPLES_PATH = Path(__file__).parent / "data" / "n5_vocab_examples.json"


def main() -> None:
    examples = json.loads(EXAMPLES_PATH.read_text())
    db = SessionLocal()

    updated = 0
    missing = 0
    try:
        for vocab_id, sentence in examples.items():
            card = db.query(models.VocabCard).filter(models.VocabCard.id == vocab_id).first()
            if card is None:
                missing += 1
                continue
            card.example_sentence = sentence
            updated += 1

        db.commit()
    finally:
        db.close()

    print(f"Updated {updated} rows with example sentences, {missing} ids not found.")


if __name__ == "__main__":
    main()
