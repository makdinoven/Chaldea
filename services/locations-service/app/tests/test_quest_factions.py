"""FEAT-205 (task 11): faction quests in locations-service.

Sync tests only (the local containers have no pytest-asyncio): the async crud / faction_read code runs on a real
file-backed aiosqlite session through ``asyncio.run``; the routes run through ``TestClient``.

* ``faction_read``: gates (members only «Только для членов фракции X», rank «Нужно звание Y во фракции X», secret ->
  hidden), fail-closed when the faction tables / the faction row are missing, ``in_any_faction`` (error -> True),
  ``quest_referenced`` (rank condition, entry condition params as JSON, missing tables -> False);
* NPC quest list: non-member locked / secret hidden / rank lock / active & completed never hidden; nothing is read
  when no quest of the list has a faction;
* accept: 403 with the gate text / 404 for a secret faction's quest, nothing created; members accepted;
* admin quest fields: schema (points ≠ 0, ±10000, ≤ 5, unique faction ids, injection strings), crud validation
  (rank of another faction, missing faction, rank without faction), persistence, explicit null clears,
  repeatable switch / delete of a referenced quest -> 409;
* completion: ``_apply_quest_faction`` payload / one retry on 5xx & network errors / no retry on 4xx / never raises;
  the route calls it when the quest pays faction points or the character is in some faction (read error -> call);
* migration 058 up / down / re-run.
"""

import asyncio
import importlib.util
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, inspect, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT, TINYINT
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import faction_read  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
from auth_http import UserRead, get_admin_user, get_current_user_via_http  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


@compiles(MEDIUMTEXT, "sqlite")
def _mediumtext(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "TEXT"


@compiles(TINYINT, "sqlite")
def _tinyint(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


CHAR, USER, NPC = 100, 5, 9
F_ORDER, F_SHADOW = 1, 2                         # «Орден Зари» (open), «Тени» (secret)
R_NOVICE, R_KNIGHT, R_SHADOW = 11, 12, 21
Q_OPEN, Q_MEMBERS, Q_RANK, Q_SECRET, Q_TRIAL, Q_COND = 42, 50, 51, 52, 60, 61

FACTION_DDL = [
    "CREATE TABLE factions (id INTEGER PRIMARY KEY, name VARCHAR(100), is_secret INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE faction_ranks (id INTEGER PRIMARY KEY, faction_id INTEGER, name VARCHAR(100), "
    "sort_order INTEGER, required_quest_id INTEGER NULL)",
    "CREATE TABLE faction_members (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, faction_id INTEGER, "
    "status VARCHAR(10), rank_id INTEGER NULL)",
    "CREATE TABLE faction_conditions (id INTEGER PRIMARY KEY AUTOINCREMENT, faction_id INTEGER, "
    "cond_type VARCHAR(30), params TEXT)",
]


class World:
    def __init__(self, path):
        self.path = path

    def sql(self, query, **params):
        eng = create_engine(f"sqlite:///{self.path}")
        with eng.begin() as conn:
            res = conn.execute(text(query), params)
            out = res.fetchall() if res.returns_rows else None
        eng.dispose()
        return out

    def run(self, fn):
        """``await fn(session)`` on a fresh aiosqlite session (sync wrapper — no pytest-asyncio needed)."""
        async def go():
            engine = create_async_engine(f"sqlite+aiosqlite:///{self.path}", poolclass=NullPool)
            Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with Session() as s:
                    return await fn(s)
            finally:
                await engine.dispose()
        return asyncio.run(go())

    def join(self, faction_id, rank_id=None, status="active", cid=CHAR):
        self.sql("INSERT INTO faction_members (character_id, faction_id, status, rank_id) VALUES (:c, :f, :s, :r)",
                 c=cid, f=faction_id, s=status, r=rank_id)

    def quests(self, cid=CHAR):
        return {r["id"]: r for r in self.run(lambda s: crud.get_available_quests_for_npc(s, NPC, cid))}

    def cq_count(self, quest_id):
        return self.sql("SELECT COUNT(*) FROM character_quests WHERE character_id = :c AND quest_id = :q",
                        c=CHAR, q=quest_id)[0][0]


@pytest.fixture()
def qw(tmp_path):
    path = tmp_path / "qf.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        for m in (models.Quest, models.QuestObjective, models.CharacterQuest, models.CharacterQuestProgress):
            m.__table__.create(conn)
        conn.execute(text("CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', "
                          "user_id INTEGER, current_location_id INTEGER, level INTEGER DEFAULT 5, "
                          "is_npc INTEGER NOT NULL DEFAULT 0)"))
        conn.execute(text("INSERT INTO characters (id, user_id, level) VALUES (:c, :u, 5)"), {"c": CHAR, "u": USER})
        conn.execute(text("INSERT INTO characters (id, is_npc) VALUES (:n, 1)"), {"n": NPC})
        for ddl in FACTION_DDL:
            conn.execute(text(ddl))
        conn.execute(text("INSERT INTO factions (id, name, is_secret) VALUES (1, 'Орден Зари', 0), (2, 'Тени', 1)"))
        conn.execute(text("INSERT INTO faction_ranks (id, faction_id, name, sort_order) VALUES "
                          "(11, 1, 'Послушник', 1), (12, 1, 'Рыцарь', 2), (21, 2, 'Посвящённый', 1)"))
    eng.dispose()
    w = World(path)

    async def seed(s):
        for qid, title, faction, rank, qtype in (
                (Q_OPEN, "Гонец", None, None, "standard"),
                (Q_MEMBERS, "Поручение ордена", F_ORDER, None, "standard"),
                (Q_RANK, "Дело рыцаря", F_ORDER, R_KNIGHT, "standard"),
                (Q_SECRET, "Тайное дело", F_SHADOW, None, "standard"),
                (Q_TRIAL, "Испытание", None, None, "standard"),
                (Q_COND, "Клятва", None, None, "standard")):
            s.add(models.Quest(id=qid, npc_id=NPC, title=title, description="", quest_type=qtype, min_level=1,
                               reward_currency=0, reward_exp=0, reward_items=None, is_active=True,
                               faction_id=faction, min_faction_rank_id=rank))
            s.add(models.QuestObjective(quest_id=qid, description="Поговорить", objective_type="talk_npc",
                                        target_id=NPC, target_count=1, sort_order=0))
        await s.commit()

    w.run(seed)
    return w


# ═══════════════════════════════════════════════════════════════════════════
# NPC quest list
# ═══════════════════════════════════════════════════════════════════════════

class TestQuestList:

    def test_non_member(self, qw):
        rows = qw.quests()
        assert Q_SECRET not in rows                                                  # secret: invisible
        assert rows[Q_OPEN]["locked_reason"] is None
        assert rows[Q_MEMBERS]["locked_reason"] == "Только для членов фракции «Орден Зари»"
        assert rows[Q_RANK]["locked_reason"] == "Только для членов фракции «Орден Зари»"
        assert "Тени" not in json.dumps(list(rows.values()), ensure_ascii=False)

    FACTION_FIELDS = ("faction_id", "min_faction_rank_id", "faction_points_rewards")

    @pytest.mark.parametrize("member", [False, True])
    def test_player_list_has_no_faction_fields(self, qw, member):
        # review #1: a public quest that rewards / penalises a SECRET faction must not leak its id or points
        qw.sql("UPDATE quests SET faction_points_rewards = :r WHERE id = :q",
               r=json.dumps([{"faction_id": F_SHADOW, "points": 25}, {"faction_id": F_ORDER, "points": -5}]),
               q=Q_OPEN)
        if member:
            qw.join(F_ORDER, R_KNIGHT)
            qw.join(F_SHADOW, R_SHADOW)
        rows = qw.quests()
        assert Q_OPEN in rows and Q_MEMBERS in rows
        for row in rows.values():
            assert not set(self.FACTION_FIELDS) & set(row)
        assert "points" not in json.dumps(list(rows.values()), ensure_ascii=False)

    def test_admin_schema_keeps_the_faction_fields(self):
        assert set(self.FACTION_FIELDS) <= set(schemas.QuestRead.__fields__)
        assert not set(self.FACTION_FIELDS) & set(schemas.QuestAvailableRead.__fields__)

    def test_member_below_the_rank(self, qw):
        qw.join(F_ORDER, R_NOVICE)
        rows = qw.quests()
        assert rows[Q_MEMBERS]["locked_reason"] is None
        assert rows[Q_RANK]["locked_reason"] == "Нужно звание «Рыцарь» во фракции «Орден Зари»"
        qw.sql("UPDATE faction_members SET rank_id = :r", r=R_KNIGHT)
        assert qw.quests()[Q_RANK]["locked_reason"] is None

    def test_member_without_a_rank_is_below_any_rank(self, qw):
        qw.join(F_ORDER, None)
        assert qw.quests()[Q_RANK]["locked_reason"] == "Нужно звание «Рыцарь» во фракции «Орден Зари»"

    @pytest.mark.parametrize("status", ["left", "expelled"])
    def test_former_member_is_a_non_member(self, qw, status):
        qw.join(F_ORDER, R_KNIGHT, status=status)
        qw.join(F_SHADOW, R_SHADOW, status=status)
        rows = qw.quests()
        assert rows[Q_MEMBERS]["locked_reason"] == "Только для членов фракции «Орден Зари»"
        assert Q_SECRET not in rows

    def test_secret_member_sees_the_secret_quest(self, qw):
        qw.join(F_SHADOW, R_SHADOW)
        assert qw.quests()[Q_SECRET]["locked_reason"] is None

    def test_another_characters_membership_does_not_count(self, qw):
        qw.join(F_SHADOW, R_SHADOW, cid=CHAR + 1)
        assert Q_SECRET not in qw.quests()

    @pytest.mark.parametrize("status", ["active", "completed"])
    def test_taken_secret_quest_stays_visible_after_leaving(self, qw, status):
        qw.sql("INSERT INTO character_quests (character_id, quest_id, status) VALUES (:c, :q, :s)",
               c=CHAR, q=Q_SECRET, s=status)
        rows = qw.quests()
        assert rows[Q_SECRET]["player_status"] == status and rows[Q_SECRET]["locked_reason"] is None

    def test_missing_faction_tables_fail_closed(self, qw):
        for table in ("faction_members", "faction_ranks", "factions"):
            qw.sql(f"DROP TABLE {table}")
        rows = qw.quests()
        assert set(rows) == {Q_OPEN, Q_TRIAL, Q_COND}

    def test_deleted_faction_hides_its_quests(self, qw):
        qw.join(F_ORDER, R_KNIGHT)
        qw.sql("DELETE FROM factions WHERE id = 1")
        assert {Q_MEMBERS, Q_RANK} & set(qw.quests()) == set()

    def test_rank_of_another_faction_is_no_rank_gate(self, qw):
        qw.join(F_ORDER, R_NOVICE)
        qw.sql("UPDATE quests SET min_faction_rank_id = :r WHERE id = :q", r=R_SHADOW, q=Q_RANK)
        assert qw.quests()[Q_RANK]["locked_reason"] is None

    def test_nothing_is_read_without_faction_quests(self, qw):
        qw.sql("UPDATE quests SET is_active = 0 WHERE faction_id IS NOT NULL")
        with patch.object(faction_read, "factions_by_ids", AsyncMock()) as factions, \
                patch.object(faction_read, "active_memberships", AsyncMock()) as members:
            rows = qw.quests()
        assert set(rows) == {Q_OPEN, Q_TRIAL, Q_COND}
        factions.assert_not_awaited()
        members.assert_not_awaited()

    def test_faction_reason_comes_before_reputation(self, qw, monkeypatch):
        import reputation_read

        class Gates:
            def reason(self, code):
                return "Нужна репутация: Свой человек"

        async def gates(*_a, **_k):
            return Gates()

        monkeypatch.setattr(reputation_read, "quest_gates", gates)
        rows = qw.quests()
        assert rows[Q_MEMBERS]["locked_reason"] == "Только для членов фракции «Орден Зари»"
        assert rows[Q_OPEN]["locked_reason"] == "Нужна репутация: Свой человек"


# ═══════════════════════════════════════════════════════════════════════════
# Accept
# ═══════════════════════════════════════════════════════════════════════════

def accept(qw, quest_id):
    return qw.run(lambda s: crud.accept_quest(s, quest_id, CHAR))


class TestAccept:

    def test_non_member_is_403_and_nothing_is_created(self, qw):
        with pytest.raises(HTTPException) as exc:
            accept(qw, Q_MEMBERS)
        assert (exc.value.status_code, exc.value.detail) == (403, "Только для членов фракции «Орден Зари»")
        assert qw.cq_count(Q_MEMBERS) == 0

    def test_secret_faction_quest_is_404_for_non_members(self, qw):
        with pytest.raises(HTTPException) as exc:
            accept(qw, Q_SECRET)
        assert (exc.value.status_code, exc.value.detail) == (404, "Задание не найдено")
        assert qw.cq_count(Q_SECRET) == 0

    def test_rank_gate_is_403(self, qw):
        qw.join(F_ORDER, R_NOVICE)
        with pytest.raises(HTTPException) as exc:
            accept(qw, Q_RANK)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужно звание «Рыцарь» во фракции «Орден Зари»")

    def test_members_accept(self, qw):
        qw.join(F_ORDER, R_KNIGHT)
        qw.join(F_SHADOW, R_SHADOW)
        for qid in (Q_MEMBERS, Q_RANK, Q_SECRET, Q_OPEN):
            assert accept(qw, qid).status == "active"
            assert qw.cq_count(qid) == 1

    def test_missing_tables_fail_closed_on_accept(self, qw):
        qw.sql("DROP TABLE factions")
        with pytest.raises(HTTPException) as exc:
            accept(qw, Q_MEMBERS)
        assert exc.value.status_code == 404
        assert accept(qw, Q_OPEN).status == "active"


# ═══════════════════════════════════════════════════════════════════════════
# faction_read helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestFactionRead:

    def test_in_any_faction(self, qw):
        assert qw.run(lambda s: faction_read.in_any_faction(s, CHAR)) is False
        qw.join(F_ORDER, status="left")
        assert qw.run(lambda s: faction_read.in_any_faction(s, CHAR)) is False
        qw.join(F_SHADOW)
        assert qw.run(lambda s: faction_read.in_any_faction(s, CHAR)) is True
        qw.sql("DROP TABLE faction_members")
        assert qw.run(lambda s: faction_read.in_any_faction(s, CHAR)) is True              # error -> call anyway

    def test_quest_referenced(self, qw):
        assert qw.run(lambda s: faction_read.quest_referenced(s, Q_TRIAL)) is False
        qw.sql("INSERT INTO faction_conditions (faction_id, cond_type, params) VALUES (1, 'quest', :p)",
               p=json.dumps({"quest_id": Q_TRIAL}))
        qw.sql("INSERT INTO faction_conditions (faction_id, cond_type, params) VALUES (1, 'level', :p)",
               p=json.dumps({"min_level": Q_COND}))                                       # same number, not a quest
        qw.sql("UPDATE faction_ranks SET required_quest_id = :q WHERE id = :r", q=Q_COND - 100, r=R_KNIGHT)
        assert qw.run(lambda s: faction_read.quest_referenced(s, Q_TRIAL)) is True
        assert qw.run(lambda s: faction_read.quest_referenced(s, Q_COND)) is False
        qw.sql("UPDATE faction_ranks SET required_quest_id = :q WHERE id = :r", q=Q_COND, r=R_KNIGHT)
        assert qw.run(lambda s: faction_read.quest_referenced(s, Q_COND)) is True

    def test_quest_referenced_without_tables(self, qw):
        qw.sql("DROP TABLE faction_ranks")
        qw.sql("DROP TABLE faction_conditions")
        assert qw.run(lambda s: faction_read.quest_referenced(s, Q_TRIAL)) is False

    @pytest.mark.parametrize("params,expected", [({"quest_id": 7}, 7), ('{"quest_id": 7}', 7), ("not json", None),
                                                 ({"quest_id": "x"}, None), (None, None), ([7], None)])
    def test_param_quest_id(self, params, expected):
        assert faction_read._param_quest_id(params) == expected

    def test_gate_pure(self):
        gates = faction_read.FactionGates(
            {1: faction_read.FactionInfo(1, "Орден", False), 2: faction_read.FactionInfo(2, "Тени", True)},
            {11: faction_read.RankInfo(11, 1, "Послушник", 1), 12: faction_read.RankInfo(12, 1, "Рыцарь", 2)},
            {1: 12})
        assert gates.gate(None, None) == faction_read.OPEN_GATE
        assert gates.gate(1, 11) == faction_read.OPEN_GATE                                  # higher rank held
        assert gates.gate(1, 12) == faction_read.OPEN_GATE
        assert gates.gate(2, None) == faction_read.HIDDEN_GATE
        assert gates.gate(3, None) == faction_read.HIDDEN_GATE                              # unknown faction
        assert gates.gate(1, 99) == faction_read.OPEN_GATE                                  # rank gone


# ═══════════════════════════════════════════════════════════════════════════
# Admin quest fields
# ═══════════════════════════════════════════════════════════════════════════

def quest_create(**over):
    body = {"npc_id": NPC, "title": "Новое поручение", "objectives": []}
    body.update(over)
    return schemas.QuestCreate(**body)


class TestQuestSchema:

    def test_valid_rewards(self):
        q = quest_create(faction_id=1, min_faction_rank_id=12,
                         faction_points_rewards=[{"faction_id": 1, "points": 20}, {"faction_id": 2, "points": -10}])
        assert [r.dict() for r in q.faction_points_rewards] == [{"faction_id": 1, "points": 20},
                                                                {"faction_id": 2, "points": -10}]
        assert quest_create(faction_points_rewards=[]).faction_points_rewards is None

    @pytest.mark.parametrize("rewards", [
        [{"faction_id": 1, "points": 0}],
        [{"faction_id": 1, "points": 10001}],
        [{"faction_id": 1, "points": -10001}],
        [{"faction_id": 0, "points": 5}],
        [{"faction_id": "1; DROP TABLE quests", "points": 5}],
        [{"faction_id": 1, "points": 5}, {"faction_id": 1, "points": 6}],
        [{"faction_id": i, "points": 1} for i in range(1, 7)],
    ])
    def test_invalid_rewards(self, rewards):
        with pytest.raises(ValidationError):
            quest_create(faction_points_rewards=rewards)

    @pytest.mark.parametrize("field", ["faction_id", "min_faction_rank_id"])
    def test_ids_must_be_positive(self, field):
        with pytest.raises(ValidationError):
            quest_create(**{field: 0})
        with pytest.raises(ValidationError):
            schemas.QuestUpdate(**{field: "1 OR 1=1"})


@pytest.fixture()
def admin_http():
    from database import get_db

    async def _db():
        db = MagicMock()
        db.commit = AsyncMock()
        yield db

    main.app.dependency_overrides[get_db] = _db
    main.app.dependency_overrides[get_admin_user] = lambda: UserRead(id=1, username="a", role="admin",
                                                                     permissions=[])
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


class TestQuestAdminHttp:

    def test_invalid_rewards_are_422_and_touch_nothing(self, admin_http):
        with patch.object(crud, "create_quest", AsyncMock()) as create:
            r = admin_http.post("/locations/admin/quests", json={
                "npc_id": NPC, "title": "t", "faction_points_rewards": [{"faction_id": 1, "points": 0}]})
        assert r.status_code == 422
        create.assert_not_awaited()

    def test_fields_reach_crud_as_plain_dicts(self, admin_http):
        quest = models.Quest(id=1, npc_id=NPC, title="t", description="", quest_type="standard", min_level=1,
                             reward_currency=0, reward_exp=0, is_active=True, objectives=[], faction_id=1,
                             min_faction_rank_id=12, faction_points_rewards=[{"faction_id": 1, "points": 5}])
        with patch.object(crud, "create_quest", AsyncMock(return_value=quest)) as create:
            r = admin_http.post("/locations/admin/quests", json={
                "npc_id": NPC, "title": "t", "faction_id": 1, "min_faction_rank_id": 12,
                "faction_points_rewards": [{"faction_id": 1, "points": 5}]})
        assert r.status_code == 200, r.text
        data = create.await_args.args[1]
        assert (data["faction_id"], data["min_faction_rank_id"], data["faction_points_rewards"]) == (
            1, 12, [{"faction_id": 1, "points": 5}])
        assert r.json()["faction_points_rewards"] == [{"faction_id": 1, "points": 5}]

    def test_update_passes_the_explicit_clear(self, admin_http):
        quest = models.Quest(id=1, npc_id=NPC, title="t", description="", quest_type="standard", min_level=1,
                             reward_currency=0, reward_exp=0, is_active=True, objectives=[])
        with patch.object(crud, "update_quest", AsyncMock(return_value=quest)) as update:
            r = admin_http.put("/locations/admin/quests/1", json={"faction_id": None, "faction_points_rewards": []})
        assert r.status_code == 200, r.text
        assert update.await_args.args[2] == {"faction_id": None, "faction_points_rewards": None}

    def test_non_admin_cannot_create(self):
        from database import get_db

        async def _db():
            yield MagicMock()

        main.app.dependency_overrides[get_db] = _db
        try:
            with TestClient(main.app) as c:
                r = c.post("/locations/admin/quests", json={"npc_id": NPC, "title": "t", "faction_id": 1})
            assert r.status_code in (401, 403)
        finally:
            main.app.dependency_overrides.clear()


def create_data(**over):
    return quest_create(**over).dict()


class TestQuestCrud:

    @pytest.mark.parametrize("over,detail", [
        ({"min_faction_rank_id": 12}, "Минимальное звание задаётся только вместе с фракцией"),
        ({"faction_id": 9}, "Фракция не найдена"),
        ({"faction_points_rewards": [{"faction_id": 9, "points": 5}]}, "Фракция из награды не найдена"),
        ({"faction_id": 1, "min_faction_rank_id": 21}, "Звание не найдено или принадлежит другой фракции"),
        ({"faction_id": 1, "min_faction_rank_id": 99}, "Звание не найдено или принадлежит другой фракции"),
    ])
    def test_create_validation(self, qw, over, detail):
        before = qw.sql("SELECT COUNT(*) FROM quests")[0][0]
        with pytest.raises(HTTPException) as exc:
            qw.run(lambda s: crud.create_quest(s, create_data(**over)))
        assert (exc.value.status_code, exc.value.detail) == (422, detail)
        assert qw.sql("SELECT COUNT(*) FROM quests")[0][0] == before

    def test_create_persists_the_fields(self, qw):
        data = create_data(faction_id=1, min_faction_rank_id=12,
                           faction_points_rewards=[{"faction_id": 1, "points": 15}, {"faction_id": 2, "points": -5}])
        quest = qw.run(lambda s: crud.create_quest(s, data))
        row = qw.sql("SELECT faction_id, min_faction_rank_id, faction_points_rewards FROM quests WHERE id = :q",
                     q=quest.id)[0]
        assert (row[0], row[1], json.loads(row[2])) == (1, 12, [{"faction_id": 1, "points": 15},
                                                                {"faction_id": 2, "points": -5}])

    def test_create_without_faction_tables_still_works_for_plain_quests(self, qw):
        qw.sql("DROP TABLE factions")
        quest = qw.run(lambda s: crud.create_quest(s, create_data()))
        assert quest.faction_id is None
        with pytest.raises(HTTPException):
            qw.run(lambda s: crud.create_quest(s, create_data(faction_id=1)))

    def test_update_validates_the_resulting_combination(self, qw):
        # the quest keeps faction 1; a rank of faction 2 is refused even when only the rank is sent
        with pytest.raises(HTTPException) as exc:
            qw.run(lambda s: crud.update_quest(s, Q_RANK, {"min_faction_rank_id": R_SHADOW}))
        assert exc.value.status_code == 422
        # clearing the faction while a rank stays is refused
        with pytest.raises(HTTPException) as exc:
            qw.run(lambda s: crud.update_quest(s, Q_RANK, {"faction_id": None}))
        assert exc.value.detail == "Минимальное звание задаётся только вместе с фракцией"
        qw.run(lambda s: crud.update_quest(s, Q_RANK, {"faction_id": None, "min_faction_rank_id": None,
                                                       "faction_points_rewards": None}))
        assert qw.sql("SELECT faction_id, min_faction_rank_id FROM quests WHERE id = :q", q=Q_RANK)[0] == (None, None)

    def test_referenced_quest_cannot_become_repeatable(self, qw):
        qw.sql("INSERT INTO faction_conditions (faction_id, cond_type, params) VALUES (1, 'quest', :p)",
               p=json.dumps({"quest_id": Q_TRIAL}))
        qw.sql("UPDATE faction_ranks SET required_quest_id = :q WHERE id = :r", q=Q_COND, r=R_KNIGHT)
        for qid in (Q_TRIAL, Q_COND):
            with pytest.raises(HTTPException) as exc:
                qw.run(lambda s, qid=qid: crud.update_quest(s, qid, {"quest_type": "repeatable"}))
            assert (exc.value.status_code, exc.value.detail) == (409, "Задание используется как условие фракции")
            assert qw.sql("SELECT quest_type FROM quests WHERE id = :q", q=qid)[0][0] == "standard"
        qw.run(lambda s: crud.update_quest(s, Q_TRIAL, {"title": "Новое имя"}))           # other edits are fine
        qw.run(lambda s: crud.update_quest(s, Q_OPEN, {"quest_type": "repeatable"}))
        assert qw.sql("SELECT quest_type FROM quests WHERE id = :q", q=Q_OPEN)[0][0] == "repeatable"

    def test_referenced_quest_cannot_be_deleted(self, qw):
        qw.sql("UPDATE faction_ranks SET required_quest_id = :q WHERE id = :r", q=Q_COND, r=R_KNIGHT)
        with pytest.raises(HTTPException) as exc:
            qw.run(lambda s: crud.delete_quest(s, Q_COND))
        assert exc.value.status_code == 409
        assert qw.sql("SELECT COUNT(*) FROM quests WHERE id = :q", q=Q_COND)[0][0] == 1
        assert qw.run(lambda s: crud.delete_quest(s, Q_OPEN)) is True


# ═══════════════════════════════════════════════════════════════════════════
# Completion -> character-service
# ═══════════════════════════════════════════════════════════════════════════

def _client(*outcomes):
    """An httpx.AsyncClient stand-in whose post answers / raises the given outcomes in order."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    effects = []
    for o in outcomes:
        if isinstance(o, BaseException):
            effects.append(o)
        else:
            resp = MagicMock()
            resp.status_code = o
            effects.append(resp)
    client.post = AsyncMock(side_effect=effects)
    return client


def apply(rewards, *outcomes):
    client = _client(*outcomes)
    with patch("main.httpx.AsyncClient", return_value=client):
        ok = asyncio.run(main._apply_quest_faction(CHAR, Q_MEMBERS, 77, rewards))
    return ok, client.post


class TestApplyQuestFaction:

    def test_payload_url_and_token(self, monkeypatch):
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "tok", raising=False)
        ok, post = apply([{"faction_id": 1, "points": 20}, {"faction_id": 2, "points": 0}, {"points": 5},
                          "junk"], 200)
        assert ok is True and post.await_count == 1
        url = post.await_args.args[0]
        assert url.endswith("/characters/internal/factions/quest-completed")
        assert post.await_args.kwargs["json"] == {"character_id": CHAR, "quest_id": Q_MEMBERS, "cq_id": 77,
                                                  "rewards": [{"faction_id": 1, "points": 20}]}
        assert post.await_args.kwargs["headers"] == main._internal_token_headers()

    def test_no_rewards_still_calls_with_an_empty_list(self):
        ok, post = apply(None, 200)
        assert ok and post.await_args.kwargs["json"]["rewards"] == []

    def test_one_retry_on_5xx(self):
        ok, post = apply([], 503, 200)
        assert ok is True and post.await_count == 2

    def test_one_retry_on_network_error_then_gives_up(self):
        ok, post = apply([], httpx.ConnectError("down"), httpx.ReadTimeout("slow"))
        assert ok is False and post.await_count == 2

    @pytest.mark.parametrize("status", [401, 404, 422])
    def test_4xx_is_not_retried(self, status):
        ok, post = apply([], status)
        assert ok is False and post.await_count == 1

    def test_unexpected_error_never_raises(self):
        ok, post = apply([], RuntimeError("boom"))
        assert ok is False and post.await_count == 1


class _FakeQuest:
    def __init__(self, faction_points_rewards=None):
        self.id = Q_MEMBERS
        self.reward_exp = 0
        self.reward_currency = 0
        self.reward_items = []
        self.npc_id = None
        self.reputation_reward = 0
        self.fame_reward = 0
        self.faction_points_rewards = faction_points_rewards


MOCK_USER = UserRead(id=USER, username="p", role="user", permissions=[])


class TestCompleteRoute:

    def _complete(self, client, quest, in_any=False, in_any_error=False):
        main.app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        in_any_mock = AsyncMock(side_effect=RuntimeError("db")) if in_any_error else AsyncMock(return_value=in_any)
        try:
            with patch("main.verify_character_ownership", AsyncMock()), \
                    patch("main.crud.check_quest_completable",
                          AsyncMock(return_value={"all_completed": True, "character_quest_id": 55})), \
                    patch("main.crud.get_quest_by_id", AsyncMock(return_value=quest)), \
                    patch("main.crud.complete_quest_record", AsyncMock(return_value=True)), \
                    patch("main._track_cumulative_stats", AsyncMock()), \
                    patch("main._auto_progress_quest", AsyncMock()), \
                    patch("main.faction_read.in_any_faction", in_any_mock), \
                    patch("main._apply_quest_faction", AsyncMock(return_value=False)) as apply_mock:
                resp = client.post(f"/locations/quests/{Q_MEMBERS}/complete", json={"character_id": CHAR})
        finally:
            main.app.dependency_overrides.pop(get_current_user_via_http, None)
        return resp, apply_mock, in_any_mock

    def test_quest_with_faction_points_calls_without_reading_memberships(self, client):
        rewards = [{"faction_id": 1, "points": 10}]
        resp, apply_mock, in_any = self._complete(client, _FakeQuest(rewards))
        assert resp.status_code == 200, resp.text
        apply_mock.assert_awaited_once_with(CHAR, Q_MEMBERS, 55, rewards)
        in_any.assert_not_awaited()

    def test_member_without_points_still_triggers_the_rank_recheck(self, client):
        resp, apply_mock, _ = self._complete(client, _FakeQuest(), in_any=True)
        assert resp.status_code == 200
        apply_mock.assert_awaited_once_with(CHAR, Q_MEMBERS, 55, None)

    def test_non_member_without_points_no_call(self, client):
        resp, apply_mock, in_any = self._complete(client, _FakeQuest(), in_any=False)
        assert resp.status_code == 200
        in_any.assert_awaited_once()
        apply_mock.assert_not_awaited()

    def test_membership_read_error_calls_anyway(self, client):
        resp, apply_mock, _ = self._complete(client, _FakeQuest(), in_any_error=True)
        assert resp.status_code == 200
        apply_mock.assert_awaited_once()

    def test_failed_faction_call_never_fails_the_completion(self, client):
        quest = _FakeQuest([{"faction_id": 1, "points": 10}])
        main.app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        try:
            with patch("main.verify_character_ownership", AsyncMock()), \
                    patch("main.crud.check_quest_completable",
                          AsyncMock(return_value={"all_completed": True, "character_quest_id": 55})), \
                    patch("main.crud.get_quest_by_id", AsyncMock(return_value=quest)), \
                    patch("main.crud.complete_quest_record", AsyncMock(return_value=True)), \
                    patch("main._track_cumulative_stats", AsyncMock()), \
                    patch("main._auto_progress_quest", AsyncMock()), \
                    patch("main.httpx.AsyncClient", return_value=_client(httpx.ConnectError("x"),
                                                                         httpx.ConnectError("x"))):
                resp = client.post(f"/locations/quests/{Q_MEMBERS}/complete", json={"character_id": CHAR})
        finally:
            main.app.dependency_overrides.pop(get_current_user_via_http, None)
        assert resp.status_code == 200 and resp.json()["success"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Migration 058
# ═══════════════════════════════════════════════════════════════════════════

def _load_058():
    path = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "058_quest_faction_vouchers.py")
    spec = importlib.util.spec_from_file_location("mig058", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_058_chain():
    mod = _load_058()
    assert mod.revision == "058_quest_faction_vouchers" and len(mod.revision) <= 32
    assert mod.down_revision == "057_country_prison_district"


def test_migration_058_upgrade_rerun_downgrade_upgrade(tmp_path, monkeypatch):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    mod = _load_058()
    # SQLite cannot ALTER constraints (MySQL can): record the FK instead of creating it
    fks = []
    monkeypatch.setattr(mod.op, "create_foreign_key", lambda *a, **k: fks.append((a, k)), raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    quest_cols = lambda conn: {c["name"]: c for c in inspect(conn).get_columns("quests")}  # noqa: E731
    new = {"faction_id", "min_faction_rank_id", "faction_points_rewards"}

    def migrate(conn, step):
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE \"Locations\" (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("CREATE TABLE quests (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO quests (id, title) VALUES (1, 'Старое')"))
        migrate(conn, "upgrade")
        cols = quest_cols(conn)
        assert new <= set(cols) and all(cols[c]["nullable"] for c in new)
        assert tuple(conn.execute(text("SELECT faction_id, min_faction_rank_id, faction_points_rewards "
                                       "FROM quests")).first()) == (None, None, None)
        assert "ix_quests_faction" in {i["name"] for i in inspect(conn).get_indexes("quests")}
        vcols = {c["name"] for c in inspect(conn).get_columns("house_vouchers")}
        assert vcols == {"id", "character_id", "location_id", "kind", "source_key", "source_text", "status",
                         "claimed_house_id", "claimed_at", "created_at"}
        assert {"ix_house_vouchers_character", "ix_house_vouchers_location"} <= {
            i["name"] for i in inspect(conn).get_indexes("house_vouchers")}
        assert fks == [(("fk_house_vouchers_location", "house_vouchers", "Locations", ["location_id"], ["id"]),
                        {"ondelete": "CASCADE"})]
        migrate(conn, "upgrade")                                                           # re-run = no-op
        assert len(fks) == 1
        migrate(conn, "downgrade")
        assert set(quest_cols(conn)) == {"id", "title"}
        assert "house_vouchers" not in inspect(conn).get_table_names()
        migrate(conn, "downgrade")                                                         # re-run = no-op
        migrate(conn, "upgrade")
        assert new <= set(quest_cols(conn))
    engine.dispose()


def test_models_carry_the_columns():
    c = models.Quest.__table__.c
    assert {"faction_id", "min_faction_rank_id", "faction_points_rewards"} <= set(c.keys())
    v = models.HouseVoucher.__table__
    assert v.c.source_key.unique and v.c.source_key.type.length == 120
