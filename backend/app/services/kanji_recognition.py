"""
recognize_character: identifies a hand-drawn Japanese character from a
base64 PNG via a vision-capable LLM (see app.agents.llm.get_vision_llm_provider).

Originally planned as Google Cloud Vision (see the build plan); no GCP
credentials were ever configured for this project, so this reuses the
LLM provider abstraction already built for the agents instead -- same
swappable-provider intent, just for image input.
"""

import json

from app.agents.llm import get_vision_llm_provider

PROMPT = """A user is practicing Japanese handwriting. The image shows a
single hand-drawn character (kanji, hiragana, or katakana) on a blank
background.

Identify the character. Respond with ONLY a JSON object (no markdown
fences, no prose):
{"character": "<the single character, or null if you cannot identify one>", "confidence": <0.0-1.0>}
"""


class RecognitionError(Exception):
    pass


def recognize_character(image_base64: str) -> dict:
    """
    Returns {"character": str | None, "confidence": float}. Raises
    RecognitionError on any failure (API error, unparseable response) so
    the caller's retry wrapper can retry / fall back -- a low-confidence
    or "no character found" result is NOT an error, since retrying won't
    fix an illegible drawing.
    """
    provider = get_vision_llm_provider()

    try:
        text = provider.recognize_image(image_base64, PROMPT)
    except Exception as e:
        raise RecognitionError(f"vision API call failed: {e}") from e

    try:
        cleaned = text.strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        result = json.loads(cleaned[start : end + 1])
    except (ValueError, json.JSONDecodeError) as e:
        raise RecognitionError(f"could not parse vision model response: {e}") from e

    character = result.get("character") or None
    confidence = result.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.0

    return {"character": character, "confidence": float(confidence)}
