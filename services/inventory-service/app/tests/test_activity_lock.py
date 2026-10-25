"""FEAT-175: activity lock (dungeon run / knocked out) in inventory-service.

Trade and crafting are refused for a locked character; inventory/equipment
management stays allowed. Runs the REAL shared-DB query against a SQLite
`characters` table that carries the two character-service columns.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead

pytestmark = pytest.mark.real_activity_lock


@pytest.fixture()
def lock_client(client, db_session):
    from main import app

    # Other files leave their own (narrower) `characters` mirror behind.
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        """CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            name TEXT,
            current_location_id INTEGER,
            currency_balance INTEGER DEFAULT 0,
            dungeon_session_id INTEGER,
            unconscious_until DATETIME
        )"""
    ))
    db_session.execute(text(
        "INSERT INTO characters (id, user_id, name, current_location_id) VALUES "
        "(1, 1, 'Алиса', 100), (2, 2, 'Борис', 100)"
    ))
    db_session.commit()
    user = UserRead(id=1, username="alice", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


def _lock(db_session, cid, *, dungeon=None, unconscious=None):
    db_session.execute(
        text("UPDATE characters SET dungeon_session_id=:d, unconscious_until=:u WHERE id=:cid"),
        {"d": dungeon, "u": unconscious, "cid": cid},
    )
    db_session.commit()


def _trade(db_session):
    import models

    t = models.TradeOffer(
        initiator_character_id=1, target_character_id=2, location_id=100, status="negotiating",
    )
    db_session.add(t)
    db_session.commit()
    return t.id


class TestTrade:
    def test_propose_refused_when_initiator_in_dungeon(self, lock_client, db_session):
        _lock(db_session, 1, dungeon=9)
        r = lock_client.post("/inventory/trade/propose",
                             json={"initiator_character_id": 1, "target_character_id": 2})
        assert r.status_code == 409
        assert r.json()["detail"] == "Ваш персонаж находится в подземелье"

    def test_propose_refused_when_target_unconscious(self, lock_client, db_session):
        _lock(db_session, 2, unconscious=datetime.utcnow() + timedelta(hours=1))
        r = lock_client.post("/inventory/trade/propose",
                             json={"initiator_character_id": 1, "target_character_id": 2})
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Целевой персонаж без сознания до")

    def test_propose_allowed_after_knockout_expired(self, lock_client, db_session):
        _lock(db_session, 2, unconscious=datetime.utcnow() - timedelta(minutes=1))
        with patch("main.publish_notification_sync"):
            r = lock_client.post("/inventory/trade/propose",
                                 json={"initiator_character_id": 1, "target_character_id": 2})
        assert r.status_code == 201, r.text

    def test_update_items_refused_when_other_side_locked(self, lock_client, db_session):
        trade_id = _trade(db_session)
        _lock(db_session, 2, dungeon=4)
        r = lock_client.put(f"/inventory/trade/{trade_id}/items",
                            json={"character_id": 1, "items": [], "gold": 0})
        assert r.status_code == 409
        assert r.json()["detail"] == "Другой участник обмена находится в подземелье"

    def test_confirm_refused_when_self_locked(self, lock_client, db_session):
        trade_id = _trade(db_session)
        _lock(db_session, 1, dungeon=4)
        r = lock_client.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})
        assert r.status_code == 409
        assert r.json()["detail"] == "Ваш персонаж находится в подземелье"


CRAFT_CALLS = [
    ("/inventory/crafting/1/craft", {"recipe_id": 1}),
    ("/inventory/crafting/1/sharpen",
     {"inventory_item_id": 1, "whetstone_item_id": 2, "stat_field": "strength_modifier"}),
    ("/inventory/crafting/1/refine", {"source_item_id": 1, "quantity": 1}),
]


class TestCrafting:
    @pytest.mark.parametrize("url,payload", CRAFT_CALLS)
    def test_crafting_refused_in_dungeon(self, lock_client, db_session, url, payload):
        _lock(db_session, 1, dungeon=3)
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            r = lock_client.post(url, json=payload)
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж находится в подземелье"

    @pytest.mark.parametrize("url,payload", CRAFT_CALLS)
    def test_crafting_refused_when_unconscious(self, lock_client, db_session, url, payload):
        _lock(db_session, 1, unconscious=datetime.utcnow() + timedelta(minutes=20))
        r = lock_client.post(url, json=payload)
        assert r.status_code == 409
        assert "без сознания" in r.json()["detail"]


def test_inventory_listing_still_allowed(lock_client, db_session):
    """Inventory management stays available inside a dungeon run."""
    _lock(db_session, 1, dungeon=3)
    r = lock_client.get("/inventory/1/items")
    assert r.status_code != 409
