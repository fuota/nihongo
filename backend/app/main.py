import random
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials

from app.database import get_db
from app import models
from app.srs import calculate_next_review, SRSState
from app.agents.session_builder import run_session_builder_agent
from app.agents.tutor import run_tutor_agent
from app.agents.quiz_review import run_quiz_review_agent
from app.agents.reading_generator import run_reading_generator_agent
from app.services.vocab_lookup import get_or_fetch_word
from app.services.kanji_recognition import recognize_character
from app.utils.retry import call_with_retry

app = FastAPI(title="Nihongo API")

clerk_config = ClerkConfig(
    jwks_url="https://decent-koi-28.clerk.accounts.dev/.well-known/jwks.json"
)
clerk_auth_guard = ClerkHTTPBearer(config=clerk_config)


def get_or_create_user(db: Session, clerk_user_id: str, email: Optional[str]) -> models.User:
    """
    Shared get-or-create logic, used by /me and any other endpoint that
    needs to resolve a Clerk identity to our own User row.
    """
    user = db.query(models.User).filter(
        models.User.clerk_user_id == clerk_user_id
    ).first()

    if user is None:
        user = models.User(clerk_user_id=clerk_user_id, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


def _record_activity_day(db: Session, user_id: str) -> None:
    """
    Marks today as an active day for this user, if not already recorded.
    Called from the four things that count toward the daily streak:
    starting a Learning Session, starting a Reading, starting a Drill
    (GET /review/due, the Play screen's entry point), and a writing-
    practice attempt (POST /kanji/recognize). Does not commit -- callers
    already commit as part of their own request.
    """
    today = datetime.utcnow().date()
    exists = (
        db.query(models.UserActivityDay)
        .filter(models.UserActivityDay.user_id == user_id, models.UserActivityDay.activity_date == today)
        .first()
    )
    if exists is None:
        db.add(models.UserActivityDay(user_id=user_id, activity_date=today))


def _compute_streak(db: Session, user_id: str) -> int:
    """
    Current consecutive-day streak. If today has no activity yet, the
    streak still counts back from yesterday (rather than showing 0)
    so a streak doesn't visually break just because the user hasn't
    done anything YET today.
    """
    rows = db.query(models.UserActivityDay.activity_date).filter(models.UserActivityDay.user_id == user_id).all()
    active_dates = {row.activity_date for row in rows}

    today = datetime.utcnow().date()
    cursor = today if today in active_dates else today - timedelta(days=1)

    streak = 0
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _characters_by_vocab_id(db: Session, vocab_ids: list) -> dict:
    """
    Batch-loads {vocab_card_id: [{id, character}]} for the given card ids,
    via the VocabCharacterLink table built during kanji seeding. Only
    covers the ~100 seeded kanji, so most words return an empty list --
    that's expected, not an error.
    """
    if not vocab_ids:
        return {}

    rows = (
        db.query(models.VocabCharacterLink.vocab_card_id, models.WritingCharacter)
        .join(models.WritingCharacter, models.WritingCharacter.id == models.VocabCharacterLink.character_id)
        .filter(models.VocabCharacterLink.vocab_card_id.in_(vocab_ids))
        .all()
    )

    result: dict = {}
    for vocab_card_id, char in rows:
        result.setdefault(vocab_card_id, []).append({"id": char.id, "character": char.character})
    return result


@app.get("/")
def read_root():
    return {"message": "hello world", "status": "ok"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/me")
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    words_learnt = (
        db.query(models.UserLearntItem)
        .filter(models.UserLearntItem.user_id == user.id, models.UserLearntItem.content_type == "vocab")
        .count()
    )
    grammar_learnt = (
        db.query(models.UserLearntItem)
        .filter(models.UserLearntItem.user_id == user.id, models.UserLearntItem.content_type == "grammar")
        .count()
    )
    # "days attended" still counts from the registration day itself
    # (day 1 on signup day) rather than real UserActivityDay rows --
    # that rewiring is still Day 13 scope. streak_count below DOES use
    # UserActivityDay now (Day 12), since that's what was actually asked for.
    days_attended = (datetime.utcnow().date() - user.created_at.date()).days + 1

    return {
        "id": user.id,
        "clerk_user_id": user.clerk_user_id,
        "email": user.email,
        "name": user.name,
        "avatar": user.avatar,
        "jlpt_level": user.jlpt_level,
        "streak_count": _compute_streak(db, user.id),
        "days_attended": days_attended,
        "words_learnt": words_learnt,
        "grammar_learnt": grammar_learnt,
        "session_item_count": user.session_item_count,
        "created_at": user.created_at,
    }


AVATAR_CHOICES = ["cat", "dog", "panda", "rabbit", "koala"]


class UpdateSettingsRequest(BaseModel):
    session_item_count: Optional[int] = Field(default=None, ge=5, le=15)
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    avatar: Optional[str] = None
    # Clerk's session token has no email claim, so get_or_create_user's
    # payload.get("email") is always None -- this lets the mobile app
    # backfill the real value it already has from Clerk on-device.
    email: Optional[str] = None


@app.patch("/me")
def update_settings(
    body: UpdateSettingsRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    if body.session_item_count is not None:
        user.session_item_count = body.session_item_count

    if body.name is not None:
        user.name = body.name.strip()

    if body.avatar is not None:
        if body.avatar not in AVATAR_CHOICES:
            raise HTTPException(status_code=400, detail=f"avatar must be one of {AVATAR_CHOICES}")
        user.avatar = body.avatar

    if body.email is not None:
        user.email = body.email

    db.commit()
    db.refresh(user)

    return {
        "session_item_count": user.session_item_count,
        "name": user.name,
        "avatar": user.avatar,
        "email": user.email,
    }


@app.get("/vocab")
def get_vocab(
    level: Optional[str] = Query(default=None, description="JLPT level, e.g. N5. Omit to search across all levels"),
    topic: Optional[str] = Query(default=None, description="Filter to a single topic"),
    q: Optional[str] = Query(default=None, description="Search kanji/reading/meaning across ALL levels, ignoring level/topic"),
    learnt: Optional[bool] = Query(
        default=None, description="If true, only words the current user has marked Learnt"
    ),
    in_drill: Optional[bool] = Query(
        default=None, description="If true, only words the current user has added to Drill"
    ),
    limit: int = Query(default=100, ge=1, le=500, description="Max results to return"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip, for pagination"),
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learnt_ids = {
        row.content_id
        for row in db.query(models.UserLearntItem.content_id).filter(
            models.UserLearntItem.user_id == user.id,
            models.UserLearntItem.content_type == "vocab",
        )
    }
    drill_ids = {
        row.content_id
        for row in db.query(models.UserCardProgress.content_id).filter(
            models.UserCardProgress.user_id == user.id,
            models.UserCardProgress.content_type == "vocab",
        )
    }

    if q:
        # A search spans every level -- the user is looking for a
        # specific word, not browsing one level's list -- so level/topic
        # are ignored rather than combined with q.
        term = f"%{q}%"
        query = db.query(models.VocabCard).filter(
            or_(
                models.VocabCard.kanji.ilike(term),
                models.VocabCard.reading.ilike(term),
                models.VocabCard.meaning.ilike(term),
            )
        )
    else:
        query = db.query(models.VocabCard)
        if level is not None:
            query = query.filter(models.VocabCard.jlpt_level == level)
        if topic is not None:
            query = query.filter(models.VocabCard.topic == topic)

    if learnt is True:
        query = query.filter(models.VocabCard.id.in_(learnt_ids))
    elif learnt is False:
        query = query.filter(~models.VocabCard.id.in_(learnt_ids))

    if in_drill is True:
        query = query.filter(models.VocabCard.id.in_(drill_ids))
    elif in_drill is False:
        query = query.filter(~models.VocabCard.id.in_(drill_ids))

    # a stable order is required for offset/limit pagination to behave
    # consistently across repeated calls (unordered queries can otherwise
    # skip or repeat rows between pages)
    vocab_cards = query.order_by(models.VocabCard.id).offset(offset).limit(limit).all()
    characters_by_card = _characters_by_vocab_id(db, [card.id for card in vocab_cards])

    return {
        "level": level,
        "count": len(vocab_cards),
        "results": [
            {
                "id": card.id,
                "kanji": card.kanji,
                "reading": card.reading,
                "meaning": card.meaning,
                "example_sentence": card.example_sentence,
                "example_sentence_en": card.example_sentence_en,
                "example_sentence_furigana": card.example_sentence_furigana,
                "jlpt_level": card.jlpt_level,
                "topic": card.topic,
                "is_learnt": card.id in learnt_ids,
                "in_drill": card.id in drill_ids,
                "characters": characters_by_card.get(card.id, []),
            }
            for card in vocab_cards
        ],
    }


@app.get("/vocab/lookup")
def lookup_vocab(
    word: str = Query(..., description="Kanji or reading to look up"),
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Resolves an arbitrary word (e.g. tapped inside an example sentence) via
    the Day 2 hybrid DB/API path: checks VocabCard first, falls back to
    Jisho, persists on success. Returns a typed "unavailable" result on
    failure rather than ever inventing a definition.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    result = get_or_fetch_word(db, word)

    if result["status"] != "unavailable":
        result["is_learnt"] = (
            db.query(models.UserLearntItem)
            .filter(
                models.UserLearntItem.user_id == user.id,
                models.UserLearntItem.content_type == "vocab",
                models.UserLearntItem.content_id == result["id"],
            )
            .first()
            is not None
        )
        result["in_drill"] = (
            db.query(models.UserCardProgress)
            .filter(
                models.UserCardProgress.user_id == user.id,
                models.UserCardProgress.content_type == "vocab",
                models.UserCardProgress.content_id == result["id"],
            )
            .first()
            is not None
        )

    return result


@app.get("/vocab/topics")
def get_vocab_topics(
    level: str = Query(default="N5", description="JLPT level, e.g. N5"),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.VocabCard.topic, models.VocabCard.id)
        .filter(models.VocabCard.jlpt_level == level, models.VocabCard.topic.isnot(None))
        .all()
    )

    counts: dict[str, int] = {}
    for topic, _ in rows:
        counts[topic] = counts.get(topic, 0) + 1

    return {
        "level": level,
        "results": [
            {"topic": topic, "count": count} for topic, count in sorted(counts.items())
        ],
    }


@app.get("/grammar")
def get_grammar(
    level: str = Query(default="N5", description="JLPT level, e.g. N5"),
    q: Optional[str] = Query(default=None, description="Search pattern/explanation across ALL levels, ignoring level"),
    learnt: Optional[bool] = Query(
        default=None, description="If true, only patterns the current user has marked Learnt"
    ),
    limit: int = Query(default=100, ge=1, le=500, description="Max results to return"),
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learnt_ids = {
        row.content_id
        for row in db.query(models.UserLearntItem.content_id).filter(
            models.UserLearntItem.user_id == user.id,
            models.UserLearntItem.content_type == "grammar",
        )
    }
    drill_ids = {
        row.content_id
        for row in db.query(models.UserCardProgress.content_id).filter(
            models.UserCardProgress.user_id == user.id,
            models.UserCardProgress.content_type == "grammar",
        )
    }

    if q:
        term = f"%{q}%"
        query = db.query(models.GrammarPattern).filter(
            or_(
                models.GrammarPattern.pattern.ilike(term),
                models.GrammarPattern.explanation.ilike(term),
            )
        )
    else:
        query = db.query(models.GrammarPattern).filter(models.GrammarPattern.jlpt_level == level)

    if learnt is True:
        query = query.filter(models.GrammarPattern.id.in_(learnt_ids))
    elif learnt is False:
        query = query.filter(~models.GrammarPattern.id.in_(learnt_ids))

    patterns = query.limit(limit).all()

    return {
        "level": level,
        "count": len(patterns),
        "results": [
            {
                "id": p.id,
                "pattern": p.pattern,
                "explanation": p.explanation,
                "example_sentence": p.example_sentence,
                "example_sentence_en": p.example_sentence_en,
                "example_sentence_furigana": p.example_sentence_furigana,
                "drill_sentence": p.drill_sentence,
                "jlpt_level": p.jlpt_level,
                "is_learnt": p.id in learnt_ids,
                "in_drill": p.id in drill_ids,
            }
            for p in patterns
        ],
    }


@app.get("/kanji/{kanji_id}")
def get_kanji(
    kanji_id: str,
    db: Session = Depends(get_db),
):
    char = db.query(models.WritingCharacter).filter(models.WritingCharacter.id == kanji_id).first()
    if char is None:
        raise HTTPException(status_code=404, detail="kanji not found")

    compounds = (
        db.query(models.VocabCard)
        .join(models.VocabCharacterLink, models.VocabCharacterLink.vocab_card_id == models.VocabCard.id)
        .filter(models.VocabCharacterLink.character_id == char.id)
        .all()
    )

    return {
        "id": char.id,
        "character": char.character,
        "character_type": char.character_type,
        "romaji": char.romaji,
        "meaning": char.meaning,
        "onyomi": char.onyomi,
        "kunyomi": char.kunyomi,
        "stroke_count": char.stroke_count,
        "stroke_paths": char.stroke_paths,
        "jlpt_level": char.jlpt_level,
        "topic": char.topic,
        "compounds": [
            {"id": v.id, "kanji": v.kanji, "reading": v.reading, "meaning": v.meaning}
            for v in compounds
        ],
    }


class RecognizeRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded PNG of the drawn character")


@app.post("/kanji/recognize")
def recognize_kanji(
    body: RecognizeRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    # A submitted drawing attempt is the countable writing-practice
    # activity -- counts toward the streak whether or not it's
    # recognized correctly (attempting is what counts, not accuracy).
    _record_activity_day(db, user.id)
    db.commit()

    result = call_with_retry(
        db,
        user_id=user.id,
        agent_name="KanjiRecognition",
        tool_name="recognize_character",
        fn=lambda: recognize_character(body.image_base64),
        fallback={
            "character": None,
            "confidence": 0.0,
            "message": "Couldn't read your drawing, try again.",
        },
    )

    if result.get("character") is None and "message" not in result:
        result["message"] = "Couldn't read your drawing, try again."

    return result


class KanjiFeedbackRequest(BaseModel):
    character_id: str = Field(..., description="id of the target WritingCharacter")
    recognized_character: Optional[str] = Field(default=None, description="what POST /kanji/recognize returned")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    mode: str = Field(
        default="practice",
        description="'practice' (Learn > Writing, default) doesn't log mistakes -- only 'drill' does",
    )


@app.post("/kanji/feedback")
def kanji_feedback(
    body: KanjiFeedbackRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    char = db.query(models.WritingCharacter).filter(models.WritingCharacter.id == body.character_id).first()
    if char is None:
        raise HTTPException(status_code=404, detail="kanji not found")

    is_correct = body.recognized_character == char.character
    prior_mistakes = (
        db.query(models.UserMistake)
        .filter(
            models.UserMistake.user_id == user.id,
            models.UserMistake.content_type == "writing",
            models.UserMistake.content_id == char.id,
        )
        .count()
    )
    is_first_correct = is_correct and prior_mistakes == 0

    result = run_tutor_agent(
        db,
        user.id,
        char.id,
        char.character,
        body.recognized_character,
        body.confidence,
        is_correct,
        mode=body.mode,
    )

    db.add(
        models.AgentLog(
            user_id=user.id,
            agent_name="TutorAgent",
            reasoning=result["feedback"],
            tool_calls=result["tool_calls"],
            decision={"feedback": result["feedback"], "is_correct": is_correct},
        )
    )
    db.commit()

    return {
        "feedback": result["feedback"],
        "is_correct": is_correct,
        "is_first_correct": is_first_correct,
    }


# --- Learnt / Drill enrollment ---


class LearnRequest(BaseModel):
    content_type: str = Field(..., description="'vocab' or 'grammar'")
    content_id: str = Field(..., description="id of the VocabCard or GrammarPattern")


@app.post("/learn")
def mark_learnt(
    body: LearnRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    existing = (
        db.query(models.UserLearntItem)
        .filter(
            models.UserLearntItem.user_id == user.id,
            models.UserLearntItem.content_type == body.content_type,
            models.UserLearntItem.content_id == body.content_id,
        )
        .first()
    )

    if existing is None:
        existing = models.UserLearntItem(
            user_id=user.id,
            content_type=body.content_type,
            content_id=body.content_id,
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

    return {
        "content_type": existing.content_type,
        "content_id": existing.content_id,
        "learnt_at": existing.learnt_at,
    }


@app.delete("/learn")
def unmark_learnt(
    body: LearnRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """Undoes a mistaken 'Mark as Learnt' tap."""
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    db.query(models.UserLearntItem).filter(
        models.UserLearntItem.user_id == user.id,
        models.UserLearntItem.content_type == body.content_type,
        models.UserLearntItem.content_id == body.content_id,
    ).delete()
    db.commit()

    return {"content_type": body.content_type, "content_id": body.content_id, "learnt": False}


class DrillAddRequest(BaseModel):
    content_type: str = Field(..., description="'vocab', 'writing', or 'grammar'")
    content_id: str = Field(..., description="id of the VocabCard, WritingCharacter, or GrammarPattern")


@app.post("/drill/add")
def add_to_drill(
    body: DrillAddRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    progress = (
        db.query(models.UserCardProgress)
        .filter(
            models.UserCardProgress.user_id == user.id,
            models.UserCardProgress.content_type == body.content_type,
            models.UserCardProgress.content_id == body.content_id,
        )
        .first()
    )

    if progress is None:
        now = datetime.utcnow()
        progress = models.UserCardProgress(
            user_id=user.id,
            content_type=body.content_type,
            content_id=body.content_id,
            ease_factor=2.5,
            repetitions=0,
            interval_days=1,
            next_review_date=now,  # immediately due, since it hasn't been reviewed yet
        )
        db.add(progress)
        db.commit()
        db.refresh(progress)

    return {
        "content_type": progress.content_type,
        "content_id": progress.content_id,
        "next_review_date": progress.next_review_date,
    }


@app.delete("/drill/add")
def remove_from_drill(
    body: DrillAddRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Undoes a mistaken 'Add to Drill' tap. This deletes all SM-2 progress
    for the item, not just a pause -- appropriate for "I didn't mean to
    add this," not for temporarily skipping a review.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    db.query(models.UserCardProgress).filter(
        models.UserCardProgress.user_id == user.id,
        models.UserCardProgress.content_type == body.content_type,
        models.UserCardProgress.content_id == body.content_id,
    ).delete()
    db.commit()

    return {"content_type": body.content_type, "content_id": body.content_id, "in_drill": False}


# --- Review / SRS endpoints ---

class ReviewGradeRequest(BaseModel):
    content_type: str = Field(..., description="'vocab', 'grammar', or 'writing'")
    content_id: str = Field(..., description="id of the VocabCard, GrammarPattern, or WritingCharacter")
    grade: int = Field(..., ge=0, le=5, description="0-5 self-graded recall score")


@app.post("/review/grade")
def grade_review(
    body: ReviewGradeRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    progress = (
        db.query(models.UserCardProgress)
        .filter(
            models.UserCardProgress.user_id == user.id,
            models.UserCardProgress.content_type == body.content_type,
            models.UserCardProgress.content_id == body.content_id,
        )
        .first()
    )
    if progress is None:
        raise HTTPException(
            status_code=404,
            detail="not in Drill yet. POST /drill/add first",
        )

    current_state = SRSState(
        ease_factor=progress.ease_factor,
        interval_days=progress.interval_days,
        repetitions=progress.repetitions,
    )

    now = datetime.utcnow()
    result = calculate_next_review(current_state, grade=body.grade, reviewed_at=now)

    progress.ease_factor = result.ease_factor
    progress.interval_days = result.interval_days
    progress.repetitions = result.repetitions
    progress.next_review_date = result.next_review_date
    progress.last_reviewed_at = now

    db.commit()
    db.refresh(progress)

    return {
        "content_type": progress.content_type,
        "content_id": progress.content_id,
        "ease_factor": progress.ease_factor,
        "interval_days": progress.interval_days,
        "repetitions": progress.repetitions,
        "next_review_date": progress.next_review_date,
    }


def _build_drill_question(db: Session, item: models.UserCardProgress) -> Optional[dict]:
    """
    Turns a due UserCardProgress row into a self-contained, ready-to-render
    question. vocab/grammar are multiple choice (the correct answer and
    distractors travel with the question -- this is a single-player
    self-check app, not a proctored exam, so there's no reason to hide it
    from the payload and force a second round trip to grade). writing has
    no options at all: it reuses the Day 7/8 draw-and-recognize flow
    instead, via POST /kanji/recognize + POST /kanji/feedback(mode="drill").
    """
    if item.content_type == "vocab":
        card = db.query(models.VocabCard).filter(models.VocabCard.id == item.content_id).first()
        if card is None:
            return None

        ask_reading = card.kanji is not None and random.random() < 0.5
        if ask_reading:
            question_kind = "reading"
            prompt = card.kanji
            correct = card.reading
            pool = (
                db.query(models.VocabCard.reading)
                .filter(
                    models.VocabCard.jlpt_level == card.jlpt_level,
                    models.VocabCard.id != card.id,
                    models.VocabCard.reading != correct,
                )
                .distinct()
                .all()
            )
        else:
            question_kind = "meaning"
            prompt = card.kanji or card.reading
            correct = card.meaning
            pool = (
                db.query(models.VocabCard.meaning)
                .filter(
                    models.VocabCard.jlpt_level == card.jlpt_level,
                    models.VocabCard.id != card.id,
                    models.VocabCard.meaning != correct,
                )
                .distinct()
                .all()
            )

        distractors = [row[0] for row in pool]
        random.shuffle(distractors)
        options = [correct] + distractors[:3]
        if len(options) < 2:
            return None  # not enough same-level content to build a fair question
        random.shuffle(options)

        return {
            "content_type": "vocab",
            "content_id": card.id,
            "question_kind": question_kind,
            "prompt": prompt,
            "options": options,
            "correct_answer": correct,
        }

    if item.content_type == "grammar":
        pattern = db.query(models.GrammarPattern).filter(models.GrammarPattern.id == item.content_id).first()
        if pattern is None or not pattern.drill_sentence:
            return None  # no drill_sentence -- can't build a fill-in-the-blank

        correct = pattern.pattern
        pool = (
            db.query(models.GrammarPattern.pattern)
            .filter(
                models.GrammarPattern.jlpt_level == pattern.jlpt_level,
                models.GrammarPattern.id != pattern.id,
                models.GrammarPattern.pattern != correct,
            )
            .distinct()
            .all()
        )
        distractors = [row[0] for row in pool]
        random.shuffle(distractors)
        options = [correct] + distractors[:3]
        if len(options) < 2:
            return None
        random.shuffle(options)

        return {
            "content_type": "grammar",
            "content_id": pattern.id,
            "drill_sentence": pattern.drill_sentence,
            "options": options,
            "correct_answer": correct,
        }

    if item.content_type == "writing":
        char = db.query(models.WritingCharacter).filter(models.WritingCharacter.id == item.content_id).first()
        if char is None:
            return None

        return {
            "content_type": "writing",
            "content_id": char.id,
            "character": char.character,
            "meaning": char.meaning,
            "romaji": char.romaji,
            "stroke_paths": char.stroke_paths,
        }

    return None


@app.get("/review/due")
def get_due_reviews(
    limit: int = Query(default=10, ge=1, le=50, description="Max questions to build"),
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Returns up to `limit` Drill questions, ordered as an SRS priority
    queue (most overdue / soonest-due first), not filtered to strictly
    due-today. Drill is meant to never dead-end: once something's been
    added, there's always a question to answer even if everything is
    technically "not due yet" -- next_review_date is used purely to
    decide what to ask *first*, not whether an item is askable at all.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    queue_items = (
        db.query(models.UserCardProgress)
        .filter(models.UserCardProgress.user_id == user.id)
        .order_by(models.UserCardProgress.next_review_date.asc())
        .limit(limit)
        .all()
    )

    questions = [_build_drill_question(db, item) for item in queue_items]
    questions = [q for q in questions if q is not None]

    # This is the Drill Play screen's entry point, so a non-empty
    # result here means the user is genuinely starting a drill --
    # counts toward the daily streak. An empty Drill (nothing added
    # yet) shouldn't count as "starting" anything.
    if questions:
        _record_activity_day(db, user.id)
        db.commit()

    return {"count": len(questions), "results": questions}


def _hydrate_session_item(db: Session, user: models.User, content_type: str, content_id: str) -> Optional[dict]:
    """
    Turns a bare (content_type, content_id) into the same shape GET
    /vocab / GET /grammar return, so the For You screen can render and
    navigate into the existing word/pattern detail screens without an
    extra round trip per item.
    """
    if content_type == "vocab":
        card = db.query(models.VocabCard).filter(models.VocabCard.id == content_id).first()
        if card is None:
            return None
        is_learnt = (
            db.query(models.UserLearntItem)
            .filter(
                models.UserLearntItem.user_id == user.id,
                models.UserLearntItem.content_type == "vocab",
                models.UserLearntItem.content_id == card.id,
            )
            .first()
            is not None
        )
        in_drill = (
            db.query(models.UserCardProgress)
            .filter(
                models.UserCardProgress.user_id == user.id,
                models.UserCardProgress.content_type == "vocab",
                models.UserCardProgress.content_id == card.id,
            )
            .first()
            is not None
        )
        characters = _characters_by_vocab_id(db, [card.id]).get(card.id, [])
        return {
            "content_type": "vocab",
            "id": card.id,
            "kanji": card.kanji,
            "reading": card.reading,
            "meaning": card.meaning,
            "example_sentence": card.example_sentence,
            "example_sentence_en": card.example_sentence_en,
            "example_sentence_furigana": card.example_sentence_furigana,
            "jlpt_level": card.jlpt_level,
            "topic": card.topic,
            "is_learnt": is_learnt,
            "in_drill": in_drill,
            "characters": characters,
        }

    elif content_type == "grammar":
        pattern = db.query(models.GrammarPattern).filter(models.GrammarPattern.id == content_id).first()
        if pattern is None:
            return None
        is_learnt = (
            db.query(models.UserLearntItem)
            .filter(
                models.UserLearntItem.user_id == user.id,
                models.UserLearntItem.content_type == "grammar",
                models.UserLearntItem.content_id == pattern.id,
            )
            .first()
            is not None
        )
        in_drill = (
            db.query(models.UserCardProgress)
            .filter(
                models.UserCardProgress.user_id == user.id,
                models.UserCardProgress.content_type == "grammar",
                models.UserCardProgress.content_id == pattern.id,
            )
            .first()
            is not None
        )
        return {
            "content_type": "grammar",
            "id": pattern.id,
            "pattern": pattern.pattern,
            "explanation": pattern.explanation,
            "example_sentence": pattern.example_sentence,
            "example_sentence_en": pattern.example_sentence_en,
            "example_sentence_furigana": pattern.example_sentence_furigana,
            "drill_sentence": pattern.drill_sentence,
            "jlpt_level": pattern.jlpt_level,
            "is_learnt": is_learnt,
            "in_drill": in_drill,
        }

    return None


def _session_response(db: Session, user: models.User, learning_session: models.LearningSession) -> dict:
    items = (
        db.query(models.SessionItem)
        .filter(models.SessionItem.session_id == learning_session.id)
        .order_by(models.SessionItem.order_index)
        .all()
    )
    hydrated = [_hydrate_session_item(db, user, si.content_type, si.content_id) for si in items]

    return {
        "session_id": learning_session.id,
        "status": learning_session.status,
        "reasoning": learning_session.reasoning or "",
        "items": [item for item in hydrated if item is not None],
    }


@app.post("/session/generate")
def generate_session(
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    # Counts toward the daily streak regardless of which branch below
    # runs (new session or handing back an existing one) -- either way
    # the user is starting/continuing a Learning Session today.
    _record_activity_day(db, user.id)
    db.commit()

    # Only one active For You session at a time -- if one's already in
    # progress, hand that back instead of generating (and orphaning) a
    # second one. The mobile app should check GET /session/current
    # first, but guard here too in case it's called directly.
    existing = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "for_you",
            models.LearningSession.status == "in_progress",
        )
        .order_by(models.LearningSession.created_at.desc())
        .first()
    )
    if existing is not None:
        return _session_response(db, user, existing)

    agent_result = run_session_builder_agent(db, user.id, item_count=user.session_item_count)
    session_plan = agent_result["session_plan"]
    # Expected shape of session_plan:
    # {
    #   "reasoning": "...",
    #   "items": [{"content_type": "vocab"|"grammar", "content_id": "..."}]
    # }

    # Create the actual LearningSession row
    learning_session = models.LearningSession(
        user_id=user.id,
        session_type="for_you",
        status="in_progress",
        reasoning=session_plan.get("reasoning", ""),
    )
    db.add(learning_session)
    db.flush()  # need learning_session.id before creating SessionItems

    # Create one SessionItem per item in the agent's plan
    for index, item in enumerate(session_plan.get("items", [])):
        db.add(
            models.SessionItem(
                session_id=learning_session.id,
                content_type=item["content_type"],
                content_id=item["content_id"],
                order_index=index,
            )
        )

    # Log the agent's full reasoning + tool call trace for observability
    agent_log = models.AgentLog(
        user_id=user.id,
        agent_name="SessionBuilderAgent",
        reasoning=session_plan.get("reasoning", ""),
        tool_calls=agent_result["tool_calls"],
        decision=session_plan,
    )
    db.add(agent_log)

    db.commit()
    db.refresh(learning_session)

    return _session_response(db, user, learning_session)


@app.get("/session/current")
def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """Returns the user's active (in_progress) For You session, or null."""
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "for_you",
            models.LearningSession.status == "in_progress",
        )
        .order_by(models.LearningSession.created_at.desc())
        .first()
    )
    if learning_session is None:
        return None

    item_count = (
        db.query(models.SessionItem)
        .filter(models.SessionItem.session_id == learning_session.id)
        .count()
    )
    return {
        "session_id": learning_session.id,
        "item_count": item_count,
        "created_at": learning_session.created_at,
    }


@app.get("/session/{session_id}")
def get_session(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(models.LearningSession.id == session_id, models.LearningSession.user_id == user.id)
        .first()
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="session not found")

    return _session_response(db, user, learning_session)


@app.post("/session/{session_id}/finish")
def finish_session(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Officially confirms every item in this session as Learnt (so
    fetch_new_content won't suggest them again) and marks the session
    completed. This is the moment items become "known" -- not the
    individual per-card actions during the session.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(models.LearningSession.id == session_id, models.LearningSession.user_id == user.id)
        .first()
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if learning_session.status != "in_progress":
        raise HTTPException(status_code=400, detail="session is not in progress")

    items = (
        db.query(models.SessionItem)
        .filter(models.SessionItem.session_id == learning_session.id)
        .all()
    )

    learnt_count = 0
    for item in items:
        if item.content_type not in ("vocab", "grammar"):
            continue
        exists = (
            db.query(models.UserLearntItem)
            .filter(
                models.UserLearntItem.user_id == user.id,
                models.UserLearntItem.content_type == item.content_type,
                models.UserLearntItem.content_id == item.content_id,
            )
            .first()
        )
        if exists is None:
            db.add(
                models.UserLearntItem(
                    user_id=user.id,
                    content_type=item.content_type,
                    content_id=item.content_id,
                )
            )
            learnt_count += 1

    learning_session.status = "completed"
    learning_session.completed_at = datetime.utcnow()
    db.commit()

    return {"completed": True, "learnt_count": learnt_count}


# --- Drill session recording ---


class DrillResultItem(BaseModel):
    content_type: str = Field(..., description="'vocab', 'grammar', or 'writing'")
    content_id: str
    is_correct: bool
    user_answer: Optional[str] = Field(default=None, description="the option text or recognized character")


class DrillCompleteRequest(BaseModel):
    results: List[DrillResultItem]


@app.post("/drill/complete")
def complete_drill(
    body: DrillCompleteRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Finalizes a Drill run: grades every answered item's SM-2 state in one
    shot (right/wrong is objective here, so correct maps to grade 5 and
    incorrect to grade 1 -- no self-assessment scale like /review/grade's
    freeform 0-5), and records the whole run as a completed LearningSession
    (session_type="drill") with one SessionItem per question, mirroring
    how For You sessions are persisted.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    if not body.results:
        raise HTTPException(status_code=400, detail="no results to record")

    learning_session = models.LearningSession(
        user_id=user.id,
        session_type="drill",
        status="completed",
        completed_at=datetime.utcnow(),
    )
    db.add(learning_session)
    db.flush()

    now = datetime.utcnow()
    correct_count = 0

    for index, result in enumerate(body.results):
        progress = (
            db.query(models.UserCardProgress)
            .filter(
                models.UserCardProgress.user_id == user.id,
                models.UserCardProgress.content_type == result.content_type,
                models.UserCardProgress.content_id == result.content_id,
            )
            .first()
        )
        # progress should always exist -- these came from GET /review/due,
        # which only ever returns items already in Drill -- but if it was
        # removed from Drill mid-run, still record the answer and just
        # skip the now-meaningless SRS update rather than failing the batch.
        if progress is not None:
            current_state = SRSState(
                ease_factor=progress.ease_factor,
                interval_days=progress.interval_days,
                repetitions=progress.repetitions,
            )
            grade = 5 if result.is_correct else 1
            srs_result = calculate_next_review(current_state, grade=grade, reviewed_at=now)
            progress.ease_factor = srs_result.ease_factor
            progress.interval_days = srs_result.interval_days
            progress.repetitions = srs_result.repetitions
            progress.next_review_date = srs_result.next_review_date
            progress.last_reviewed_at = now

        db.add(
            models.SessionItem(
                session_id=learning_session.id,
                content_type=result.content_type,
                content_id=result.content_id,
                order_index=index,
                is_correct=result.is_correct,
                user_answer=result.user_answer,
            )
        )
        if result.is_correct:
            correct_count += 1

    db.commit()

    return {
        "session_id": learning_session.id,
        "correct_count": correct_count,
        "total": len(body.results),
    }


def _describe_drill_item(db: Session, content_type: str, content_id: str) -> Optional[dict]:
    """
    Turns a bare (content_type, content_id) from a finished SessionItem
    into a human-readable {prompt, correct_answer} pair for
    DrillReviewAgent's transcript -- distinct from _build_drill_question,
    which builds a *forward-looking* question (with distractors) rather
    than a plain description of what was asked and what the right answer
    actually was.
    """
    if content_type == "vocab":
        card = db.query(models.VocabCard).filter(models.VocabCard.id == content_id).first()
        if card is None:
            return None
        return {
            "prompt": card.kanji or card.reading,
            "correct_answer": f"{card.reading} -- {card.meaning}",
        }

    if content_type == "grammar":
        pattern = db.query(models.GrammarPattern).filter(models.GrammarPattern.id == content_id).first()
        if pattern is None:
            return None
        return {
            "prompt": pattern.drill_sentence or pattern.pattern,
            "correct_answer": f"{pattern.pattern} -- {pattern.explanation}",
        }

    if content_type == "writing":
        char = db.query(models.WritingCharacter).filter(models.WritingCharacter.id == content_id).first()
        if char is None:
            return None
        return {
            "prompt": f"draw the character for: {char.meaning}",
            "correct_answer": char.character,
        }

    return None


@app.post("/drill/{session_id}/review")
def get_drill_review(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    On-demand "AI Detailed Feedback" for a completed Drill run. Calls
    QuizReviewAgent with the full transcript, hydrated from SessionItem
    + the underlying content rows (no agent-side DB lookups needed --
    see quiz_review.py). Separate endpoint from /drill/complete on
    purpose: this costs a real LLM call, so it only runs if the user
    actually asks for it.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.id == session_id,
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "drill",
        )
        .first()
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="drill session not found")

    session_items = (
        db.query(models.SessionItem)
        .filter(models.SessionItem.session_id == learning_session.id)
        .order_by(models.SessionItem.order_index)
        .all()
    )

    items = []
    for si in session_items:
        described = _describe_drill_item(db, si.content_type, si.content_id)
        if described is None:
            continue
        items.append(
            {
                "content_type": si.content_type,
                "prompt": described["prompt"],
                "user_answer": si.user_answer,
                "correct_answer": described["correct_answer"],
                "is_correct": si.is_correct,
            }
        )

    if not items:
        raise HTTPException(status_code=400, detail="nothing to review")

    result = run_quiz_review_agent(db, user.id, items, session_label="Drill")

    db.add(
        models.AgentLog(
            user_id=user.id,
            agent_name="QuizReviewAgent",
            reasoning=result["review"],
            decision={"session_id": learning_session.id},
        )
    )
    db.commit()

    return {"review": result["review"]}


# --- Reading module ---

READING_UNLOCK_THRESHOLD = 10


def _reading_response(learning_session: models.LearningSession) -> dict:
    """
    Shapes a reading LearningSession row (payload JSON + top-level
    columns) into the response GET/POST reading endpoints all share --
    generate, history detail, and post-complete all return this same
    shape so the mobile screen doesn't need separate types for "freshly
    generated" vs. "resumed from history".
    """
    body = learning_session.payload or {}
    return {
        "session_id": learning_session.id,
        "status": learning_session.status,
        "reasoning": learning_session.reasoning or "",
        "passage": body.get("passage", ""),
        "passage_furigana": body.get("passage_furigana"),
        "questions": body.get("questions", []),
        "answers": body.get("answers"),
        "score": body.get("score"),
        "review": body.get("review"),
        "created_at": learning_session.created_at,
    }


def _generate_reading_review(db: Session, user_id: str, learning_session: models.LearningSession) -> str:
    """
    Builds the Q&A transcript from a reading session's stored questions +
    answers and calls QuizReviewAgent. Shared by /complete (auto-called
    right after grading) and /review (manual regenerate/backfill for
    older sessions completed before this existed). Does not commit --
    callers own the transaction.
    """
    body = learning_session.payload or {}
    questions = body.get("questions", [])
    answers = body.get("answers", [])

    items = [
        {
            "content_type": "reading",
            "prompt": q.get("question"),
            "user_answer": answers[i] if i < len(answers) else None,
            "correct_answer": q.get("correct_answer"),
            "is_correct": (answers[i] if i < len(answers) else None) == q.get("correct_answer"),
        }
        for i, q in enumerate(questions)
    ]
    if not items:
        return ""

    result = run_quiz_review_agent(db, user_id, items, session_label="Reading")

    db.add(
        models.AgentLog(
            user_id=user_id,
            agent_name="QuizReviewAgent",
            reasoning=result["review"],
            decision={"session_id": learning_session.id},
        )
    )

    return result["review"]


@app.post("/reading/generate")
def generate_reading(
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Runs ReadingGeneratorAgent and persists a brand-new in-progress
    reading session (passage + questions, no answers yet). Always
    creates a fresh one -- unlike For You, Reading has no "one active
    session" limit, since re-reading practice is meant to be repeatable
    rather than a single curated daily batch. Gated on having learnt
    enough content first -- with fewer than READING_UNLOCK_THRESHOLD
    words/grammar marked Learnt, there's nothing real to meaningfully
    constrain a passage to.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learnt_count = (
        db.query(models.UserLearntItem).filter(models.UserLearntItem.user_id == user.id).count()
    )
    if learnt_count < READING_UNLOCK_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail=f"Learn at least {READING_UNLOCK_THRESHOLD} words or grammar patterns first to unlock Reading.",
        )

    _record_activity_day(db, user.id)
    db.commit()

    agent_result = run_reading_generator_agent(db, user.id)
    plan = agent_result["plan"]

    learning_session = models.LearningSession(
        user_id=user.id,
        session_type="reading",
        status="in_progress",
        reasoning=plan.get("reasoning", ""),
        payload={
            "passage": plan.get("passage", ""),
            "passage_furigana": plan.get("passage_furigana"),
            "questions": plan.get("questions", []),
        },
    )
    db.add(learning_session)
    db.flush()

    db.add(
        models.AgentLog(
            user_id=user.id,
            agent_name="ReadingGeneratorAgent",
            reasoning=plan.get("reasoning", ""),
            tool_calls=agent_result["tool_calls"],
            decision={"session_id": learning_session.id, **plan},
        )
    )
    db.commit()
    db.refresh(learning_session)

    return _reading_response(learning_session)


@app.get("/reading/history")
def get_reading_history(
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """The "board of previous readings" -- every reading session (in progress or completed), newest first."""
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    sessions = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "reading",
        )
        .order_by(models.LearningSession.created_at.desc())
        .limit(30)
        .all()
    )

    results = []
    for s in sessions:
        body = s.payload or {}
        passage = body.get("passage", "")
        results.append(
            {
                "session_id": s.id,
                "status": s.status,
                "passage_preview": passage[:40] + ("..." if len(passage) > 40 else ""),
                "score": body.get("score"),
                "total": len(body.get("questions", [])),
                "created_at": s.created_at,
            }
        )

    return {"results": results}


@app.get("/reading/{session_id}")
def get_reading(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """Fetches one reading session (in progress, to resume, or completed, to review) by id."""
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.id == session_id,
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "reading",
        )
        .first()
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="reading session not found")

    return _reading_response(learning_session)


class ReadingCompleteRequest(BaseModel):
    answers: List[Optional[str]] = Field(..., description="the picked option text per question, in order")
    looked_up_vocab_ids: List[str] = Field(default_factory=list)


@app.post("/reading/{session_id}/complete")
def complete_reading(
    session_id: str,
    body: ReadingCompleteRequest,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Grades the comprehension answers against the questions stored at
    generation time (not client-reported, so the score can't drift from
    what was actually asked), stores the answers/score back onto the
    session, marks it completed, and immediately generates the AI
    Detailed Feedback in the same request -- saved onto the session so
    it's there instantly on every future GET /reading/{id}, no separate
    on-demand call needed. Also logs any vocab the user looked up
    mid-passage (via GET /vocab/lookup on a tapped word) -- NOT
    auto-added to Drill, the user has to explicitly tap Add to Drill if
    they want it scheduled, consistent with the Learnt/Drill split.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.id == session_id,
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "reading",
        )
        .first()
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="reading session not found")
    if learning_session.status != "in_progress":
        raise HTTPException(status_code=400, detail="reading session is not in progress")

    questions = (learning_session.payload or {}).get("questions", [])
    if len(body.answers) != len(questions):
        raise HTTPException(status_code=400, detail="answers length does not match questions length")

    score = sum(
        1 for answer, q in zip(body.answers, questions) if answer == q.get("correct_answer")
    )

    learning_session.payload = {
        **(learning_session.payload or {}),
        "answers": body.answers,
        "score": score,
    }
    learning_session.status = "completed"
    learning_session.completed_at = datetime.utcnow()

    review = _generate_reading_review(db, user.id, learning_session)
    learning_session.payload = {**learning_session.payload, "review": review}
    db.flush()

    for index, vocab_id in enumerate(body.looked_up_vocab_ids):
        db.add(
            models.SessionItem(
                session_id=learning_session.id,
                content_type="vocab",
                content_id=vocab_id,
                order_index=index,
            )
        )

    db.commit()

    return {"score": score, "total": len(questions), "review": review}


@app.post("/reading/{session_id}/review")
def get_reading_review(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Regenerates AI Detailed Feedback for a completed Reading session.
    Normally not needed -- /complete auto-generates and saves it -- this
    exists as a backfill/retry path for sessions completed before that
    existed, or if the auto-generated one used the generic retry
    fallback message and the user wants a real attempt.
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.id == session_id,
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "reading",
        )
        .first()
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="reading session not found")
    if learning_session.status != "completed":
        raise HTTPException(status_code=400, detail="reading session is not completed yet")

    review = _generate_reading_review(db, user.id, learning_session)
    if not review:
        raise HTTPException(status_code=400, detail="nothing to review")

    learning_session.payload = {**(learning_session.payload or {}), "review": review}
    db.commit()

    return {"review": review}


@app.post("/reading/{session_id}/redo")
def redo_reading(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    """
    Resets a completed reading session back to in_progress so the user
    can answer the same passage's comprehension questions again --
    clears answers/score/review but keeps the passage and questions
    themselves (this is "redo the questions", not "generate a new
    passage" -- that's what + New Reading is for).
    """
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    learning_session = (
        db.query(models.LearningSession)
        .filter(
            models.LearningSession.id == session_id,
            models.LearningSession.user_id == user.id,
            models.LearningSession.session_type == "reading",
        )
        .first()
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="reading session not found")
    if learning_session.status != "completed":
        raise HTTPException(status_code=400, detail="reading session is not completed yet")

    learning_session.payload = {
        "passage": (learning_session.payload or {}).get("passage", ""),
        "passage_furigana": (learning_session.payload or {}).get("passage_furigana"),
        "questions": (learning_session.payload or {}).get("questions", []),
    }
    learning_session.status = "in_progress"
    learning_session.completed_at = None
    db.commit()
    db.refresh(learning_session)

    return _reading_response(learning_session)
