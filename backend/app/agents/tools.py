"""
Tool functions for SessionBuilderAgent.

Each function here corresponds 1:1 to a tool the model can call. They
are plain Python functions that take a db session + arguments and
return plain JSON-serializable dicts/lists -- no LLM-vendor-specific
code here, that lives in the agent orchestration layer
(session_builder.py) and the provider abstraction (llm.py).
"""

from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

from app import models


def get_weak_areas(db: Session, user_id: str) -> dict:
    """
    Returns specific content items the user has struggled with, grouped
    by (content_type, content_id, error_type).
    This means the agent gets back "you've gotten 食 wrong twice on
    stroke order" rather than just "writing/stroke_order: 2 mistakes",
    so it can target that exact item rather than a vague category.
    """
    results = (
        db.query(
            models.UserMistake.content_type,
            models.UserMistake.content_id,
            models.UserMistake.error_type,
            func.count(models.UserMistake.id).label("count"),
        )
        .filter(models.UserMistake.user_id == user_id)
        .group_by(
            models.UserMistake.content_type,
            models.UserMistake.content_id,
            models.UserMistake.error_type,
        )
        .order_by(func.count(models.UserMistake.id).desc())
        .limit(10)
        .all()
    )
    '''
        content_type='writing', content_id='a1b2c3-id-of-食',           error_type='stroke_order',  count=2
        content_type='grammar', content_id='d4e5f6-id-of-ます-pattern', error_type='wrong_form',    count=1
    '''
    weak_areas = []
    for row in results:
        display_label = _resolve_content_label(db, row.content_type, row.content_id)

        weak_areas.append({
            "content_type": row.content_type,
            "content_id": row.content_id,
            "display_label": display_label,
            "error_type": row.error_type,
            "mistake_count": row.count,
        })

    return {"weak_areas": weak_areas}


def _resolve_content_label(db: Session, content_type: str, content_id: str) -> str:
    """
    Resolves a content_id into a human-readable label (the actual
    character or word), so the agent's reasoning can mention specific
    content by NAME instead of just an opaque ID.
    """
    if content_type == "writing":
        item = db.query(models.WritingCharacter).filter(
            models.WritingCharacter.id == content_id
        ).first()
        return item.character if item else "unknown"

    elif content_type == "vocab":
        item = db.query(models.VocabCard).filter(
            models.VocabCard.id == content_id
        ).first()
        return item.kanji if item else "unknown"

    elif content_type == "grammar":
        item = db.query(models.GrammarPattern).filter(
            models.GrammarPattern.id == content_id
        ).first()
        return item.pattern if item else "unknown"

    return "unknown"


def get_due_reviews(db: Session, user_id: str) -> dict:
    now = datetime.utcnow()

    due_items = (
        db.query(models.UserCardProgress)
        .filter(
            models.UserCardProgress.user_id == user_id,
            models.UserCardProgress.next_review_date <= now,
        )
        .order_by(models.UserCardProgress.next_review_date.asc())
        .limit(50)
        .all()
    )

    return {
        "due_count": len(due_items),
        "due_items": [
            {
                "content_type": item.content_type,
                "content_id": item.content_id,
                "ease_factor": item.ease_factor,
                "days_overdue": (now - item.next_review_date).days,
            }
            for item in due_items
        ],
    }


def _learnt_ids(db: Session, user_id: str, content_type: str) -> set:
    return {
        row.content_id
        for row in db.query(models.UserLearntItem.content_id).filter(
            models.UserLearntItem.user_id == user_id,
            models.UserLearntItem.content_type == content_type,
        )
    }


def fetch_new_content(db: Session, user_id: str, level: str, content_type: str, limit: int = 5) -> dict:
    """
    Returns content the user hasn't learnt yet, at a given JLPT level.
    Filters server-side against UserLearntItem (vocab/grammar only --
    writing has no "learnt" state of its own) rather than relying on
    the LLM to enumerate an exclude_ids list, which doesn't scale as
    My Words grows into the hundreds.
    """
    if content_type == "vocab":
        query = db.query(models.VocabCard).filter(models.VocabCard.jlpt_level == level)
        learnt = _learnt_ids(db, user_id, "vocab")
        if learnt:
            query = query.filter(models.VocabCard.id.notin_(learnt))
        items = query.limit(limit).all()
        return {
            "content_type": "vocab",
            "items": [
                {"id": i.id, "kanji": i.kanji, "reading": i.reading, "meaning": i.meaning}
                for i in items
            ],
        }

    elif content_type == "writing":
        items = (
            db.query(models.WritingCharacter)
            .filter(models.WritingCharacter.jlpt_level == level)
            .limit(limit)
            .all()
        )
        return {
            "content_type": "writing",
            "items": [
                {
                    "id": i.id,
                    "character": i.character,
                    "character_type": i.character_type,
                    "meaning": i.meaning,
                }
                for i in items
            ],
        }

    elif content_type == "grammar":
        query = db.query(models.GrammarPattern).filter(models.GrammarPattern.jlpt_level == level)
        learnt = _learnt_ids(db, user_id, "grammar")
        if learnt:
            query = query.filter(models.GrammarPattern.id.notin_(learnt))
        items = query.limit(limit).all()
        return {
            "content_type": "grammar",
            "items": [
                {"id": i.id, "pattern": i.pattern, "explanation": i.explanation}
                for i in items
            ],
        }

    return {"content_type": content_type, "items": [], "error": "unknown content_type"}


def get_kanji_data(db: Session, kanji_id: str) -> dict:
    char = db.query(models.WritingCharacter).filter(models.WritingCharacter.id == kanji_id).first()
    if char is None:
        return {"error": "kanji not found"}
    return {
        "character": char.character,
        "meaning": char.meaning,
        "stroke_count": char.stroke_count,
        "onyomi": char.onyomi,
        "kunyomi": char.kunyomi,
    }


def get_user_kanji_history(db: Session, user_id: str, kanji_id: str) -> dict:
    """
    Past mistakes logged for this user on this specific character, oldest
    first. There's no "total attempts" counter (successful attempts
    aren't logged anywhere), so this is a history of past *mistakes*
    only -- enough for the agent to say "you've struggled with this
    before" without needing a full attempt-by-attempt log.
    """
    mistakes = (
        db.query(models.UserMistake)
        .filter(
            models.UserMistake.user_id == user_id,
            models.UserMistake.content_type == "writing",
            models.UserMistake.content_id == kanji_id,
        )
        .order_by(models.UserMistake.created_at.asc())
        .all()
    )
    return {
        "past_mistake_count": len(mistakes),
        "past_error_types": [m.error_type for m in mistakes],
    }


def log_mistake(db: Session, user_id: str, kanji_id: str, error_type: str) -> dict:
    db.add(
        models.UserMistake(
            user_id=user_id, content_type="writing", content_id=kanji_id, error_type=error_type
        )
    )
    db.commit()
    return {"logged": True}


def get_known_vocab(db: Session, user_id: str, limit: int = 200) -> dict:
    """
    Vocab the user has explicitly marked Learnt -- the only words
    ReadingGeneratorAgent is allowed to build a passage from. Capped at
    `limit` (most recently learnt first) so the prompt doesn't grow
    unbounded as My Words grows into the hundreds.
    """
    rows = (
        db.query(models.UserLearntItem.content_id)
        .filter(
            models.UserLearntItem.user_id == user_id,
            models.UserLearntItem.content_type == "vocab",
        )
        .order_by(models.UserLearntItem.learnt_at.desc())
        .limit(limit)
        .all()
    )
    ids = [row.content_id for row in rows]
    if not ids:
        return {"count": 0, "items": []}

    cards = db.query(models.VocabCard).filter(models.VocabCard.id.in_(ids)).all()
    return {
        "count": len(cards),
        "items": [
            {"id": c.id, "kanji": c.kanji, "reading": c.reading, "meaning": c.meaning}
            for c in cards
        ],
    }


def get_known_grammar(db: Session, user_id: str, limit: int = 100) -> dict:
    """Grammar patterns the user has explicitly marked Learnt. See get_known_vocab."""
    rows = (
        db.query(models.UserLearntItem.content_id)
        .filter(
            models.UserLearntItem.user_id == user_id,
            models.UserLearntItem.content_type == "grammar",
        )
        .order_by(models.UserLearntItem.learnt_at.desc())
        .limit(limit)
        .all()
    )
    ids = [row.content_id for row in rows]
    if not ids:
        return {"count": 0, "items": []}

    patterns = db.query(models.GrammarPattern).filter(models.GrammarPattern.id.in_(ids)).all()
    return {
        "count": len(patterns),
        "items": [{"id": p.id, "pattern": p.pattern, "explanation": p.explanation} for p in patterns],
    }


def get_user_profile(db: Session, user_id: str) -> dict:
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if user is None:
        return {"error": "user not found"}

    last_session = (
        db.query(models.LearningSession)
        .filter(models.LearningSession.user_id == user_id)
        .order_by(models.LearningSession.created_at.desc())
        .first()
    )

    days_since_last_session = None
    if last_session is not None:
        days_since_last_session = (datetime.utcnow() - last_session.created_at).days

    return {
        "jlpt_level": user.jlpt_level,
        "streak_count": user.streak_count,
        "days_since_last_session": days_since_last_session,
    }
