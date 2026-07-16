"""
FEAT-148 Task #2 — Tests for the character coins contract (currency_balance).

Covers:
1. CharacterShort schema tolerates a MISSING currency_balance key
   (old character-service without the field -> None, no ValidationError)
   and accepts a present integer value.
2. _fetch_character_short maps currency_balance from the character-service
   short_info response (None-safe via .get() when the key is absent).
3. GET /users/me carries character.currency_balance through to the payload
   (value present) and returns null gracefully when the field is missing
   (proves no lockstep deploy of character-service is required).
"""

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

import main
import models
from crud import create_user
from schemas import CharacterShort, UserCreate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHARACTER_ID = 7

# short_info payload as returned by an OLD character-service (no currency_balance)
SHORT_INFO_WITHOUT_COINS = {
    "id": CHARACTER_ID,
    "name": "Артория",
    "avatar": "artoria.webp",
    "level": 10,
    "current_location_id": None,
    "id_race": 1,
    "id_class": 1,
    "id_subrace": 1,
    "race_name": "Человек",
    "class_name": "Воин",
    "subrace_name": "Норд",
    "travel_cooldown_until": None,
}

# short_info payload as returned by the NEW character-service (FEAT-148)
SHORT_INFO_WITH_COINS = {**SHORT_INFO_WITHOUT_COINS, "currency_balance": 1500}


def _make_user(db, username="player1", email="player1@test.com",
               password="Pass1234", current_character=None):
    """Create a user via CRUD; optionally set the active character id."""
    user = create_user(db, UserCreate(email=email, username=username, password=password))
    if current_character is not None:
        db.query(models.User).filter(models.User.id == user.id).update(
            {models.User.current_character: current_character}
        )
        db.commit()
        db.refresh(user)
    return user


def _auth_header(user):
    """Build an Authorization header with a valid JWT for the given user."""
    from auth import create_access_token
    token = create_access_token(data={"sub": user.email}, role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _mock_httpx_client(short_info_payload):
    """Build a patched httpx.AsyncClient whose GET returns the given short_info JSON."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = short_info_payload
    mock_resp.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


# ---------------------------------------------------------------------------
# 1. CharacterShort schema — missing key must NOT raise (Pydantic v1)
# ---------------------------------------------------------------------------

class TestCharacterShortSchema:

    def test_missing_currency_balance_defaults_to_none(self):
        """Old character-service payload (no key) validates, field is None."""
        char = CharacterShort(id=1, name="Артория", avatar="artoria.webp")
        assert char.currency_balance is None

    def test_missing_key_does_not_raise_validation_error(self):
        """Full old-style payload without currency_balance must validate."""
        try:
            char = CharacterShort(**SHORT_INFO_WITHOUT_COINS)
        except ValidationError as exc:  # pragma: no cover
            pytest.fail(f"CharacterShort must tolerate missing currency_balance: {exc}")
        assert char.currency_balance is None

    def test_present_currency_balance_passes_through(self):
        char = CharacterShort(**SHORT_INFO_WITH_COINS)
        assert char.currency_balance == 1500

    def test_zero_currency_balance_preserved(self):
        """Boundary: 0 gold must stay 0, not become None/falsy-dropped."""
        char = CharacterShort(**{**SHORT_INFO_WITHOUT_COINS, "currency_balance": 0})
        assert char.currency_balance == 0


# ---------------------------------------------------------------------------
# 2. _fetch_character_short — mapping from character-service response
# ---------------------------------------------------------------------------

class TestFetchCharacterShort:

    def test_maps_currency_balance_from_short_info(self):
        """New character-service: value flows into the aggregated dict."""
        mock_client = _mock_httpx_client(SHORT_INFO_WITH_COINS)
        with patch("main.httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__.return_value = mock_client
            result = asyncio.run(main._fetch_character_short(CHARACTER_ID))

        assert result is not None
        assert result["currency_balance"] == 1500

    def test_missing_key_yields_none(self):
        """Old character-service: .get() must return None, no KeyError."""
        mock_client = _mock_httpx_client(SHORT_INFO_WITHOUT_COINS)
        with patch("main.httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__.return_value = mock_client
            result = asyncio.run(main._fetch_character_short(CHARACTER_ID))

        assert result is not None
        assert result["currency_balance"] is None
        # existing fields are still mapped
        assert result["id"] == CHARACTER_ID
        assert result["name"] == "Артория"
        assert result["level"] == 10


# ---------------------------------------------------------------------------
# 3. GET /users/me — currency_balance in the character payload
# ---------------------------------------------------------------------------

class TestMeCurrencyBalance:

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_me_returns_character_currency_balance(self, mock_fetch, client, db_session):
        """/users/me carries the coins value through to character payload."""
        mock_fetch.return_value = {
            "id": CHARACTER_ID,
            "name": "Артория",
            "avatar": "artoria.webp",
            "level": 10,
            "current_location": None,
            "currency_balance": 1500,
        }
        user = _make_user(db_session, current_character=CHARACTER_ID)

        resp = client.get("/users/me", headers=_auth_header(user))
        assert resp.status_code == 200
        data = resp.json()

        assert data["character"] is not None
        assert data["character"]["currency_balance"] == 1500

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_me_missing_currency_balance_returns_null(self, mock_fetch, client, db_session):
        """Old character-service (no key): /users/me returns null, not 500."""
        mock_fetch.return_value = {
            "id": CHARACTER_ID,
            "name": "Артория",
            "avatar": "artoria.webp",
            "level": 10,
            "current_location": None,
            # no currency_balance key — old character-service
        }
        user = _make_user(db_session, current_character=CHARACTER_ID)

        resp = client.get("/users/me", headers=_auth_header(user))
        assert resp.status_code == 200
        data = resp.json()

        assert data["character"] is not None
        assert "currency_balance" in data["character"]
        assert data["character"]["currency_balance"] is None

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_me_without_character_unaffected(self, mock_fetch, client, db_session):
        """User with no active character: character stays null (regression guard)."""
        user = _make_user(db_session)  # current_character is NULL

        resp = client.get("/users/me", headers=_auth_header(user))
        assert resp.status_code == 200
        assert resp.json()["character"] is None
