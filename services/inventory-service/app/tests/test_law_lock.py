"""FEAT-198 QA (task 10): law in inventory-service.

  * The activity-lock copy (sync): reason priority, relative messages, the REAL shared-DB
    query against SQLite incl. the unknown-column fallback (a `characters` table without the
    law columns = character-service migration 039 not applied yet).
  * The 5 auction write routes (deposit, create listing, bid, buyout, claim) refuse a jailed or
    guard-stopped character with 409 BEFORE touching anything; ownership still comes first.
"""

import itertools
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import activity_lock
from auth_http import get_current_user_via_http, UserRead

pytestmark = pytest.mark.real_activity_lock

SOON = datetime.utcnow() + timedelta(hours=6)
PAST = datetime.utcnow() - timedelta(minutes=2)

_FULL_TABLE = """CREATE TABLE characters (
    id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1,
    user_id INTEGER, name TEXT, current_location_id INTEGER,
    currency_balance INTEGER DEFAULT 0,
    dungeon_session_id INTEGER, unconscious_until DATETIME,
    asleep_since DATETIME, reading_since DATETIME,
    jailed_until DATETIME, law_encounter_id INTEGER
)"""
_LEGACY_TABLE = """CREATE TABLE characters (
    id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1,
    user_id INTEGER, name TEXT, current_location_id INTEGER,
    currency_balance INTEGER DEFAULT 0,
    dungeon_session_id INTEGER, unconscious_until DATETIME,
    asleep_since DATETIME, reading_since DATETIME
)"""


def _make_characters(db_session, ddl):
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(ddl))
    db_session.execute(text(
        "INSERT INTO characters (id, user_id, name, current_location_id) VALUES "
        "(1, 1, 'Алиса', 100), (2, 2, 'Борис', 100)"
    ))
    db_session.commit()


@pytest.fixture()
def law_db(db_session):
    _make_characters(db_session, _FULL_TABLE)
    yield db_session
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


def _set(db_session, cid, **cols):
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    db_session.execute(text(f"UPDATE characters SET {sets} WHERE id = :cid"), {**cols, "cid": cid})
    db_session.commit()


# ===========================================================================
# 1. Lock semantics
# ===========================================================================

REASONS = ["jail", "law_encounter", "unconscious", "dungeon", "asleep", "reading"]


@pytest.mark.parametrize(
    "present",
    [set(c) for n in range(len(REASONS) + 1) for c in itertools.combinations(REASONS, n)],
    ids=lambda s: "+".join(sorted(s)) or "free",
)
def test_reason_priority_matrix(present):
    later = datetime.utcnow() + timedelta(hours=3)
    lock = activity_lock.compute_lock(
        7 if "dungeon" in present else None,
        later if "unconscious" in present else None,
        asleep_since=datetime.utcnow() if "asleep" in present else None,
        reading_since=datetime.utcnow() if "reading" in present else None,
        jailed_until=later if "jail" in present else None,
        law_encounter_id=5 if "law_encounter" in present else None,
    )
    expected = next((r for r in REASONS if r in present), None)
    assert lock["reason"] == expected
    assert lock["locked"] is (expected is not None)


class TestRealQuery:
    def test_jail_from_sqlite(self, law_db):
        _set(law_db, 1, jailed_until=SOON)
        lock = activity_lock.get_activity_lock(law_db, 1)
        assert lock["reason"] == "jail"
        assert activity_lock.lock_message(lock).startswith("Персонаж в тюрьме — осталось")

    def test_expired_jail_is_free(self, law_db):
        _set(law_db, 1, jailed_until=PAST)
        assert activity_lock.get_activity_lock(law_db, 1)["locked"] is False

    def test_encounter_beats_unconscious_and_dungeon(self, law_db):
        _set(law_db, 1, law_encounter_id=12, unconscious_until=SOON, dungeon_session_id=4)
        lock = activity_lock.get_activity_lock(law_db, 1)
        assert lock["reason"] == "law_encounter"
        assert lock["law_encounter_id"] == 12

    def test_jail_beats_encounter(self, law_db):
        _set(law_db, 1, law_encounter_id=12, jailed_until=SOON)
        assert activity_lock.get_activity_lock(law_db, 1)["reason"] == "jail"

    def test_unknown_character_is_free(self, law_db):
        assert activity_lock.get_activity_lock(law_db, 999)["locked"] is False

    def test_legacy_table_falls_back(self, db_session):
        """No law columns (migration 039 not applied) -> the old SELECT, no 500."""
        _make_characters(db_session, _LEGACY_TABLE)
        try:
            _set(db_session, 1, dungeon_session_id=3)
            lock = activity_lock.get_activity_lock(db_session, 1)
            assert lock["reason"] == "dungeon"
            assert activity_lock.get_activity_lock(db_session, 2)["locked"] is False
        finally:
            db_session.execute(text("DROP TABLE IF EXISTS characters"))
            db_session.commit()

    def test_check_raises_409(self, law_db):
        _set(law_db, 1, law_encounter_id=3)
        with pytest.raises(HTTPException) as exc:
            activity_lock.check_not_activity_locked(law_db, 1, subject="Ваш персонаж")
        assert exc.value.status_code == 409
        assert exc.value.detail == "Ваш персонаж остановлен стражей — сначала нужно решить, как поступить"


# ===========================================================================
# 2. Auction write routes
# ===========================================================================

AUCTION_ROUTES = [
    ("/inventory/auction/storage/deposit", {"character_id": 1, "inventory_item_id": 1, "quantity": 1}),
    ("/inventory/auction/listings", {"character_id": 1, "storage_id": 1, "start_price": 10}),
    ("/inventory/auction/listings/1/bid", {"character_id": 1, "amount": 20}),
    ("/inventory/auction/listings/1/buyout", {"character_id": 1}),
    ("/inventory/auction/storage/claim", {"character_id": 1, "storage_ids": [1]}),
]
ROUTE_IDS = ["deposit", "create", "bid", "buyout", "claim"]


@pytest.fixture()
def auction_client(client, law_db):
    from main import app

    user = UserRead(id=1, username="alice", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


@pytest.mark.parametrize("url,payload", AUCTION_ROUTES, ids=ROUTE_IDS)
@pytest.mark.parametrize("cols,prefix", [
    ({"jailed_until": SOON}, "Персонаж в тюрьме — осталось"),
    ({"law_encounter_id": 8}, "Персонаж остановлен стражей"),
    ({"dungeon_session_id": 5}, "Персонаж находится в подземелье"),
], ids=["jail", "encounter", "dungeon"])
def test_locked_character_gets_409(auction_client, law_db, url, payload, cols, prefix):
    _set(law_db, 1, **cols)
    with patch("crud.is_character_in_battle") as in_battle, \
            patch("crud.check_auctioneer_at_character_location") as auctioneer:
        r = auction_client.post(url, json=payload)
    assert r.status_code == 409, r.text
    assert r.json()["detail"].startswith(prefix)
    in_battle.assert_not_called()
    auctioneer.assert_not_called()


@pytest.mark.parametrize("url,payload", AUCTION_ROUTES, ids=ROUTE_IDS)
def test_free_character_passes_the_lock(auction_client, law_db, url, payload):
    """Unlocked (an expired jail term) -> the route goes on to its next check."""
    _set(law_db, 1, jailed_until=PAST)
    with patch("crud.is_character_in_battle", return_value=True), \
            patch("crud.check_auctioneer_at_character_location", return_value=None):
        r = auction_client.post(url, json=payload)
    assert r.status_code != 409, r.text


@pytest.mark.parametrize("url,payload", AUCTION_ROUTES, ids=ROUTE_IDS)
def test_ownership_is_checked_before_the_lock(auction_client, law_db, url, payload):
    """Someone else's jailed character -> 403, not a lock message that leaks its state."""
    _set(law_db, 2, jailed_until=SOON)
    body = dict(payload, character_id=2)
    r = auction_client.post(url, json=body)
    assert r.status_code == 403, r.text
