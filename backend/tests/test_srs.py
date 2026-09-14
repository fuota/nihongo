from datetime import datetime, timedelta

import pytest

from app.srs import MIN_EASE_FACTOR, SRSState, calculate_next_review


def test_invalid_grade_raises():
    state = SRSState(ease_factor=2.5, interval_days=1, repetitions=0)
    with pytest.raises(ValueError):
        calculate_next_review(state, grade=-1)
    with pytest.raises(ValueError):
        calculate_next_review(state, grade=6)


def test_first_successful_review_sets_interval_to_one_day():
    state = SRSState(ease_factor=2.5, interval_days=1, repetitions=0)
    result = calculate_next_review(state, grade=5)

    assert result.repetitions == 1
    assert result.interval_days == 1
    assert result.ease_factor == 2.6  # grade 5: +0.1


def test_second_successful_review_sets_interval_to_six_days():
    state = SRSState(ease_factor=2.5, interval_days=1, repetitions=1)
    result = calculate_next_review(state, grade=4)

    assert result.repetitions == 2
    assert result.interval_days == 6
    assert result.ease_factor == 2.5  # grade 4: +0.0, no change


def test_third_and_later_reviews_scale_interval_by_ease_factor():
    state = SRSState(ease_factor=2.5, interval_days=6, repetitions=2)
    result = calculate_next_review(state, grade=5)

    assert result.repetitions == 3
    # Uses the *pre-update* ease factor to scale the previous interval.
    assert result.interval_days == round(6 * 2.5)
    assert result.ease_factor == 2.6


def test_failed_review_resets_repetitions_and_interval_but_still_updates_ease():
    state = SRSState(ease_factor=2.5, interval_days=15, repetitions=3)
    result = calculate_next_review(state, grade=1)

    assert result.repetitions == 0
    assert result.interval_days == 1
    # grade 1: delta = 0.1 - 4*(0.08 + 4*0.02) = -0.54
    assert result.ease_factor == 1.96


def test_ease_factor_never_drops_below_minimum():
    state = SRSState(ease_factor=MIN_EASE_FACTOR, interval_days=1, repetitions=0)
    result = calculate_next_review(state, grade=0)

    assert result.ease_factor == MIN_EASE_FACTOR


def test_ease_factor_is_rounded_to_two_decimal_places():
    state = SRSState(ease_factor=2.36, interval_days=1, repetitions=0)
    result = calculate_next_review(state, grade=3)

    assert result.ease_factor == round(result.ease_factor, 2)


def test_next_review_date_is_reviewed_at_plus_interval():
    state = SRSState(ease_factor=2.5, interval_days=1, repetitions=1)
    reviewed_at = datetime(2026, 1, 1, 12, 0, 0)

    result = calculate_next_review(state, grade=4, reviewed_at=reviewed_at)

    assert result.next_review_date == reviewed_at + timedelta(days=result.interval_days)


def test_reviewed_at_defaults_to_now():
    state = SRSState(ease_factor=2.5, interval_days=1, repetitions=0)
    before = datetime.utcnow()

    result = calculate_next_review(state, grade=5)

    after = datetime.utcnow()
    expected_min = before + timedelta(days=result.interval_days)
    expected_max = after + timedelta(days=result.interval_days)
    assert expected_min <= result.next_review_date <= expected_max
