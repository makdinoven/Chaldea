"""FEAT-198 QA: shared SQLite world for the law tests (not a test module).

Built on top of :mod:`tests.reputation_world` (same characters / regions), plus:

    locations: 101 «Застава» @10 (guard 60), 102 «Темница» @10 (jail of region 10), 103 «Тракт» @10 (no guard),
               111 «Хутор» @11 (guard 61; region 11 has NO jail)
    NPCs:      60 guard @101, 61 guard @111, 62 banker @200 (region 20), 63 banker @100
    note:      reputation_world already has guards 52 / 54 (kill override -5) @100
    tables owned by other services (raw SQL): character_attributes, battles, battle_participants,
               dungeon_sessions, dungeon_session_members, users
    law_settings row id=1 + the 5 levels exactly as migration 039 seeds them

Every external side effect is mocked:
    * RabbitMQ — ``law_notify._send`` (conftest autouse stub) and ``reputation_notify._send`` (rep_world);
    * the forced-move HTTP side effects — ``main._prepare_move`` (AsyncMock, returns False = no gathering);
    * battle-service — ``battle_client.create_guard_battle`` / ``get_battle_result`` are patched per test.
"""

import importlib.util
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import auth_http
import econ_ledger
import law_api
import law_crud
import law_notify
import main
import models
import reputation_api
import shadow_api
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.reputation_world import (  # noqa: F401
    ALPHA, BANDIT, BETA, GAMMA, GUARD, MERCHANT, NO_ROLE, NOWHERE, OVERRIDE, R_DUNY, R_HOLMY, R_OST, R_PASHNI,
    SCRIBE, USER_ALPHA, USER_BETA, USER_GAMMA, exec_, force_witnessed, q, rep_world, rows, set_value,
)

L_MARKET, L_POST, L_JAIL, L_ROAD, L_FARM, L_OASIS, L_NIVA = 100, 101, 102, 103, 111, 200, 110
GUARD_POST, GUARD_FARM, BANKER_DUNY, BANKER_MARKET = 60, 61, 62, 63
TOKEN = "test-internal-token"
INTERNAL = {"X-Internal-Token": TOKEN}

_EXTRA_DDL = (
    "CREATE TABLE IF NOT EXISTS character_attributes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "character_id INTEGER NOT NULL, agility INTEGER DEFAULT 0, luck INTEGER DEFAULT 0, "
    "current_health INTEGER DEFAULT 100, max_health INTEGER DEFAULT 100, current_mana INTEGER DEFAULT 50, "
    "max_mana INTEGER DEFAULT 50, current_energy INTEGER DEFAULT 50, max_energy INTEGER DEFAULT 50, "
    "current_stamina INTEGER DEFAULT 50, max_stamina INTEGER DEFAULT 50)",
    "CREATE TABLE IF NOT EXISTS battles (id INTEGER PRIMARY KEY, status VARCHAR(20), law_encounter_id INTEGER NULL)",
    "CREATE TABLE IF NOT EXISTS battle_participants (id INTEGER PRIMARY KEY AUTOINCREMENT, battle_id INTEGER, "
    "character_id INTEGER, dropped_out_at DATETIME)",
    "CREATE TABLE IF NOT EXISTS dungeon_sessions (id INTEGER PRIMARY KEY, status VARCHAR(20))",
    "CREATE TABLE IF NOT EXISTS dungeon_session_members (id INTEGER PRIMARY KEY, session_id INTEGER, "
    "character_id INTEGER)",
    "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username VARCHAR(80), current_character INTEGER)",
)

_MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "039_law.py")


def load_migration():
    """The 039_law migration module (its file name starts with a digit, so it is loaded by path)."""
    spec = importlib.util.spec_from_file_location("migration_039_law", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.utcnow().replace(microsecond=0)


def _build_law(factory):
    mig = load_migration()
    db = factory()
    try:
        for ddl in _EXTRA_DDL:
            db.execute(text(ddl))
        db.execute(text("INSERT INTO Locations (id, name, region_id) VALUES (101, 'Застава', 10), "
                        "(102, 'Темница', 10), (103, 'Тракт', 10), (111, 'Хутор', 11)"))
        db.execute(text("UPDATE Regions SET jail_location_id = 102 WHERE id = 10"))
        with econ_ledger.allow_direct_balance_write(db):
            for cid, name, role, loc in ((GUARD_POST, "Стражник Орм", "guard", L_POST),
                                         (GUARD_FARM, "Стражник Хутора", "guard", L_FARM),
                                         (BANKER_DUNY, "Банкир Дюн", "banker", L_OASIS),
                                         (BANKER_MARKET, "Банкир Рынка", "banker", L_MARKET)):
                db.add(models.Character(id=cid, name=name, user_id=None, id_subrace=1, id_class=1, id_race=1,
                                        appearance="-", avatar="ava-%d" % cid, is_npc=True, npc_role=role,
                                        npc_status="alive", current_location_id=loc, level=5,
                                        currency_balance=0))
            db.flush()
        for cid in (ALPHA, BETA, GAMMA, GUARD, OVERRIDE, GUARD_POST, GUARD_FARM):
            db.execute(text("INSERT INTO character_attributes (character_id, agility, luck) VALUES (:c, 0, 0)"),
                       {"c": cid})
        for uid in (USER_ALPHA, USER_BETA, USER_GAMMA):
            db.execute(text("INSERT INTO users (id, username) VALUES (:u, :n)"), {"u": uid, "n": f"user{uid}"})
        db.execute(text("INSERT INTO users (id, username) VALUES (1, 'admin'), (2, 'moder')"))
        db.add(models.LawSettings(id=1, updated_at=now()))
        for code, order, name, min_value, fine, hours in mig.LEVELS:
            db.add(models.LawLevel(code=code, sort_order=order, name=name, min_value=min_value, fine=fine,
                                   jail_hours=hours))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def law_world(rep_world, monkeypatch):
    """rep_world + the law extras; ``main._prepare_move`` mocked (``factory.prepare_move``)."""
    _build_law(rep_world)
    prepare = AsyncMock(return_value=False)
    monkeypatch.setattr(main, "_prepare_move", prepare)
    rep_world.prepare_move = prepare
    return rep_world


@pytest.fixture
def api(law_world, monkeypatch):
    def override_get_db():
        session = law_world()
        try:
            yield session
        finally:
            session.close()

    for dep in (law_api.get_db, main.get_db, reputation_api.get_db, shadow_api.get_db):
        app.dependency_overrides[dep] = override_get_db
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    yield TestClient(app, raise_server_exceptions=False)
    for dep in (law_api.get_db, main.get_db, reputation_api.get_db, shadow_api.get_db, get_current_user_via_http):
        app.dependency_overrides.pop(dep, None)


# --------------------------------------------------------------------------------------------- auth helpers

def as_user(user_id=USER_ALPHA, role="user", permissions=()):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username=f"u{user_id}", role=role, permissions=list(permissions))


def as_admin():
    as_user(1, "admin", ["reputation:read", "reputation:manage", "reputation:settings", "characters:read"])


def as_moderator():
    as_user(2, "moderator", ["reputation:read", "reputation:manage", "characters:read"])


def rid():
    return str(uuid.uuid4())


# --------------------------------------------------------------------------------------------- data helpers

def set_wanted(f, character_id, region_id, val, decay_at=None):
    exec_(f, "DELETE FROM character_wanted WHERE character_id = :c AND region_id = :r", c=character_id, r=region_id)
    exec_(f, "INSERT INTO character_wanted (character_id, region_id, value, decay_at, updated_at) "
             "VALUES (:c, :r, :v, :d, :u)", c=character_id, r=region_id, v=val,
          d=decay_at if decay_at is not None else (now() if val else None), u=now())


def wanted(f, character_id, region_id):
    v = q(f, "SELECT value FROM character_wanted WHERE character_id = :c AND region_id = :r",
          c=character_id, r=region_id)
    return None if v is None else int(v)


def set_gold(f, character_id, amount):
    exec_(f, "UPDATE characters SET currency_balance = :a WHERE id = :c", a=amount, c=character_id)


def gold(f, character_id):
    return int(q(f, "SELECT currency_balance FROM characters WHERE id = :c", c=character_id) or 0)


def treasury(f, kind, ref_id):
    v = q(f, "SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=kind, r=ref_id)
    return int(v or 0)


def char_row(f, character_id):
    db = f()
    try:
        return db.query(models.Character).filter(models.Character.id == character_id).first()
    finally:
        db.close()


def make_encounter(f, character_id=ALPHA, location_id=L_POST, from_location_id=L_MARKET, source="move"):
    """Move the character into ``location_id`` through law_crud.evaluate_entry (the real creation path)."""
    db = f()
    try:
        character = db.query(models.Character).filter(models.Character.id == character_id).first()
        character.current_location_id = location_id
        enc = law_crud.evaluate_entry(db, character, location_id, source, from_location_id=from_location_id)
        db.commit()
        return int(enc.id) if enc is not None else None
    finally:
        db.close()


def encounter(f, encounter_id):
    db = f()
    try:
        return db.query(models.LawEncounter).filter(models.LawEncounter.id == encounter_id).first()
    finally:
        db.close()


def jail_character(f, character_id=ALPHA, hours=12, region_id=R_OST, location_id=L_JAIL, fine=150, bail=300,
                   next_escape_at=None, attempts=0):
    """Seed a serving term directly (the jail path itself is tested through the choices)."""
    until = now() + timedelta(hours=hours)
    db = f()
    try:
        term = models.LawJailTerm(character_id=character_id, region_id=region_id, location_id=location_id,
                                  encounter_id=None, level_code="offender", fine_base=fine, bail_price=bail,
                                  started_at=now(), until=until, status="serving", escape_attempts=attempts,
                                  next_escape_at=next_escape_at, notified=False)
        db.add(term)
        c = db.query(models.Character).filter(models.Character.id == character_id).first()
        c.jailed_until = until
        c.jail_region_id = region_id
        c.current_location_id = location_id
        db.commit()
        return int(term.id)
    finally:
        db.close()


def log_actions(f, character_id):
    return [r[0] for r in rows(f, "SELECT action FROM law_log WHERE character_id = :c ORDER BY id", c=character_id)]


def law_payloads(stub):
    out = []
    for call in stub.call_args_list:
        out.extend(call.args[0])
    return out


class FixedRng:
    """A deterministic ``random()`` for the flee / escape rolls."""

    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value
