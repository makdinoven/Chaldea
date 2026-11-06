"""FEAT-197 QA: shared SQLite world for the reputation tests (not a test module).

World:
    country 1 «Мидденгерд»: regions 10 «Ост», 11 «Пашни», 12 «Холмы»; country 2 «Пустошь»: region 20 «Дюны»
    locations 100 @10, 110 @11, 200 @20, 300 (no region)
    players: 1 «Альфа» (user 7) @100, 2 «Бета» (user 8) @100, 3 «Гамма» (user 9) @200
    NPCs @100: 50 merchant, 51 bandit, 52 guard, 53 no role, 54 guard with kill override -5, 56 scribe (role
               without a weight row); 55 merchant @300 (no region)
    reputation_settings row id=1 with the defaults (tiers / actions / role weights are NOT seeded: the code falls
    back to the reputation_core defaults, exactly like a fresh database)

Every test using :func:`rep_world` gets ``reputation_notify._send`` replaced by a recorder, so nothing is ever
published to the dev RabbitMQ.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_ledger
import models
import reputation_crud
import reputation_notify

ALPHA, BETA, GAMMA = 1, 2, 3
USER_ALPHA, USER_BETA, USER_GAMMA = 7, 8, 9
MERCHANT, BANDIT, GUARD, NO_ROLE, OVERRIDE, NOWHERE, SCRIBE = 50, 51, 52, 53, 54, 55, 56
R_OST, R_PASHNI, R_HOLMY, R_DUNY = 10, 11, 12, 20

PEOPLE = [  # id, name, user, npc, role, status, location, kill override
    (ALPHA, "Альфа", USER_ALPHA, False, None, "alive", 100, None),
    (BETA, "Бета", USER_BETA, False, None, "alive", 100, None),
    (GAMMA, "Гамма", USER_GAMMA, False, None, "alive", 200, None),
    (MERCHANT, "Лавочник", None, True, "merchant", "alive", 100, None),
    (BANDIT, "Разбойник", None, True, "bandit", "alive", 100, None),
    (GUARD, "Стражник", None, True, "guard", "alive", 100, None),
    (NO_ROLE, "Безымянный", None, True, None, "alive", 100, None),
    (OVERRIDE, "Капитан стражи", None, True, "guard", "alive", 100, -5),
    (NOWHERE, "Странник", None, True, "merchant", "alive", 300, None),
    (SCRIBE, "Писарь", None, True, "scribe", "alive", 100, None),
]


# FEAT-199: the foreign tables the witness roll reads by raw SQL (attributes / battles / inventory / skills).
# Readers fail loudly, so every world that can kill an NPC must have them (memory: «фикстура не той схемы»).
SHADOW_DDL = (
    "CREATE TABLE IF NOT EXISTS character_attributes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "character_id INTEGER NOT NULL, agility INTEGER DEFAULT 0, luck INTEGER DEFAULT 0, stealth INTEGER DEFAULT 0, "
    "current_health INTEGER DEFAULT 100, max_health INTEGER DEFAULT 100, current_mana INTEGER DEFAULT 50, "
    "max_mana INTEGER DEFAULT 50, current_energy INTEGER DEFAULT 50, max_energy INTEGER DEFAULT 50, "
    "current_stamina INTEGER DEFAULT 50, max_stamina INTEGER DEFAULT 50)",
    "CREATE TABLE IF NOT EXISTS battles (id INTEGER PRIMARY KEY, status VARCHAR(20), law_encounter_id INTEGER NULL)",
    "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name VARCHAR(100), item_type VARCHAR(30), "
    "is_mask INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS equipment_slots (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, "
    "slot_type VARCHAR(30), item_id INTEGER NULL)",
    "CREATE TABLE IF NOT EXISTS tree_nodes (id INTEGER PRIMARY KEY, node_type VARCHAR(30), subclass_key VARCHAR(40), "
    "name VARCHAR(100) NULL)",
    "CREATE TABLE IF NOT EXISTS character_tree_progress (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "character_id INTEGER, node_id INTEGER)",
)


def build(factory):
    db = factory()
    try:
        for ddl in SHADOW_DDL:
            db.execute(text(ddl))
        # FEAT-199: Locations.marker_type (locations-service; not in the portable hierarchy DDL)
        db.execute(text("ALTER TABLE Locations ADD COLUMN marker_type VARCHAR(16) NOT NULL DEFAULT 'safe'"))
        db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд'), (2, 'Пустошь')"))
        db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Ост', 1), (11, 'Пашни', 1), "
                        "(12, 'Холмы', 1), (20, 'Дюны', 2)"))
        db.execute(text("INSERT INTO Locations (id, name, region_id) VALUES (100, 'Рынок', 10), "
                        "(110, 'Нива', 11), (200, 'Оазис', 20), (300, 'Пустошь', NULL)"))
        with econ_ledger.allow_direct_balance_write(db):
            for cid, name, user, npc, role, status, loc, kill in PEOPLE:
                db.add(models.Character(id=cid, name=name, user_id=user, id_subrace=1, id_class=1, id_race=1,
                                        appearance="-", avatar="-", is_npc=npc, npc_role=role, npc_status=status,
                                        current_location_id=loc, level=2, currency_balance=0,
                                        reputation_kill_points=kill))
            db.flush()
        db.add(models.ReputationSettings(id=1, min_value=-1000, max_value=1000, echo_pct=20, decay_per_day=10,
                                         updated_at=datetime.utcnow()))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def rep_world(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    build(factory)
    sent = MagicMock(name="reputation_notify._send")
    monkeypatch.setattr(reputation_notify, "_send", sent)
    factory.sent = sent
    factory.engine = eng
    yield factory
    eng.dispose()


class _ZeroRng:
    """``random()`` = 0.0: the witness roll 0.00 is below any chance (min 5 %) -> always witnessed."""

    def random(self):
        return 0.0


@pytest.fixture
def force_witnessed(monkeypatch):
    """FEAT-199: FEAT-197/198 kill tests assume immediate reputation + wanted -> force «witnessed» through the
    ``law_crud.rng`` seam (the witness readers still run against the world's tables)."""
    import law_crud
    monkeypatch.setattr(law_crud, "rng", lambda: _ZeroRng())


# --------------------------------------------------------------------------------------------- helpers

def q(f, sql, **params):
    db = f()
    try:
        return db.execute(text(sql), params).scalar()
    finally:
        db.close()


def rows(f, sql, **params):
    db = f()
    try:
        return [tuple(r) for r in db.execute(text(sql), params).fetchall()]
    finally:
        db.close()


def exec_(f, sql, **params):
    db = f()
    try:
        db.execute(text(sql), params)
        db.commit()
    finally:
        db.close()


def value(f, character_id, region_id):
    v = q(f, "SELECT value FROM character_reputation WHERE character_id = :c AND region_id = :r",
          c=character_id, r=region_id)
    return None if v is None else int(v)


def values(f, character_id):
    return {int(r): int(v) for r, v in rows(
        f, "SELECT region_id, value FROM character_reputation WHERE character_id = :c", c=character_id)}


def log_rows(f, character_id=None):
    sql = ("SELECT character_id, region_id, action, event_key, is_echo, origin_region_id, requested_delta, "
           "applied_delta, value_after, tier_before, tier_after, reason, actor_user_id FROM reputation_log")
    params = {}
    if character_id is not None:
        sql += " WHERE character_id = :c"
        params["c"] = character_id
    return rows(f, sql + " ORDER BY id", **params)


def apply(f, **kwargs):
    """apply_reputation in its own committed transaction."""
    db = f()
    try:
        result = reputation_crud.apply_reputation(db, **kwargs)
        db.commit()
        return result
    finally:
        db.close()


def set_value(f, character_id, region_id, val, decay_at=None):
    """Seed a reputation row directly (fixture shortcut, bypasses the journal on purpose)."""
    now = datetime.utcnow().replace(microsecond=0)
    if q(f, "SELECT COUNT(*) FROM character_reputation WHERE character_id = :c AND region_id = :r",
         c=character_id, r=region_id):
        exec_(f, "UPDATE character_reputation SET value = :v, decay_at = :d WHERE character_id = :c "
                 "AND region_id = :r", v=val, d=decay_at, c=character_id, r=region_id)
    else:
        exec_(f, "INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
                 "VALUES (:c, :r, :v, :d, :u)", c=character_id, r=region_id, v=val, d=decay_at, u=now)


def days_ago(days):
    return datetime.utcnow().replace(microsecond=0) - timedelta(days=days)


def sent_payloads(f):
    """Every payload handed to the (mocked) RabbitMQ sender."""
    out = []
    for call in f.sent.call_args_list:
        out.extend(call.args[0])
    return out
