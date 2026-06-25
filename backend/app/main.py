from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials

from app.database import get_db
from app import models
from app.srs import calculate_next_review, SRSState

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

    return {
        "id": user.id,
        "clerk_user_id": user.clerk_user_id,
        "email": user.email,
        "jlpt_level": user.jlpt_level,
        "streak_count": user.streak_count,
        "created_at": user.created_at,
    }


@app.get("/vocab")
def get_vocab(
    level: str = Query(default="N5", description="JLPT level, e.g. N5"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results to return"),
    db: Session = Depends(get_db),
):
    vocab_cards = (
        db.query(models.VocabCard)
        .filter(models.VocabCard.jlpt_level == level)
        .limit(limit)
        .all()
    )

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
                "jlpt_level": card.jlpt_level,
            }
            for card in vocab_cards
        ],
    }


# --- Review / SRS endpoints ---

class ReviewGradeRequest(BaseModel):
    content_type: str = Field(..., description="'vocab' or 'writing'")
    content_id: str = Field(..., description="id of the VocabCard or WritingCharacter")
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
        current_state = SRSState(ease_factor=2.5, interval_days=1, repetitions=0)
    else:
        current_state = SRSState(
            ease_factor=progress.ease_factor,
            interval_days=progress.interval_days,
            repetitions=progress.repetitions,
        )

    now = datetime.utcnow()
    result = calculate_next_review(current_state, grade=body.grade, reviewed_at=now)

    if progress is None:
        progress = models.UserCardProgress(
            user_id=user.id,
            content_type=body.content_type,
            content_id=body.content_id,
        )
        db.add(progress)

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


@app.get("/review/due")
def get_due_reviews(
    credentials: HTTPAuthorizationCredentials = Depends(clerk_auth_guard),
    db: Session = Depends(get_db),
):
    payload = credentials.decoded
    user = get_or_create_user(db, payload.get("sub"), payload.get("email"))

    now = datetime.utcnow()

    due_items = (
        db.query(models.UserCardProgress)
        .filter(
            models.UserCardProgress.user_id == user.id,
            models.UserCardProgress.next_review_date <= now,
        )
        .all()
    )

    return {
        "count": len(due_items),
        "results": [
            {
                "content_type": item.content_type,
                "content_id": item.content_id,
                "ease_factor": item.ease_factor,
                "interval_days": item.interval_days,
                "repetitions": item.repetitions,
                "next_review_date": item.next_review_date,
                "last_reviewed_at": item.last_reviewed_at,
            }
            for item in due_items
        ],
    }