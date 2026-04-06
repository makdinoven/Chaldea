"""
Tests for admin NPC list endpoint fix (FEAT-110): mob exclusion and pagination.

Covers:
- GET /characters/admin/npcs excludes mobs (npc_role='mob') from results
- Pagination params (page, page_size) work correctly
- Response includes correct total, page, page_size metadata
- Explicit npc_role='mob' filter still returns empty (mobs never in NPC list)
- Page beyond data returns empty items with correct total
- Search filter (q) works alongside mob exclusion
"""

import pytest
from fastapi.testclient import TestClient

from auth_http import (
    get_admin_user,
    get_current_user_via_http,
    OAUTH2_SCHEME,
    UserRead,
)
from main import app, get_db
import models
import database


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=["npcs:read", "npcs:create", "npcs:update", "npcs:delete"],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(test_engine):
    """Real SQLite session for integration tests."""
    models.Base.metadata.create_all(bind=test_engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def npc_client(db_session):
    """TestClient with real DB and mocked admin auth."""

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
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def seed_data(db_session, seed_fk_data):
    """Seed reference data and return the session."""
    seed_fk_data(db_session)
    return db_session


@pytest.fixture
def create_npc(seed_data):
    """Helper to insert an NPC/mob character directly into the DB."""

    def _create(
        name="Тестовый НПС",
        npc_role="merchant",
        npc_status="alive",
        location_id=1,
        is_npc=True,
    ):
        npc = models.Character(
            name=name,
            id_race=1,
            id_subrace=1,
            id_class=1,
            appearance="test",
            avatar="test.jpg",
            is_npc=is_npc,
            npc_role=npc_role,
            npc_status=npc_status,
            current_location_id=location_id,
            level=1,
            stat_points=0,
            currency_balance=0,
        )
        seed_data.add(npc)
        seed_data.commit()
        seed_data.refresh(npc)
        return npc

    return _create


# ============================================================
# 1. Mob exclusion
# ============================================================


class TestAdminNpcListMobExclusion:
    """GET /characters/admin/npcs should never return mobs."""

    def test_mobs_excluded_from_results(self, npc_client, create_npc):
        """Characters with npc_role='mob' must not appear in NPC list."""
        create_npc(name="НПС-торговец", npc_role="merchant")
        create_npc(name="НПС-стражник", npc_role="guard")
        create_npc(name="Моб-волк", npc_role="mob")
        create_npc(name="Моб-скелет", npc_role="mob")

        resp = npc_client.get("/characters/admin/npcs")
        assert resp.status_code == 200
        body = resp.json()
        names = [item["name"] for item in body["items"]]

        assert "НПС-торговец" in names
        assert "НПС-стражник" in names
        assert "Моб-волк" not in names
        assert "Моб-скелет" not in names
        assert body["total"] == 2

    def test_explicit_mob_role_filter_returns_empty(self, npc_client, create_npc):
        """Even with npc_role='mob' filter, mobs should not appear (base exclusion wins)."""
        create_npc(name="Моб-дракон", npc_role="mob")
        create_npc(name="НПС-кузнец", npc_role="blacksmith")

        resp = npc_client.get("/characters/admin/npcs", params={"npc_role": "mob"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_only_npcs_with_is_npc_true_returned(self, npc_client, create_npc):
        """Player characters (is_npc=False) must not appear in the list."""
        create_npc(name="НПС-жрец", npc_role="priest")
        create_npc(name="Игрок", npc_role=None, is_npc=False)

        resp = npc_client.get("/characters/admin/npcs")
        assert resp.status_code == 200
        body = resp.json()
        names = [item["name"] for item in body["items"]]
        assert "НПС-жрец" in names
        assert "Игрок" not in names
        assert body["total"] == 1

    def test_various_npc_roles_returned(self, npc_client, create_npc):
        """All non-mob NPC roles should appear in results."""
        roles = ["merchant", "guard", "hero", "sage", "blacksmith", "healer"]
        for i, role in enumerate(roles):
            create_npc(name=f"НПС-{role}", npc_role=role)

        resp = npc_client.get("/characters/admin/npcs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == len(roles)
        assert len(body["items"]) == len(roles)


# ============================================================
# 2. Pagination
# ============================================================


class TestAdminNpcListPagination:
    """GET /characters/admin/npcs pagination params and metadata."""

    def test_default_pagination(self, npc_client, create_npc):
        """Default page=1, page_size=20 should be reflected in response."""
        create_npc(name="НПС-один", npc_role="merchant")

        resp = npc_client.get("/characters/admin/npcs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 1
        assert body["page_size"] == 20
        assert body["total"] == 1
        assert len(body["items"]) == 1

    def test_custom_page_size(self, npc_client, create_npc):
        """page_size param should limit items returned."""
        for i in range(5):
            create_npc(name=f"НПС-{i}", npc_role="merchant")

        resp = npc_client.get("/characters/admin/npcs", params={"page_size": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_second_page(self, npc_client, create_npc):
        """page=2 should return the next batch of items."""
        for i in range(5):
            create_npc(name=f"НПС-{i}", npc_role="guard")

        resp = npc_client.get("/characters/admin/npcs", params={"page": 2, "page_size": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["page"] == 2

    def test_last_page_partial(self, npc_client, create_npc):
        """Last page may have fewer items than page_size."""
        for i in range(5):
            create_npc(name=f"НПС-{i}", npc_role="sage")

        resp = npc_client.get("/characters/admin/npcs", params={"page": 3, "page_size": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["total"] == 5
        assert body["page"] == 3

    def test_page_beyond_data_returns_empty_items(self, npc_client, create_npc):
        """Requesting a page beyond the data should return empty items with correct total."""
        for i in range(3):
            create_npc(name=f"НПС-{i}", npc_role="healer")

        resp = npc_client.get("/characters/admin/npcs", params={"page": 10, "page_size": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 3
        assert body["page"] == 10
        assert body["page_size"] == 5

    def test_pagination_excludes_mobs_from_total(self, npc_client, create_npc):
        """Mobs should not count toward total in pagination."""
        for i in range(3):
            create_npc(name=f"НПС-{i}", npc_role="merchant")
        for i in range(2):
            create_npc(name=f"Моб-{i}", npc_role="mob")

        resp = npc_client.get("/characters/admin/npcs", params={"page_size": 10})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_items_ordered_by_id(self, npc_client, create_npc):
        """Items should be ordered by id ascending."""
        npc_a = create_npc(name="НПС-А", npc_role="merchant")
        npc_b = create_npc(name="НПС-Б", npc_role="guard")
        npc_c = create_npc(name="НПС-В", npc_role="sage")

        resp = npc_client.get("/characters/admin/npcs")
        assert resp.status_code == 200
        body = resp.json()
        ids = [item["id"] for item in body["items"]]
        assert ids == sorted(ids)


# ============================================================
# 3. Search + mob exclusion
# ============================================================


class TestAdminNpcListSearchAndFilters:
    """GET /characters/admin/npcs with search/filter params + mob exclusion."""

    def test_search_by_name_excludes_mobs(self, npc_client, create_npc):
        """Search query should find NPCs but never mobs."""
        create_npc(name="Торговец Иван", npc_role="merchant")
        create_npc(name="Моб Иван", npc_role="mob")

        resp = npc_client.get("/characters/admin/npcs", params={"q": "Иван"})
        assert resp.status_code == 200
        body = resp.json()
        names = [item["name"] for item in body["items"]]
        assert "Торговец Иван" in names
        assert "Моб Иван" not in names
        assert body["total"] == 1

    def test_filter_by_npc_role(self, npc_client, create_npc):
        """Filtering by a valid NPC role should work."""
        create_npc(name="Торговец", npc_role="merchant")
        create_npc(name="Стражник", npc_role="guard")

        resp = npc_client.get("/characters/admin/npcs", params={"npc_role": "guard"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Стражник"

    def test_filter_by_npc_status(self, npc_client, create_npc):
        """Filtering by npc_status should work alongside mob exclusion."""
        create_npc(name="Живой НПС", npc_role="merchant", npc_status="alive")
        create_npc(name="Мертвый НПС", npc_role="guard", npc_status="dead")
        create_npc(name="Живой Моб", npc_role="mob", npc_status="alive")

        resp = npc_client.get("/characters/admin/npcs", params={"npc_status": "alive"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        names = [item["name"] for item in body["items"]]
        assert "Живой НПС" in names
        assert "Живой Моб" not in names

    def test_filter_by_location(self, npc_client, create_npc):
        """Filtering by location_id should work alongside mob exclusion."""
        create_npc(name="НПС-лок1", npc_role="merchant", location_id=10)
        create_npc(name="НПС-лок2", npc_role="guard", location_id=20)
        create_npc(name="Моб-лок1", npc_role="mob", location_id=10)

        resp = npc_client.get("/characters/admin/npcs", params={"location_id": 10})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "НПС-лок1"

    def test_empty_result_with_filters(self, npc_client, create_npc):
        """No matches should return empty items with total=0."""
        create_npc(name="НПС", npc_role="merchant")

        resp = npc_client.get("/characters/admin/npcs", params={"q": "nonexistent"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


# ============================================================
# 4. Security — unauthorized access
# ============================================================


class TestAdminNpcListSecurity:
    """GET /characters/admin/npcs security tests."""

    def test_unauthenticated_request_rejected(self, db_session):
        """Request without auth token should be rejected."""
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/characters/admin/npcs")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()

    def test_user_without_permission_rejected(self, db_session):
        """User without npcs:read permission should be rejected."""
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
            resp = client.get("/characters/admin/npcs")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_sql_injection_in_search(self, npc_client, create_npc):
        """SQL injection attempt in search param should not crash the server."""
        create_npc(name="НПС", npc_role="merchant")
        resp = npc_client.get(
            "/characters/admin/npcs",
            params={"q": "'; DROP TABLE characters; --"},
        )
        assert resp.status_code in (200, 400)
