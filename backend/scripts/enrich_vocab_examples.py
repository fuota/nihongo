"""
Backfills English translation + furigana segmentation for every
VocabCard.example_sentence that doesn't have them yet (idempotent --
only touches rows where example_sentence_furigana IS NULL, so a rerun
naturally retries anything that failed last time, translation included).

furigana segments are an ordered list of {"surface": str, "reading":
str | None} chunks that reconstruct the sentence when concatenated.
Non-null reading marks a kanji-bearing chunk the mobile app renders as
furigana and makes tappable.

Usage (from backend/): PYTHONPATH=. .venv/bin/python scripts/enrich_vocab_examples.py
"""
import json

from app.database import SessionLocal
from app import models
from app.agents.llm import get_llm_provider

BATCH_SIZE = 15

SYSTEM_PROMPT = """You enrich Japanese JLPT example sentences for a language-learning app.

For each numbered sentence, produce:
1. "translation": a natural, idiomatic English translation.
2. "segments": the sentence split into an ordered array of word-level
   chunks. Each chunk is {"surface": "...", "reading": "..." or null}.
   - A kanji-bearing word (including any okurigana that's part of the
     same word, e.g. "持って") is one chunk, with "reading" = that
     chunk's full hiragana reading (e.g. "もって").
   - A chunk with no kanji (particles, punctuation, pure-kana words)
     has "reading": null.
   - Concatenating every chunk's "surface" in order MUST reconstruct
     the original sentence exactly, character for character.

Respond with ONLY a JSON array (no markdown fences, no prose):
[{"index": 0, "translation": "...", "segments": [{"surface": "...", "reading": "..."}]}]
"""


def main():
    db = SessionLocal()
    cards = (
        db.query(models.VocabCard)
        .filter(
            models.VocabCard.example_sentence.isnot(None),
            models.VocabCard.example_sentence_furigana.is_(None),
        )
        .all()
    )
    print(f"Enriching {len(cards)} example sentences")

    assigned = 0
    failed = 0

    for start in range(0, len(cards), BATCH_SIZE):
        batch = cards[start : start + BATCH_SIZE]
        sentence_list = "\n".join(
            f"{i}. {card.example_sentence}" for i, card in enumerate(batch)
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

        for i, card in enumerate(batch):
            result = results.get(i)
            if result is None:
                failed += 1
                continue

            segments = result.get("segments", [])
            for seg in segments:
                # Drop self-referential readings on pure-kana chunks
                # (e.g. "します" -> "します") -- the model sometimes adds
                # these even though they carry no furigana information.
                if seg.get("reading") == seg.get("surface"):
                    seg["reading"] = None

            reconstructed = "".join(seg.get("surface", "") for seg in segments)
            if reconstructed != card.example_sentence:
                # Most mismatches are the model dropping trailing
                # punctuation (e.g. the final "。"). If what we got is an
                # exact prefix of the real sentence, patch the missing
                # tail on as a final plain (non-furigana) segment rather
                # than discarding otherwise-correct segmentation.
                if segments and card.example_sentence.startswith(reconstructed):
                    missing_tail = card.example_sentence[len(reconstructed):]
                    segments = segments + [{"surface": missing_tail, "reading": None}]
                else:
                    print(
                        f"  batch {start}: segment mismatch for {card.kanji or card.reading!r}, "
                        f"keeping translation only"
                    )
                    segments = None

            card.example_sentence_en = result.get("translation")
            card.example_sentence_furigana = segments
            assigned += 1

        db.commit()
        print(f"  batch {start}: {len(batch)} processed")

    print(f"Enriched: {assigned} (failed: {failed})")


if __name__ == "__main__":
    main()
