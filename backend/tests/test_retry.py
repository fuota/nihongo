from unittest.mock import MagicMock, patch

from app.utils.retry import call_with_retry


def test_returns_result_on_first_success_without_logging():
    db = MagicMock()
    fn = MagicMock(return_value={"ok": True})

    result = call_with_retry(
        db,
        user_id="u1",
        agent_name="TestAgent",
        tool_name="some_tool",
        fn=fn,
        fallback={"ok": False},
    )

    assert result == {"ok": True}
    fn.assert_called_once()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_retries_then_succeeds_without_logging_failure():
    db = MagicMock()
    fn = MagicMock(side_effect=[RuntimeError("boom"), {"ok": True}])

    with patch("app.utils.retry.time.sleep") as mock_sleep:
        result = call_with_retry(
            db,
            user_id="u1",
            agent_name="TestAgent",
            tool_name="some_tool",
            fn=fn,
            fallback={"ok": False},
            max_attempts=3,
        )

    assert result == {"ok": True}
    assert fn.call_count == 2
    mock_sleep.assert_called_once_with(0.5)  # backoff before the 2nd attempt
    db.add.assert_not_called()


def test_exhausting_all_attempts_logs_failure_and_returns_fallback():
    db = MagicMock()
    fn = MagicMock(side_effect=RuntimeError("network is down"))

    with patch("app.utils.retry.time.sleep") as mock_sleep:
        result = call_with_retry(
            db,
            user_id="u1",
            agent_name="TestAgent",
            tool_name="get_weak_areas",
            fn=fn,
            fallback={"weak_areas": []},
            max_attempts=3,
        )

    assert result == {"weak_areas": []}
    assert fn.call_count == 3
    assert mock_sleep.call_args_list == [((0.5,),), ((1,),)]  # exponential backoff

    logged = db.add.call_args[0][0]
    assert logged.agent_name == "TestAgent"
    assert logged.tool_name == "get_weak_areas"
    assert logged.success is False
    assert logged.fallback_used is True
    assert "network is down" in logged.error_detail
    db.commit.assert_called_once()
