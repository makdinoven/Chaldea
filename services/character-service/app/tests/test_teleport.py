"""
Tests for FEAT-123 — character-service teleport flow + admin links CRUD (T15).

Covers:
- POST /characters/npcs/{id}/teleport — success, insufficient gold, cooldown,
  broken link, source not teleport master, player not in source location.
- GET /characters/npcs/{id}/teleport-options — happy path + auto-filtering.
- Admin CRUD /characters/admin/teleport-links — bidirectional/non-bidirectional
  create, validation, duplicates, delete with reverse, auth (401/403).
- NPC role change side-effect: purge of links when role moves away from
  teleport_master (covered via direct CRUD purge — endpoint hits cross-service
  HTTP that is out of scope here).
- Concurrency smoke: cooldown blocks the second teleport.
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    text as sa_text,
)

import database
from database import Base
import models
import crud
from main import app, get_db
from auth_http import (
    get_admin_user,
    get_current_user_via_http,
    OAUTH2_SCHEME,
    UserRead,
)


# ---------------------------------------------------------------------------
# Extra tables required by raw SQL inside crud.execute_teleport / options
#   - users (current_character_id lookup)
#   - Locations (location name lookup)
# Both belong to other services in production but live in the same DB.
# ---------------------------------------------------------------------------

class _UsersTable(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    current_character_id = Column(Integer, nullable=True)
    username = Column(String(80), nullable=True)


class _LocationsTable(Base):
    __tablename__ = "Locations"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAYER_USER_ID = 100
LOC_A_ID = 10
LOC_B_ID = 20

_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=[
        "npcs:read", "npcs:create", "npcs:update", "npcs:delete",
        "characters:read",
    ],
)

_PLAYER_USER = UserRead(
    id=PLAYER_USER_ID,
    username="player",
    role="user",
    permissions=[],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)

    # Seed Locations
    session.execute(
        sa_text("INSERT INTO Locations (id, name) VALUES (:id, :name)"),
        {"id": LOC_A_ID, "name": "Локация A"},
    )
    session.execute(
        sa_text("INSERT INTO Locations (id, name) VALUES (:id, :name)"),
        {"id": LOC_B_ID, "name": "Локация B"},
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


def _make_character(
    session,
    *,
    name,
    is_npc,
    npc_role,
    location_id,
    user_id=None,
    currency_balance=0,
    last_teleport_at=None,
):
    char = models.Character(
        name=name,
        id_race=1,
        id_subrace=1,
        id_class=1,
        appearance="test",
        avatar="test.jpg",
        is_npc=is_npc,
        npc_role=npc_role,
        npc_status="alive" if is_npc else None,
        current_location_id=location_id,
        level=1,
        stat_points=0,
        currency_balance=currency_balance,
        user_id=user_id,
        last_teleport_at=last_teleport_at,
    )
    session.add(char)
    session.commit()
    session.refresh(char)
    return char


@pytest.fixture
def world(db_session):
    """Create two teleport-master NPCs in two locations + a player in loc A."""
    npc_a = _make_character(
        db_session, name="Мастер A", is_npc=True,
        npc_role="teleport_master", location_id=LOC_A_ID,
    )
    npc_b = _make_character(
        db_session, name="Мастер B", is_npc=True,
        npc_role="teleport_master", location_id=LOC_B_ID,
    )
    player = _make_character(
        db_session, name="Игрок", is_npc=False, npc_role=None,
        location_id=LOC_A_ID, user_id=PLAYER_USER_ID, currency_balance=500,
    )

    # link A -> B (cost 100), and B -> A (cost 100)
    link_ab = models.TeleportLink(
        from_npc_id=npc_a.id, to_npc_id=npc_b.id, cost_gold=100,
    )
    link_ba = models.TeleportLink(
        from_npc_id=npc_b.id, to_npc_id=npc_a.id, cost_gold=100,
    )
    db_session.add_all([link_ab, link_ba])
    db_session.commit()
    db_session.refresh(link_ab)
    db_session.refresh(link_ba)

    # users row pointing at our player
    db_session.execute(
        sa_text(
            "INSERT INTO users (id, current_character_id, username) "
            "VALUES (:id, :cid, :u)"
        ),
        {"id": PLAYER_USER_ID, "cid": player.id, "u": "player"},
    )
    db_session.commit()

    return {
        "npc_a": npc_a,
        "npc_b": npc_b,
        "player": player,
        "link_ab": link_ab,
        "link_ba": link_ba,
    }


def _player_overrides(db_session):
    def override_get_db():
        yield db_session

    def override_user():
        return _PLAYER_USER

    def override_token():
        return "fake-player-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_user
    app.dependency_overrides[OAUTH2_SCHEME] = override_token


def _admin_overrides(db_session):
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


@pytest.fixture
def player_client(db_session):
    _player_overrides(db_session)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    _admin_overrides(db_session)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. POST /characters/npcs/{id}/teleport — happy path
# ===========================================================================

class TestTeleportSuccess:
    def test_teleport_success_path(self, player_client, db_session, world):
        """Gold deducted, location moved, last_teleport_at set, gold tx logged."""
        before_balance = world["player"].currency_balance

        with patch.object(crud, "log_gold_transaction", wraps=crud.log_gold_transaction) as spy:
            resp = player_client.post(
                f"/characters/npcs/{world['npc_a'].id}/teleport",
                json={"link_id": world["link_ab"].id},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["new_location_id"] == LOC_B_ID
        assert body["new_location_name"] == "Локация B"
        assert body["currency_balance"] == before_balance - 100
        assert body["last_teleport_at"] is not None

        # log_gold_transaction must have been called once with negative amount
        assert spy.called
        kwargs = spy.call_args.kwargs
        assert kwargs["amount"] == -100
        assert kwargs["transaction_type"] == "teleport"

        # DB-level assertions
        db_session.expire_all()
        player = db_session.query(models.Character).filter_by(id=world["player"].id).first()
        assert player.current_location_id == LOC_B_ID
        assert player.currency_balance == before_balance - 100
        assert player.last_teleport_at is not None

        tx = (
            db_session.query(models.GoldTransaction)
            .filter_by(character_id=player.id, transaction_type="teleport")
            .first()
        )
        assert tx is not None
        assert tx.amount == -100


# ===========================================================================
# 2. POST teleport — error paths
# ===========================================================================

class TestTeleportErrors:
    def test_insufficient_gold_returns_402(self, player_client, db_session, world):
        # Drain the player's gold
        world["player"].currency_balance = 10
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 402
        detail = resp.json()["detail"]
        assert detail["error"] == "insufficient_gold"
        assert detail["required"] == 100

        # Player must NOT have moved
        db_session.expire_all()
        player = db_session.query(models.Character).filter_by(id=world["player"].id).first()
        assert player.current_location_id == LOC_A_ID

    def test_cooldown_active_returns_409(self, player_client, db_session, world):
        # Set last_teleport_at to 1 hour ago
        world["player"].last_teleport_at = datetime.utcnow() - timedelta(hours=1)
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["error"] == "cooldown_active"
        assert detail["cooldown_seconds_remaining"] > 0
        assert detail["cooldown_seconds_remaining"] <= 23 * 3600 + 60

    def test_broken_link_target_role_downgraded_returns_422(
        self, player_client, db_session, world
    ):
        # Demote target NPC away from teleport_master
        world["npc_b"].npc_role = "merchant"
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 422

    def test_broken_link_filtered_from_options(self, player_client, db_session, world):
        """If target NPC role is downgraded, options endpoint hides the link."""
        world["npc_b"].npc_role = "guard"
        db_session.commit()

        resp = player_client.get(
            f"/characters/npcs/{world['npc_a'].id}/teleport-options"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["options"] == []

    def test_source_not_teleport_master_returns_422(
        self, player_client, db_session, world
    ):
        # Demote source NPC
        world["npc_a"].npc_role = "merchant"
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 422

    def test_player_not_in_source_npc_location_returns_422(
        self, player_client, db_session, world
    ):
        # Move the player elsewhere
        world["player"].current_location_id = 999
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 422


# ===========================================================================
# 3. GET teleport-options
# ===========================================================================

class TestTeleportOptions:
    def test_options_returns_target_location_name(
        self, player_client, db_session, world
    ):
        resp = player_client.get(
            f"/characters/npcs/{world['npc_a'].id}/teleport-options"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["from_npc_id"] == world["npc_a"].id
        assert body["cooldown_seconds_remaining"] == 0
        assert len(body["options"]) == 1
        opt = body["options"][0]
        assert opt["to_npc_id"] == world["npc_b"].id
        assert opt["to_location_id"] == LOC_B_ID
        assert opt["to_location_name"] == "Локация B"
        assert opt["cost_gold"] == 100

    def test_options_404_when_not_teleport_master(
        self, player_client, db_session, world
    ):
        world["npc_a"].npc_role = "guard"
        db_session.commit()

        resp = player_client.get(
            f"/characters/npcs/{world['npc_a'].id}/teleport-options"
        )
        assert resp.status_code == 404


# ===========================================================================
# 4. Admin CRUD /admin/teleport-links
# ===========================================================================

class TestAdminTeleportLinksCRUD:
    def test_create_bidirectional_creates_two_rows(self, admin_client, db_session):
        # Two fresh teleport masters
        npc1 = _make_character(
            db_session, name="M1", is_npc=True,
            npc_role="teleport_master", location_id=LOC_A_ID,
        )
        npc2 = _make_character(
            db_session, name="M2", is_npc=True,
            npc_role="teleport_master", location_id=LOC_B_ID,
        )

        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": npc1.id,
                "to_npc_id": npc2.id,
                "cost_gold": 50,
                "bidirectional": True,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 2

        rows = (
            db_session.query(models.TeleportLink)
            .filter(
                (models.TeleportLink.from_npc_id == npc1.id)
                | (models.TeleportLink.from_npc_id == npc2.id)
            )
            .all()
        )
        assert len(rows) == 2

    def test_create_non_bidirectional_creates_one_row(self, admin_client, db_session):
        npc1 = _make_character(
            db_session, name="N1", is_npc=True,
            npc_role="teleport_master", location_id=LOC_A_ID,
        )
        npc2 = _make_character(
            db_session, name="N2", is_npc=True,
            npc_role="teleport_master", location_id=LOC_B_ID,
        )

        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": npc1.id,
                "to_npc_id": npc2.id,
                "cost_gold": 75,
                "bidirectional": False,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 1

    def test_create_with_non_teleport_master_returns_422(
        self, admin_client, db_session
    ):
        npc1 = _make_character(
            db_session, name="TM", is_npc=True,
            npc_role="teleport_master", location_id=LOC_A_ID,
        )
        npc2 = _make_character(
            db_session, name="Merchant", is_npc=True,
            npc_role="merchant", location_id=LOC_B_ID,
        )

        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": npc1.id,
                "to_npc_id": npc2.id,
                "cost_gold": 50,
                "bidirectional": True,
            },
        )
        assert resp.status_code == 422

    def test_create_duplicate_pair_returns_409(self, admin_client, db_session, world):
        # link A->B already exists in `world`
        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": world["npc_a"].id,
                "to_npc_id": world["npc_b"].id,
                "cost_gold": 100,
                "bidirectional": False,
            },
        )
        assert resp.status_code == 409

    def test_delete_with_delete_reverse_true_removes_both(
        self, admin_client, db_session, world
    ):
        link_id = world["link_ab"].id
        resp = admin_client.delete(
            f"/characters/admin/teleport-links/{link_id}",
            params={"delete_reverse": "true"},
        )
        assert resp.status_code == 200

        remaining = (
            db_session.query(models.TeleportLink)
            .filter(
                (
                    (models.TeleportLink.from_npc_id == world["npc_a"].id)
                    & (models.TeleportLink.to_npc_id == world["npc_b"].id)
                )
                | (
                    (models.TeleportLink.from_npc_id == world["npc_b"].id)
                    & (models.TeleportLink.to_npc_id == world["npc_a"].id)
                )
            )
            .all()
        )
        assert remaining == []


# ===========================================================================
# 5. Admin CRUD — auth
# ===========================================================================

class TestAdminTeleportLinksAuth:
    def test_unauthenticated_request_rejected(self, db_session):
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/characters/admin/teleport-links")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()

    def test_regular_user_rejected(self, db_session):
        regular_user = UserRead(
            id=2, username="player", role="user", permissions=[]
        )

        def override_get_db():
            yield db_session

        def override_user():
            return regular_user

        def override_token():
            return "fake-user-token"

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user_via_http] = override_user
        app.dependency_overrides[OAUTH2_SCHEME] = override_token
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/characters/admin/teleport-links")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ===========================================================================
# 6. NPC role change side-effect — purge_teleport_links_for_npc
# ===========================================================================

class TestNpcRoleChangeSideEffect:
    def test_purge_removes_all_links_for_npc(self, db_session, world):
        """Direct CRUD test: purge removes both incoming and outgoing links."""
        # Sanity: both links exist
        assert db_session.query(models.TeleportLink).count() == 2

        crud.purge_teleport_links_for_npc(db_session, world["npc_a"].id)
        db_session.commit()

        rows = db_session.query(models.TeleportLink).all()
        # Both A->B and B->A involved npc_a, so both should be gone
        assert rows == []


# ===========================================================================
# 7. Concurrency smoke — second teleport blocked by cooldown
# ===========================================================================

class TestTeleportConcurrencySmoke:
    def test_second_teleport_blocked_by_cooldown(
        self, player_client, db_session, world
    ):
        """Two sequential teleports: first succeeds, second fails with 409.

        SQLite in-memory cannot model true row-locking races, but the cooldown
        guarantees only one of N requests can succeed in a 24h window — which
        is the same end-state guaranteed by FOR UPDATE in production MySQL.
        """
        resp1 = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp1.status_code == 200, resp1.text

        # Player is now in B; to attempt a second teleport from B we need the
        # B->A link, with the player already in loc B (which they are after
        # the first teleport). Cooldown should kick in.
        resp2 = player_client.post(
            f"/characters/npcs/{world['npc_b'].id}/teleport",
            json={"link_id": world["link_ba"].id},
        )
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["error"] == "cooldown_active"
