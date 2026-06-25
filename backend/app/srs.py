"""
SM-2 spaced repetition algorithm.

Reference: SuperMemo 2 algorithm (Wozniak, 1987).

Grade scale (0-5):
  0 - complete blackout, no recollection at all
  1 - incorrect, but the correct answer felt familiar once shown
  2 - incorrect, but the correct answer seemed easy to recall once shown
  3 - correct, but required significant effort to recall
  4 - correct, with some hesitation
  5 - correct, perfect recall with no hesitation

Higher ease factor means future successful reviews grow the interval
faster (card is treated as "well known"); lower ease factor means
intervals grow more slowly (card stays in tighter rotation).
ease_factor = ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class SRSState:
    ease_factor: float
    interval_days: int
    repetitions: int = 0


@dataclass
class SRSResult:
    ease_factor: float
    interval_days: int
    repetitions: int
    next_review_date: datetime


MIN_EASE_FACTOR = 1.3


def calculate_next_review(
    current_state: SRSState,
    grade: int,
    reviewed_at: Optional[datetime] = None,
) -> SRSResult:
    if not (0 <= grade <= 5):
        raise ValueError(f"grade must be between 0 and 5, got {grade}")

    if reviewed_at is None:
        reviewed_at = datetime.utcnow()

    ease_factor = current_state.ease_factor
    repetitions = current_state.repetitions

    if grade < 3:
        interval_days = 1
        repetitions = 0
    else:
        repetitions += 1

        if repetitions == 1:
            interval_days = 1
        elif repetitions == 2:
            interval_days = 6
        else:
            interval_days = round(current_state.interval_days * ease_factor)

    ease_factor = ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))

    if ease_factor < MIN_EASE_FACTOR:
        ease_factor = MIN_EASE_FACTOR

    next_review_date = reviewed_at + timedelta(days=interval_days)

    return SRSResult(
        ease_factor=round(ease_factor, 2),
        interval_days=interval_days,
        repetitions=repetitions,
        next_review_date=next_review_date,
    )