"""FEAT-202 QA (task 6): the country prison in locations-service.

Covers:
  * migration 057 (driven against a fake inspector: up / re-run no-op / down / partial state) and the ORM column;
  * `PUT /locations/countries/{id}/update` prison validation on a real (file SQLite) world: unknown / other
    country / empty district -> 400 with the Russian text and nothing saved, a nested sub-district is accepted,
    an explicit null clears, an omitted field keeps the prison, 403 without `locations:update`;
  * `GET /locations/countries/{id}/districts`: permission, 404, ordering (region name, parent-first, sort_order),
    nested districts, `location_count` of the subtree, the parent-cycle fallback; details payload carries the field;
  * `crud.prison_location_ids` on SQLite (nested + parent_id chain + ordering);
  * `check_not_locked_for_post` tri-state and `check_not_locked_for_move`, incl. the missing
    `characters.jail_district_id` fallback (WARNING) and that other errors propagate;
  * `move_and_post` calls update_location for a prison move but not in place; `quick_move` inside the subtree
    reaches update_location, outside -> 409; `/posts/` never allows a prison move;
  * `crud.SQL_PRISON_LOCATIONS` is byte-identical to character-service `law_facility.SQL_PRISON_LOCATIONS`
    (skipped when the other service is not mounted, like the activity_lock copy test).
"""

import ast
import importlib.util
import logging
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import crud
import main
import models
import schemas
from auth_http import UserRead, get_current_user_via_http
from database import get_db

pytestmark = pytest.mark.real_activity_lock

ADMIN = UserRead(id=1, username="admin", role="admin", permissions=["locations:update"])
PLAYER = UserRead(id=10, username="prisoner", role="user", permissions=[])
CID = 1
CELL, CELL2, YARD, CELLAR = 510, 511, 512, 513
OUTSIDE = 200
SOON = datetime.utcnow() + timedelta(hours=5)


# ===========================================================================
# file SQLite world (sync seed, async reads)
# ===========================================================================

_TABLES = ("Countries", "Regions", "Districts", "Locations")


def _seed(conn):
    for name in _TABLES:
        models.Base.metadata.tables[name].create(conn)
    conn.execute(text("INSERT INTO Countries (id, name, description) VALUES "
                      "(1, 'Мидденгерд', '-'), (2, 'Пустошь', '-'), (3, 'Безземелье', '-')"))
    conn.execute(text("INSERT INTO Regions (id, name, country_id, description) VALUES "
                      "(10, 'Ост', 1, '-'), (12, 'Холмы', 1, '-'), (20, 'Дюны', 2, '-')"))
    conn.execute(text(
        "INSERT INTO Districts (id, name, region_id, parent_district_id, entrance_location_id, description, "
        "sort_order) VALUES "
        "(500, 'Казематы', 12, NULL, 510, '-', 1), (501, 'Двор', 12, 500, NULL, '-', 0), "
        "(520, 'Пустырь', 12, NULL, NULL, '-', 0), (505, 'Арка', 10, NULL, NULL, '-', 0), "
        "(530, 'Чужбина', 20, NULL, NULL, '-', 0)"))
    loc = ("INSERT INTO Locations (id, name, type, recommended_level, quick_travel_marker, description, "
           "marker_type, sort_order, district_id, parent_id) VALUES "
           "(:id, :n, 'location', 1, 0, '-', 'safe', :s, :d, :p)")
    for lid, name, sort, district, parent in (
            (510, 'Камеры', 2, 500, None), (511, 'Карцер', 1, 500, None), (512, 'Двор', 0, 501, None),
            (513, 'Подвал', 0, None, 512), (506, 'Ворота', 0, 505, None), (531, 'Острог', 0, 530, None)):
        conn.execute(text(loc), {"id": lid, "n": name, "s": sort, "d": district, "p": parent})


@pytest.fixture
def world(tmp_path):
    path = tmp_path / "world.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        _seed(conn)
    eng.dispose()
    return str(path)


def _q(path, sql, **params):
    eng = create_engine(f"sqlite:///{path}")
    try:
        with eng.begin() as conn:
            return conn.execute(text(sql), params).fetchall()
    finally:
        eng.dispose()


def _exec(path, sql, **params):
    _q_exec = create_engine(f"sqlite:///{path}")
    try:
        with _q_exec.begin() as conn:
            conn.execute(text(sql), params)
    finally:
        _q_exec.dispose()


@pytest.fixture
def api(world):
    async def override():
        eng = create_async_engine(f"sqlite+aiosqlite:///{world}")
        factory = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session
        await eng.dispose()

    main.app.dependency_overrides[get_db] = override
    main.app.dependency_overrides[get_current_user_via_http] = lambda: ADMIN
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
async def session(world):
    eng = create_async_engine(f"sqlite+aiosqlite:///{world}")
    factory = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await eng.dispose()


def _prison(path, country_id=1):
    return _q(path, "SELECT prison_district_id FROM Countries WHERE id = :c", c=country_id)[0][0]


# ===========================================================================
# 1. migration 057 + ORM
# ===========================================================================

_VERSIONS = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _load_057():
    spec = importlib.util.spec_from_file_location("mig057_qa", os.path.join(_VERSIONS, "057_country_prison_district.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeSchema:
    """Countries' columns / indexes / FKs as MySQL would report them, mutated by the fake op."""

    def __init__(self, columns=("id", "name"), indexes=(), fks=()):
        self.columns = set(columns)
        self.indexes = set(indexes)
        self.fks = {}
        for name in fks:
            self.fks[name] = None
        self.calls = []

    # inspector API
    def get_columns(self, table):
        assert table == "Countries"
        return [{"name": c} for c in sorted(self.columns)]

    def get_indexes(self, table):
        return [{"name": i} for i in sorted(self.indexes)]

    def get_foreign_keys(self, table):
        return [{"name": f} for f in sorted(self.fks)]


class _FakeOp:
    def __init__(self, schema):
        self.schema = schema

    def get_bind(self):
        return self.schema

    def add_column(self, table, column):
        self.schema.calls.append(("add_column", table, column.name))
        self.schema.added = column
        self.schema.columns.add(column.name)

    def create_index(self, name, table, cols):
        self.schema.calls.append(("create_index", name, table, tuple(cols)))
        self.schema.indexes.add(name)

    def create_foreign_key(self, name, source, referent, local_cols, remote_cols, ondelete=None):
        self.schema.calls.append(("create_foreign_key", name, source, referent, tuple(local_cols),
                                  tuple(remote_cols), ondelete))
        self.schema.fks[name] = ondelete

    def drop_constraint(self, name, table, type_=None):
        self.schema.calls.append(("drop_constraint", name, table, type_))
        del self.schema.fks[name]

    def drop_index(self, name, table_name=None):
        self.schema.calls.append(("drop_index", name, table_name))
        self.schema.indexes.discard(name)

    def drop_column(self, table, column):
        self.schema.calls.append(("drop_column", table, column))
        self.schema.columns.discard(column)


def _run_057(schema, step):
    mod = _load_057()
    mod.op = _FakeOp(schema)
    mod.inspect = lambda bind: bind
    getattr(mod, step)()
    return mod


def test_057_chain():
    mod = _load_057()
    assert mod.revision == "057_country_prison_district" and len(mod.revision) <= 32
    assert mod.down_revision == "056_quest_fame"


def test_057_upgrade_rerun_downgrade():
    schema = _FakeSchema()
    _run_057(schema, "upgrade")
    assert [c[0] for c in schema.calls] == ["add_column", "create_index", "create_foreign_key"]
    col = schema.added
    assert col.name == "prison_district_id" and col.nullable is True
    assert type(col.type).__name__ == "BigInteger"
    assert schema.calls[1] == ("create_index", "ix_countries_prison_district_id", "Countries",
                               ("prison_district_id",))
    assert schema.calls[2] == ("create_foreign_key", "fk_countries_prison_district", "Countries", "Districts",
                               ("prison_district_id",), ("id",), "SET NULL")
    schema.calls.clear()
    _run_057(schema, "upgrade")
    assert schema.calls == []                                                   # idempotent re-run
    _run_057(schema, "downgrade")
    assert [c[0] for c in schema.calls] == ["drop_constraint", "drop_index", "drop_column"]   # FK before index
    assert schema.calls[0][3] == "foreignkey"
    assert "prison_district_id" not in schema.columns and not schema.indexes and not schema.fks
    schema.calls.clear()
    _run_057(schema, "downgrade")
    assert schema.calls == []


def test_057_partial_state_adds_only_what_is_missing():
    schema = _FakeSchema(columns=("id", "prison_district_id"), indexes=("ix_countries_prison_district_id",))
    _run_057(schema, "upgrade")
    assert [c[0] for c in schema.calls] == ["create_foreign_key"]


def test_orm_column_matches_districts_id():
    col = models.Country.__table__.c.prison_district_id
    assert col.nullable is True and col.index is True
    assert type(col.type) is type(models.District.__table__.c.id.type)              # BIGINT = BIGINT (FK types)
    fk = next(iter(col.foreign_keys))
    assert (fk.column.table.name, fk.column.name, fk.ondelete) == ("Districts", "id", "SET NULL")


def test_schemas_carry_the_field():
    assert schemas.CountryUpdate.__fields__["prison_district_id"].required is False
    assert schemas.CountryRead.__fields__["prison_district_id"].required is False
    assert "prison_district_id" not in schemas.CountryCreate.__fields__
    assert set(schemas.CountryDistrictRead.__fields__) == {
        "id", "name", "region_id", "region_name", "parent_district_id", "location_count", "entrance_location_id"}


# ===========================================================================
# 2. prison_location_ids on SQLite
# ===========================================================================

async def test_prison_location_ids_subtree(session):
    assert await crud.prison_location_ids(session, 500) == [CELL2, CELL, YARD, CELLAR]
    assert await crud.prison_location_ids(session, 501) == [YARD, CELLAR]
    assert await crud.prison_location_ids(session, 520) == []
    assert await crud.prison_location_ids(session, 99999) == []


async def test_prison_location_ids_cycle_terminates(session, world):
    _exec(world, "INSERT INTO Districts (id, name, region_id, parent_district_id, description, sort_order) "
                 "VALUES (540, 'Круг', 12, 541, '-', 0), (541, 'Петля', 12, 540, '-', 0)")
    _exec(world, "INSERT INTO Locations (id, name, type, recommended_level, quick_travel_marker, description, "
                 "marker_type, sort_order, district_id) VALUES (542, 'А', 'location', 1, 0, '-', 'safe', 0, 541)")
    assert await crud.prison_location_ids(session, 540) == [542]


# ===========================================================================
# 3. PUT /countries/{id}/update
# ===========================================================================

def _put(api, country_id, body):
    return api.put(f"/locations/countries/{country_id}/update", json=body)


@pytest.mark.parametrize("district,detail", [
    (99999, "Район тюрьмы не найден"),
    (530, "Район тюрьмы должен находиться в одном из краёв этой страны"),
    (520, "В районе тюрьмы нет ни одной локации"),
], ids=["unknown", "other-country", "empty"])
def test_invalid_prison_is_400_and_nothing_is_saved(api, world, district, detail):
    resp = _put(api, 1, {"name": "Переименовано", "prison_district_id": district})
    assert resp.status_code == 400 and resp.json()["detail"] == detail
    assert _q(world, "SELECT name, prison_district_id FROM Countries WHERE id = 1") == [("Мидденгерд", None)]


@pytest.mark.parametrize("district", [500, 501, 505], ids=["root", "nested-sub-district", "another-region"])
def test_valid_prison_is_saved(api, world, district):
    resp = _put(api, 1, {"prison_district_id": district})
    assert resp.status_code == 200, resp.text
    assert resp.json()["prison_district_id"] == district
    assert _prison(world) == district


def test_parent_id_location_makes_a_district_non_empty(api, world):
    """A district whose only location hangs off another district's location by parent_id is still empty;
    a district whose subtree reaches a location through parent_id is not."""
    _exec(world, "INSERT INTO Districts (id, name, region_id, parent_district_id, description, sort_order) "
                 "VALUES (521, 'Тайник', 12, NULL, '-', 0)")
    assert _put(api, 1, {"prison_district_id": 521}).status_code == 400
    _exec(world, "UPDATE Locations SET district_id = 521 WHERE id = 512")       # 513 hangs off 512
    assert _put(api, 1, {"prison_district_id": 521}).status_code == 200


def test_null_clears_and_omitted_keeps(api, world):
    assert _put(api, 1, {"prison_district_id": 500}).status_code == 200
    resp = _put(api, 1, {"name": "Мидденгерд II"})
    assert resp.status_code == 200 and resp.json()["prison_district_id"] == 500
    assert _prison(world) == 500
    resp = _put(api, 1, {"prison_district_id": None})
    assert resp.status_code == 200 and resp.json()["prison_district_id"] is None
    assert _prison(world) is None


def test_region_moved_away_invalidates_on_next_save(api, world):
    assert _put(api, 1, {"prison_district_id": 500}).status_code == 200
    _exec(world, "UPDATE Regions SET country_id = 2 WHERE id = 12")
    resp = _put(api, 1, {"prison_district_id": 500})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Район тюрьмы должен находиться в одном из краёв этой страны"


def test_unknown_country_is_404(api):
    assert _put(api, 99, {"prison_district_id": 500}).status_code == 404


def test_update_requires_locations_update(api, world):
    main.app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
    resp = _put(api, 1, {"prison_district_id": 500})
    assert resp.status_code == 403
    assert _prison(world) is None


@pytest.mark.parametrize("value", ["abc", "5x", [500], {"id": 500}])
def test_non_integer_district_is_422(api, value):
    assert _put(api, 1, {"prison_district_id": value}).status_code == 422


def test_details_and_list_carry_the_prison(api, world):
    _exec(world, "UPDATE Countries SET prison_district_id = 500 WHERE id = 1")
    assert api.get("/locations/countries/1/details").json()["prison_district_id"] == 500


# ===========================================================================
# 4. GET /countries/{id}/districts
# ===========================================================================

def test_districts_shape_and_order(api):
    resp = api.get("/locations/countries/1/districts")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Ост: 505; Холмы: roots by sort_order (520 sort 0, 500 sort 1), children right after their parent
    assert [d["id"] for d in data] == [505, 520, 500, 501]
    by_id = {d["id"]: d for d in data}
    assert by_id[500] == {"id": 500, "name": "Казематы", "region_id": 12, "region_name": "Холмы",
                          "parent_district_id": None, "location_count": 4, "entrance_location_id": 510}
    assert by_id[501]["parent_district_id"] == 500 and by_id[501]["location_count"] == 2
    assert by_id[520]["location_count"] == 0 and by_id[505]["location_count"] == 1
    assert 530 not in by_id                                                     # another country


def test_districts_of_a_country_without_regions(api):
    resp = api.get("/locations/countries/3/districts")
    assert resp.status_code == 200 and resp.json() == []


def test_districts_404(api):
    resp = api.get("/locations/countries/99/districts")
    assert resp.status_code == 404 and resp.json()["detail"] == "Страна не найдена"


def test_districts_403_without_permission(api):
    main.app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
    resp = api.get("/locations/countries/1/districts")
    assert resp.status_code == 403


def test_districts_401_without_token(world):
    main.app.dependency_overrides.clear()
    try:
        assert TestClient(main.app).get("/locations/countries/1/districts").status_code == 401
    finally:
        main.app.dependency_overrides.clear()


def test_districts_parent_in_another_country_is_a_root(api, world):
    _exec(world, "UPDATE Districts SET parent_district_id = 530 WHERE id = 520")     # parent outside the list
    ids = [d["id"] for d in api.get("/locations/countries/1/districts").json()]
    assert sorted(ids) == [500, 501, 505, 520]


async def test_districts_parent_cycle_is_still_listed(session, world):
    _exec(world, "INSERT INTO Districts (id, name, region_id, parent_district_id, description, sort_order) "
                 "VALUES (540, 'Круг', 12, 541, '-', 0), (541, 'Петля', 12, 540, '-', 0)")
    data = await crud.get_country_districts(session, 1)
    ids = [d["id"] for d in data]
    assert ids[:4] == [505, 520, 500, 501] and sorted(ids[4:]) == [540, 541]
    assert len(ids) == len(set(ids))


# ===========================================================================
# 5. check_not_locked_for_post / check_not_locked_for_move
# ===========================================================================

def _res(row=None, first=None):
    r = MagicMock()
    r.fetchone.return_value = row
    r.first.return_value = row
    r.fetchall.return_value = [row] if row is not None else []
    r.scalars.return_value.first.return_value = first
    r.scalars.return_value.all.return_value = []
    r.scalar.return_value = 0
    return r


def _lock_session(jailed=None, encounter=None, location=CELL, district=500, neighbor=None, dest=None,
                  missing_column=False, broken=False):
    """AsyncSession mock: the lock row, (current_location_id, jail_district_id), neighbours, destination."""
    session = AsyncMock()

    async def execute(query, params=None):
        q = str(query)
        if "jailed_until, law_encounter_id FROM characters" in q:
            return _res((None, None, None, None, jailed, encounter))
        if "jail_district_id FROM characters" in q:
            if broken:
                raise RuntimeError("(2013, 'Lost connection to MySQL server during query')")
            if missing_column:
                raise RuntimeError("(1054, \"Unknown column 'jail_district_id' in 'field list'\")")
            return _res((location, district))
        if "SELECT current_location_id" in q and "FROM characters" in q:
            return _res((location,))
        if "LocationNeighbors" in q:
            return _res(first=neighbor)
        if dest is not None and '"Locations"' in q:
            return _res(first=dest)
        return _res()

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def subtree(monkeypatch):
    mock = AsyncMock(return_value=[CELL2, CELL, YARD, CELLAR])
    monkeypatch.setattr(crud, "prison_location_ids", mock)
    return mock


class TestPostTriState:
    async def test_free(self, subtree):
        assert await main.check_not_locked_for_post(_lock_session(), CID, OUTSIDE,
                                                    allow_prison_move=True) == main.POST_FREE
        subtree.assert_not_awaited()

    async def test_in_place(self, subtree):
        s = _lock_session(jailed=SOON)
        assert await main.check_not_locked_for_post(s, CID, CELL, allow_prison_move=True) == main.POST_IN_PLACE

    async def test_prison_move(self, subtree):
        s = _lock_session(jailed=SOON)
        assert await main.check_not_locked_for_post(s, CID, YARD, allow_prison_move=True) == main.POST_PRISON_MOVE
        assert subtree.await_args.args[1] == 500                               # the snapshot district

    async def test_prison_move_not_allowed_for_posts(self, subtree):
        with pytest.raises(HTTPException) as exc:
            await main.check_not_locked_for_post(_lock_session(jailed=SOON), CID, YARD, allow_prison_move=False)
        assert exc.value.status_code == 409 and exc.value.detail.startswith("Персонаж в тюрьме")
        subtree.assert_not_awaited()

    async def test_outside_the_subtree_is_409(self, subtree):
        with pytest.raises(HTTPException) as exc:
            await main.check_not_locked_for_post(_lock_session(jailed=SOON), CID, OUTSIDE, allow_prison_move=True)
        assert exc.value.status_code == 409

    async def test_station_prisoner_cannot_move(self, subtree):
        with pytest.raises(HTTPException):
            await main.check_not_locked_for_post(_lock_session(jailed=SOON, district=None), CID, YARD,
                                                 allow_prison_move=True)
        subtree.assert_not_awaited()

    async def test_encounter_lock_wins_even_inside_the_subtree(self, subtree):
        with pytest.raises(HTTPException) as exc:
            await main.check_not_locked_for_post(_lock_session(encounter=4), CID, YARD, allow_prison_move=True)
        assert exc.value.detail.startswith("Персонаж остановлен стражей")

    async def test_missing_column_falls_back_with_a_warning(self, subtree, caplog):
        s = _lock_session(jailed=SOON, missing_column=True)
        with caplog.at_level(logging.WARNING):
            assert await main.check_not_locked_for_post(s, CID, CELL, allow_prison_move=True) == main.POST_IN_PLACE
            with pytest.raises(HTTPException) as exc:
                await main.check_not_locked_for_post(s, CID, YARD, allow_prison_move=True)
        assert exc.value.status_code == 409
        assert any(r.levelno == logging.WARNING and "jail_district_id" in r.getMessage() for r in caplog.records)
        subtree.assert_not_awaited()

    async def test_other_errors_propagate(self, subtree):
        with pytest.raises(RuntimeError):
            await main.check_not_locked_for_post(_lock_session(jailed=SOON, broken=True), CID, YARD,
                                                 allow_prison_move=True)


class TestMoveCheck:
    async def test_free(self, subtree):
        assert await main.check_not_locked_for_move(_lock_session(), CID, OUTSIDE) is None

    async def test_inside(self, subtree):
        assert await main.check_not_locked_for_move(_lock_session(jailed=SOON), CID, CELLAR) is None

    @pytest.mark.parametrize("kw,dest", [({}, OUTSIDE), ({}, CELL), ({"district": None}, YARD),
                                         ({"missing_column": True}, YARD)],
                             ids=["outside", "same-location", "station", "missing-column"])
    async def test_refused(self, subtree, kw, dest):
        with pytest.raises(HTTPException) as exc:
            await main.check_not_locked_for_move(_lock_session(jailed=SOON, **kw), CID, dest)
        assert exc.value.status_code == 409 and exc.value.detail.startswith("Персонаж в тюрьме")

    async def test_encounter_lock(self, subtree):
        with pytest.raises(HTTPException):
            await main.check_not_locked_for_move(_lock_session(encounter=3), CID, YARD)


# ===========================================================================
# 6. move_and_post / quick_move / posts
# ===========================================================================

def _http(current_location=CELL, stamina=50):
    async def get(url, *a, **kw):
        resp = MagicMock(status_code=200)
        if "/profile" in url:
            resp.json.return_value = {"current_location_id": current_location, "travel_cooldown_until": None,
                                      "character_name": "Узник"}
        else:
            resp.json.return_value = {"current_stamina": stamina}
        return resp

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get)
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    client.put = AsyncMock(side_effect=AssertionError("update_location must go through the helper"))
    return client


def _fake_post(location_id):
    return SimpleNamespace(id=555, character_id=CID, location_id=location_id, content="x",
                           created_at=datetime(2026, 11, 5, 12, 0))


def _client(session, user=PLAYER):
    async def override():
        yield session

    main.app.dependency_overrides[get_db] = override
    main.app.dependency_overrides[get_current_user_via_http] = lambda: user
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


def _drive(path, payload, session, dest, current=CELL, update_exc=None):
    http = _http(current)
    update = AsyncMock(return_value=main.NO_LAW_ARRIVAL, side_effect=update_exc)
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
            patch("main.check_not_in_battle", new_callable=AsyncMock), \
            patch("main.check_not_gathering", new_callable=AsyncMock), \
            patch("main._update_character_location", update), \
            patch("main._try_spawn_mob", new_callable=AsyncMock), \
            patch("main._track_cumulative_stats", new_callable=AsyncMock), \
            patch("main._auto_progress_quest", new_callable=AsyncMock), \
            patch("main._count_unique_locations", new_callable=AsyncMock, return_value=0), \
            patch("crud.get_favorite_user_ids", new_callable=AsyncMock, return_value=[]), \
            patch("crud.create_post", new_callable=AsyncMock, return_value=_fake_post(dest)), \
            patch("crud.archive_draft_on_post", new_callable=AsyncMock), \
            patch("crud.award_post_xp_and_log", new_callable=AsyncMock), \
            patch("crud.expire_action_gates", new_callable=AsyncMock), \
            patch("crud.expire_gate_requests", new_callable=AsyncMock), \
            patch("httpx.AsyncClient", return_value=http):
        r = _client(session).post(path, json=payload)
    return r, update


MOVE_TEXT = "Узник бредёт по тюремному двору и смотрит на стены. " * 8
NEIGHBOR = SimpleNamespace(energy_cost=0)


class TestMoveAndPostInPrison:
    def test_prison_move_calls_update_location(self, subtree):
        s = _lock_session(jailed=SOON, neighbor=NEIGHBOR)
        r, update = _drive(f"/locations/{YARD}/move_and_post", {"character_id": CID, "content": MOVE_TEXT}, s, YARD)
        assert r.status_code == 200, r.text
        assert update.await_args.args == (CID, YARD, "move")

    def test_country_prisoner_post_in_place_skips_update_location(self, subtree):
        s = _lock_session(jailed=SOON, neighbor=NEIGHBOR)
        r, update = _drive(f"/locations/{CELL}/move_and_post", {"character_id": CID, "content": MOVE_TEXT}, s, CELL)
        assert r.status_code == 200, r.text
        update.assert_not_called()

    def test_move_outside_the_prison_is_409_before_anything(self, subtree):
        s = _lock_session(jailed=SOON, neighbor=NEIGHBOR)
        r, update = _drive(f"/locations/{OUTSIDE}/move_and_post", {"character_id": CID, "content": MOVE_TEXT}, s,
                           OUTSIDE)
        assert r.status_code == 409 and r.json()["detail"].startswith("Персонаж в тюрьме")
        update.assert_not_called()

    def test_character_service_refusal_reaches_the_player(self, subtree):
        s = _lock_session(jailed=SOON, neighbor=NEIGHBOR)
        exc = HTTPException(status_code=409, detail="Персонаж в тюрьме — осталось 2 ч")
        r, _ = _drive(f"/locations/{YARD}/move_and_post", {"character_id": CID, "content": MOVE_TEXT}, s, YARD,
                      update_exc=exc)
        assert r.status_code == 409 and r.json()["detail"] == "Персонаж в тюрьме — осталось 2 ч"


class TestQuickMoveInPrison:
    def _session(self, dest_id, **kw):
        dest = SimpleNamespace(id=dest_id, name="Двор", no_quick_move=False)
        return _lock_session(jailed=SOON, neighbor=NEIGHBOR, dest=dest, **kw)

    def test_inside_reaches_update_location(self, subtree):
        r, update = _drive(f"/locations/{YARD}/quick_move", {"character_id": CID}, self._session(YARD), YARD)
        assert r.status_code == 200, r.text
        assert update.await_args.args == (CID, YARD, "quick_move")

    def test_outside_is_409(self, subtree):
        r, update = _drive(f"/locations/{OUTSIDE}/quick_move", {"character_id": CID}, self._session(OUTSIDE),
                           OUTSIDE)
        assert r.status_code == 409 and r.json()["detail"].startswith("Персонаж в тюрьме")
        update.assert_not_called()

    def test_station_prisoner_is_409(self, subtree):
        r, update = _drive(f"/locations/{YARD}/quick_move", {"character_id": CID},
                           self._session(YARD, district=None), YARD)
        assert r.status_code == 409
        update.assert_not_called()


class TestPostsEndpointUnchanged:
    def _post(self, session, location_id):
        with patch("main.verify_character_ownership", new_callable=AsyncMock), \
                patch("main.check_not_in_battle", new_callable=AsyncMock), \
                patch("main.check_not_gathering", new_callable=AsyncMock), \
                patch("crud.create_post", new_callable=AsyncMock,
                      side_effect=HTTPException(status_code=418, detail="past the lock")):
            return _client(session).post("/locations/posts/", json={
                "character_id": CID, "location_id": location_id, "content": "Узник пишет на стене. " * 15})

    def test_country_prisoner_cannot_post_into_another_prison_location(self, subtree):
        r = self._post(_lock_session(jailed=SOON), YARD)
        assert r.status_code == 409 and r.json()["detail"].startswith("Персонаж в тюрьме")
        subtree.assert_not_awaited()

    def test_country_prisoner_posts_where_he_is(self, subtree):
        r = self._post(_lock_session(jailed=SOON, location=YARD), YARD)
        assert r.status_code == 418, r.text


# ===========================================================================
# 7. SQL parity with character-service
# ===========================================================================

_SERVICES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_LAW_FACILITY = os.path.join(_SERVICES_DIR, "character-service", "app", "law_facility.py")


def _module_constant(path, name):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path}")


@pytest.mark.skipif(not os.path.exists(_LAW_FACILITY), reason="needs the whole repository (CI checkout)")
def test_prison_subtree_sql_is_identical_to_character_service():
    other = _module_constant(_LAW_FACILITY, "SQL_PRISON_LOCATIONS")
    assert isinstance(other, str) and other == crud.SQL_PRISON_LOCATIONS
    assert other.encode("utf-8") == crud.SQL_PRISON_LOCATIONS.encode("utf-8")


def test_prison_subtree_sql_has_the_depth_guards():
    sql = crud.SQL_PRISON_LOCATIONS
    assert "WHERE t.depth < 10" in sql and "WHERE t.hops < 10" in sql
    assert ":d" in sql and "%" not in sql and "{" not in sql                   # parameterised, no formatting
