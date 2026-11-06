"""FEAT-205 QA: shared SQLite world for the faction tests (not a test module).

Built on :mod:`tests.reputation_world` (characters 1 «Альфа» / 2 «Бета» / 3 «Гамма» of users 7 / 8 / 9, NPCs 50..56,
regions 10 «Ост» / 11 «Пашни» / 12 «Холмы» / 20 «Дюны», locations 100 / 110 / 200 / 300, items / tree tables), plus:

    tables of other services read by raw SQL: ``quests`` (id, title, quest_type), ``character_quests``;
    ``character_attributes`` gets ``passive_experience`` / ``active_experience`` (rank XP rewards, level-up hook);
    level thresholds: level 3 = 100, 4 = 300, 5 = 1000, 6 = 5000 total XP (every character starts at level 2);
    classes 1 «Воин» / 2 «Плут» / 3 «Маг», races 1 «Человек» / 2 «Эльф», subraces 1 «Норд» / 4 «Лесной»;
    quests 700 «Испытание» (standard), 701 «Поручение магистра» (standard), 702 «Каждый день» (repeatable);
    items 501 «Меч Зари», 502 «Щит Зари»; title 1 «Рыцарь Зари»;
    ``faction_settings`` row id=1 with the defaults (3 d / 7 d / 50 % / 50 % / 24 h).

Every external side effect is mocked:
    * RabbitMQ — ``faction_notify._send`` (recorder ``factory.fsent``), ``reputation_notify._send`` (rep_world);
    * HTTP of the reward outbox — ``faction_rewards.http_post`` (:class:`HttpFake`, ``factory.http``);
    * the outbox / level-up hook sessions — ``faction_rewards._factory`` returns this world's factory.
"""

import importlib.util
import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import auth_http
import faction_api
import faction_crud
import faction_notify
import faction_rewards
import main
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.reputation_world import (  # noqa: F401  (rep_world is a fixture)
    ALPHA, BETA, GAMMA, MERCHANT, BANDIT, GUARD, R_OST, R_PASHNI, USER_ALPHA, USER_BETA, USER_GAMMA, exec_, q,
    rep_world, rows, set_value,
)

TOKEN = "test-internal-token"
INTERNAL = {"X-Internal-Token": TOKEN}
Q_TRIAL, Q_MASTER, Q_DAILY = 700, 701, 702
ITEM_SWORD, ITEM_SHIELD = 501, 502
TITLE_KNIGHT = 1
L_MARKET, L_NIVA = 100, 110

ALL_PERMS = ["factions:read", "factions:edit", "factions:delete", "factions:manage", "factions:settings",
             "characters:read"]
MODERATOR_PERMS = ["factions:read", "factions:edit", "factions:manage", "characters:read"]

_EXTRA_DDL = (
    "CREATE TABLE IF NOT EXISTS quests (id INTEGER PRIMARY KEY, title VARCHAR(200), "
    "quest_type VARCHAR(20) NOT NULL DEFAULT 'standard')",
    "CREATE TABLE IF NOT EXISTS character_quests (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, "
    "quest_id INTEGER, status VARCHAR(20))",
    "ALTER TABLE character_attributes ADD COLUMN passive_experience INTEGER DEFAULT 0",
    "ALTER TABLE character_attributes ADD COLUMN active_experience INTEGER DEFAULT 0",
)

_MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "045_factions_core.py")


def load_migration():
    spec = importlib.util.spec_from_file_location("migration_045_factions_core_qa", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_STEADY_LAST = [datetime.min]


def steady_utcnow():
    """A wall clock that never steps backwards. The Docker / WSL2 container clock jumps back up to ~1 s under load;
    a test that writes a row at one read of the clock and checks «is it due yet» at a later read then flakes. The
    ``fw`` fixture installs this as ``faction_crud.now_utc`` (every faction module reads time through it) and the
    tests' own :func:`now` uses it too, so all reads in one test are monotonic."""
    t = datetime.utcnow().replace(microsecond=0)
    if t < _STEADY_LAST[0]:
        t = _STEADY_LAST[0]
    _STEADY_LAST[0] = t
    return t


def now():
    return steady_utcnow()


class Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code


class HttpFake:
    """``faction_rewards.http_post`` stand-in: records (url, payload); answers from a queue (default 200).
    A queued exception instance is raised instead of answering."""

    def __init__(self):
        self.calls = []
        self.queue = []

    def push(self, *outcomes):
        self.queue.extend(outcomes)

    def __call__(self, url, payload):
        self.calls.append((url, dict(payload)))
        outcome = self.queue.pop(0) if self.queue else 200
        if isinstance(outcome, BaseException):
            raise outcome
        return Resp(outcome)

    def urls(self):
        return [u for u, _p in self.calls]


def _build(factory):
    db = factory()
    try:
        for ddl in _EXTRA_DDL:
            db.execute(text(ddl))
        for cid in (ALPHA, BETA, GAMMA):
            db.execute(text("INSERT INTO character_attributes (character_id, passive_experience, active_experience) "
                            "VALUES (:c, 0, 0)"), {"c": cid})
        for level, xp in ((3, 100), (4, 300), (5, 1000), (6, 5000)):
            db.add(models.LevelThreshold(level_number=level, required_experience=xp))
        for cid, name in ((1, "Воин"), (2, "Плут"), (3, "Маг")):
            db.add(models.Class(id_class=cid, name=name))
        for rid, name in ((1, "Человек"), (2, "Эльф")):
            db.add(models.Race(id_race=rid, name=name))
        db.flush()
        for sid, rid, name in ((1, 1, "Норд"), (4, 2, "Лесной")):
            db.add(models.Subrace(id_subrace=sid, id_race=rid, name=name))
        db.execute(text("INSERT INTO quests (id, title, quest_type) VALUES (700, 'Испытание', 'standard'), "
                        "(701, 'Поручение магистра', 'standard'), (702, 'Каждый день', 'repeatable')"))
        db.execute(text("INSERT INTO items (id, name, item_type) VALUES (501, 'Меч Зари', 'weapon'), "
                        "(502, 'Щит Зари', 'shield')"))
        db.add(models.Title(id_title=TITLE_KNIGHT, name="Рыцарь Зари", rarity="common", reward_passive_exp=0,
                            reward_active_exp=0))
        db.add(models.FactionSettings(id=1))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def fw(rep_world, monkeypatch):
    """rep_world + the faction extras; notifications and outbox HTTP recorded, outbox sessions = this world."""
    _build(rep_world)
    monkeypatch.setattr(faction_crud, "now_utc", steady_utcnow)
    fsent = MagicMock(name="faction_notify._send")
    monkeypatch.setattr(faction_notify, "_send", fsent)
    http = HttpFake()
    monkeypatch.setattr(faction_rewards, "http_post", http)
    monkeypatch.setattr(faction_rewards, "_factory", lambda: rep_world)
    rep_world.fsent = fsent
    rep_world.http = http
    return rep_world


@pytest.fixture
def fapi(fw, monkeypatch):
    def override_get_db():
        session = fw()
        try:
            yield session
        finally:
            session.close()

    for dep in (faction_api.get_db, main.get_db):
        app.dependency_overrides[dep] = override_get_db
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    yield TestClient(app, raise_server_exceptions=False)
    for dep in (faction_api.get_db, main.get_db, get_current_user_via_http):
        app.dependency_overrides.pop(dep, None)


# --------------------------------------------------------------------------------------------- auth helpers

def as_user(user_id=USER_ALPHA, role="user", permissions=()):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username=f"u{user_id}", role=role, permissions=list(permissions))


def as_admin():
    as_user(1, "admin", ALL_PERMS)


def as_moderator():
    as_user(2, "moderator", MODERATOR_PERMS)


# --------------------------------------------------------------------------------------------- data helpers

def make_faction(f, name="Орден Зари", *, active=True, secret=False, invite=False, limit=None, sort=0,
                 leaders=None, hq=None):
    db = f()
    try:
        row = models.Faction(name=name, description="Описание", emblem_url=None, hq_location_id=hq,
                             leader_npc_ids=leaders, member_limit=limit, is_invite_only=invite, is_secret=secret,
                             is_active=active, sort_order=sort, created_at=now(), updated_at=now())
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def add_rank(f, faction_id, name, sort_order, **fields):
    db = f()
    try:
        row = models.FactionRank(faction_id=faction_id, name=name, sort_order=sort_order, created_at=now(),
                                 **fields)
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def set_conditions(f, faction_id, conditions):
    db = f()
    try:
        db.query(models.FactionCondition).filter(models.FactionCondition.faction_id == faction_id).delete()
        for i, (cond_type, params) in enumerate(conditions):
            db.add(models.FactionCondition(faction_id=faction_id, cond_type=cond_type, params=params, sort_order=i))
        db.commit()
    finally:
        db.close()


def hostile(f, a, b, irreconcilable=False):
    lo, hi = sorted((a, b))
    db = f()
    try:
        db.add(models.FactionHostility(faction_a_id=lo, faction_b_id=hi, irreconcilable=irreconcilable,
                                       created_at=now()))
        db.commit()
    finally:
        db.close()


def settings(f, **values):
    db = f()
    try:
        row = db.get(models.FactionSettings, 1)
        for k, v in values.items():
            setattr(row, k, v)
        db.commit()
    finally:
        db.close()


def member(f, character_id, faction_id):
    """dict of the membership row (None without one)."""
    r = rows(f, "SELECT id, status, points, rank_id, rejoin_after, warning_at, warning_reasons, left_at "
                "FROM faction_members WHERE character_id = :c AND faction_id = :fid", c=character_id, fid=faction_id)
    if not r:
        return None
    keys = ("id", "status", "points", "rank_id", "rejoin_after", "warning_at", "warning_reasons", "left_at")
    out = dict(zip(keys, r[0]))
    if isinstance(out["warning_reasons"], str):                 # raw SQL read of a JSON column
        out["warning_reasons"] = json.loads(out["warning_reasons"])
    return out


def set_points(f, character_id, faction_id, points):
    exec_(f, "UPDATE faction_members SET points = :p WHERE character_id = :c AND faction_id = :fid",
          p=points, c=character_id, fid=faction_id)


def complete_quest(f, character_id, quest_id, status="completed"):
    exec_(f, "INSERT INTO character_quests (character_id, quest_id, status) VALUES (:c, :q, :s)",
          c=character_id, q=quest_id, s=status)


def set_renown(f, character_id, fame=0, infamy=0):
    exec_(f, "DELETE FROM character_renown WHERE character_id = :c", c=character_id)
    exec_(f, "INSERT INTO character_renown (character_id, fame, infamy, updated_at) VALUES (:c, :fame, :i, :u)",
          c=character_id, fame=fame, i=infamy, u=now())


def set_level(f, character_id, level):
    exec_(f, "UPDATE characters SET level = :l WHERE id = :c", l=level, c=character_id)


def passive_xp(f, character_id):
    return int(q(f, "SELECT passive_experience FROM character_attributes WHERE character_id = :c", c=character_id)
               or 0)


def level(f, character_id):
    return int(q(f, "SELECT level FROM characters WHERE id = :c", c=character_id))


def grants(f, character_id):
    return [int(r[0]) for r in rows(f, "SELECT rank_id FROM faction_rank_grants WHERE character_id = :c ORDER BY id",
                                    c=character_id)]


def deliveries(f, character_id=None):
    sql = "SELECT id, kind, status, attempts, last_error, payload FROM faction_reward_deliveries"
    params = {}
    if character_id is not None:
        sql += " WHERE character_id = :c"
        params["c"] = character_id
    return rows(f, sql + " ORDER BY id", **params)


def log_types(f, character_id, faction_id=None):
    sql = "SELECT event_type FROM faction_log WHERE character_id = :c"
    params = {"c": character_id}
    if faction_id is not None:
        sql += " AND faction_id = :fid"
        params["fid"] = faction_id
    return [r[0] for r in rows(f, sql + " ORDER BY id", **params)]


def notices(f):
    """Every payload handed to the (mocked) faction RabbitMQ sender."""
    out = []
    for call in f.fsent.call_args_list:
        out.extend(call.args[0])
    return out


def run_flow(f, fn, *args, **kwargs):
    """A faction_crud / admin flow in its own committed transaction (the API ``_write`` shape)."""
    db = f()
    try:
        result = fn(db, *args, **kwargs)
        db.commit()
        return result
    finally:
        db.close()


def join(f, character_id, faction_id, at=None):
    return run_flow(f, faction_crud.join, character_id, faction_id, at)


def days_ago(days):
    return now() - timedelta(days=days)


def connect_error():
    return httpx.ConnectError("refused")


def read_timeout():
    return httpx.ReadTimeout("slow")


# ============================================================================================= FEAT-206 economy
#
# The faction economy reads the econ world (ledger accounts, econ_regions, goods groups / region goods,
# econ_item_groups) and the inventory ``items`` columns the market resolver needs (``core.sql_item_market``).
# :func:`econ_world` adds them on top of :func:`fw`; the ledger / regions tables come from the ORM metadata.

import econ_core as core          # noqa: E402
import econ_ledger                # noqa: E402

ECON_ITEM_DDL = (
    "ALTER TABLE items ADD COLUMN resource_subcategory VARCHAR(30)",
    "ALTER TABLE items ADD COLUMN is_food INTEGER DEFAULT 0",
    "ALTER TABLE items ADD COLUMN item_rarity VARCHAR(20)",
    "ALTER TABLE items ADD COLUMN price INTEGER DEFAULT 0",
    "ALTER TABLE items ADD COLUMN image VARCHAR(255)",
)
ITEM_SCROLL = 503                 # «Свиток Зари» — off-market by the admin flag
QM_NPC = 53                       # «Безымянный» NPC @100 (region 10)
QM_NPC_2 = 56                     # «Писарь» NPC @100
GROUP_ARMS = "arms"

_MIGRATION_046_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "046_faction_economy.py")


def load_migration_046():
    spec = importlib.util.spec_from_file_location("migration_046_faction_economy_qa206", _MIGRATION_046_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION_047_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "047_faction_territory.py")


def load_migration_047():
    """FEAT-207 migration module (its ``_COLUMNS`` are skipped by the 045 / 046 DDL-vs-model checks)."""
    spec = importlib.util.spec_from_file_location("migration_047_faction_territory_qa207", _MIGRATION_047_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_templates(f):
    """The five templates exactly as migration 046 seeds them."""
    db = f()
    try:
        for code, name, description, params, order in load_migration_046().TEMPLATES:
            db.add(models.FactionEconTemplate(code=code, name=name, description=description, params=params,
                                              sort_order=order, updated_at=now()))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def econ_world(fw):
    """fw + the econ extras: item market columns, items 501 / 502 «arms» (price 100 / 50), 503 off-market scroll,
    the five seeded templates. Region 10 is NOT simulated until :func:`simulate_region` is called."""
    for ddl in ECON_ITEM_DDL:
        exec_(fw, ddl)
    exec_(fw, "UPDATE items SET price = 100, item_rarity = 'common' WHERE id = :i", i=ITEM_SWORD)
    exec_(fw, "UPDATE items SET price = 50, item_rarity = 'common' WHERE id = :i", i=ITEM_SHIELD)
    exec_(fw, "INSERT INTO items (id, name, item_type, price, item_rarity) VALUES (:i, 'Свиток Зари', 'scroll', 40, "
              "'common')", i=ITEM_SCROLL)
    exec_(fw, "INSERT INTO econ_goods_groups (code, name, base_price, norm_per_1000, norm_days) "
              "VALUES (:g, 'Оружие', 100, 1, 1)", g=GROUP_ARMS)
    for item in (ITEM_SWORD, ITEM_SHIELD):
        exec_(fw, "INSERT INTO econ_item_groups (item_id, group_code, off_market, updated_at) VALUES (:i, :g, 0, :n)",
              i=item, g=GROUP_ARMS, n=now())
    exec_(fw, "INSERT INTO econ_item_groups (item_id, group_code, off_market, updated_at) VALUES (:i, NULL, 1, :n)",
          i=ITEM_SCROLL, n=now())
    seed_templates(fw)
    return fw


def simulate_region(f, region_id=R_OST, *, population=1000, last_income=0, stock=1000, price_mult=1):
    """A participating region with an «arms» market row."""
    exec_(f, "INSERT INTO econ_regions (region_id, template_code, population, last_income) VALUES (:r, 'x', :p, :li)",
          r=region_id, p=population, li=last_income)
    exec_(f, "INSERT INTO econ_region_goods (region_id, group_code, stock, price_mult) VALUES (:r, :g, :s, :m)",
          r=region_id, g=GROUP_ARMS, s=stock, m=price_mult)


def world_sum(f) -> int:
    """sum(characters) + sum(accounts) — the ledger's world invariant (must stay 0)."""
    return int(q(f, "SELECT (SELECT COALESCE(SUM(currency_balance), 0) FROM characters) + "
                    "(SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character')"))


def fund(f, ref, amount, key=None):
    """Emission into any account / character (test seed money; keeps the world sum at 0)."""
    db = f()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION,
                                   legs=[core.Leg(core.AccountRef.emission(), ref, int(amount))],
                                   source_service="test", comment="seed", apply_tax=False, idempotency_key=key)
        db.commit()
    finally:
        db.close()


def drain(f, ref, amount):
    """Admin adjustment out of an account (to empty a treasury)."""
    db = f()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_ADJUST,
                                   legs=[core.Leg(ref, core.AccountRef.adjustment(), int(amount))],
                                   source_service="test", comment="drain", apply_tax=False)
        db.commit()
    finally:
        db.close()


def balance(f, ref) -> int:
    if ref.is_character:
        return int(q(f, "SELECT currency_balance FROM characters WHERE id = :c", c=ref.ref_id) or 0)
    return int(q(f, "SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=ref.kind,
                 r=ref.ref_id) or 0)


def treasury(f, fid) -> int:
    return balance(f, core.AccountRef.faction(fid))


def cash(f, cid) -> int:
    return balance(f, core.AccountRef.character(cid))


def econ_faction(f, fid, template="order", *, members=100, overrides=None, enabled=True, members_min=10,
                 members_max=5000):
    """The faction's economy row (inserted or replaced)."""
    exec_(f, "DELETE FROM faction_economy WHERE faction_id = :fid", fid=fid)
    db = f()
    try:
        db.add(models.FactionEconomy(faction_id=fid, template_code=template, overrides=overrides,
                                     econ_enabled=enabled, members_count=members, members_min=members_min,
                                     members_max=members_max, updated_at=now()))
        db.commit()
    finally:
        db.close()


ECON_KEYS = ("members_count", "members_carry", "last_run_id", "last_dues", "last_profile", "last_wages_due",
             "last_wages_paid", "last_restock", "last_debts_paid", "last_members_delta", "last_wealth", "payout_seq")


def econ_row(f, fid) -> dict:
    r = rows(f, f"SELECT {', '.join(ECON_KEYS)} FROM faction_economy WHERE faction_id = :fid", fid=fid)
    return dict(zip(ECON_KEYS, r[0])) if r else None


def qm_item(f, fid, item_id=ITEM_SWORD, *, price=50, stock=3, target=0, min_rank=None, active=True, sort=0) -> int:
    db = f()
    try:
        row = models.FactionQmItem(faction_id=fid, item_id=item_id, price=price, min_rank_id=min_rank, stock=stock,
                                   restock_target=target, is_active=active, sort_order=sort, updated_at=now())
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def bind_qm(f, fid, npc_id=QM_NPC, role="quartermaster"):
    exec_(f, "UPDATE characters SET npc_role = :r WHERE id = :n", r=role, n=npc_id)
    exec_(f, "INSERT INTO faction_quartermasters (npc_id, faction_id, created_at) VALUES (:n, :fid, :t)",
          n=npc_id, fid=fid, t=now())


DEBT_KEYS = ("id", "character_id", "faction_id", "source", "source_key", "amount", "paid", "status",
             "unpaid_notified")


def debts(f, character_id=None, faction_id=None):
    sql = f"SELECT {', '.join(DEBT_KEYS)} FROM faction_debts WHERE 1 = 1"
    params = {}
    if character_id is not None:
        sql += " AND character_id = :c"
        params["c"] = character_id
    if faction_id is not None:
        sql += " AND faction_id = :fid"
        params["fid"] = faction_id
    return [dict(zip(DEBT_KEYS, r)) for r in rows(f, sql + " ORDER BY id", **params)]


def ops(f, op_type=None):
    sql = "SELECT op_type, idempotency_key FROM econ_operations"
    params = {}
    if op_type is not None:
        sql += " WHERE op_type = :t"
        params["t"] = op_type
    return rows(f, sql + " ORDER BY id", **params)


def notice_texts(f):
    return [n["message"] for n in notices(f)]


@pytest.fixture
def gate_open(monkeypatch):
    """The FEAT-145 dialogue gate (locations-service HTTP) answers ``gate.answer`` (default open)."""
    import locations_client
    calls = []

    async def gate(*args):
        calls.append(args)
        return gate.answer

    gate.answer = True
    gate.calls = calls
    monkeypatch.setattr(locations_client, "check_npc_gate", gate)
    return gate


# ============================================================================================= FEAT-207 territory
#
# Closed territories / eject / kill points need tables of other services on top of :func:`fw`:
# ``LocationNeighbors`` (eject neighbour pick), ``battle_participants`` + ``dungeon_sessions`` (the eject busy check),
# ``users`` (teleport master), ``dungeons`` (admin rule target). :func:`tw` adds them plus
#     locations 120 «Цитадель» @10 (neighbours 100 «Рынок» and 110 «Нива»), 121 «Караульня» @10 = region 10 station;
#     the mob NPC 60 «Волк» @100 (npc_role 'mob'), mob templates 900 «Волк» / 901 «Медведь», dungeon 77 «Склеп»;
# and replaces ``main._prepare_move`` (locations-service HTTP) by :class:`PrepareMoveFake` (``factory.moves``).

L_CITADEL, L_STATION = 120, 121
WOLF = 60
MOB_WOLF_T, MOB_BEAR_T = 900, 901
DUNGEON_CRYPT = 77

TERRITORY_DDL = (
    "CREATE TABLE IF NOT EXISTS LocationNeighbors (id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER NOT NULL, "
    "neighbor_id INTEGER NOT NULL, energy_cost INTEGER DEFAULT 0, path_data TEXT NULL, "
    "is_auto_arrow INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS battle_participants (id INTEGER PRIMARY KEY AUTOINCREMENT, battle_id INTEGER, "
    "character_id INTEGER, dropped_out_at DATETIME)",
    "CREATE TABLE IF NOT EXISTS dungeon_sessions (id INTEGER PRIMARY KEY, status VARCHAR(20))",
    "CREATE TABLE IF NOT EXISTS dungeon_session_members (id INTEGER PRIMARY KEY, session_id INTEGER, "
    "character_id INTEGER)",
    "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username VARCHAR(80), current_character INTEGER)",
    "CREATE TABLE IF NOT EXISTS dungeons (id INTEGER PRIMARY KEY, name VARCHAR(100))",
)


class PrepareMoveFake:
    """``main._prepare_move`` stand-in: records (character, from, reason); raises ``error`` when set."""

    def __init__(self):
        self.calls = []
        self.error = None

    async def __call__(self, db, character_id, from_location_id, reason):
        self.calls.append((int(character_id), from_location_id, reason))
        if self.error is not None:
            raise self.error
        return False


@pytest.fixture
def tw(fw, monkeypatch):
    """fw + the FEAT-207 territory extras (see the block comment above)."""
    for ddl in TERRITORY_DDL:
        exec_(fw, ddl)
    exec_(fw, "INSERT INTO Locations (id, name, region_id) VALUES (120, 'Цитадель', 10), (121, 'Караульня', 10)")
    exec_(fw, "UPDATE Regions SET jail_location_id = 121 WHERE id = 10")
    for a, b in ((L_CITADEL, L_MARKET), (L_CITADEL, L_NIVA)):
        for x, y in ((a, b), (b, a)):
            exec_(fw, "INSERT INTO LocationNeighbors (location_id, neighbor_id) VALUES (:a, :b)", a=x, b=y)
    exec_(fw, "INSERT INTO dungeons (id, name) VALUES (77, 'Склеп')")
    db = fw()
    try:
        for tid, name in ((MOB_WOLF_T, "Волк"), (MOB_BEAR_T, "Медведь")):
            db.add(models.MobTemplate(id=tid, name=name, tier="normal", level=1, id_race=1, id_subrace=1, id_class=1,
                                      xp_reward=0, gold_reward=0, respawn_enabled=False))
        with econ_ledger.allow_direct_balance_write(db):
            db.add(models.Character(id=WOLF, name="Волк", user_id=None, id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", is_npc=True, npc_role="mob", npc_status="alive",
                                    current_location_id=L_MARKET, level=2, currency_balance=0))
            db.flush()
        db.commit()
    finally:
        db.close()
    moves = PrepareMoveFake()
    monkeypatch.setattr(main, "_prepare_move", moves)
    fw.moves = moves
    return fw


def access_rule(f, faction_id, target, kind="location", rank=None):
    exec_(f, "INSERT INTO faction_access_rules (kind, target_id, faction_id, min_rank_id, created_at, updated_at) "
             "VALUES (:k, :t, :fid, :r, :n, :n)", k=kind, t=target, fid=faction_id, r=rank, n=now())


def place(f, character_id, location_id):
    exec_(f, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=location_id, c=character_id)


def location_of(f, character_id):
    return int(q(f, "SELECT current_location_id FROM characters WHERE id = :c", c=character_id))


def enemy(f, faction_id, kind, ref_id, points):
    exec_(f, "INSERT INTO faction_enemies (faction_id, kind, ref_id, points) VALUES (:fid, :k, :r, :p)",
          fid=faction_id, k=kind, r=ref_id, p=points)


def outlaw(f, faction_id, region_id, level_code="criminal"):
    exec_(f, "INSERT INTO faction_outlaw_regions (faction_id, region_id, level_code) VALUES (:fid, :r, :l)",
          fid=faction_id, r=region_id, l=level_code)


# FEAT-207 item donations: the bag (``character_inventory``, plain-stack columns) and quest objectives (quest items)
ITEM_DONATION_DDL = (
    "CREATE TABLE IF NOT EXISTS character_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "character_id INTEGER NOT NULL, item_id INTEGER NOT NULL, quantity INTEGER DEFAULT 1, "
    "enhancement_points_spent INTEGER DEFAULT 0, socketed_gems TEXT NULL, current_durability INTEGER NULL)",
    "CREATE TABLE IF NOT EXISTS quest_objectives (id INTEGER PRIMARY KEY, quest_id INTEGER NOT NULL DEFAULT 1, "
    "objective_type VARCHAR(32) NOT NULL, target_id INTEGER NULL)",
)


def give_item(f, character_id, item_id, quantity, **extra):
    cols = ", ".join(["character_id", "item_id", "quantity", *extra])
    vals = ", ".join([":c", ":i", ":n", *(f":{k}" for k in extra)])
    exec_(f, f"INSERT INTO character_inventory ({cols}) VALUES ({vals})", c=character_id, i=item_id, n=quantity,
          **extra)


def bag(f, character_id, item_id):
    return int(q(f, "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory WHERE character_id = :c "
                    "AND item_id = :i", c=character_id, i=item_id))


def item_stock(f, faction_id, item_id):
    return int(q(f, "SELECT COALESCE(SUM(quantity), 0) FROM faction_item_stock WHERE faction_id = :fid "
                    "AND item_id = :i", fid=faction_id, i=item_id))
