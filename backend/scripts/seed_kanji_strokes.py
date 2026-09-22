"""
Backfills WritingCharacter.stroke_paths from the KanjiVG dataset
(https://kanjivg.tagaini.net, CC BY-SA 3.0 -- attribution required
wherever stroke data is shown in the app).

For each seeded character, fetches kanji/<codepoint>.svg from KanjiVG's
GitHub mirror and extracts the ordered list of stroke <path> "d"
attributes (KanjiVG's stroke order == document order). Idempotent --
only touches rows where stroke_paths is still empty.

Usage (from backend/): PYTHONPATH=. .venv/bin/python scripts/seed_kanji_strokes.py
"""
import re
import time

import requests
from sqlalchemy import func

from app.database import SessionLocal
from app import models

KANJIVG_URL = "https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/{codepoint}.svg"
STROKE_PATH_RE = re.compile(r'<path\b[^>]*\bd="([^"]+)"')


def codepoint_for(character: str) -> str:
    return format(ord(character), "05x")


def fetch_stroke_paths(character: str) -> list[str]:
    url = KANJIVG_URL.format(codepoint=codepoint_for(character))
    response = requests.get(url, timeout=10)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return STROKE_PATH_RE.findall(response.text)


def main():
    db = SessionLocal()
    characters = (
        db.query(models.WritingCharacter)
        .filter(func.json_array_length(models.WritingCharacter.stroke_paths) == 0)
        .all()
    )
    print(f"Fetching stroke data for {len(characters)} characters")

    assigned = 0
    missing = []

    for char in characters:
        try:
            paths = fetch_stroke_paths(char.character)
        except requests.RequestException as e:
            print(f"  {char.character}: request failed ({e}), skipping")
            continue

        if not paths:
            missing.append(char.character)
            continue

        char.stroke_paths = paths
        assigned += 1
        db.commit()
        time.sleep(0.1)  # be polite to GitHub's raw content host

    print(f"Assigned: {assigned}")
    if missing:
        print(f"No KanjiVG entry found for: {''.join(missing)}")


if __name__ == "__main__":
    main()
