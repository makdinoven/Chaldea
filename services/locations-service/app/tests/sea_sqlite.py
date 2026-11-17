"""FEAT-213 test world on a real SQLite file DB (shared by test_sea_zones.py and test_sea_passages.py).

LS tables are created from the ORM models; the character-service tables that ``sea_read`` reads
(``sea_ships``, ``sea_ship_stops``, ``sea_passes``) are hand-written stand-ins with only the columns read.

Layout::

    Country 1 «Земля» (visible): region 10 «Побережье», region 11 «Острова»
    Country 2 «Моря» (hidden):   region 20 «Море Эйдонэи», region 21 «Внутреннее море», region 22 «Корабли»

    PORT_A (r10, port → Z1) — LAND (r10) — LAND2 (r10)       PORT_B (r11, port → Z2)   PORT_C (r11, port, no zone)
    Z1 — Z2 (r20 zones)   Z3 (r21 zone)   HIDDEN_LAND (r22, plain location of the hidden country)
    DECK (r22) = ship 1 «Морская дева»: docked at PORT_A, active, trip_no 4, stops PORT_A, PORT_B
    DECK2 (r22) = ship 2 «Буревестник»: sailing (no docked port), active, trip_no 2, stops PORT_B, PORT_A
"""
import asyncio

from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import models


@compiles(BigInteger, "sqlite")
def _bigint(type_, compiler, **kw):  # pragma: no cover - DDL hook (autoincrement ids on SQLite)
    return "INTEGER"


C_LAND, C_SEAS = 1, 2
R_COAST, R_ISLES, R_SEA, R_INNER_SEA, R_SHIPS = 10, 11, 20, 21, 22
PORT_A, PORT_B, LAND, LAND2, PORT_C = 1, 2, 3, 4, 5
Z1, Z2, Z3 = 50, 51, 52
DECK, DECK2 = 60, 61
HIDDEN_LAND = 70
SHIP, SHIP2 = 1, 2
SHIP_NAME, SHIP2_NAME = "Морская дева", "Буревестник"
CHAR, OTHER_CHAR = 100, 101
TRIP_NO = 4          # ship 1: the next trip is 5
NEXT_TRIP = TRIP_NO + 1

LS_TABLES = (models.Area, models.Country, models.Region, models.District, models.Location,
             models.LocationNeighbor, models.RegionTransitionArrow, models.ArrowNeighbor)

CS_DDL = [
    "CREATE TABLE sea_ships (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, deck_location_id INTEGER NOT NULL, "
    "is_active INTEGER NOT NULL DEFAULT 1, status VARCHAR(10) NOT NULL DEFAULT 'docked', "
    "trip_no INTEGER NOT NULL DEFAULT 0, docked_port_id INTEGER NULL)",
    "CREATE TABLE sea_ship_stops (id INTEGER PRIMARY KEY AUTOINCREMENT, ship_id INTEGER NOT NULL, idx INTEGER NOT NULL, "
    "port_location_id INTEGER NOT NULL)",
    "CREATE TABLE sea_passes (id INTEGER PRIMARY KEY AUTOINCREMENT, ship_id INTEGER NOT NULL, "
    "character_id INTEGER NOT NULL, kind VARCHAR(10) NOT NULL, first_trip INTEGER NOT NULL, "
    "last_trip INTEGER NOT NULL, status VARCHAR(12) NOT NULL)",
]

_LOC_SQL = (
    "INSERT INTO Locations (id, name, district_id, region_id, type, image_url, recommended_level, "
    "quick_travel_marker, description, marker_type, sort_order, no_quick_move, is_starting, "
    "is_port, is_sea_zone, port_sea_zone_id) VALUES "
    "(:id, :name, NULL, :region, 'location', :img, :lvl, 0, '', 'safe', 0, 0, 0, :port, :zone, :pz)"
)

LOCATIONS = [
    # id, name, region, is_port, is_sea_zone, port_sea_zone_id
    (PORT_A, "Гавань Рассвета", R_COAST, 1, 0, Z1),
    (PORT_B, "Островной причал", R_ISLES, 1, 0, Z2),
    (LAND, "Прибрежный тракт", R_COAST, 0, 0, None),
    (LAND2, "Маяк", R_COAST, 0, 0, None),
    (PORT_C, "Рыбацкая пристань", R_ISLES, 1, 0, None),
    (Z1, "Пролив Ветров", R_SEA, 0, 1, None),
    (Z2, "Северный залив", R_SEA, 0, 1, None),
    (Z3, "Тихая бухта", R_INNER_SEA, 0, 1, None),
    (DECK, "Палуба «Морской девы»", R_SHIPS, 0, 0, None),
    (DECK2, "Палуба «Буревестника»", R_SHIPS, 0, 0, None),
    (HIDDEN_LAND, "Безымянный риф", R_SHIPS, 0, 0, None),
]


class SeaWorld:
    """A file DB plus helpers: ``sql`` (sync write), ``run`` (an async fn on a fresh session), ``session_factory``."""

    def __init__(self, path):
        self.path = path
        self.url = f"sqlite+aiosqlite:///{path}"

    def sql(self, query, **params):
        eng = create_engine(f"sqlite:///{self.path}")
        with eng.begin() as conn:
            result = conn.execute(text(query), params)
            rows = result.fetchall() if result.returns_rows else None
        eng.dispose()
        return rows

    def run(self, fn):
        async def go():
            engine = create_async_engine(self.url, poolclass=NullPool)
            Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with Session() as s:
                    return await fn(s)
            finally:
                await engine.dispose()
        return asyncio.run(go())

    def db_override(self):
        """A FastAPI ``get_db`` override yielding a real session on this file (engine per request)."""
        url = self.url

        async def override():
            engine = create_async_engine(url, poolclass=NullPool)
            Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with Session() as s:
                    yield s
            finally:
                await engine.dispose()
        return override

    # ---------------------------------------------------------------- data helpers
    def add_pass(self, kind="ticket", first=NEXT_TRIP, last=NEXT_TRIP, status="active", cid=CHAR, ship=SHIP):
        self.sql("INSERT INTO sea_passes (ship_id, character_id, kind, first_trip, last_trip, status) "
                 "VALUES (:s, :c, :k, :f, :l, :st)", s=ship, c=cid, k=kind, f=first, l=last, st=status)

    def ship(self, ship_id=SHIP, **cols):
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        self.sql(f"UPDATE sea_ships SET {sets} WHERE id = :sid", sid=ship_id, **cols)

    def link(self, a, b, cost=1, auto=0):
        for x, y in ((a, b), (b, a)):
            self.sql("INSERT INTO LocationNeighbors (location_id, neighbor_id, energy_cost, is_auto_arrow) "
                     "VALUES (:a, :b, :c, :auto)", a=x, b=y, c=cost, auto=auto)

    def links(self, a=None):
        q = "SELECT location_id, neighbor_id FROM LocationNeighbors"
        rows = self.sql(q + (" WHERE location_id = :a OR neighbor_id = :a" if a is not None else ""), a=a)
        return sorted((int(x), int(y)) for x, y in rows)

    def loc(self, loc_id):
        rows = self.sql("SELECT is_port, is_sea_zone, port_sea_zone_id, name FROM Locations WHERE id = :i", i=loc_id)
        if not rows:
            return None
        p, z, pz, name = rows[0]
        return {"is_port": bool(p), "is_sea_zone": bool(z), "port_sea_zone_id": pz, "name": name}


def build_world(path, with_cs_tables=True) -> SeaWorld:
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        for m in LS_TABLES:
            m.__table__.create(conn)
        conn.execute(text("INSERT INTO Countries (id, name, description, is_hidden) VALUES "
                          "(1, 'Земля', '', 0), (2, 'Моря', '', 1)"))
        conn.execute(text("INSERT INTO Regions (id, name, country_id, description) VALUES "
                          "(10, 'Побережье', 1, ''), (11, 'Острова', 1, ''), (20, 'Море Эйдонэи', 2, ''), "
                          "(21, 'Внутреннее море', 2, ''), (22, 'Корабли', 2, '')"))
        for lid, name, region, port, zone, pz in LOCATIONS:
            conn.execute(text(_LOC_SQL), {"id": lid, "name": name, "region": region, "img": f"img/{lid}.png",
                                          "lvl": 3, "port": port, "zone": zone, "pz": pz})
        for a, b, cost in ((LAND, PORT_A, 3), (LAND, LAND2, 2), (Z1, Z2, 1)):
            for x, y in ((a, b), (b, a)):
                conn.execute(text("INSERT INTO LocationNeighbors (location_id, neighbor_id, energy_cost, "
                                  "is_auto_arrow) VALUES (:a, :b, :c, 0)"), {"a": x, "b": y, "c": cost})
        if with_cs_tables:
            for q in CS_DDL:
                conn.execute(text(q))
            conn.execute(text(
                "INSERT INTO sea_ships (id, name, deck_location_id, is_active, status, trip_no, docked_port_id) "
                "VALUES (:s1, :n1, :d1, 1, 'docked', :t1, :p1), (:s2, :n2, :d2, 1, 'sailing', 2, NULL)"),
                {"s1": SHIP, "n1": SHIP_NAME, "d1": DECK, "t1": TRIP_NO, "p1": PORT_A,
                 "s2": SHIP2, "n2": SHIP2_NAME, "d2": DECK2})
            conn.execute(text("INSERT INTO sea_ship_stops (ship_id, idx, port_location_id) VALUES "
                              f"({SHIP}, 0, {PORT_A}), ({SHIP}, 1, {PORT_B}), "
                              f"({SHIP2}, 0, {PORT_B}), ({SHIP2}, 1, {PORT_A})"))
    eng.dispose()
    return SeaWorld(path)
