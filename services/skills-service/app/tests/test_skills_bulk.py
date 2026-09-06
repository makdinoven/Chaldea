"""
Tests for GET /skills/bulk (FEAT-154, task #9).

Contract (§3.1):
- ``ids`` is a comma-separated list of ints, deduplicated, capped at 100
- unknown ids are silently omitted
- malformed input and an oversized list are 400
- the endpoint is public — no token required

N1: the payload carries ``class_limitations`` (a comma-separated string), NOT
``class_id`` — the ``skills`` table has no class FK. §3.1 named a field that
does not exist, and these tests pin the real shape.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


# ---------------------------------------------------------------------------
# Async SQLite setup (mirrors test_admin_skills_search.py)
# ---------------------------------------------------------------------------

_async_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)

_AsyncTestSessionLocal = async_sessionmaker(
    _async_test_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

import database  # noqa: E402

_original_get_db = database.get_db


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session


import models  # noqa: E402
import schemas  # noqa: E402
from main import app  # noqa: E402

app.router.on_startup.clear()


@pytest_asyncio.fixture()
async def setup_db():
    database.engine = _async_test_engine
    database.async_session = _AsyncTestSessionLocal
    database.get_db = _override_get_db
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def client(setup_db):
    """Anonymous client — /skills/bulk is public, no auth override is set."""
    app.dependency_overrides[_original_get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _seed_skills():
    async with _AsyncTestSessionLocal() as session:
        session.add_all([
            models.Skill(
                id=1, name="Рассечение", skill_type="Attack",
                description="Широкий замах.", skill_image="https://s3/cleave.webp",
                class_limitations="warrior,paladin",
            ),
            models.Skill(
                id=2, name="Ледяная стрела", skill_type="Attack",
                description=None, skill_image=None, class_limitations=None,
            ),
            models.Skill(
                id=3, name="Исцеление", skill_type="Support",
                description="Лечит раны.", skill_image="https://s3/heal.webp",
                class_limitations="priest",
            ),
        ])
        await session.commit()


# ===========================================================================
# 1. Happy path
# ===========================================================================

@pytest.mark.asyncio
async def test_returns_requested_skills(client):
    await _seed_skills()
    resp = await client.get("/skills/bulk", params={"ids": "1,3"})
    assert resp.status_code == 200
    assert [row["id"] for row in resp.json()] == [1, 3]


@pytest.mark.asyncio
async def test_no_auth_required(client):
    await _seed_skills()
    resp = await client.get("/skills/bulk", params={"ids": "1"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_payload_carries_class_limitations_not_class_id(client):
    """N1 — the skills table has no class FK; scoping is a string."""
    await _seed_skills()
    row = (await client.get("/skills/bulk", params={"ids": "1"})).json()[0]
    assert set(row.keys()) == {
        "id", "name", "description", "icon_url", "class_limitations",
    }
    assert "class_id" not in row
    assert row["class_limitations"] == "warrior,paladin"
    assert row["icon_url"] == "https://s3/cleave.webp"


@pytest.mark.asyncio
async def test_schema_has_no_class_id_field():
    assert "class_id" not in schemas.SkillBulkResponse.__fields__
    assert "class_limitations" in schemas.SkillBulkResponse.__fields__


@pytest.mark.asyncio
async def test_nullable_fields_come_back_as_null(client):
    await _seed_skills()
    row = (await client.get("/skills/bulk", params={"ids": "2"})).json()[0]
    assert row["description"] is None
    assert row["icon_url"] is None
    assert row["class_limitations"] is None


@pytest.mark.asyncio
async def test_results_are_ordered_by_id(client):
    await _seed_skills()
    body = (await client.get("/skills/bulk", params={"ids": "3,1,2"})).json()
    assert [row["id"] for row in body] == [1, 2, 3]


@pytest.mark.asyncio
async def test_duplicate_ids_are_deduplicated(client):
    await _seed_skills()
    body = (await client.get("/skills/bulk", params={"ids": "1,1,1"})).json()
    assert len(body) == 1


@pytest.mark.asyncio
async def test_whitespace_around_ids_is_tolerated(client):
    await _seed_skills()
    body = (await client.get("/skills/bulk", params={"ids": " 1 , 2 "})).json()
    assert [row["id"] for row in body] == [1, 2]


@pytest.mark.asyncio
async def test_exactly_100_ids_is_allowed(client):
    await _seed_skills()
    ids = ",".join(str(i) for i in range(1, 101))
    resp = await client.get("/skills/bulk", params={"ids": ids})
    assert resp.status_code == 200


# ===========================================================================
# 2. Unknown ids are silently omitted
# ===========================================================================

@pytest.mark.asyncio
async def test_unknown_ids_are_omitted_not_errors(client):
    await _seed_skills()
    resp = await client.get("/skills/bulk", params={"ids": "1,99999"})
    assert resp.status_code == 200
    assert [row["id"] for row in resp.json()] == [1]


@pytest.mark.asyncio
async def test_all_unknown_ids_return_an_empty_list(client):
    await _seed_skills()
    resp = await client.get("/skills/bulk", params={"ids": "70000,80000"})
    assert resp.status_code == 200
    assert resp.json() == []


# ===========================================================================
# 3. Malformed input -> 400
# ===========================================================================

@pytest.mark.asyncio
async def test_missing_ids_param_returns_422(client):
    resp = await client.get("/skills/bulk")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_empty_ids_returns_400(client):
    resp = await client.get("/skills/bulk", params={"ids": ""})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Параметр ids не должен быть пустым"


@pytest.mark.asyncio
async def test_only_commas_returns_400(client):
    resp = await client.get("/skills/bulk", params={"ids": ",,,"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_numeric_id_returns_400(client):
    resp = await client.get("/skills/bulk", params={"ids": "1,abc"})
    assert resp.status_code == 400
    assert "целые числа" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_float_id_returns_400(client):
    resp = await client.get("/skills/bulk", params={"ids": "1.5"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zero_and_negative_ids_return_400(client):
    assert (await client.get("/skills/bulk", params={"ids": "0"})).status_code == 400
    assert (await client.get("/skills/bulk", params={"ids": "1,-2"})).status_code == 400


@pytest.mark.asyncio
async def test_more_than_100_ids_returns_400(client):
    ids = ",".join(str(i) for i in range(1, 102))
    resp = await client.get("/skills/bulk", params={"ids": ids})
    assert resp.status_code == 400
    assert "максимум 100" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_the_cap_counts_raw_tokens_not_unique_ids(client):
    """101 raw entries that dedupe to 2 still hit the cap — it guards parsing."""
    ids = ",".join(["1", "2"] * 50 + ["1"])
    resp = await client.get("/skills/bulk", params={"ids": ids})
    assert resp.status_code == 400
    assert "максимум 100" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_exactly_100_unique_ids_is_allowed(client):
    ids = ",".join(str(i) for i in range(1, 101))
    resp = await client.get("/skills/bulk", params={"ids": ids})
    assert resp.status_code == 200


# ===========================================================================
# 4. Security — SQL injection
# ===========================================================================

@pytest.mark.asyncio
async def test_injection_string_is_rejected_with_400(client):
    await _seed_skills()
    resp = await client.get(
        "/skills/bulk", params={"ids": "1; DROP TABLE skills; --"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_injection_does_not_execute(client):
    """The skills table must survive every injection attempt."""
    await _seed_skills()
    payloads = [
        "1; DROP TABLE skills; --",
        "1) OR 1=1 --",
        "' OR '1'='1",
        "1 UNION SELECT id, name FROM skills",
        "1,(SELECT 1)",
    ]
    for payload in payloads:
        resp = await client.get("/skills/bulk", params={"ids": payload})
        assert resp.status_code == 400, payload

    ok = await client.get("/skills/bulk", params={"ids": "1,2,3"})
    assert ok.status_code == 200
    assert len(ok.json()) == 3


@pytest.mark.asyncio
async def test_or_1_equals_1_does_not_widen_the_result(client):
    """A tautology must never turn a 1-id request into "everything"."""
    await _seed_skills()
    resp = await client.get("/skills/bulk", params={"ids": "1 OR 1=1"})
    assert resp.status_code == 400


# ===========================================================================
# 5. Routing — "bulk" must not be parsed as a skill id
# ===========================================================================

@pytest.mark.asyncio
async def test_bulk_route_wins_over_the_skill_id_route(client):
    """Without ids the bulk route answers 422, not the /{skill_id} 404/422."""
    await _seed_skills()
    resp = await client.get("/skills/bulk")
    assert resp.status_code == 422
    # And the parametric route still works for a real id.
    assert (await client.get("/skills/1")).status_code == 200
