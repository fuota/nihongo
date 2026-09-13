"""
Seed GrammarPattern rows from a hand-curated N5 grammar list
(scripts/data/n5_grammar.json). Unlike vocab, there's no equivalent
public API for JLPT grammar points -- this list is the standard set
of ~30 N5 patterns that appears consistently across JLPT prep
materials (particles, polite verb forms, adjective conjugation,
comparison, etc).

Usage:
    uv run python scripts/seed_grammar.py --level N5
"""

import argparse
import json
from pathlib import Path

from app.database import SessionLocal
from app import models

DATA_DIR = Path(__file__).parent / "data"


def seed(level: str) -> None:
    data_path = DATA_DIR / f"{level.lower()}_grammar.json"
    patterns = json.loads(data_path.read_text())

    db = SessionLocal()
    inserted = 0
    skipped = 0
    try:
        for item in patterns:
            exists = (
                db.query(models.GrammarPattern)
                .filter(models.GrammarPattern.pattern == item["pattern"])
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(
                models.GrammarPattern(
                    pattern=item["pattern"],
                    explanation=item["explanation"],
                    example_sentence=item["example_sentence"],
                    drill_sentence=item["drill_sentence"],
                    jlpt_level=level.upper(),
                )
            )
            inserted += 1

        db.commit()
    finally:
        db.close()

    print(f"Inserted {inserted} new GrammarPattern rows, skipped {skipped} already present.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", default="N5")
    args = parser.parse_args()

    seed(args.level)
