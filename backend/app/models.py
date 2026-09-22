import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Date,
    DateTime,
    ForeignKey,
    Text,
    JSON,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    clerk_user_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=True)
    # Display name, set once during onboarding ("How should we call you?").
    # Null means the user hasn't completed onboarding yet -- the mobile
    # app's AuthGate checks this to decide whether to show that screen.
    name = Column(String, nullable=True)
    # One of AVATAR_CHOICES in main.py -- an icon key, not an image URL.
    avatar = Column(String, nullable=False, default="cat")
    jlpt_level = Column(String, default="N5")
    streak_count = Column(Integer, default=0)
    last_session_at = Column(DateTime, nullable=True)
    session_item_count = Column(Integer, nullable=False, default=10)  # For You session size, 5-15
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("LearningSession", back_populates="user")
    mistakes = relationship("UserMistake", back_populates="user")
    card_progress = relationship("UserCardProgress", back_populates="user")
    agent_logs = relationship("AgentLog", back_populates="user")


class WritingCharacter(Base):
    __tablename__ = "writing_characters"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    character = Column(String, nullable=False, index=True)
    character_type = Column(String, nullable=False)

    romaji = Column(String, nullable=True)

    meaning = Column(String, nullable=True)
    onyomi = Column(JSON, nullable=True)
    kunyomi = Column(JSON, nullable=True)

    stroke_count = Column(Integer, nullable=False)
    stroke_paths = Column(JSON, nullable=False)
    jlpt_level = Column(String, default="N5")
    topic = Column(String, nullable=True)  # e.g. "numbers", "time_calendar" -- for grouping into modules

    created_at = Column(DateTime, default=datetime.utcnow)

    vocab_links = relationship("VocabCharacterLink", back_populates="character")


class VocabCard(Base):
    __tablename__ = "vocab_cards"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    kanji = Column(String, nullable=True)
    reading = Column(String, nullable=False)
    meaning = Column(String, nullable=False)
    example_sentence = Column(Text, nullable=True)
    example_sentence_en = Column(Text, nullable=True)
    # Ordered list of {"surface": str, "reading": str | None} chunks that
    # reconstruct example_sentence when concatenated. A non-null `reading`
    # marks a kanji-bearing chunk: the mobile app renders it as furigana
    # and makes it tappable (looked up via GET /vocab/lookup). Kana-only
    # chunks (particles, punctuation) have reading=None and aren't tappable.
    example_sentence_furigana = Column(JSON, nullable=True)
    jlpt_level = Column(String, default="N5")
    source = Column(String, nullable=False, default="seeded")  # "seeded" | "api_fetched" | "textbook"
    topic = Column(String, nullable=True)  # e.g. "numbers", "time_calendar" -- for grouping into modules
    created_at = Column(DateTime, default=datetime.utcnow)

    character_links = relationship("VocabCharacterLink", back_populates="vocab_card")


class VocabCharacterLink(Base):
    __tablename__ = "vocab_character_links"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    vocab_card_id = Column(UUID(as_uuid=False), ForeignKey("vocab_cards.id"), nullable=False)
    character_id = Column(UUID(as_uuid=False), ForeignKey("writing_characters.id"), nullable=False)

    vocab_card = relationship("VocabCard", back_populates="character_links")
    character = relationship("WritingCharacter", back_populates="vocab_links")


class GrammarPattern(Base):
    __tablename__ = "grammar_patterns"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    pattern = Column(String, nullable=False)
    explanation = Column(Text, nullable=False)
    example_sentence = Column(Text, nullable=True)
    example_sentence_en = Column(Text, nullable=True)
    example_sentence_furigana = Column(JSON, nullable=True)  # see VocabCard for shape
    drill_sentence = Column(Text, nullable=True)
    jlpt_level = Column(String, default="N5")
    created_at = Column(DateTime, default=datetime.utcnow)


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    session_type = Column(String, default="for_you")  # "for_you" | "drill" | "reading"
    status = Column(String, default="in_progress")
    reasoning = Column(Text, nullable=True)  # SessionBuilderAgent's reasoning, for later retrieval
    # Generic JSON bag for session-type-specific structured data that
    # doesn't fit SessionItem's fixed shape -- today only "reading" uses
    # it (passage, passage_furigana, questions, and once submitted,
    # answers/score), so a past reading can be resumed or re-reviewed
    # without regenerating it.
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")
    items = relationship("SessionItem", back_populates="session")


class SessionItem(Base):
    __tablename__ = "session_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(
        UUID(as_uuid=False), ForeignKey("learning_sessions.id"), nullable=False
    )
    content_type = Column(String, nullable=False)  # "vocab" | "writing" | "grammar" | "reading"
    content_id = Column(String, nullable=True)
    order_index = Column(Integer, default=0)
    is_correct = Column(Boolean, nullable=True)
    user_answer = Column(Text, nullable=True)

    session = relationship("LearningSession", back_populates="items")


class UserMistake(Base):
    __tablename__ = "user_mistakes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    content_id = Column(String, nullable=True)
    content_type = Column(String, nullable=False)  # "vocab" | "writing" | "grammar"
    error_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="mistakes")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    agent_name = Column(String, nullable=False)
    reasoning = Column(Text, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    decision = Column(JSON, nullable=True)
    tool_name = Column(String, nullable=True)
    success = Column(Boolean, nullable=True)
    fallback_used = Column(Boolean, nullable=False, default=False)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="agent_logs")


class UserCardProgress(Base):
    """
    SM-2 spaced repetition state. Exactly one row per (user, content_type,
    content_id) -- unlike UserMistake, this is NOT an event log. Each
    review updates this same row in place rather than inserting a new one.

    A row here means the item has been explicitly "added to Drill" --
    it is created once by POST /drill/add and from then on only updated
    by POST /review/grade, never re-created automatically.
    """
    __tablename__ = "user_card_progress"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    content_type = Column(String, nullable=False)  # "vocab" | "writing" | "grammar"
    content_id = Column(String, nullable=False)

    ease_factor = Column(Float, default=2.5)
    repetitions = Column(Integer, default=0)
    interval_days = Column(Integer, default=1)
    next_review_date = Column(DateTime, nullable=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="card_progress")


class UserLearntItem(Base):
    """
    Marks that a user has studied a vocab word or grammar pattern at least
    once (via Learn > Vocab/Grammar or For You). This is separate from
    UserCardProgress: being "Learnt" just feeds My Words/My Grammar and
    the Reading agent's known-vocab/known-grammar tools -- it does NOT put
    the item on an SRS schedule. Only an explicit "Add to Drill" does that.
    """
    __tablename__ = "user_learnt_items"
    __table_args__ = (
        UniqueConstraint("user_id", "content_type", "content_id", name="uq_user_learnt_item"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    content_type = Column(String, nullable=False)  # "vocab" | "grammar"
    content_id = Column(String, nullable=False)
    learnt_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class UserActivityDay(Base):
    """
    One row per (user, calendar date) the user did anything countable
    toward the daily streak: started a Learning Session, started a
    Reading, started a Drill, or attempted a writing-practice
    character. Written by main.py's _record_activity_day() helper.
    GET /me computes streak_count from consecutive rows here, rather
    than a stored counter that could drift out of sync.
    """
    __tablename__ = "user_activity_days"
    __table_args__ = (
        UniqueConstraint("user_id", "activity_date", name="uq_user_activity_day"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    activity_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
