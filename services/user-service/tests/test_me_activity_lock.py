"""FEAT-175: /users/me carries the current character's activity lock
(dungeon run / knocked out) so the frontend can show a banner."""

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import main
import models
from crud import create_user
from schemas import CharacterShort, UserCreate

LOCK = {"locked": True, "reason": "unconscious", "until": "2026-10-22T20:30:00", "dungeon_session_id": None}
SHORT_INFO = {
    "id": 7, "name": "Артория", "avatar": "a.webp", "level": 3, "current_location_id": None,
    "currency_balance": 10, "activity_lock": LOCK,
}


def test_schema_accepts_and_defaults_activity_lock():
    assert CharacterShort(id=1, name="x", avatar="y").activity_lock is None
    assert CharacterShort(**SHORT_INFO).activity_lock == LOCK


def test_fetch_character_short_maps_activity_lock():
    resp = MagicMock(status_code=200)
    resp.json.return_value = SHORT_INFO
    resp.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    with patch("main.httpx.AsyncClient") as ac:
        ac.return_value.__aenter__.return_value = client
        result = asyncio.run(main._fetch_character_short(7))
    assert result["activity_lock"] == LOCK


@patch("main._fetch_character_short", new_callable=AsyncMock)
def test_me_returns_activity_lock(mock_fetch, client, db_session):
    mock_fetch.return_value = {"id": 7, "name": "Артория", "avatar": "a.webp", "activity_lock": LOCK}
    user = create_user(db_session, UserCreate(email="l@test.com", username="lockuser", password="Pass1234"))
    db_session.query(models.User).filter(models.User.id == user.id).update({models.User.current_character: 7})
    db_session.commit()
    from auth import create_access_token
    token = create_access_token(data={"sub": user.email}, role=user.role)
    resp = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["character"]["activity_lock"] == LOCK
