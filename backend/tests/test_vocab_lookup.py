from unittest.mock import MagicMock, patch

import requests

from app.services.vocab_lookup import get_or_fetch_word


def _mock_db_returning(existing_card):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing_card
    return db


def test_returns_existing_card_without_calling_api():
    existing = MagicMock(
        id="abc",
        kanji="水",
        reading="みず",
        meaning="water",
        example_sentence="水を飲みます。",
        jlpt_level="N5",
        source="seeded",
    )
    db = _mock_db_returning(existing)

    with patch("app.services.vocab_lookup.requests.get") as mock_get:
        result = get_or_fetch_word(db, "水")

    mock_get.assert_not_called()
    assert result["status"] == "found_in_db"
    assert result["kanji"] == "水"
    assert result["source"] == "seeded"


def test_fetches_from_api_and_persists_on_success():
    db = _mock_db_returning(None)

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "data": [
            {
                "japanese": [{"word": "犬", "reading": "いぬ"}],
                "senses": [{"english_definitions": ["dog"]}],
                "jlpt": ["jlpt-n5"],
            }
        ]
    }
    fake_response.raise_for_status.return_value = None

    with patch("app.services.vocab_lookup.requests.get", return_value=fake_response) as mock_get:
        result = get_or_fetch_word(db, "犬")

    mock_get.assert_called_once()
    assert result["status"] == "fetched_from_api"
    assert result["kanji"] == "犬"
    assert result["reading"] == "いぬ"
    assert result["jlpt_level"] == "N5"

    added_card = db.add.call_args[0][0]
    assert added_card.source == "api_fetched"
    db.commit.assert_called_once()


def test_api_network_failure_returns_typed_unavailable_result():
    db = _mock_db_returning(None)

    with patch(
        "app.services.vocab_lookup.requests.get",
        side_effect=requests.exceptions.ConnectionError("network is down"),
    ):
        result = get_or_fetch_word(db, "unknownword")

    assert result == {
        "status": "unavailable",
        "word": "unknownword",
        "reason": "Jisho API request failed: network is down",
    }
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_word_not_found_on_jisho_returns_unavailable():
    db = _mock_db_returning(None)

    fake_response = MagicMock()
    fake_response.json.return_value = {"data": []}
    fake_response.raise_for_status.return_value = None

    with patch("app.services.vocab_lookup.requests.get", return_value=fake_response):
        result = get_or_fetch_word(db, "asdfghjkl")

    assert result["status"] == "unavailable"
    assert result["word"] == "asdfghjkl"
    db.add.assert_not_called()
