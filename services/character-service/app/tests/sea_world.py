"""FEAT-213 QA: shared SQLite world for the sea tests (not a test module).

Built on :mod:`tests.law_world` (rep_world + law extras: players 1 «Альфа» (user 7), 2 «Бета» (user 8), 3 «Гамма»
(user 9); regions 10 «Ост» / 11 «Пашни» of country 1, region 20 «Дюны» of country 2; guards; law settings), plus the
locations-service stand-ins the sea code reads by raw SQL:

    Locations   + is_port, is_sea_zone, port_sea_zone_id, image_url, is_starting   (LS 060 / older columns)
    Countries   + is_hidden
    LocationNeighbors, arrow_neighbors, posts, gathering_sessions

Sea geography (hidden country 3 «Моря»; seas = regions 30 «Море Эйдонэи», 31 «Внутреннее море»):

    zones  501 «Пролив Ветров», 502 «Северный залив», 503 «Тихая бухта», 505 «Обходной пролив» @30; 504 «Глубь» @31
    edges  501-502, 502-503, 501-505, 505-503, 503-504 (both ways)  ->  BFS 501→503 = [501, 502, 503] (ascending ids)
    ports  103 «Тракт» (region 10, no guard) -> zone 501; 200 «Оазис» (region 20) -> 503; 110 «Нива» (region 11) -> 504
    decks  600 «Палуба Морской девы», 601 «Палуба Чайки», 602 «Палуба без корабля» @30 (hidden country)
    start  300 «Пустошь» is_starting = 1

Captains: 70 «Капитан Дрейк» @103 (ship 1), 71 «Капитан Чайки» @200 (free unless a test binds him).
Ship 1 «Морская дева» (created through ``sea_admin.create_ship``): deck 600, Captain 70, stops 103 → 200 → 110
(there-and-back), capacity 2, crew 1, boarding 30 min, zone 10 min, fare 10 + 5 per zone; docked at 103.
Legs: trip 1 103→200 = 3 zones (fare 25), trip 2 200→110 = [503, 504] (fare to 110 = 10 + 5×5 = 35).
Players 1 and 2 stand in the port 103 with 1000 each.

Every external side effect is mocked: the dialogue gate (``locations_client.check_npc_gate``), the LS cleanup after
a put ashore (``notify_character_left_location_sync`` / ``cancel_gathering``), RabbitMQ (conftest ``law_notify._send``
+ rep_world ``reputation_notify._send``).
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

import economy_api
import econ_ledger
import locations_client
import models
import sea_admin
import sea_crud
import sea_pass
from main import app
from tests.law_world import (  # noqa: F401  (fixtures + helpers re-exported)
    ALPHA, BETA, GAMMA, INTERNAL, USER_ALPHA, USER_BETA, USER_GAMMA, api, as_user, exec_, gold, law_world, q,
    rep_world, rows, set_gold, treasury,
)

SEAS_COUNTRY = 3
SEA_EIDO, SEA_INNER = 30, 31
Z1, Z2, Z3, Z4, Z5 = 501, 502, 503, 504, 505
P_A, P_B, P_C = 103, 200, 110          # ports: «Тракт» (region 10), «Оазис» (region 20), «Нива» (region 11)
R_A, R_B, R_C = 10, 20, 11
C_A, C_B = 1, 2                        # countries of the ports' regions (A, C -> 1; B -> 2)
DECK, DECK2, DECK_FREE = 600, 601, 602
START = 300
CAPTAIN, CAPTAIN2 = 70, 71
LAND = 100                             # «Рынок» (region 10, not a port)

_DDL = (
    "ALTER TABLE Locations ADD COLUMN is_port INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE Locations ADD COLUMN is_sea_zone INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE Locations ADD COLUMN port_sea_zone_id INTEGER NULL",
    "ALTER TABLE Locations ADD COLUMN image_url VARCHAR(255) NULL",
    "ALTER TABLE Locations ADD COLUMN is_starting INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE Countries ADD COLUMN is_hidden INTEGER NOT NULL DEFAULT 0",
    "CREATE TABLE IF NOT EXISTS LocationNeighbors (id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER NOT NULL, "
    "neighbor_id INTEGER NOT NULL, energy_cost INTEGER NOT NULL DEFAULT 1)",
    "CREATE TABLE IF NOT EXISTS arrow_neighbors (id INTEGER PRIMARY KEY AUTOINCREMENT, arrow_id INTEGER, "
    "location_id INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, "
    "location_id INTEGER, content TEXT)",
    "CREATE TABLE IF NOT EXISTS gathering_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, "
    "status VARCHAR(20))",
)

ZONE_EDGES = ((Z1, Z2), (Z2, Z3), (Z1, Z5), (Z5, Z3), (Z3, Z4))


def now():
    return datetime.utcnow().replace(microsecond=0)


def _build(f):
    exec_many(f, list(_DDL))
    exec_many(f, [
        "INSERT INTO Countries (id, name, is_hidden) VALUES (3, 'Моря', 1)",
        "INSERT INTO Regions (id, name, country_id) VALUES (30, 'Море Эйдонэи', 3), (31, 'Внутреннее море', 3)",
        "INSERT INTO Locations (id, name, region_id, is_sea_zone) VALUES (501, 'Пролив Ветров', 30, 1), "
        "(502, 'Северный залив', 30, 1), (503, 'Тихая бухта', 30, 1), (504, 'Глубь', 31, 1), "
        "(505, 'Обходной пролив', 30, 1)",
        "INSERT INTO Locations (id, name, region_id, image_url) VALUES (600, 'Палуба Морской девы', 30, 'deck.png'), "
        "(601, 'Палуба Чайки', 30, NULL), (602, 'Палуба без корабля', 30, NULL)",
        "UPDATE Locations SET is_port = 1, port_sea_zone_id = 501 WHERE id = 103",
        "UPDATE Locations SET is_port = 1, port_sea_zone_id = 503 WHERE id = 200",
        "UPDATE Locations SET is_port = 1, port_sea_zone_id = 504 WHERE id = 110",
        "UPDATE Locations SET is_starting = 1 WHERE id = 300",
    ])
    for a, b in ZONE_EDGES:
        exec_(f, "INSERT INTO LocationNeighbors (location_id, neighbor_id) VALUES (:a, :b), (:b, :a)", a=a, b=b)
    db = f()
    try:
        with econ_ledger.allow_direct_balance_write(db):
            for cid, name, loc in ((CAPTAIN, "Капитан Дрейк", P_A), (CAPTAIN2, "Капитан Чайки", P_B)):
                db.add(models.Character(id=cid, name=name, user_id=None, id_subrace=1, id_class=1, id_race=1,
                                        appearance="-", avatar=f"cap-{cid}", is_npc=True, npc_role="captain",
                                        npc_status="alive", current_location_id=loc, level=5, currency_balance=0))
        db.add(models.SeaSetting(id=1))          # seeded by migration 052
        db.commit()
    finally:
        db.close()
    for cid in (ALPHA, BETA):
        exec_(f, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=P_A, c=cid)
        set_gold(f, cid, 1000)


def exec_many(f, statements):
    db = f()
    try:
        for sql in statements:
            db.execute(text(sql))
        db.commit()
    finally:
        db.close()


def make_ship(f, *, name="Морская дева", deck=DECK, captain=CAPTAIN, stops=(P_A, P_B, P_C), when=None, **kwargs):
    """Create a ship through the real admin crud (validations + Captain placement); returns its id."""
    body = dict(name=name, deck_location_id=deck, captain_npc_id=captain, capacity=2, crew_slots=1,
                boarding_minutes=30, zone_minutes=10, fare_base=10, fare_per_zone=5,
                stops=[s if isinstance(s, dict) else {"port_location_id": s} for s in stops])
    body.update(kwargs)
    db = f()
    try:
        ship = sea_admin.create_ship(db, sea_admin.ShipCreate(**body), now=when or now())
        db.commit()
        return int(ship.id)
    finally:
        db.close()


@pytest.fixture
def sea(law_world, monkeypatch):
    """law_world + the sea geography + ship 1; LS side effects mocked (``sea.gate`` / ``sea.left`` / ``sea.cancel``)."""
    f = law_world
    _build(f)
    econ_ledger.invalidate_settings_cache()
    f.gate = AsyncMock(return_value=True)
    monkeypatch.setattr(locations_client, "check_npc_gate", f.gate)
    f.left = MagicMock(name="notify_character_left_location_sync")
    monkeypatch.setattr(locations_client, "notify_character_left_location_sync", f.left)
    f.cancel = AsyncMock(name="cancel_gathering", return_value={"cancelled": True})
    monkeypatch.setattr(locations_client, "cancel_gathering", f.cancel)
    f.t0 = now()
    f.ship_id = make_ship(f, when=f.t0)
    yield f
    econ_ledger.invalidate_settings_cache()


@pytest.fixture
def client(api, sea):
    """The law_world TestClient + the economy_api ``get_db`` (sea_api / sea_admin) on the sea world."""
    def override():
        session = sea()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override
    yield api
    app.dependency_overrides.pop(economy_api.get_db, None)


# --------------------------------------------------------------------------------------------- helpers

def ship(f, ship_id=None):
    db = f()
    try:
        row = db.get(models.SeaShip, int(ship_id or f.ship_id))
        if row is not None:
            db.expunge(row)
        return row
    finally:
        db.close()


def set_ship(f, ship_id=None, **cols):
    db = f()
    try:
        row = db.get(models.SeaShip, int(ship_id or f.ship_id))
        for k, v in cols.items():
            setattr(row, k, v)
        db.commit()
    finally:
        db.close()


def passes(f, ship_id=None, character_id=None):
    db = f()
    try:
        qy = db.query(models.SeaPass).filter(models.SeaPass.ship_id == int(ship_id or f.ship_id))
        if character_id is not None:
            qy = qy.filter(models.SeaPass.character_id == int(character_id))
        out = qy.order_by(models.SeaPass.id).all()
        for p in out:
            db.expunge(p)
        return out
    finally:
        db.close()


def add_pass(f, character_id, kind="ticket", first=1, last=1, status="active", ship_id=None, fare=0,
             post_floor_id=None, from_port=P_A, to_port=P_B):
    """A pass row inserted directly (the purchase path itself is tested through S2–S4)."""
    db = f()
    try:
        row = models.SeaPass(ship_id=int(ship_id or f.ship_id), character_id=character_id, kind=kind,
                             first_trip=first, last_trip=last, from_port_id=from_port, to_port_id=to_port,
                             from_name="from", to_name="to", zones=3, fare=fare, status=status,
                             post_floor_id=post_floor_id, created_at=now())
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def place(f, character_id, location_id):
    exec_(f, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=location_id, c=character_id)


def loc(f, character_id):
    v = q(f, "SELECT current_location_id FROM characters WHERE id = :c", c=character_id)
    return None if v is None else int(v)


def buy(f, character_id=ALPHA, to_trip=1, npc=CAPTAIN, ship_id=None, when=None):
    """S2 crud path in its own committed transaction (the HTTP path is covered separately)."""
    user = int(q(f, "SELECT user_id FROM characters WHERE id = :c", c=character_id))
    db = f()
    try:
        ctx = sea_crud.resolve_captain(db, npc, character_id, user)
        db.rollback()
        result = sea_crud.buy_ticket(db, ctx, ship_id or f.ship_id, to_trip, now=when)
        db.commit()
        return int(result.pass_row.id)
    finally:
        db.close()


def run_ship(f, when, ship_id=None):
    """One ship of the sea pass in its own transaction + the post-commit work (like ``run_pass``)."""
    db = f()
    try:
        out = sea_pass.process_ship(db, int(ship_id or f.ship_id), when)
        db.commit()
        sea_pass.after_commit(db, out)
        return out
    finally:
        db.close()


def depart(f, ship_id=None):
    """Run the sea pass for the ship just after its planned departure; returns (outcome, departure time)."""
    s = ship(f, ship_id)
    when = s.departs_at + timedelta(minutes=1)
    return run_ship(f, when, ship_id), when


def money_total(f):
    """Every coin of the world: player / NPC balances + every non-character ledger account."""
    chars = int(q(f, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters") or 0)
    accounts = int(q(f, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind != 'character'") or 0)
    return chars + accounts


def postings(f, op_id):
    return rows(f, "SELECT fa.kind, fa.ref_id, ta.kind, ta.ref_id, p.amount, p.leg_type FROM econ_postings p "
                   "JOIN econ_accounts fa ON fa.id = p.from_account_id "
                   "JOIN econ_accounts ta ON ta.id = p.to_account_id WHERE p.operation_id = :o ORDER BY p.id",
                o=op_id)


def op(f, op_id):
    r = rows(f, "SELECT op_type, idempotency_key FROM econ_operations WHERE id = :o", o=op_id)
    return r[0] if r else None


def post(f, character_id, location_id, content):
    exec_(f, "INSERT INTO posts (character_id, location_id, content) VALUES (:c, :l, :t)",
          c=character_id, l=location_id, t=content)
    return int(q(f, "SELECT MAX(id) FROM posts"))


def sea_payloads(stub, ws_type="sea"):
    out = []
    for call in stub.call_args_list:
        out.extend(p for p in call.args[0] if ws_type is None or p["ws_type"] == ws_type)
    return out


def sea_logs(f, character_id):
    return [r[0] for r in rows(f, "SELECT description FROM character_logs WHERE character_id = :c "
                                  "AND event_type = 'sea' ORDER BY id", c=character_id)]


class FixedRng:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def random(self):
        self.calls += 1
        return self.value
