"""
Tests for the origin-country reference book of FEAT-154 (task #2).

Endpoints under test:
- ``GET    /locations/origins``              — public, soft-deleted rows hidden
- ``GET    /locations/admin/origins``        — ``origins:read``
- ``POST   /locations/admin/origins``        — ``origins:create``
- ``PUT    /locations/admin/origins/{id}``   — ``origins:update``
- ``DELETE /locations/admin/origins/{id}``   — ``origins:delete`` (soft delete)

Strategy:
- The crud layer runs against in-memory aiosqlite, because the soft-delete
  semantics ("the row is hidden, never removed") can only be proven against a
  real table.
- The routes run through the shared ``client`` fixture with crud mocked and
  ``auth_http.requests.get`` patched, matching ``test_game_time.py`` /
  ``test_rbac_enforcement.py``.

Note (N4/N5): the admin list includes soft-deleted rows *by default*
(``include_inactive`` defaults to ``True``) — otherwise a hidden origin could
never be found and restored. The public list is the opposite.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import BigInteger, select, func as sa_func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import schemas  # noqa: E402
from models import OriginCountry  # noqa: E402


# SQLite only auto-assigns a primary key for the exact type "INTEGER"; a BIGINT
# PK stays NULL and the INSERT fails. MySQL (production) has no such quirk, so
# this is purely a test-harness adjustment to the emitted DDL.
@compiles(BigInteger, "sqlite")
def _bigint_as_sqlite_integer(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(OriginCountry.__table__.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            OriginCountry(
                id=1, name="Belyi Klin", summary="Northern republic.",
                skitaltsy_attitude="Revered as heroes.", archive_slug="belyi-klin",
                is_active=True, sort_order=30,
            ),
            OriginCountry(
                id=2, name="Aldergard", summary="Old kingdom.",
                is_active=True, sort_order=10,
            ),
            # Soft-deleted: hidden from the public list, visible to admins.
            OriginCountry(
                id=3, name="Forgotten Duchy", summary="Hidden.",
                is_active=False, sort_order=20,
            ),
        ])
        await s.commit()
        yield s

    await engine.dispose()


# ===========================================================================
# 1. crud — listing and soft delete
# ===========================================================================

class TestOriginCrud:

    @pytest.mark.asyncio
    async def test_public_list_excludes_soft_deleted(self, session):
        rows = await crud.get_origin_countries(session, include_inactive=False)
        assert [r.id for r in rows] == [2, 1]  # ordered by sort_order

    @pytest.mark.asyncio
    async def test_admin_list_includes_soft_deleted(self, session):
        rows = await crud.get_origin_countries(session, include_inactive=True)
        assert {r.id for r in rows} == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_soft_delete_hides_but_does_not_remove_the_row(self, session):
        before = (await session.execute(
            select(sa_func.count()).select_from(OriginCountry)
        )).scalar_one()

        origin = await crud.deactivate_origin_country(session, 1)
        assert origin.is_active is False

        after = (await session.execute(
            select(sa_func.count()).select_from(OriginCountry)
        )).scalar_one()
        assert after == before, "soft delete must never remove the physical row"

        still_there = await crud.get_origin_country_by_id(session, 1)
        assert still_there is not None
        assert still_there.is_active is False

        public = await crud.get_origin_countries(session, include_inactive=False)
        assert 1 not in {r.id for r in public}

    @pytest.mark.asyncio
    async def test_soft_deleted_origin_can_be_restored_via_update(self, session):
        """N5: there is no restore endpoint — restore is PUT is_active=true."""
        restored = await crud.update_origin_country(
            session, 3, schemas.OriginCountryUpdate(is_active=True)
        )
        assert restored.is_active is True
        public = await crud.get_origin_countries(session, include_inactive=False)
        assert 3 in {r.id for r in public}

    @pytest.mark.asyncio
    async def test_delete_missing_origin_raises_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.deactivate_origin_country(session, 999999)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_missing_origin_raises_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.update_origin_country(
                session, 999999, schemas.OriginCountryUpdate(name="X")
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_origin_persists(self, session):
        created = await crud.create_origin_country(
            session,
            schemas.OriginCountryCreate(name="Elven Gardens", sort_order=40),
        )
        assert created.id is not None
        assert created.is_active is True
        rows = await crud.get_origin_countries(session, include_inactive=False)
        assert "Elven Gardens" in {r.name for r in rows}

    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises_409(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.create_origin_country(
                session, schemas.OriginCountryCreate(name="Aldergard")
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_partial_update_leaves_other_fields_intact(self, session):
        updated = await crud.update_origin_country(
            session, 2, schemas.OriginCountryUpdate(summary="Rewritten.")
        )
        assert updated.summary == "Rewritten."
        assert updated.name == "Aldergard"
        assert updated.sort_order == 10


# ===========================================================================
# 2. Schema validation
# ===========================================================================

class TestOriginSchemas:

    def test_blank_name_is_rejected(self):
        with pytest.raises(Exception):
            schemas.OriginCountryCreate(name="   ")

    def test_bad_archive_slug_is_rejected(self):
        with pytest.raises(Exception):
            schemas.OriginCountryCreate(name="X", archive_slug="Not A Slug!")

    def test_public_schema_never_exposes_is_active_or_description(self):
        """Rule 4: the public card carries its own summary, not Countries.description."""
        fields = set(schemas.OriginCountryRead.__fields__)
        assert "description" not in fields
        assert "is_active" not in fields
        assert "summary" in fields

    def test_admin_schema_adds_is_active(self):
        assert "is_active" in schemas.OriginCountryAdminRead.__fields__


# ===========================================================================
# 3. Routes — public
# ===========================================================================

def _origin_obj(**kwargs):
    """A MagicMock shaped like an OriginCountry row (orm_mode reads attributes)."""
    defaults = dict(
        id=7, name="Belyi Klin", emblem_url=None, map_image_url=None,
        summary="Northern republic.", skitaltsy_attitude="Revered.",
        archive_slug="belyi-klin", sort_order=30, is_active=True,
    )
    defaults.update(kwargs)
    obj = MagicMock()
    for key, value in defaults.items():
        setattr(obj, key, value)
    return obj


ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}

ORIGINS_ADMIN_USER = {
    "id": 1, "username": "admin", "role": "admin",
    "permissions": [
        "origins:read", "origins:create", "origins:update", "origins:delete",
    ],
}
# A moderator who administers locations but was never granted the origins module.
OTHER_MODULE_USER = {
    "id": 2, "username": "moderator", "role": "moderator",
    "permissions": ["locations:create", "locations:update", "locations:delete"],
}
PLAIN_USER = {"id": 3, "username": "player", "role": "user", "permissions": []}

CREATE_BODY = {
    "name": "Elven Gardens",
    "summary": "Woodland realm.",
    "archive_slug": "elfiyskie-sady",
    "sort_order": 40,
}


def _auth(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


class TestPublicOriginsRoute:

    @patch("crud.get_origin_countries", new_callable=AsyncMock)
    def test_returns_200_without_auth(self, mock_crud, client):
        mock_crud.return_value = [_origin_obj()]
        resp = client.get("/locations/origins")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["name"] == "Belyi Klin"

    @patch("crud.get_origin_countries", new_callable=AsyncMock)
    def test_public_route_asks_crud_to_hide_inactive(self, mock_crud, client):
        mock_crud.return_value = []
        client.get("/locations/origins")
        assert mock_crud.await_args.kwargs.get("include_inactive") is False

    @patch("crud.get_origin_countries", new_callable=AsyncMock)
    def test_public_payload_omits_is_active_and_description(self, mock_crud, client):
        mock_crud.return_value = [_origin_obj()]
        body = client.get("/locations/origins").json()[0]
        assert "is_active" not in body
        assert "description" not in body
        assert set(body.keys()) == {
            "id", "name", "emblem_url", "map_image_url", "summary",
            "skitaltsy_attitude", "archive_slug", "sort_order",
        }


# ===========================================================================
# 4. Routes — admin RBAC
# ===========================================================================

class TestAdminOriginsAuth:
    """Every admin origin route is gated by require_permission, not by role."""

    def test_list_without_token_returns_401(self, client):
        assert client.get("/locations/admin/origins").status_code == 401

    def test_create_without_token_returns_401(self, client):
        assert client.post(
            "/locations/admin/origins", json=CREATE_BODY
        ).status_code == 401

    def test_update_without_token_returns_401(self, client):
        assert client.put(
            "/locations/admin/origins/1", json={"name": "X"}
        ).status_code == 401

    def test_delete_without_token_returns_401(self, client):
        assert client.delete("/locations/admin/origins/1").status_code == 401

    @patch("auth_http.requests.get")
    def test_plain_user_gets_403_on_every_route(self, mock_auth, client):
        mock_auth.return_value = _auth(PLAIN_USER)
        assert client.get(
            "/locations/admin/origins", headers=ADMIN_HEADERS).status_code == 403
        assert client.post(
            "/locations/admin/origins", json=CREATE_BODY,
            headers=ADMIN_HEADERS).status_code == 403
        assert client.put(
            "/locations/admin/origins/1", json={"name": "X"},
            headers=ADMIN_HEADERS).status_code == 403
        assert client.delete(
            "/locations/admin/origins/1", headers=ADMIN_HEADERS).status_code == 403

    @patch("auth_http.requests.get")
    def test_locations_permissions_do_not_grant_origins_access(self, mock_auth, client):
        """Cross-module isolation — a locations moderator is not an origins editor."""
        mock_auth.return_value = _auth(OTHER_MODULE_USER)
        resp = client.post(
            "/locations/admin/origins", json=CREATE_BODY, headers=ADMIN_HEADERS
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Недостаточно прав"

    @patch("auth_http.requests.get")
    def test_read_permission_alone_does_not_allow_writes(self, mock_auth, client):
        mock_auth.return_value = _auth(
            {**ORIGINS_ADMIN_USER, "permissions": ["origins:read"]}
        )
        assert client.post(
            "/locations/admin/origins", json=CREATE_BODY,
            headers=ADMIN_HEADERS).status_code == 403
        assert client.delete(
            "/locations/admin/origins/1", headers=ADMIN_HEADERS).status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        mock_auth.return_value = _auth(None, status_code=401)
        resp = client.get("/locations/admin/origins", headers=ADMIN_HEADERS)
        assert resp.status_code == 401


class TestAdminOriginsCrudRoutes:

    @patch("crud.get_origin_countries", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_list_includes_inactive_by_default(self, mock_auth, mock_crud, client):
        """N5: soft-deleted rows must be reachable, or they could never be restored."""
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.return_value = [_origin_obj(id=3, name="Hidden", is_active=False)]

        resp = client.get("/locations/admin/origins", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert mock_crud.await_args.kwargs.get("include_inactive") is True
        assert resp.json()[0]["is_active"] is False

    @patch("crud.get_origin_countries", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_list_can_opt_out_of_inactive(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.return_value = []
        client.get(
            "/locations/admin/origins?include_inactive=false", headers=ADMIN_HEADERS
        )
        assert mock_crud.await_args.kwargs.get("include_inactive") is False

    @patch("crud.create_origin_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_returns_201(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.return_value = _origin_obj(id=9, name="Elven Gardens")

        resp = client.post(
            "/locations/admin/origins", json=CREATE_BODY, headers=ADMIN_HEADERS
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Elven Gardens"
        assert resp.json()["is_active"] is True

    @patch("auth_http.requests.get")
    def test_create_with_blank_name_returns_422(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.post(
            "/locations/admin/origins", json={"name": "  "}, headers=ADMIN_HEADERS
        )
        assert resp.status_code == 422

    @patch("auth_http.requests.get")
    def test_create_with_bad_archive_slug_returns_422(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.post(
            "/locations/admin/origins",
            json={"name": "X", "archive_slug": "Bad Slug!"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422

    @patch("crud.update_origin_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_returns_200(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.return_value = _origin_obj(id=7, summary="Rewritten.")

        resp = client.put(
            "/locations/admin/origins/7",
            json={"summary": "Rewritten."},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["summary"] == "Rewritten."

    @patch("crud.update_origin_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_missing_origin_returns_404(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.side_effect = HTTPException(
            status_code=404, detail="Происхождение не найдено."
        )
        resp = client.put(
            "/locations/admin/origins/999999",
            json={"name": "X"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404

    @patch("crud.deactivate_origin_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_is_soft(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.return_value = _origin_obj(id=7, is_active=False)

        resp = client.delete("/locations/admin/origins/7", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == {"id": 7, "is_active": False}

    @patch("crud.deactivate_origin_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_missing_origin_returns_404(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.side_effect = HTTPException(
            status_code=404, detail="Происхождение не найдено."
        )
        resp = client.delete("/locations/admin/origins/999999", headers=ADMIN_HEADERS)
        assert resp.status_code == 404


# ===========================================================================
# 5. Security — injection strings must not reach SQL
# ===========================================================================

class TestOriginInjection:

    @pytest.mark.asyncio
    async def test_injection_in_name_is_stored_as_a_literal(self, session):
        """The ORM parameterises everything — a payload is just a name."""
        payload = "'; DROP TABLE origin_countries; --"
        created = await crud.create_origin_country(
            session, schemas.OriginCountryCreate(name=payload)
        )
        assert created.name == payload
        # The table survived and still holds every row.
        total = (await session.execute(
            select(sa_func.count()).select_from(OriginCountry)
        )).scalar_one()
        assert total == 4
