from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials

from app.database import get_db
from app import models

app = FastAPI(title="Nihongo API")

clerk_config = ClerkConfig(
    jwks_url="https://decent-koi-28.clerk.accounts.dev/.well-known/jwks.json"
)
clerk_auth_guard = ClerkHTTPBearer(config=clerk_config)


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
    clerk_user_id = payload.get("sub")

    user = db.query(models.User).filter(
        models.User.clerk_user_id == clerk_user_id
    ).first()

    if user is None:
        email = payload.get("email")

        user = models.User(
            clerk_user_id=clerk_user_id,
            email=email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

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