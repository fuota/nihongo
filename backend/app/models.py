import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    Text,
    JSON,
    Boolean,
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
    jlpt_level = Column(String, default="N5")
    streak_count = Column(Integer, default=0)
    last_session_at = Column(DateTime, nullable=True)
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

    created_at = Column(DateTime, default=datetime.utcnow)

    vocab_links = relationship("VocabCharacterLink", back_populates="character")


class VocabCard(Base):
    __tablename__ = "vocab_cards"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    kanji = Column(String, nullable=True)
    reading = Column(String, nullable=False)
    meaning = Column(String, nullable=False)
    example_sentence = Column(Text, nullable=True)
    jlpt_level = Column(String, default="N5")
    source = Column(String, nullable=False, default="seeded")  # "seeded" | "api_fetched"
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
    drill_sentence = Column(Text, nullable=True)
    jlpt_level = Column(String, default="N5")
    created_at = Column(DateTime, default=datetime.utcnow)


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    mode = Column(String, default="serious")
    status = Column(String, default="in_progress")
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
    """
    __tablename__ = "user_card_progress"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    content_type = Column(String, nullable=False)  # "vocab" | "writing"
    content_id = Column(String, nullable=False)

    ease_factor = Column(Float, default=2.5)
    repetitions = Column(Integer, default=0)
    interval_days = Column(Integer, default=1)
    next_review_date = Column(DateTime, nullable=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="card_progress")
