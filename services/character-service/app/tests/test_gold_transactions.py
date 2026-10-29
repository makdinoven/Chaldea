"""
Gold writers of character-service post to the economy ledger (FEAT-181 B2).

Originally (FEAT-102) these tests checked rows in `gold_transactions`. That table is
frozen since FEAT-181: every gold change is an `econ_operations` row with double-entry
`econ_postings`, and character-service writes nothing to `gold_transactions` any more.

1. add_rewards with gold > 0 posts `battle_reward` (payer = treasury, default world)
2. add_rewards with gold = 0 posts nothing
3. new optional fields: gold_op_type / payer / location_id / idempotency_key (duplicate -> no XP, no gold)
4. Admin balance edit = `admin_adjust` posting, needs economy:adjust
5. Starter kit gold = `starter_kit` posting from the start-location treasury
6. the ORM balance guard is strict; fixtures bypass it with allow_direct_balance_write
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import String, text

import database
import models

# Patch Enum columns to String for SQLite compatibility
for tbl in [
    models.Character,
    models.CharacterRequest,
    models.MobTemplate,
    models.MobLootTable,
    models.MobTemplateSkill,
    models.LocationMobSpawn,
    models.ActiveMob,
]:
    for col in tbl.__table__.columns:
        if type(col.type).__name__ == "Enum":
            col.type = String(50)

from fastapi.testclient import TestClient
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead, require_permission
from main import app, get_db
import crud
import auth_http

# FEAT-169: POST /characters/{cid}/add_rewards закрыт internal-токеном.
auth_http.INTERNAL_SERVICE_TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_reference_data(session):
    """Insert minimal FK reference data."""
    for rid, name in [(1, "Человек")]:
        if not session.query(models.Race).filter_by(id_race=rid).first():
            session.add(models.Race(id_race=rid, name=name))
    session.flush()
    for sid, rid, name in [(1, 1, "Норд")]:
        if not session.query(models.Subrace).filter_by(id_subrace=sid).first():
            session.add(models.Subrace(id_subrace=sid, id_race=rid, name=name))
    session.flush()
    for cid, name in [(1, "Воин")]:
        if not session.query(models.Class).filter_by(id_class=cid).first():
            session.add(models.Class(id_class=cid, name=name))
    session.commit()


def _create_character(session, character_id=1, name="TestChar", currency_balance=100,
                      user_id=10, is_npc=False):
    """Create a minimal Character record."""
    char = models.Character(
        id=character_id,
        name=name,
        id_subrace=1,
        biography="bio",
        personality="pers",
        id_class=1,
        currency_balance=currency_balance,
        user_id=user_id,
        appearance="appearance",
        sex="male",
        id_race=1,
        avatar="/avatar.jpg",
        is_npc=is_npc,
        level=1,
        stat_points=0,
    )
    session.add(char)
    session.commit()
    return char


def _insert_character_attributes(session, character_id, passive_experience=0):
    """Insert a row into the character_attributes table."""
    session.execute(
        text("INSERT INTO character_attributes (character_id, passive_experience) VALUES (:cid, :xp)"),
        {"cid": character_id, "xp": passive_experience},
    )
    session.commit()


def _count_gold_transactions(session):
    """Rows in the frozen gold_transactions table (must stay 0)."""
    return session.execute(text("SELECT COUNT(*) FROM gold_transactions")).scalar()


def _ops(session, op_type=None):
    q = "SELECT id, op_type, idempotency_key, location_id, region_id, actor_user_id, comment FROM econ_operations"
    params = {}
    if op_type:
        q += " WHERE op_type = :t"
        params["t"] = op_type
    return session.execute(text(q + " ORDER BY id"), params).fetchall()


def _legs(session, operation_id):
    """[(from_kind, from_ref, to_kind, to_ref, amount, leg_type)] of one operation."""
    return [tuple(r) for r in session.execute(text(
        "SELECT fa.kind, fa.ref_id, ta.kind, ta.ref_id, p.amount, p.leg_type "
        "FROM econ_postings p JOIN econ_accounts fa ON fa.id = p.from_account_id "
        "JOIN econ_accounts ta ON ta.id = p.to_account_id WHERE p.operation_id = :op ORDER BY p.id"
    ), {"op": operation_id}).fetchall()]


def _account_balance(session, kind, ref_id=0):
    row = session.execute(text("SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r"),
                          {"k": kind, "r": ref_id}).first()
    return row[0] if row else None


def _ledger_closes(session):
    """Net postings into character accounts + all non-character balances == 0
    (characters were seeded with opening balances outside the ledger)."""
    accounts = session.execute(text(
        "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character'")).scalar()
    char_in = session.execute(text(
        "SELECT COALESCE(SUM(p.amount), 0) FROM econ_postings p JOIN econ_accounts a ON a.id = p.to_account_id "
        "WHERE a.kind = 'character'")).scalar()
    char_out = session.execute(text(
        "SELECT COALESCE(SUM(p.amount), 0) FROM econ_postings p JOIN econ_accounts a ON a.id = p.from_account_id "
        "WHERE a.kind = 'character'")).scalar()
    return (char_in - char_out) + accounts == 0


def _seed_region(session, location_id=50, region_id=7, country_id=3):
    session.execute(text("INSERT INTO Countries (id, name) VALUES (:c, 'Страна')"), {"c": country_id})
    session.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (:r, 'Регион', :c)"),
                    {"r": region_id, "c": country_id})
    session.execute(text("INSERT INTO Locations (id, name, region_id) VALUES (:l, 'Город', :r)"),
                    {"l": location_id, "r": region_id})
    session.commit()


_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve", "economy:adjust",
    ],
)

_EDITOR_WITHOUT_ECONOMY = UserRead(
    id=2, username="editor", role="editor",
    permissions=["characters:update", "characters:read"],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(test_engine, test_session_factory):
    """Real SQLite session with all tables created, including character_attributes."""
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    # Create character_attributes table (not an ORM model in character-service)
    session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    session.execute(text(
        "CREATE TABLE character_attributes ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  character_id INTEGER NOT NULL,"
        "  passive_experience INTEGER DEFAULT 0"
        ")"
    ))
    session.commit()
    _seed_reference_data(session)
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client_with_db(db_session):
    """FastAPI TestClient with real SQLite DB session."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False), db_session
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    """FastAPI TestClient with admin auth and real SQLite DB."""
    def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    app.dependency_overrides[require_permission("characters:update")] = override_admin
    yield TestClient(app, raise_server_exceptions=False), db_session
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Tests: add_rewards posts to the ledger
# ═══════════════════════════════════════════════════════════════════════════


class TestAddRewardsLedger:
    """add_rewards gold is a `battle_reward` (or caller-chosen) posting from a treasury."""

    def test_gold_reward_posts_operation(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        response = client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 50}, headers=INTERNAL_HEADERS)
        assert response.status_code == 200
        assert response.json()["new_balance"] == 150
        assert response.json()["duplicate"] is False

        ops = _ops(session, "battle_reward")
        assert len(ops) == 1
        # The character has no location -> «Казна Скитальцев» pays.
        assert _legs(session, ops[0][0]) == [("world_treasury", 0, "character", 1, 50, "main")]
        assert _account_balance(session, "world_treasury") == -50
        assert _count_gold_transactions(session) == 0
        assert _ledger_closes(session)

    def test_zero_gold_posts_nothing(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        response = client.post("/characters/1/add_rewards", json={"xp": 50, "gold": 0}, headers=INTERNAL_HEADERS)
        assert response.status_code == 200
        assert _ops(session) == []
        assert _count_gold_transactions(session) == 0

    def test_multiple_rewards_create_multiple_operations(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=0)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 10}, headers=INTERNAL_HEADERS)
        client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 20}, headers=INTERNAL_HEADERS)

        assert len(_ops(session, "battle_reward")) == 2
        assert session.execute(text("SELECT currency_balance FROM characters WHERE id = 1")).scalar() == 30

    def test_location_payer_uses_region_treasury(self, client_with_db):
        """payer=location (default) + location_id -> that region's treasury pays; payouts are not taxed."""
        client, session = client_with_db
        _seed_region(session, location_id=50, region_id=7, country_id=3)
        _create_character(session, character_id=1, currency_balance=0)
        _insert_character_attributes(session, character_id=1)

        response = client.post(
            "/characters/1/add_rewards",
            json={"gold": 40, "gold_op_type": "dungeon_reward", "location_id": 50},
            headers=INTERNAL_HEADERS,
        )
        assert response.status_code == 200
        ops = _ops(session, "dungeon_reward")
        assert len(ops) == 1
        assert ops[0][3] == 50 and ops[0][4] == 7      # location_id, region_id
        assert _legs(session, ops[0][0]) == [("region_treasury", 7, "character", 1, 40, "main")]
        assert _account_balance(session, "region_treasury", 7) == -40
        assert _ledger_closes(session)

    def test_world_payer(self, client_with_db):
        client, session = client_with_db
        _seed_region(session)
        _create_character(session, character_id=1, currency_balance=0)
        _insert_character_attributes(session, character_id=1)

        response = client.post(
            "/characters/1/add_rewards",
            json={"gold": 25, "gold_op_type": "battle_pass_reward", "payer": "world", "location_id": 50},
            headers=INTERNAL_HEADERS,
        )
        assert response.status_code == 200
        ops = _ops(session, "battle_pass_reward")
        assert _legs(session, ops[0][0]) == [("world_treasury", 0, "character", 1, 25, "main")]

    def test_duplicate_key_adds_neither_xp_nor_gold(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=0)
        _insert_character_attributes(session, character_id=1, passive_experience=0)
        payload = {"xp": 30, "gold": 15, "gold_op_type": "battle_pass_reward", "payer": "world",
                   "idempotency_key": "battle_pass_reward:claim:55"}

        first = client.post("/characters/1/add_rewards", json=payload, headers=INTERNAL_HEADERS)
        second = client.post("/characters/1/add_rewards", json=payload, headers=INTERNAL_HEADERS)

        assert first.status_code == 200 and first.json()["duplicate"] is False
        assert second.status_code == 200 and second.json()["duplicate"] is True
        assert second.json()["new_balance"] == 15
        assert len(_ops(session)) == 1
        xp = session.execute(text(
            "SELECT passive_experience FROM character_attributes WHERE character_id = 1")).scalar()
        assert xp == 30

    @pytest.mark.parametrize("payload", [
        {"gold": 5, "gold_op_type": "admin_adjust"},
        {"gold": 5, "gold_op_type": "genesis"},
        {"gold": 5, "payer": "emission"},
        {"gold": 5, "idempotency_key": "k" * 129},
    ])
    def test_invalid_new_fields_rejected(self, client_with_db, payload):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=0)
        response = client.post("/characters/1/add_rewards", json=payload, headers=INTERNAL_HEADERS)
        assert response.status_code == 422
        assert _ops(session) == []


# ═══════════════════════════════════════════════════════════════════════════
# Tests: admin balance edit = admin_adjust posting
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminCurrencyLedger:

    @patch("main.httpx.AsyncClient")
    def test_admin_increase_posts_adjustment(self, mock_httpx, admin_client):
        client, session = admin_client
        _create_character(session, character_id=1, currency_balance=100)

        response = client.put("/characters/admin/1", json={"currency_balance": 500})
        assert response.status_code == 200

        ops = _ops(session, "admin_adjust")
        assert len(ops) == 1
        assert ops[0][5] == 1                               # actor_user_id
        assert ops[0][6] == "Правка в карточке персонажа"    # comment
        assert _legs(session, ops[0][0]) == [("adjustment", 0, "character", 1, 400, "main")]
        assert session.execute(text("SELECT currency_balance FROM characters WHERE id = 1")).scalar() == 500
        assert _count_gold_transactions(session) == 0
        assert _ledger_closes(session)

    @patch("main.httpx.AsyncClient")
    def test_admin_same_balance_no_operation(self, mock_httpx, admin_client):
        client, session = admin_client
        _create_character(session, character_id=1, currency_balance=100)

        response = client.put("/characters/admin/1", json={"currency_balance": 100})
        assert response.status_code == 200
        assert _ops(session) == []

    @patch("main.httpx.AsyncClient")
    def test_admin_decrease_posts_to_adjustment(self, mock_httpx, admin_client):
        client, session = admin_client
        _create_character(session, character_id=1, currency_balance=500)

        response = client.put("/characters/admin/1", json={"currency_balance": 200})
        assert response.status_code == 200

        ops = _ops(session, "admin_adjust")
        assert _legs(session, ops[0][0]) == [("character", 1, "adjustment", 0, 300, "main")]
        assert _account_balance(session, "adjustment") == 300

    @patch("main.httpx.AsyncClient")
    def test_balance_change_without_economy_adjust_is_403(self, mock_httpx, admin_client):
        client, session = admin_client
        app.dependency_overrides[require_permission("characters:update")] = lambda: _EDITOR_WITHOUT_ECONOMY
        app.dependency_overrides[get_current_user_via_http] = lambda: _EDITOR_WITHOUT_ECONOMY
        _create_character(session, character_id=1, currency_balance=100)

        response = client.put("/characters/admin/1", json={"currency_balance": 900, "stat_points": 3})
        assert response.status_code == 403
        assert response.json()["detail"] == "Недостаточно прав для изменения баланса"
        assert _ops(session) == []
        session.expire_all()
        char = session.query(models.Character).get(1)
        assert char.currency_balance == 100 and char.stat_points == 0

    @patch("main.httpx.AsyncClient")
    def test_unchanged_balance_without_economy_adjust_is_allowed(self, mock_httpx, admin_client):
        """The admin card always sends the balance; an unchanged value needs no economy permission."""
        client, session = admin_client
        app.dependency_overrides[require_permission("characters:update")] = lambda: _EDITOR_WITHOUT_ECONOMY
        app.dependency_overrides[get_current_user_via_http] = lambda: _EDITOR_WITHOUT_ECONOMY
        _create_character(session, character_id=1, currency_balance=100)

        response = client.put("/characters/admin/1", json={"currency_balance": 100, "stat_points": 3})
        assert response.status_code == 200
        assert _ops(session) == []


# ═══════════════════════════════════════════════════════════════════════════
# Tests: starter kit gold
# ═══════════════════════════════════════════════════════════════════════════


class TestStarterKitLedger:

    def test_starter_kit_posts_from_start_location_treasury(self, db_session):
        _seed_region(db_session, location_id=50, region_id=7)
        _create_character(db_session, character_id=5, currency_balance=0)

        crud.post_starter_kit(db_session, 5, 100, 50, metadata={"class_id": 1})
        db_session.commit()

        ops = _ops(db_session, "starter_kit")
        assert len(ops) == 1
        assert ops[0][2] == "starter_kit:c:5"
        assert _legs(db_session, ops[0][0]) == [("region_treasury", 7, "character", 5, 100, "main")]
        assert db_session.execute(text("SELECT currency_balance FROM characters WHERE id = 5")).scalar() == 100
        assert _count_gold_transactions(db_session) == 0

    def test_starter_kit_without_location_uses_world(self, db_session):
        _create_character(db_session, character_id=5, currency_balance=0)
        crud.post_starter_kit(db_session, 5, 60, None)
        db_session.commit()
        ops = _ops(db_session, "starter_kit")
        assert _legs(db_session, ops[0][0]) == [("world_treasury", 0, "character", 5, 60, "main")]

    def test_zero_kit_posts_nothing(self, db_session):
        _create_character(db_session, character_id=5, currency_balance=0)
        crud.post_starter_kit(db_session, 5, 0, None)
        db_session.commit()
        assert _ops(db_session) == []


# ═══════════════════════════════════════════════════════════════════════════
# Tests: the ORM balance guard (strict since FEAT-181 B2)
# ═══════════════════════════════════════════════════════════════════════════


class TestBalanceGuard:

    def test_orm_write_of_balance_is_rejected(self, db_session):
        import econ_ledger
        _create_character(db_session, character_id=1, currency_balance=100)
        char = db_session.query(models.Character).get(1)
        char.currency_balance = 999
        with pytest.raises(econ_ledger.EconomyError):
            db_session.flush()
        db_session.rollback()

    def test_allow_direct_balance_write_lets_fixtures_seed(self, db_session):
        import econ_ledger
        _create_character(db_session, character_id=1, currency_balance=100)
        char = db_session.query(models.Character).get(1)
        with econ_ledger.allow_direct_balance_write(db_session):
            char.currency_balance = 999
            db_session.commit()
        assert db_session.execute(text("SELECT currency_balance FROM characters WHERE id = 1")).scalar() == 999


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /characters/internal/deduct-gold (FEAT-181 C3)
# ═══════════════════════════════════════════════════════════════════════════


class TestDeductGoldLedger:

    def test_old_shape_posts_dungeon_expense(self, client_with_db):
        """dungeon-service sends only character_id + amount: still works, money goes to a treasury."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)

        r = client.post("/characters/internal/deduct-gold", json={"character_id": 1, "amount": 30},
                        headers=INTERNAL_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"ok": True, "new_balance": 70, "duplicate": False}
        ops = _ops(session, "dungeon_expense")
        assert _legs(session, ops[0][0]) == [("character", 1, "world_treasury", 0, 30, "main")]
        assert _ledger_closes(session)

    def test_location_routes_to_region_with_tax(self, client_with_db):
        client, session = client_with_db
        _seed_region(session, location_id=50, region_id=7, country_id=3)
        _create_character(session, character_id=1, currency_balance=100)

        r = client.post("/characters/internal/deduct-gold",
                        json={"character_id": 1, "amount": 50, "location_id": 50}, headers=INTERNAL_HEADERS)
        assert r.status_code == 200
        ops = _ops(session, "dungeon_expense")
        assert _legs(session, ops[0][0]) == [
            ("character", 1, "region_treasury", 7, 50, "main"),
            ("region_treasury", 7, "country_treasury", 3, 5, "tax"),
        ]
        assert _ledger_closes(session)

    def test_insufficient_gold_is_400_and_moves_nothing(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=10)

        r = client.post("/characters/internal/deduct-gold", json={"character_id": 1, "amount": 30},
                        headers=INTERNAL_HEADERS)
        assert r.status_code == 400
        assert r.json()["detail"].startswith("Недостаточно золота")
        assert _ops(session) == []
        assert session.execute(text("SELECT currency_balance FROM characters WHERE id = 1")).scalar() == 10

    def test_duplicate_key_charges_once(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        body = {"character_id": 1, "amount": 20, "idempotency_key": "dungeon_expense:s:1:rest:2"}

        r1 = client.post("/characters/internal/deduct-gold", json=body, headers=INTERNAL_HEADERS)
        r2 = client.post("/characters/internal/deduct-gold", json=body, headers=INTERNAL_HEADERS)
        assert r1.json()["duplicate"] is False and r2.json()["duplicate"] is True
        assert r2.json()["new_balance"] == 80
        assert len(_ops(session)) == 1

    def test_unknown_op_type_rejected(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        r = client.post("/characters/internal/deduct-gold",
                        json={"character_id": 1, "amount": 5, "op_type": "admin_adjust"}, headers=INTERNAL_HEADERS)
        assert r.status_code == 422
        assert _ops(session) == []

    def test_requires_internal_token(self, client_with_db):
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        r = client.post("/characters/internal/deduct-gold", json={"character_id": 1, "amount": 5})
        assert r.status_code == 401
        assert _ops(session) == []
