"""
Tests for user-facing endpoint authentication in inventory-service.

Covers:
- I1: POST /inventory/{cid}/items — admin grant, require_permission("items:update")
- I2: POST /inventory/internal/characters/{cid}/items — verify_internal_token (fail-closed)
- I3: DELETE /inventory/{cid}/items/{iid} — ownership via verify_character_ownership
- I4: POST /inventory/{cid}/equip — ownership via verify_character_ownership
- I5: POST /inventory/{cid}/unequip — ownership via verify_character_ownership
- I6: POST /inventory/{cid}/use_item — ownership via verify_character_ownership
"""

from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, event, text, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import auth_http
import database
import models
from auth_http import get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


# ---------------------------------------------------------------------------
# Test engine (self-contained, same approach as conftest.py)
# ---------------------------------------------------------------------------

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Patch database module
database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

# Patch ENUM columns to String for SQLite compatibility
for col in models.Items.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(100)

for col in models.EquipmentSlot.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(100)

for col in models.TradeOffer.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth_db_session():
    """Create all ORM tables + characters table, yield session, drop all."""
    database.Base.metadata.create_all(bind=_test_engine)

    # Create the `characters` table (not owned by this service but needed
    # by verify_character_ownership raw SQL query).
    with _test_engine.connect() as conn:
        conn.execute(text(
            """CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                name TEXT NOT NULL
            )"""
        ))
        conn.commit()

    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Disable FK checks before drop_all to avoid circular dependency errors
        # (items <-> recipes have mutual FKs via blueprint_recipe_id / result_item_id)
        with _test_engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.commit()
        database.Base.metadata.drop_all(bind=_test_engine)
        with _test_engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS characters"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()


@pytest.fixture()
def auth_client(auth_db_session):
    """TestClient with DB override, NO auth override."""
    from main import get_db as main_get_db

    def override_get_db():
        yield auth_db_session

    app.dependency_overrides[main_get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def _insert_character(auth_db_session):
    """Insert a character row owned by user_id=1."""
    auth_db_session.execute(
        text("INSERT INTO characters (id, user_id, name) VALUES (:id, :uid, :name)"),
        {"id": 1, "uid": 1, "name": "TestChar"},
    )
    auth_db_session.commit()
    return 1


# ===========================================================================
# I3: DELETE /inventory/{cid}/items/{iid} — ownership check
# ===========================================================================

class TestRemoveItemAuth:
    """Auth tests for DELETE /inventory/{cid}/items/{iid}."""

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.delete("/inventory/1/items/1?quantity=1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to remove item from character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.delete(
            "/inventory/1/items/1?quantity=1",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.delete(
            "/inventory/1/items/1?quantity=1",
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; likely 404 because there's no item in inventory
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)


# ===========================================================================
# I4: POST /inventory/{cid}/equip — ownership check
# ===========================================================================

class TestEquipItemAuth:
    """Auth tests for POST /inventory/{cid}/equip."""

    EQUIP_PAYLOAD = {"item_id": 1}

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.post("/inventory/1/equip", json=self.EQUIP_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to equip on character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/equip",
            json=self.EQUIP_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/equip",
            json=self.EQUIP_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; may fail on business logic (item not found)
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)


# ===========================================================================
# I5: POST /inventory/{cid}/unequip — ownership check
# ===========================================================================

class TestUnequipItemAuth:
    """Auth tests for POST /inventory/{cid}/unequip."""

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.post("/inventory/1/unequip?slot_type=head")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to unequip from character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/unequip?slot_type=head",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/unequip?slot_type=head",
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; may fail on business logic (slot empty)
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)


# ===========================================================================
# I6: POST /inventory/{cid}/use_item — ownership check
# ===========================================================================

class TestUseItemAuth:
    """Auth tests for POST /inventory/{cid}/use_item."""

    USE_PAYLOAD = {"item_id": 1, "quantity": 1}

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.post("/inventory/1/use_item", json=self.USE_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to use item on character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/use_item",
            json=self.USE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/use_item",
            json=self.USE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; may fail on business logic (item not found)
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)


# ===========================================================================
# FEAT-167 — I1/I2: granting an item is no longer open to the world
# ===========================================================================
# Before this feature `POST /inventory/{cid}/items` had zero dependencies: any
# client reachable through the gateway could put any item in any quantity into
# any character's inventory. This file had no case for that POST at all, which
# is why the hole survived. Both audiences are pinned now:
#   * internal services  -> POST /inventory/internal/characters/{cid}/items
#                           behind the fail-closed `verify_internal_token`
#   * the admin UI       -> POST /inventory/{cid}/items behind `items:update`

_INTERNAL_TOKEN = "test-internal-token"
_INTERNAL_PATH = "/inventory/internal/characters/1/items"
_ADMIN_PATH = "/inventory/1/items"


@pytest.fixture()
def _internal_token(monkeypatch):
    """`auth_http` reads the secret into a module constant at import time — pin
    the constant, not the env var."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _INTERNAL_TOKEN)
    return _INTERNAL_TOKEN


@pytest.fixture()
def _seed_item(auth_db_session):
    """One grantable item (real column names, committed and read back)."""
    item = models.Items(
        name="Тестовый предмет FEAT-167",
        item_type="misc",
        item_rarity="common",
        item_level=1,
        max_stack_size=10,
    )
    auth_db_session.add(item)
    auth_db_session.commit()
    auth_db_session.refresh(item)
    return item


def _inventory_quantity(session, character_id, item_id):
    """Total quantity actually stored — the DB is the witness, not the response."""
    rows = session.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id,
    ).all()
    return sum(row.quantity for row in rows)


class TestAddItemInternalAuth:
    """POST /inventory/internal/characters/{cid}/items — internal token only."""

    def test_no_header_returns_401(self, auth_client, _internal_token, _seed_item,
                                   auth_db_session):
        response = auth_client.post(
            _INTERNAL_PATH, json={"item_id": _seed_item.id, "quantity": 3}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Недействительный internal token"
        # and nothing was granted
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0

    def test_wrong_header_returns_401(self, auth_client, _internal_token,
                                      _seed_item, auth_db_session):
        response = auth_client.post(
            _INTERNAL_PATH,
            json={"item_id": _seed_item.id, "quantity": 3},
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 401
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0

    def test_empty_header_returns_401(self, auth_client, _internal_token,
                                      _seed_item, auth_db_session):
        response = auth_client.post(
            _INTERNAL_PATH,
            json={"item_id": _seed_item.id, "quantity": 3},
            headers={"X-Internal-Token": ""},
        )
        assert response.status_code == 401
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0

    def test_player_jwt_is_not_enough(self, auth_client, _internal_token,
                                      _seed_item, auth_db_session):
        """An ordinary player token must NOT open the internal route (the three
        locations-service callers used to forward exactly such a token)."""
        response = auth_client.post(
            _INTERNAL_PATH,
            json={"item_id": _seed_item.id, "quantity": 3},
            headers={"Authorization": "Bearer player-token"},
        )
        assert response.status_code == 401
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0

    def test_unset_token_env_fails_closed_with_503(self, auth_client, monkeypatch,
                                                   _seed_item, auth_db_session):
        """Fail-closed: an unconfigured service rejects everything with 503 and
        never silently grants the item."""
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        response = auth_client.post(
            _INTERNAL_PATH,
            json={"item_id": _seed_item.id, "quantity": 3},
            headers={"X-Internal-Token": "anything"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Internal service token не настроен"
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0

    def test_correct_header_grants_the_item(self, auth_client, _internal_token,
                                            _seed_item, auth_db_session):
        response = auth_client.post(
            _INTERNAL_PATH,
            json={"item_id": _seed_item.id, "quantity": 3},
            headers={"X-Internal-Token": _INTERNAL_TOKEN},
        )
        assert response.status_code == 200, response.text
        # read the state back from the DB, not from the response body
        auth_db_session.expire_all()
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 3

    def test_unknown_item_is_404_not_a_leak(self, auth_client, _internal_token):
        response = auth_client.post(
            _INTERNAL_PATH,
            json={"item_id": 999999, "quantity": 1},
            headers={"X-Internal-Token": _INTERNAL_TOKEN},
        )
        assert response.status_code == 404


class TestAddItemAdminAuth:
    """POST /inventory/{cid}/items — the admin UI path, `items:update`."""

    def test_anonymous_request_is_rejected(self, auth_client, _seed_item,
                                           auth_db_session):
        """The actual hole: an unauthenticated grant must never succeed."""
        response = auth_client.post(
            _ADMIN_PATH, json={"item_id": _seed_item.id, "quantity": 5}
        )
        assert response.status_code == 401
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0

    @patch("auth_http.requests.get")
    def test_authenticated_without_permission_returns_403(
        self, mock_get, auth_client, _seed_item, auth_db_session
    ):
        mock_get.return_value = _mock_response(
            200, {"id": 5, "username": "player", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
        try:
            response = auth_client.post(
                _ADMIN_PATH,
                json={"item_id": _seed_item.id, "quantity": 5},
                headers={"Authorization": "Bearer fake-token"},
            )
            assert response.status_code == 403
            assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0
        finally:
            app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_moderator_without_items_update_returns_403(
        self, mock_get, auth_client, _seed_item, auth_db_session
    ):
        """A moderator holding only `characters:update` cannot grant items —
        the accepted trade-off recorded in the feature's §3.2.3."""
        mock_get.return_value = _mock_response(
            200, {"id": 6, "username": "mod", "role": "moderator",
                  "permissions": ["characters:update"]}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
        try:
            response = auth_client.post(
                _ADMIN_PATH,
                json={"item_id": _seed_item.id, "quantity": 5},
                headers={"Authorization": "Bearer fake-token"},
            )
            assert response.status_code == 403
            assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0
        finally:
            app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_permission_holder_grants_the_item(
        self, mock_get, auth_client, _seed_item, auth_db_session
    ):
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin",
                  "permissions": ["items:update"]}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
        try:
            response = auth_client.post(
                _ADMIN_PATH,
                json={"item_id": _seed_item.id, "quantity": 5},
                headers={"Authorization": "Bearer fake-token"},
            )
            assert response.status_code == 200, response.text
            auth_db_session.expire_all()
            assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 5
        finally:
            app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    def test_internal_token_does_not_open_the_admin_route(
        self, auth_client, _internal_token, _seed_item, auth_db_session
    ):
        """The two audiences stay separate: the service token is not a JWT."""
        response = auth_client.post(
            _ADMIN_PATH,
            json={"item_id": _seed_item.id, "quantity": 5},
            headers={"X-Internal-Token": _INTERNAL_TOKEN},
        )
        assert response.status_code == 401
        assert _inventory_quantity(auth_db_session, 1, _seed_item.id) == 0


class TestNoUnauthenticatedGrantPathRemains:
    """A sweep rather than a single route: every POST route in this service whose
    path ends in `/items` must carry an auth dependency. Adding a new open grant
    route breaks this test."""

    def test_every_item_grant_route_has_a_dependency(self):
        from fastapi.routing import APIRoute

        offenders = []
        for route in app.routes:
            if not isinstance(route, APIRoute) or "POST" not in route.methods:
                continue
            if not route.path.endswith("/items"):
                continue
            dep_names = set()
            for dep in route.dependant.dependencies:
                call = dep.call
                dep_names.add(getattr(call, "__name__", type(call).__name__))
            guarded = any(
                name in dep_names
                for name in ("verify_internal_token", "checker",
                             "get_current_user_via_http", "get_admin_user")
            )
            if not guarded:
                offenders.append(f"{route.path} deps={sorted(dep_names)}")
        assert not offenders, (
            "item-grant route(s) without any auth dependency: " + "; ".join(offenders)
        )


# ===========================================================================
# FEAT-167 #18 — POST /inventory/ (create inventory + default equipment slots)
# ===========================================================================
# Pre-existing hole found by the Reviewer while closing FEAT-167: the creation
# route had zero dependencies, so an anonymous request through the gateway
# reached the handler (422 on the schema, not 401) and could create inventory
# rows and default equipment slots for arbitrary character ids.
#
# Its only caller is character-service (`crud.send_inventory_request`, the
# starter-kit grant during character creation), so it is now internal-only
# behind the fail-closed `verify_internal_token`. The matrix below is the same
# shape as `TestAddItemInternalAuth` above, and every rejection is checked
# against the DB: a guard that answers 401 *after* creating the slots would
# still fail here.

_CREATE_PATH = "/inventory/"
_CREATE_CHARACTER_ID = 4242


def _slot_count(session, character_id):
    return session.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id
    ).count()


class TestCreateInventoryInternalAuth:
    """POST /inventory/ — internal token only."""

    def _post(self, client, headers=None, items=None):
        return client.post(
            _CREATE_PATH,
            json={"character_id": _CREATE_CHARACTER_ID, "items": items or []},
            headers=headers or {},
        )

    def test_no_header_returns_401(self, auth_client, _internal_token,
                                   auth_db_session):
        response = self._post(auth_client)
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        assert _slot_count(auth_db_session, _CREATE_CHARACTER_ID) == 0

    def test_wrong_header_returns_401(self, auth_client, _internal_token,
                                      auth_db_session):
        response = self._post(auth_client, {"X-Internal-Token": "wrong-token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Недействительный internal token"
        assert _slot_count(auth_db_session, _CREATE_CHARACTER_ID) == 0

    def test_empty_header_returns_401(self, auth_client, _internal_token,
                                      auth_db_session):
        response = self._post(auth_client, {"X-Internal-Token": ""})
        assert response.status_code == 401
        assert _slot_count(auth_db_session, _CREATE_CHARACTER_ID) == 0

    def test_player_jwt_is_not_enough(self, auth_client, _internal_token,
                                      auth_db_session):
        """There is no player-facing caller: a JWT must not open the route."""
        response = self._post(auth_client, {"Authorization": "Bearer player-token"})
        assert response.status_code == 401
        assert _slot_count(auth_db_session, _CREATE_CHARACTER_ID) == 0

    def test_unset_token_env_fails_closed_with_503(self, auth_client, monkeypatch,
                                                   auth_db_session):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        for headers in ({}, {"X-Internal-Token": "anything"},
                        {"X-Internal-Token": ""}):
            response = self._post(auth_client, headers)
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "Internal service token не настроен"
        assert _slot_count(auth_db_session, _CREATE_CHARACTER_ID) == 0

    def test_correct_header_creates_the_slots(self, auth_client, _internal_token,
                                              auth_db_session):
        """Character creation must keep working end to end."""
        response = self._post(auth_client, {"X-Internal-Token": _INTERNAL_TOKEN})
        assert response.status_code == 200, response.text
        assert response.json()["character_id"] == _CREATE_CHARACTER_ID
        auth_db_session.expire_all()
        assert _slot_count(auth_db_session, _CREATE_CHARACTER_ID) > 0

    def test_correct_header_grants_the_starter_kit(self, auth_client,
                                                   _internal_token, _seed_item,
                                                   auth_db_session):
        response = self._post(
            auth_client, {"X-Internal-Token": _INTERNAL_TOKEN},
            items=[{"item_id": _seed_item.id, "quantity": 2}],
        )
        assert response.status_code == 200, response.text
        auth_db_session.expire_all()
        assert _inventory_quantity(
            auth_db_session, _CREATE_CHARACTER_ID, _seed_item.id
        ) == 2

    def test_header_name_is_case_insensitive_but_value_is_not(
        self, auth_client, _internal_token
    ):
        assert self._post(
            auth_client, {"x-internal-token": _INTERNAL_TOKEN}
        ).status_code not in (401, 503)
        assert self._post(
            auth_client, {"X-Internal-Token": _INTERNAL_TOKEN.upper()}
        ).status_code == 401

    def test_the_creation_route_is_gated_in_the_route_table(self):
        """A sweep, so un-gating the route fails here even if somebody rewrites
        the tests above around a new path."""
        from fastapi.routing import APIRoute

        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path != "/inventory/" or "POST" not in route.methods:
                continue
            names = {
                getattr(dep.call, "__name__", type(dep.call).__name__)
                for dep in route.dependant.dependencies
            }
            assert "verify_internal_token" in names, (
                f"POST /inventory/ is not gated any more: deps={sorted(names)}"
            )
            return
        pytest.fail("POST /inventory/ is missing from the route table")
