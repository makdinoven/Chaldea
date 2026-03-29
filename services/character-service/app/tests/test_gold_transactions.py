"""
Task #13 — QA: gold_transactions tests (character-service).

Tests that gold modifications create gold_transaction records:
1. add_rewards_to_character() with gold > 0 creates transaction (type "battle_reward")
2. add_rewards_to_character() with gold = 0 does NOT create a transaction
3. Admin currency update creates transaction (type "admin_adjust")
4. Starter kit gold creates transaction (type "starter_kit")
5. log_gold_transaction() helper — correct fields stored
6. Transaction failure doesn't break the main gold operation (try/except)
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


def _count_gold_transactions(session, character_id=None, transaction_type=None):
    """Count rows in gold_transactions, optionally filtered."""
    q = "SELECT COUNT(*) FROM gold_transactions WHERE 1=1"
    params = {}
    if character_id is not None:
        q += " AND character_id = :cid"
        params["cid"] = character_id
    if transaction_type is not None:
        q += " AND transaction_type = :ttype"
        params["ttype"] = transaction_type
    row = session.execute(text(q), params).fetchone()
    return row[0]


def _get_gold_transaction(session, character_id, transaction_type=None):
    """Fetch the first gold_transaction row matching the filter."""
    q = "SELECT id, character_id, amount, balance_after, transaction_type, source, metadata FROM gold_transactions WHERE character_id = :cid"
    params = {"cid": character_id}
    if transaction_type:
        q += " AND transaction_type = :ttype"
        params["ttype"] = transaction_type
    q += " ORDER BY id DESC LIMIT 1"
    return session.execute(text(q), params).fetchone()


_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
    ],
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
# Tests: add_rewards_to_character creates gold_transaction
# ═══════════════════════════════════════════════════════════════════════════


class TestAddRewardsGoldTransaction:
    """Tests that add_rewards_to_character logs gold transactions."""

    def test_gold_reward_creates_transaction(self, client_with_db):
        """add_rewards with gold > 0 creates a gold_transaction with type 'battle_reward'."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        response = client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 50})
        assert response.status_code == 200

        # Verify transaction was created
        count = _count_gold_transactions(session, character_id=1, transaction_type="battle_reward")
        assert count == 1

        tx = _get_gold_transaction(session, character_id=1, transaction_type="battle_reward")
        assert tx is not None
        assert tx[2] == 50       # amount
        assert tx[3] == 150      # balance_after (100 + 50)
        assert tx[4] == "battle_reward"
        assert tx[5] == "battle-service"  # source

    def test_zero_gold_does_not_create_transaction(self, client_with_db):
        """add_rewards with gold=0 does NOT create a gold_transaction."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        response = client.post("/characters/1/add_rewards", json={"xp": 50, "gold": 0})
        assert response.status_code == 200

        count = _count_gold_transactions(session, character_id=1)
        assert count == 0

    def test_multiple_rewards_create_multiple_transactions(self, client_with_db):
        """Multiple add_rewards calls create separate transaction records."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=0)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 10})
        client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 20})

        count = _count_gold_transactions(session, character_id=1, transaction_type="battle_reward")
        assert count == 2


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Admin currency update creates gold_transaction
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminCurrencyGoldTransaction:
    """Tests that admin currency changes log gold transactions."""

    @patch("main.httpx.AsyncClient")
    def test_admin_currency_update_creates_transaction(self, mock_httpx, admin_client):
        """Admin changing currency_balance creates a gold_transaction with type 'admin_adjust'."""
        client, session = admin_client
        _create_character(session, character_id=1, currency_balance=100)

        response = client.put(
            "/characters/admin/1",
            json={"currency_balance": 500},
        )
        assert response.status_code == 200

        count = _count_gold_transactions(session, character_id=1, transaction_type="admin_adjust")
        assert count == 1

        tx = _get_gold_transaction(session, character_id=1, transaction_type="admin_adjust")
        assert tx is not None
        assert tx[2] == 400      # amount = 500 - 100
        assert tx[3] == 500      # balance_after
        assert tx[4] == "admin_adjust"
        assert tx[5] == "admin_panel"

    @patch("main.httpx.AsyncClient")
    def test_admin_same_balance_no_transaction(self, mock_httpx, admin_client):
        """Admin setting same balance does NOT create a transaction."""
        client, session = admin_client
        _create_character(session, character_id=1, currency_balance=100)

        response = client.put(
            "/characters/admin/1",
            json={"currency_balance": 100},
        )
        assert response.status_code == 200

        count = _count_gold_transactions(session, character_id=1, transaction_type="admin_adjust")
        assert count == 0

    @patch("main.httpx.AsyncClient")
    def test_admin_decrease_balance_creates_negative_transaction(self, mock_httpx, admin_client):
        """Admin decreasing balance creates a negative amount transaction."""
        client, session = admin_client
        _create_character(session, character_id=1, currency_balance=500)

        response = client.put(
            "/characters/admin/1",
            json={"currency_balance": 200},
        )
        assert response.status_code == 200

        tx = _get_gold_transaction(session, character_id=1, transaction_type="admin_adjust")
        assert tx is not None
        assert tx[2] == -300     # amount = 200 - 500


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Starter kit gold creates gold_transaction
# ═══════════════════════════════════════════════════════════════════════════


class TestStarterKitGoldTransaction:
    """Tests that starter kit gold (character creation) creates a transaction."""

    def test_starter_kit_with_gold_creates_transaction(self, db_session):
        """Calling log_gold_transaction with type 'starter_kit' stores correctly."""
        # We test the helper directly since the full approval flow has many
        # external dependencies. The main.py approval endpoint calls
        # crud.log_gold_transaction(..., transaction_type="starter_kit") directly.
        _create_character(db_session, character_id=5, currency_balance=100)

        crud.log_gold_transaction(
            db_session, 5,
            amount=100,
            balance_after=100,
            transaction_type="starter_kit",
            source="character_creation",
            metadata={"class_id": 1},
        )
        db_session.commit()

        tx = _get_gold_transaction(db_session, character_id=5, transaction_type="starter_kit")
        assert tx is not None
        assert tx[2] == 100      # amount
        assert tx[3] == 100      # balance_after
        assert tx[4] == "starter_kit"
        assert tx[5] == "character_creation"


# ═══════════════════════════════════════════════════════════════════════════
# Tests: log_gold_transaction() helper directly
# ═══════════════════════════════════════════════════════════════════════════


class TestLogGoldTransactionHelper:
    """Tests for the log_gold_transaction() CRUD helper."""

    def test_correct_fields_stored(self, db_session):
        """All fields are persisted correctly."""
        _create_character(db_session, character_id=1, currency_balance=200)

        crud.log_gold_transaction(
            db_session, 1,
            amount=-50,
            balance_after=150,
            transaction_type="test_type",
            source="test_source",
            metadata={"key": "value"},
        )
        db_session.commit()

        tx = _get_gold_transaction(db_session, character_id=1, transaction_type="test_type")
        assert tx is not None
        assert tx[1] == 1            # character_id
        assert tx[2] == -50          # amount
        assert tx[3] == 150          # balance_after
        assert tx[4] == "test_type"  # transaction_type
        assert tx[5] == "test_source"  # source
        # metadata stored as JSON
        assert tx[6] is not None

    def test_optional_fields_can_be_none(self, db_session):
        """source and metadata can be None."""
        _create_character(db_session, character_id=1, currency_balance=100)

        crud.log_gold_transaction(
            db_session, 1,
            amount=10,
            balance_after=110,
            transaction_type="minimal",
            source=None,
            metadata=None,
        )
        db_session.commit()

        tx = _get_gold_transaction(db_session, character_id=1, transaction_type="minimal")
        assert tx is not None
        assert tx[5] is None  # source
        # metadata_ column stores None or JSON 'null' depending on ORM serialization
        assert tx[6] is None or tx[6] == "null"

    def test_positive_and_negative_amounts(self, db_session):
        """Both positive (earn) and negative (spend) amounts are stored."""
        _create_character(db_session, character_id=1, currency_balance=500)

        crud.log_gold_transaction(db_session, 1, 100, 600, "earn_test")
        crud.log_gold_transaction(db_session, 1, -200, 400, "spend_test")
        db_session.commit()

        earn_tx = _get_gold_transaction(db_session, 1, "earn_test")
        spend_tx = _get_gold_transaction(db_session, 1, "spend_test")
        assert earn_tx[2] == 100
        assert spend_tx[2] == -200


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Transaction failure doesn't break main gold operation
# ═══════════════════════════════════════════════════════════════════════════


class TestTransactionFailureIsolation:
    """Tests that gold_transaction logging failure does not break the gold operation."""

    def test_add_rewards_succeeds_when_logging_fails(self, client_with_db):
        """Even if log_gold_transaction raises, add_rewards still updates balance."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        with patch("crud.GoldTransaction", side_effect=Exception("DB write failed")):
            response = client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 50})

        assert response.status_code == 200
        data = response.json()
        assert data["new_balance"] == 150  # Gold still added despite logging failure

    def test_log_gold_transaction_catches_exception(self, db_session):
        """log_gold_transaction catches exceptions and doesn't re-raise."""
        # Simulate by passing invalid data that could cause issues
        # The function has a try/except that logs warning but doesn't raise
        _create_character(db_session, character_id=1, currency_balance=100)

        # Patch GoldTransaction to raise on creation
        with patch("crud.GoldTransaction", side_effect=Exception("Simulated failure")):
            # This should NOT raise
            crud.log_gold_transaction(
                db_session, 1,
                amount=50,
                balance_after=150,
                transaction_type="test",
            )
        # If we reach here, the exception was caught
