"""
FEAT-173 — `game_rules.section`: three guide sections (site / roleplay / technobook).

Three layers, deliberately separated:

1. **Parity.** The section vocabulary is spelled out in three independent places —
   the ORM ENUM, the migration's ``SECTIONS`` constant and the Pydantic ``Literal``.
   Modelled on ``test_gathering_ingredient.py::TestMigration043``: adding a fourth
   section must fail loudly here until every layer is updated. Plus the revision
   chain and the migration SQL itself (one ALTER that backfills, an unconditional
   DROP on the way back).
2. **CRUD against real in-memory aiosqlite** (house style of ``test_post_drafts.py``).
   Two facts cannot be proved with a mocked session: that ``create_rule`` actually
   *persists* the requested section — it builds the model field by field and drops
   anything unlisted, exactly how ``image_url`` is already lost (§3.0 note 3 of the
   feature card) — and that a row written without a section reads back as ``site``
   from the column default. Both are storage facts, so they are tested against
   storage.
3. **Routes through ``TestClient`` with crud mocked** — that a request with no
   ``section`` parameter still asks for *everything* (the rolling-deploy contract),
   that the filter is passed through, and that a bad value is rejected at the edge
   before any DB work.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
from models import GameRule  # noqa: E402

_VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")

ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN_USER_RESPONSE = {
    "id": 1, "username": "admin", "role": "admin",
    "permissions": ["rules:create", "rules:read", "rules:update", "rules:delete"],
}
REGULAR_USER_RESPONSE = {"id": 2, "username": "user", "role": "user", "permissions": []}


def _load_migration(filename):
    path = os.path.join(_VERSIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# SQLite DDL hook — BigInteger has no sqlite spelling that auto-assigns a PK.
# ---------------------------------------------------------------------------

@compiles(BigInteger, "sqlite")
def _bigint_as_sqlite_integer(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


# ===========================================================================
# 1. Parity: migration 044 == ORM == Pydantic Literal
# ===========================================================================

class TestMigration044:

    @pytest.fixture(scope="class")
    def m044(self):
        return _load_migration("044_game_rule_section.py")

    def test_orm_enum_matches_migration(self, m044):
        orm_values = tuple(models.GameRule.__table__.c.section.type.enums)
        assert orm_values == m044.SECTIONS
        assert m044.SECTIONS == ("site", "roleplay", "technobook")

    def test_pydantic_literal_matches_orm(self):
        literal_values = set(schemas.RuleSection.__args__)
        assert literal_values == set(models.GameRule.__table__.c.section.type.enums)

    def test_default_section_is_site_and_is_a_member(self, m044):
        assert m044.DEFAULT_SECTION == "site"
        assert m044.DEFAULT_SECTION in m044.SECTIONS

    def test_orm_column_is_not_null_with_server_default(self):
        column = models.GameRule.__table__.c.section
        assert column.nullable is False
        assert "site" in str(column.server_default.arg)

    def test_revision_chain(self, m044):
        assert m044.revision == "044_game_rule_section"
        assert len(m044.revision) <= 32  # alembic_version_locations.version_num
        m043 = _load_migration("043_gathering_ingredient_category.py")
        assert m044.down_revision == m043.revision == "043_gathering_ingredient"

    def test_044_is_the_sole_child_of_043(self, m044):
        children = []
        for name in os.listdir(_VERSIONS_DIR):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(_VERSIONS_DIR, name), encoding="utf-8") as fh:
                src = fh.read()
            if f"down_revision = '{m044.down_revision}'" in src:
                children.append(name)
        assert children == ["044_game_rule_section.py"]

    def test_upgrade_adds_the_column_and_backfills_in_one_statement(self, m044):
        with patch.object(m044.op, "execute", create=True) as mock_exec:
            m044.upgrade()
        assert mock_exec.call_count == 1, "the ALTER itself backfills — no second pass"
        sql = mock_exec.call_args[0][0]
        assert "ALTER TABLE game_rules ADD COLUMN section" in sql
        assert "ENUM('site','roleplay','technobook')" in sql
        assert "NOT NULL DEFAULT 'site'" in sql
        # The ALTER fills existing rows itself; a separate UPDATE pass is a bug.
        assert "UPDATE" not in sql.upper()

    def test_downgrade_drops_the_column_unconditionally(self, m044):
        with patch.object(m044.op, "execute", create=True) as mock_exec, \
             patch.object(m044.op, "get_bind", create=True) as mock_bind:
            m044.downgrade()
        assert mock_exec.call_count == 1
        sql = mock_exec.call_args[0][0]
        assert "ALTER TABLE game_rules DROP COLUMN section" in sql
        # No fail-fast guard: rollback must not depend on how rules are filed.
        mock_bind.assert_not_called()


# ===========================================================================
# 2. Pydantic schemas
# ===========================================================================

class TestRuleSectionSchemas:

    def test_create_without_section_defaults_to_site(self):
        payload = schemas.GameRuleCreate(title="Правило")
        assert payload.section == "site"

    @pytest.mark.parametrize("section", ["site", "roleplay", "technobook"])
    def test_create_accepts_every_section(self, section):
        assert schemas.GameRuleCreate(title="Правило", section=section).section == section

    @pytest.mark.parametrize(
        "section", ["nonsense", "Site", "TECHNOBOOK", "", "site'; DROP TABLE game_rules --", "rules"],
    )
    def test_create_rejects_unknown_section(self, section):
        with pytest.raises(ValueError):
            schemas.GameRuleCreate(title="Правило", section=section)

    def test_update_without_section_leaves_it_unset(self):
        payload = schemas.GameRuleUpdate(title="Новое название")
        assert "section" not in payload.dict(exclude_unset=True)

    def test_update_with_section_is_set(self):
        payload = schemas.GameRuleUpdate(section="technobook")
        assert payload.dict(exclude_unset=True) == {"section": "technobook"}

    @pytest.mark.parametrize("section", ["nonsense", "Roleplay", ""])
    def test_update_rejects_unknown_section(self, section):
        with pytest.raises(ValueError):
            schemas.GameRuleUpdate(section=section)


# ===========================================================================
# 3. CRUD against real in-memory aiosqlite
# ===========================================================================

@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """In-memory async SQLite holding only ``game_rules``.

    The table stands alone — no FK points at it and it points at nothing — so
    nothing else needs creating.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(GameRule.__table__.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s

    await engine.dispose()


async def _seed(session, rows):
    """rows: iterable of (id, title, section, sort_order)."""
    now = datetime(2026, 1, 1, 12, 0, 0)
    for rule_id, title, section, sort_order in rows:
        session.add(GameRule(
            id=rule_id, title=title, section=section, content="<p>x</p>",
            sort_order=sort_order, created_at=now, updated_at=now,
        ))
    await session.commit()


class TestCreateRuleHonoursSection:
    """Regression guard: ``create_rule`` builds the model field by field, so a
    field it forgets to list is dropped in silence — that is how ``image_url``
    is already lost. The requested section must reach the database."""

    @pytest.mark.asyncio
    async def test_requested_section_is_persisted(self, session):
        created = await crud.create_rule(
            session,
            schemas.GameRuleCreate(title="Технобук", section="technobook", content="<p>t</p>"),
        )
        assert created.section == "technobook"

        # Read it back from storage, not from the object we just built.
        stored = (await session.execute(
            select(GameRule).where(GameRule.id == created.id)
        )).scalars().one()
        assert stored.section == "technobook"

    @pytest.mark.asyncio
    async def test_create_without_section_lands_in_site(self, session):
        created = await crud.create_rule(session, schemas.GameRuleCreate(title="Правило сайта"))
        stored = (await session.execute(
            select(GameRule).where(GameRule.id == created.id)
        )).scalars().one()
        assert stored.section == "site"

    @pytest.mark.asyncio
    async def test_every_section_round_trips(self, session):
        for section in schemas.RuleSection.__args__:
            created = await crud.create_rule(
                session, schemas.GameRuleCreate(title=f"Правило {section}", section=section),
            )
            assert created.section == section


class TestExistingRowsReadAsSite:
    """Backward compatibility: the migration's ``NOT NULL DEFAULT 'site'`` is what
    puts every pre-FEAT-173 rule into «Правила сайта» — no UPDATE pass involved."""

    @pytest.mark.asyncio
    async def test_row_written_without_a_section_reads_back_as_site(self, session):
        # A writer that knows nothing about the column — i.e. every row that
        # existed before the migration ran.
        await session.execute(text(
            "INSERT INTO game_rules (id, title, content, sort_order, created_at, updated_at) "
            "VALUES (1, 'Старое правило', '<p>x</p>', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        await session.commit()

        rule = (await session.execute(
            select(GameRule).where(GameRule.id == 1)
        )).scalars().one()
        assert rule.section == "site"
        # And it is still readable through the response schema.
        assert schemas.GameRuleRead.from_orm(rule).section == "site"


class TestGetAllRulesFilter:

    ROWS = [
        (3, "Третье", "roleplay", 0),
        (1, "Первое", "site", 0),
        (2, "Второе", "site", 1),
        (4, "Четвёртое", "roleplay", 5),
    ]

    @pytest.mark.asyncio
    async def test_no_section_returns_everything_in_todays_order(self, session):
        await _seed(session, self.ROWS)
        rules = await crud.get_all_rules(session)
        # sort_order ASC, id ASC — byte-identical to the pre-FEAT-173 behaviour.
        assert [r.id for r in rules] == [1, 3, 2, 4]

    @pytest.mark.asyncio
    async def test_explicit_none_is_the_same_as_omitting_it(self, session):
        await _seed(session, self.ROWS)
        assert [r.id for r in await crud.get_all_rules(session, None)] == [1, 3, 2, 4]

    @pytest.mark.asyncio
    async def test_filter_returns_only_that_section_in_order(self, session):
        await _seed(session, self.ROWS)
        rules = await crud.get_all_rules(session, "roleplay")
        assert [r.id for r in rules] == [3, 4]
        assert {r.section for r in rules} == {"roleplay"}

    @pytest.mark.asyncio
    async def test_empty_section_is_an_empty_list_not_an_error(self, session):
        await _seed(session, self.ROWS)
        assert await crud.get_all_rules(session, "technobook") == []


class TestUpdateRuleMovesSection:

    @pytest.mark.asyncio
    async def test_section_is_changed_by_update(self, session):
        await _seed(session, [(1, "Правило", "site", 0)])
        updated = await crud.update_rule(
            session, 1, schemas.GameRuleUpdate(section="technobook"),
        )
        assert updated.section == "technobook"
        stored = (await session.execute(
            select(GameRule).where(GameRule.id == 1)
        )).scalars().one()
        assert stored.section == "technobook"
        assert stored.title == "Правило"  # nothing else moved

    @pytest.mark.asyncio
    async def test_payload_without_section_leaves_it_untouched(self, session):
        await _seed(session, [(1, "Правило", "technobook", 0)])
        updated = await crud.update_rule(
            session, 1, schemas.GameRuleUpdate(title="Переименовано"),
        )
        assert updated.title == "Переименовано"
        assert updated.section == "technobook"

    @pytest.mark.asyncio
    async def test_rule_becomes_visible_in_its_new_section(self, session):
        """The redistribution path end to end: this is the feature's stated goal."""
        await _seed(session, [(1, "Правило", "site", 0)])
        await crud.update_rule(session, 1, schemas.GameRuleUpdate(section="roleplay"))
        assert await crud.get_all_rules(session, "site") == []
        assert [r.id for r in await crud.get_all_rules(session, "roleplay")] == [1]


# ===========================================================================
# 4. GET /rules/list — the query parameter
# ===========================================================================

def _make_rule(rule_id=1, title="Правило", section="site", sort_order=0):
    rule = MagicMock()
    rule.id = rule_id
    rule.title = title
    rule.section = section
    rule.content = "<p>x</p>"
    rule.sort_order = sort_order
    rule.image_url = None
    rule.created_at = datetime(2026, 1, 1, 12, 0, 0)
    rule.updated_at = datetime(2026, 1, 1, 12, 0, 0)
    return rule


class TestRulesListSectionParam:

    @patch("crud.get_all_rules", new_callable=AsyncMock)
    def test_no_parameter_asks_for_everything(self, mock_crud, client):
        """Rolling-deploy contract: an old bundle sends no parameter and must
        keep seeing the full list — never an implicit ``section='site'``."""
        mock_crud.return_value = [
            _make_rule(1, "Первое", "site"),
            _make_rule(2, "Второе", "roleplay"),
            _make_rule(3, "Третье", "technobook"),
        ]
        response = client.get("/rules/list")
        assert response.status_code == 200
        assert [r["id"] for r in response.json()] == [1, 2, 3]
        assert mock_crud.await_args[0][1] is None

    @pytest.mark.parametrize("section", ["site", "roleplay", "technobook"])
    @patch("crud.get_all_rules", new_callable=AsyncMock)
    def test_section_is_passed_through(self, mock_crud, client, section):
        mock_crud.return_value = [_make_rule(7, "Правило", section)]
        response = client.get(f"/rules/list?section={section}")
        assert response.status_code == 200
        assert mock_crud.await_args[0][1] == section
        assert response.json()[0]["section"] == section

    @patch("crud.get_all_rules", new_callable=AsyncMock)
    def test_filtered_response_keeps_the_order_crud_returned(self, mock_crud, client):
        mock_crud.return_value = [
            _make_rule(3, "Третье", "roleplay", sort_order=0),
            _make_rule(4, "Четвёртое", "roleplay", sort_order=5),
        ]
        data = client.get("/rules/list?section=roleplay").json()
        assert [r["id"] for r in data] == [3, 4]

    @patch("crud.get_all_rules", new_callable=AsyncMock, return_value=[])
    def test_empty_section_is_200_with_an_empty_list(self, mock_crud, client):
        response = client.get("/rules/list?section=technobook")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.parametrize("section", [
        "nonsense", "Roleplay", "SITE", "", "site,roleplay",
        "site' OR 1=1 --", "<script>alert(1)</script>",
    ])
    @patch("crud.get_all_rules", new_callable=AsyncMock)
    def test_invalid_section_is_422_before_any_db_work(self, mock_crud, client, section):
        response = client.get("/rules/list", params={"section": section})
        assert response.status_code == 422
        mock_crud.assert_not_awaited()

    @patch("crud.get_all_rules", new_callable=AsyncMock, return_value=[])
    def test_filtered_list_is_still_public(self, mock_crud, client):
        """The read path gained a parameter, not an auth requirement."""
        assert client.get("/rules/list?section=roleplay").status_code == 200


# ===========================================================================
# 5. Writes still need their rules:* permissions
# ===========================================================================

class TestSectionWritesStillGated:

    def test_create_with_section_without_token_is_401(self, client):
        response = client.post("/rules/create", json={"title": "Правило", "section": "technobook"})
        assert response.status_code == 401

    @patch("crud.create_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_with_section_without_permission_is_403(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/rules/create",
            json={"title": "Правило", "section": "technobook"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403
        mock_crud.assert_not_awaited()

    @patch("crud.create_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_create_forwards_the_section(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_rule(10, "Технобук", "technobook")
        response = client.post(
            "/rules/create",
            json={"title": "Технобук", "section": "technobook"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert mock_crud.await_args[0][1].section == "technobook"
        assert response.json()["section"] == "technobook"

    @patch("auth_http.requests.get")
    def test_admin_create_with_a_bad_section_is_422(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.post(
            "/rules/create",
            json={"title": "Правило", "section": "nonsense"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    def test_update_section_without_token_is_401(self, client):
        response = client.put("/rules/1/update", json={"section": "roleplay"})
        assert response.status_code == 401

    @patch("crud.update_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_section_without_permission_is_403(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/rules/1/update", json={"section": "roleplay"}, headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403
        mock_crud.assert_not_awaited()

    @patch("crud.update_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_update_forwards_only_the_section(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_rule(1, "Правило", "roleplay")
        response = client.put(
            "/rules/1/update", json={"section": "roleplay"}, headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        body = mock_crud.await_args[0][2]
        assert body.dict(exclude_unset=True) == {"section": "roleplay"}
        assert response.json()["section"] == "roleplay"
