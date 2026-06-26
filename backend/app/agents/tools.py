"""
Tool functions for SessionBuilderAgent.

Each function here corresponds 1:1 to a tool Claude can call. They are
plain Python functions that take a db session + arguments and return
plain JSON-serializable dicts/lists -- no Anthropic-specific code here,
that lives in the agent orchestration layer (session_builder.py).
"""

from datetime import datetime
from typing import List

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


def fetch_new_content(
    db: Session, level: str, content_type: str, exclude_ids: List[str], limit: int = 5
) -> dict:
    if content_type == "vocab":
        query = db.query(models.VocabCard).filter(models.VocabCard.jlpt_level == level)
        if exclude_ids:
            query = query.filter(models.VocabCard.id.notin_(exclude_ids))
        items = query.limit(limit).all()
        return {
            "content_type": "vocab",
            "items": [
                {"id": i.id, "kanji": i.kanji, "reading": i.reading, "meaning": i.meaning}
                for i in items
            ],
        }

    elif content_type == "writing":
        query = db.query(models.WritingCharacter).filter(
            models.WritingCharacter.jlpt_level == level
        )
        if exclude_ids:
            query = query.filter(models.WritingCharacter.id.notin_(exclude_ids))
        items = query.limit(limit).all()
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
        query = db.query(models.GrammarPattern).filter(
            models.GrammarPattern.jlpt_level == level
        )
        if exclude_ids:
            query = query.filter(models.GrammarPattern.id.notin_(exclude_ids))
        items = query.limit(limit).all()
        return {
            "content_type": "grammar",
            "items": [
                {"id": i.id, "pattern": i.pattern, "explanation": i.explanation}
                for i in items
            ],
        }

    return {"content_type": content_type, "items": [], "error": "unknown content_type"}


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
