"""
Splits GrammarPattern.example_sentence (seeded as "<JP>。(<English>)") into
a clean JP-only example_sentence + example_sentence_en, then backfills
example_sentence_furigana the same way enrich_vocab_examples.py does for
VocabCard. Idempotent -- only touches rows where example_sentence_furigana
IS NULL, and only re-splits example_sentence if it still has a trailing
"(...)" (so a rerun after a partial failure doesn't re-split an
already-cleaned sentence).

Usage (from backend/): PYTHONPATH=. .venv/bin/python scripts/enrich_grammar_examples.py
"""
import json
import re

from app.database import SessionLocal
from app import models
from app.agents.llm import get_llm_provider

BATCH_SIZE = 15

TRAILING_PAREN = re.compile(r"^(.*?)\(([^()]*)\)\s*$")

SYSTEM_PROMPT = """You segment Japanese example sentences for a language-learning app.

For each numbered sentence, produce an ordered array of word-level chunks:
{"surface": "...", "reading": "..." or null}.
- A kanji-bearing word (including any okurigana that's part of the same
  word, e.g. "持って") is one chunk, with "reading" = that chunk's full
  hiragana reading (e.g. "もって").
- A chunk with no kanji (particles, punctuation, pure-kana words) has
  "reading": null.
- Concatenating every chunk's "surface" in order MUST reconstruct the
  original sentence exactly, character for character, INCLUDING any
  trailing punctuation like "。".

Respond with ONLY a JSON array (no markdown fences, no prose):
[{"index": 0, "segments": [{"surface": "...", "reading": "..."}]}]
"""


def split_translation(db):
    patterns = (
        db.query(models.GrammarPattern)
        .filter(models.GrammarPattern.example_sentence_en.is_(None))
        .all()
    )
    split_count = 0
    for p in patterns:
        m = TRAILING_PAREN.match(p.example_sentence or "")
        if not m:
            continue
        jp, en = m.group(1).strip(), m.group(2).strip()
        p.example_sentence = jp
        p.example_sentence_en = en
        split_count += 1
    db.commit()
    return split_count


def assign_furigana(db):
    patterns = (
        db.query(models.GrammarPattern)
        .filter(
            models.GrammarPattern.example_sentence.isnot(None),
            models.GrammarPattern.example_sentence_furigana.is_(None),
        )
        .all()
    )

    assigned = 0
    failed = 0

    for start in range(0, len(patterns), BATCH_SIZE):
        batch = patterns[start : start + BATCH_SIZE]
        sentence_list = "\n".join(
            f"{i}. {p.example_sentence}" for i, p in enumerate(batch)
        )

        provider = get_llm_provider()
        provider.start_conversation(system=SYSTEM_PROMPT, user_message=sentence_list)
        turn = provider.step(tools=[])

        try:
            cleaned = turn.text.strip()
            s, e = cleaned.find("["), cleaned.rfind("]")
            results = {r["index"]: r for r in json.loads(cleaned[s : e + 1])}
        except (ValueError, json.JSONDecodeError):
            print(f"  batch {start}: could not parse LLM response, skipping")
            failed += len(batch)
            continue

        for i, p in enumerate(batch):
            result = results.get(i)
            if result is None:
                failed += 1
                continue

            segments = result.get("segments", [])
            for seg in segments:
                if seg.get("reading") == seg.get("surface"):
                    seg["reading"] = None

            reconstructed = "".join(seg.get("surface", "") for seg in segments)
            if reconstructed != p.example_sentence:
                if segments and p.example_sentence.startswith(reconstructed):
                    missing_tail = p.example_sentence[len(reconstructed):]
                    segments = segments + [{"surface": missing_tail, "reading": None}]
                else:
                    print(f"  batch {start}: segment mismatch for {p.pattern!r}, skipping furigana")
                    failed += 1
                    continue

            p.example_sentence_furigana = segments
            assigned += 1

        db.commit()
        print(f"  batch {start}: {len(batch)} processed")

    return assigned, failed


def main():
    db = SessionLocal()

    split_count = split_translation(db)
    print(f"Split translation out of example_sentence: {split_count}")

    assigned, failed = assign_furigana(db)
    print(f"Furigana assigned: {assigned} (failed: {failed})")


if __name__ == "__main__":
    main()
