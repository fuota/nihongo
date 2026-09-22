"""
Shared retry/fallback helper for agent tool calls.

Retries a tool call a few times with exponential backoff; if every
attempt fails, logs the failure to AgentLog (tool_name, success=False,
fallback_used=True, error_detail) and returns a caller-supplied
fallback value instead of raising. This is written once here and
reused by every agent that calls tools (SessionBuilderAgent today;
the kanji feedback flow, TutorAgent, and ProgressEvaluatorAgent
later) so retry/fallback behavior stays consistent instead of being
reimplemented per agent.
"""

import time
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app import models

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 0.5


def call_with_retry(
    db: Session,
    *,
    user_id: str,
    agent_name: str,
    tool_name: str,
    fn: Callable[[], T],
    fallback: T,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
) -> T:
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(base_delay * (2 ** (attempt - 1)))  # 0.5s, 1s, 2s, ...
        try:
            return fn()
        except Exception as e:
            last_error = e
            # A DB-level error (not just a network/API error) leaves the
            # session's transaction in a failed state -- every later
            # query on it (further retries, or the AgentLog write below)
            # would raise "current transaction is aborted" otherwise.
            db.rollback()

    db.add(
        models.AgentLog(
            user_id=user_id,
            agent_name=agent_name,
            tool_name=tool_name,
            success=False,
            fallback_used=True,
            error_detail=str(last_error),
        )
    )
    db.commit()

    return fallback
