"""FEAT-181 Q1: character-service money flows over the ledger, with the world invariant.

Complements tests/test_gold_transactions.py (B2). Every character balance here is funded through
the ledger itself (admin emission), so after each scenario the strict world invariant holds:
Σ characters.currency_balance + Σ econ_accounts.balance (non-character) == 0, and every
character's balance equals the sum of its postings (no drift).

Covered: add_rewards (payer from the character's current location / explicit location / world,
duplicates, old callers, unknown character), deduct-gold (current location, renamed currency in
the error), teleport into a region treasury with the country tax, admin card balance edits,
NPC create / update gold (economy:adjust), deletion of a player and of an NPC (C8).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String, text

import models

for _tbl in (models.Character, models.CharacterRequest):
    for _col in _tbl.__table__.columns:
        if type(_col.type).__name__ == "Enum":
            _col.type = String(50)

import auth_http  # noqa: E402
import econ_core  # noqa: E402
import econ_ledger  # noqa: E402
import economy_crud  # noqa: E402
from auth_http import (  # noqa: E402
    OAUTH2_SCHEME, UserRead, get_admin_user, get_current_user_via_http, require_permission,
)
from econ_core import AccountRef, Leg  # noqa: E402
from main import app, get_db  # noqa: E402

auth_http.INTERNAL_SERVICE_TOKEN = "test-internal-token"
INTERNAL = {"X-Internal-Token": "test-internal-token"}

COUNTRY_ID, REGION_ID = 3, 7
CITY, WASTELAND = 50, 60        # CITY lies in region 7; WASTELAND has no region -> world treasury


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db(test_engine, test_session_factory, seed_fk_data):
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    seed_fk_data(session)
    for sql in [
        "DROP TABLE IF EXISTS character_attributes",
        "CREATE TABLE character_attributes (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL,"
        " passive_experience INTEGER DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, current_character INTEGER NULL,"
        " username VARCHAR(80) NULL)",
        f"INSERT INTO Countries (id, name) VALUES ({COUNTRY_ID}, 'Мидденгерд')",
        f"INSERT INTO Regions (id, name, country_id) VALUES ({REGION_ID}, 'Мэттанхейм', {COUNTRY_ID})",
        f"INSERT INTO Locations (id, name, region_id) VALUES ({CITY}, 'Город', {REGION_ID})",
        f"INSERT INTO Locations (id, name) VALUES ({WASTELAND}, 'Пустошь')",
    ]:
        session.execute(text(sql))
    session.commit()
    econ_core.invalidate_settings_cache()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.clear()
        econ_core.invalidate_settings_cache()
        models.Base.metadata.drop_all(bind=test_engine)
        with test_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS character_attributes"))
            conn.execute(text("DROP TABLE IF EXISTS users"))


def _character(db, cid, *, gold=0, location=None, is_npc=False, npc_role=None, user_id=None, name=None):
    db.add(models.Character(
        id=cid, name=name or f"Герой {cid}", id_subrace=1, id_class=1, id_race=1, level=1, stat_points=0,
        currency_balance=0, appearance="a", avatar="/a.jpg", current_location_id=location, is_npc=is_npc,
        npc_role=npc_role, npc_status="alive" if is_npc else None, user_id=user_id,
    ))
    db.execute(text("INSERT INTO character_attributes (character_id, passive_experience) VALUES (:c, 0)"),
               {"c": cid})
    db.commit()
    if gold:
        econ_ledger.post_operation(db, op_type="admin_emission", legs=[Leg(AccountRef.emission(),
                                   AccountRef.character(cid), gold)], source_service="test", comment="seed",
                                   apply_tax=False)
        db.commit()
    return db.query(models.Character).get(cid)


def _balance(db, cid):
    return db.execute(text("SELECT currency_balance FROM characters WHERE id = :i"), {"i": cid}).scalar()


def _acc(db, kind, ref_id=0):
    return db.execute(text("SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r"),
                      {"k": kind, "r": ref_id}).scalar()


def _ops(db, op_type):
    return db.execute(text("SELECT id, location_id, region_id, actor_user_id, comment, idempotency_key, metadata "
                           "FROM econ_operations WHERE op_type = :t ORDER BY id"), {"t": op_type}).fetchall()


def _legs(db, op_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT fa.kind, fa.ref_id, ta.kind, ta.ref_id, p.amount, p.leg_type FROM econ_postings p "
        "JOIN econ_accounts fa ON fa.id = p.from_account_id JOIN econ_accounts ta ON ta.id = p.to_account_id "
        "WHERE p.operation_id = :o ORDER BY p.id"), {"o": op_id}).fetchall()]


def _xp(db, cid):
    return db.execute(text("SELECT passive_experience FROM character_attributes WHERE character_id = :c"),
                      {"c": cid}).scalar()


def _assert_invariant(db):
    db.expire_all()
    world = db.execute(text(
        "SELECT (SELECT COALESCE(SUM(currency_balance), 0) FROM characters) + "
        "(SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character')")).scalar()
    assert world == 0
    assert db.execute(text(economy_crud.SQL_CHARACTER_LEDGER), {"limit": 50}).fetchall() == []


def _client(db, user=None):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_current_user_via_http] = lambda: user
        app.dependency_overrides[get_admin_user] = lambda: user
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
    return TestClient(app, raise_server_exceptions=False)


def _user(*permissions, uid=1, role="admin"):
    return UserRead(id=uid, username="u", role=role, permissions=list(permissions))


# ---------------------------------------------------------------------------
# add_rewards (C2)
# ---------------------------------------------------------------------------

class TestAddRewards:

    def test_old_caller_pays_from_current_location_region(self, db):
        _character(db, 1, location=CITY)
        r = _client(db).post("/characters/1/add_rewards", json={"xp": 10, "gold": 30}, headers=INTERNAL)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "new_balance": 30, "new_xp": 10, "duplicate": False}
        (op,) = _ops(db, "battle_reward")
        assert (op.location_id, op.region_id, op.idempotency_key) == (CITY, REGION_ID, None)
        # payouts out of a treasury are not taxed
        assert _legs(db, op.id) == [("region_treasury", REGION_ID, "character", 1, 30, "main")]
        assert _acc(db, "region_treasury", REGION_ID) == -30
        _assert_invariant(db)

    def test_character_without_region_paid_by_world(self, db):
        _character(db, 1, location=WASTELAND)
        r = _client(db).post("/characters/1/add_rewards", json={"gold": 12}, headers=INTERNAL)
        assert r.status_code == 200
        (op,) = _ops(db, "battle_reward")
        assert _legs(db, op.id) == [("world_treasury", 0, "character", 1, 12, "main")]
        _assert_invariant(db)

    def test_explicit_location_overrides_current_location(self, db):
        _character(db, 1, location=WASTELAND)
        r = _client(db).post("/characters/1/add_rewards",
                             json={"gold": 8, "location_id": CITY, "gold_op_type": "dungeon_reward"}, headers=INTERNAL)
        assert r.status_code == 200
        (op,) = _ops(db, "dungeon_reward")
        assert op.location_id == CITY
        assert _legs(db, op.id) == [("region_treasury", REGION_ID, "character", 1, 8, "main")]
        _assert_invariant(db)

    def test_world_payer_ignores_the_location_treasury(self, db):
        _character(db, 1, location=CITY)
        r = _client(db).post("/characters/1/add_rewards",
                             json={"gold": 5, "payer": "world", "gold_op_type": "battle_pass_reward",
                                   "idempotency_key": "battle_pass_reward:claim:1"}, headers=INTERNAL)
        assert r.status_code == 200
        (op,) = _ops(db, "battle_pass_reward")
        assert _legs(db, op.id) == [("world_treasury", 0, "character", 1, 5, "main")]
        assert _acc(db, "region_treasury", REGION_ID) is None
        _assert_invariant(db)

    def test_duplicate_key_with_other_payload_changes_nothing(self, db):
        _character(db, 1, location=CITY)
        client = _client(db)
        key = "dungeon_reward:s:7:r:3"
        first = client.post("/characters/1/add_rewards",
                            json={"xp": 20, "gold": 40, "gold_op_type": "dungeon_reward", "idempotency_key": key},
                            headers=INTERNAL)
        replay = client.post("/characters/1/add_rewards",
                             json={"xp": 999, "gold": 999, "gold_op_type": "dungeon_reward", "idempotency_key": key},
                             headers=INTERNAL)
        assert first.json()["duplicate"] is False
        assert replay.status_code == 200
        assert replay.json() == {"ok": True, "new_balance": 40, "new_xp": None, "duplicate": True}
        assert _balance(db, 1) == 40 and _xp(db, 1) == 20
        assert len(_ops(db, "dungeon_reward")) == 1
        _assert_invariant(db)

    def test_unknown_character_404_and_nothing_posted(self, db):
        r = _client(db).post("/characters/999/add_rewards", json={"gold": 5}, headers=INTERNAL)
        assert r.status_code == 404
        assert db.execute(text("SELECT COUNT(*) FROM econ_operations")).scalar() == 0

    @pytest.mark.parametrize("payload", [{"gold": -5}, {"xp": -1}, {"gold": 5, "payer": "character"},
                                         {"gold": 5, "idempotency_key": ""}])
    def test_rejected_payloads(self, db, payload):
        _character(db, 1, location=CITY)
        r = _client(db).post("/characters/1/add_rewards", json=payload, headers=INTERNAL)
        assert r.status_code == 422
        assert db.execute(text("SELECT COUNT(*) FROM econ_operations")).scalar() == 0

    def test_requires_internal_token(self, db):
        _character(db, 1, location=CITY)
        r = _client(db).post("/characters/1/add_rewards", json={"gold": 5})
        assert r.status_code == 401
        assert _balance(db, 1) == 0


# ---------------------------------------------------------------------------
# deduct-gold (C3)
# ---------------------------------------------------------------------------

class TestDeductGold:

    def test_current_location_region_receives_with_tax(self, db):
        _character(db, 1, gold=100, location=CITY)
        r = _client(db).post("/characters/internal/deduct-gold", json={"character_id": 1, "amount": 55},
                             headers=INTERNAL)
        assert r.status_code == 200 and r.json() == {"ok": True, "new_balance": 45, "duplicate": False}
        (op,) = _ops(db, "dungeon_expense")
        assert op.location_id == CITY and op.region_id == REGION_ID
        assert _legs(db, op.id) == [("character", 1, "region_treasury", REGION_ID, 55, "main"),
                                    ("region_treasury", REGION_ID, "country_treasury", COUNTRY_ID, 5, "tax")]
        assert _acc(db, "region_treasury", REGION_ID) == 50 and _acc(db, "country_treasury", COUNTRY_ID) == 5
        _assert_invariant(db)

    def test_caller_op_type_is_recorded(self, db):
        _character(db, 1, gold=100, location=WASTELAND)
        r = _client(db).post("/characters/internal/deduct-gold",
                             json={"character_id": 1, "amount": 10, "op_type": "npc_shop_buy"}, headers=INTERNAL)
        assert r.status_code == 200
        (op,) = _ops(db, "npc_shop_buy")
        assert _legs(db, op.id) == [("character", 1, "world_treasury", 0, 10, "main")]
        _assert_invariant(db)

    def test_insufficient_message_uses_current_currency_name(self, db):
        db.execute(text("INSERT INTO econ_settings (id, currency_name, currency_genitive, currency_one, "
                        "currency_few, currency_many, currency_short, country_tax_rate) VALUES "
                        "(1, 'Серебро', 'серебра', 'серебряник', 'серебряника', 'серебряников', 'сер.', 0.1)"))
        db.commit()
        econ_core.invalidate_settings_cache()
        _character(db, 1, gold=21, location=CITY)
        r = _client(db).post("/characters/internal/deduct-gold", json={"character_id": 1, "amount": 30},
                             headers=INTERNAL)
        assert r.status_code == 400
        assert r.json()["detail"] == "Недостаточно серебра (имеется 21 серебряник, нужно 30 серебряников)"
        assert _balance(db, 1) == 21
        _assert_invariant(db)

    @pytest.mark.parametrize("amount", [0, -5])
    def test_non_positive_amount_rejected(self, db, amount):
        _character(db, 1, gold=10)
        r = _client(db).post("/characters/internal/deduct-gold", json={"character_id": 1, "amount": amount},
                             headers=INTERNAL)
        assert r.status_code == 422 and _balance(db, 1) == 10

    def test_unknown_character_404(self, db):
        r = _client(db).post("/characters/internal/deduct-gold", json={"character_id": 999, "amount": 5},
                             headers=INTERNAL)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Teleport (C4)
# ---------------------------------------------------------------------------

class TestTeleport:

    @patch("requests.post")
    def test_fare_goes_to_source_region_with_tax(self, mock_post, db):
        mock_post.return_value = MagicMock(status_code=200)
        _character(db, 10, location=CITY, is_npc=True, npc_role="teleport_master")
        _character(db, 11, location=WASTELAND, is_npc=True, npc_role="teleport_master")
        _character(db, 1, gold=500, location=CITY, user_id=100)
        link = models.TeleportLink(from_npc_id=10, to_npc_id=11, cost_gold=120)
        db.add(link)
        db.execute(text("INSERT INTO users (id, current_character, username) VALUES (100, 1, 'p')"))
        db.commit()

        r = _client(db, _user(uid=100, role="user")).post("/characters/npcs/10/teleport", json={"link_id": link.id})
        assert r.status_code == 200, r.text
        assert r.json()["currency_balance"] == 380 and r.json()["new_location_id"] == WASTELAND
        (op,) = _ops(db, "teleport")
        assert op.location_id == CITY and op.region_id == REGION_ID
        assert _legs(db, op.id) == [("character", 1, "region_treasury", REGION_ID, 120, "main"),
                                    ("region_treasury", REGION_ID, "country_treasury", COUNTRY_ID, 12, "tax")]
        _assert_invariant(db)

    @patch("requests.post")
    def test_insufficient_fare_402_and_nothing_moves(self, mock_post, db):
        _character(db, 10, location=CITY, is_npc=True, npc_role="teleport_master")
        _character(db, 11, location=WASTELAND, is_npc=True, npc_role="teleport_master")
        _character(db, 1, gold=50, location=CITY, user_id=100)
        link = models.TeleportLink(from_npc_id=10, to_npc_id=11, cost_gold=120)
        db.add(link)
        db.execute(text("INSERT INTO users (id, current_character, username) VALUES (100, 1, 'p')"))
        db.commit()
        r = _client(db, _user(uid=100, role="user")).post("/characters/npcs/10/teleport", json={"link_id": link.id})
        assert r.status_code == 402
        assert _ops(db, "teleport") == [] and _balance(db, 1) == 50
        _assert_invariant(db)


# ---------------------------------------------------------------------------
# Admin card balance (C5)
# ---------------------------------------------------------------------------

class TestAdminCardBalance:

    @patch("main.httpx.AsyncClient")
    def test_series_of_edits_keeps_the_world_closed(self, _httpx, db):
        _character(db, 1, gold=100)
        admin = _user("characters:update", "economy:adjust", uid=5)
        app.dependency_overrides[require_permission("characters:update")] = lambda: admin
        client = _client(db, admin)
        for target in (250, 40, 40, 0):
            r = client.put("/characters/admin/1", json={"currency_balance": target})
            assert r.status_code == 200, r.text
            assert _balance(db, 1) == target
        ops = _ops(db, "admin_adjust")
        assert len(ops) == 3                                   # the unchanged 40 posts nothing
        assert {op.actor_user_id for op in ops} == {5}
        assert _acc(db, "adjustment") == 100                   # +150, -210, -40 -> net -100 issued
        _assert_invariant(db)

    @patch("main.httpx.AsyncClient")
    def test_negative_target_rejected(self, _httpx, db):
        _character(db, 1, gold=100)
        admin = _user("characters:update", "economy:adjust")
        app.dependency_overrides[require_permission("characters:update")] = lambda: admin
        r = _client(db, admin).put("/characters/admin/1", json={"currency_balance": -1})
        assert r.status_code == 400
        assert _ops(db, "admin_adjust") == [] and _balance(db, 1) == 100


# ---------------------------------------------------------------------------
# NPC gold (C6)
# ---------------------------------------------------------------------------

NPC_BODY = {"name": "Торговец", "id_class": 1, "id_race": 1, "id_subrace": 1, "current_location_id": CITY}


class TestNpcGold:

    @patch("crud.send_attributes_request", new_callable=AsyncMock, return_value=None)
    def test_create_with_gold_posts_admin_adjust(self, _attrs, db):
        admin = _user("npcs:create", "economy:adjust", uid=9)
        app.dependency_overrides[require_permission("npcs:create")] = lambda: admin
        r = _client(db, admin).post("/characters/admin/npcs", json={**NPC_BODY, "currency_balance": 300})
        assert r.status_code == 200, r.text
        npc_id = r.json()["id"]
        assert _balance(db, npc_id) == 300
        (op,) = _ops(db, "admin_adjust")
        assert op.actor_user_id == 9 and op.comment == "Правка денег НПС"
        assert '"admin_npc_create"' in op.metadata
        assert _legs(db, op.id) == [("adjustment", 0, "character", npc_id, 300, "main")]
        _assert_invariant(db)

    @patch("crud.send_attributes_request", new_callable=AsyncMock, return_value=None)
    def test_create_with_gold_needs_economy_adjust(self, _attrs, db):
        editor = _user("npcs:create", uid=9, role="editor")
        app.dependency_overrides[require_permission("npcs:create")] = lambda: editor
        client = _client(db, editor)
        r = client.post("/characters/admin/npcs", json={**NPC_BODY, "currency_balance": 300})
        assert r.status_code == 403 and r.json()["detail"] == "Недостаточно прав для изменения баланса"
        assert db.query(models.Character).count() == 0
        r = client.post("/characters/admin/npcs", json={**NPC_BODY, "currency_balance": 0})
        assert r.status_code == 200
        assert db.execute(text("SELECT COUNT(*) FROM econ_operations")).scalar() == 0

    @patch("crud.send_attributes_request", new_callable=AsyncMock, return_value=None)
    def test_create_with_negative_gold_rejected(self, _attrs, db):
        admin = _user("npcs:create", "economy:adjust")
        app.dependency_overrides[require_permission("npcs:create")] = lambda: admin
        r = _client(db, admin).post("/characters/admin/npcs", json={**NPC_BODY, "currency_balance": -1})
        assert r.status_code == 400 and db.query(models.Character).count() == 0

    def test_update_gold(self, db):
        _character(db, 20, gold=300, is_npc=True, location=CITY)
        admin = _user("npcs:update", "economy:adjust", uid=4)
        app.dependency_overrides[require_permission("npcs:update")] = lambda: admin
        r = _client(db, admin).put("/characters/admin/npcs/20", json={"currency_balance": 120, "name": "Скупой"})
        assert r.status_code == 200, r.text
        (op,) = _ops(db, "admin_adjust")
        assert _legs(db, op.id) == [("character", 20, "adjustment", 0, 180, "main")]
        assert _balance(db, 20) == 120
        _assert_invariant(db)

    def test_update_gold_without_permission_changes_nothing(self, db):
        _character(db, 20, gold=300, is_npc=True, name="Торговец")
        editor = _user("npcs:update", role="editor")
        app.dependency_overrides[require_permission("npcs:update")] = lambda: editor
        client = _client(db, editor)
        r = client.put("/characters/admin/npcs/20", json={"currency_balance": 1, "name": "Взломщик"})
        assert r.status_code == 403
        db.expire_all()
        assert _balance(db, 20) == 300 and db.query(models.Character).get(20).name == "Торговец"
        # Unchanged gold (the form always sends it) needs no economy permission.
        r = client.put("/characters/admin/npcs/20", json={"currency_balance": 300, "name": "Торговец II"})
        assert r.status_code == 200
        assert _ops(db, "admin_adjust") == []

    def test_update_negative_gold_rejected(self, db):
        _character(db, 20, gold=300, is_npc=True)
        admin = _user("npcs:update", "economy:adjust")
        app.dependency_overrides[require_permission("npcs:update")] = lambda: admin
        r = _client(db, admin).put("/characters/admin/npcs/20", json={"currency_balance": -5})
        assert r.status_code == 400 and _balance(db, 20) == 300


# ---------------------------------------------------------------------------
# Deletion (C8)
# ---------------------------------------------------------------------------

def _httpx_ok():
    resp = MagicMock(status_code=200, text="OK")
    resp.json.return_value = {}
    instance = AsyncMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    for method in ("get", "post", "put", "delete", "patch"):
        setattr(instance, method, AsyncMock(return_value=resp))
    return MagicMock(return_value=instance)


class TestDeletion:

    def test_player_deletion_moves_gold_to_location_treasury(self, db):
        _character(db, 1, gold=80, location=CITY, user_id=10, name="Лоен")
        admin = _user("characters:delete")
        app.dependency_overrides[require_permission("characters:delete")] = lambda: admin
        with patch("main.httpx.AsyncClient", _httpx_ok()):
            r = _client(db, admin).delete("/characters/1")
        assert r.status_code == 200, r.text
        assert db.execute(text("SELECT COUNT(*) FROM characters WHERE id = 1")).scalar() == 0
        (op,) = _ops(db, "character_deleted")
        assert op.idempotency_key == "character_deleted:c:1" and op.location_id == CITY
        assert _legs(db, op.id) == [("character", 1, "region_treasury", REGION_ID, 80, "main"),
                                    ("region_treasury", REGION_ID, "country_treasury", COUNTRY_ID, 8, "tax")]
        assert db.execute(text("SELECT is_active FROM econ_accounts WHERE kind = 'character' AND ref_id = 1")
                          ).scalar() == 0
        _assert_invariant(db)

    def test_zero_balance_deletion_posts_nothing(self, db):
        _character(db, 1, location=CITY, user_id=10)
        admin = _user("characters:delete")
        app.dependency_overrides[require_permission("characters:delete")] = lambda: admin
        with patch("main.httpx.AsyncClient", _httpx_ok()):
            r = _client(db, admin).delete("/characters/1")
        assert r.status_code == 200
        assert db.execute(text("SELECT COUNT(*) FROM econ_operations")).scalar() == 0

    def test_npc_deletion_without_region_goes_to_world(self, db):
        _character(db, 20, gold=64, is_npc=True, location=WASTELAND)
        admin = _user("npcs:delete")
        app.dependency_overrides[require_permission("npcs:delete")] = lambda: admin
        with patch("main.httpx.AsyncClient", _httpx_ok()):
            r = _client(db, admin).delete("/characters/admin/npcs/20")
        assert r.status_code == 200, r.text
        (op,) = _ops(db, "character_deleted")
        assert '"is_npc": true' in op.metadata
        assert _legs(db, op.id) == [("character", 20, "world_treasury", 0, 64, "main")]
        assert _acc(db, "world_treasury") == 64
        _assert_invariant(db)

    def test_failed_delete_rolls_back_the_posting(self, db):
        """The posting and the row delete share one commit: a failing delete keeps the gold."""
        _character(db, 1, gold=80, location=CITY, user_id=10)
        admin = _user("characters:delete")
        app.dependency_overrides[require_permission("characters:delete")] = lambda: admin
        with patch("main.httpx.AsyncClient", _httpx_ok()), \
                patch.object(type(db), "delete", side_effect=RuntimeError("boom")):
            r = _client(db, admin).delete("/characters/1")
        assert r.status_code == 500
        assert _balance(db, 1) == 80 and _ops(db, "character_deleted") == []
        _assert_invariant(db)
