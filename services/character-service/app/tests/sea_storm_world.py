"""FEAT-214 QA: storm / raid helpers on top of :mod:`tests.sea_world` (not a test module).

The ``storm`` fixture = the ``sea`` world (ship 1 «Морская дева», zones 501–505, seas 30 / 31) plus:

* ``storm.rng`` — the shared :class:`ScriptedRng` behind ``sea_core.weather_rng`` (every storm / drift / raid roll);
* ``storm.cas`` — the CAS storm-damage stand-in behind ``sea_weather.http_post``;
* ``storm.bs`` — the battle-service stand-in behind ``battle_client.create_sea_raid_battle``;
* ``storm.poll`` — the stand-in behind ``battle_client.get_battle_result``;
* the season of the game calendar (``sea_weather.current_season``) → ``storm.season`` (None by default);
* the mob attributes call of ``crud.spawn_mob_from_template`` → no HTTP (the real spawn writes characters /
  active_mobs, so despawn is checked against real rows).
"""

import sqlite3
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

import battle_client
import crud as cs_crud
import econ_ledger
import models
import sea_core
import sea_weather
from tests.sea_world import exec_, now, q, rows  # noqa: F401

MONSTER_TPL = 40
MONSTER_TPL2 = 41
BATTLE_BASE = 900


class ScriptedRng:
    """A deterministic ``random.Random`` stand-in: ``random()`` pops ``values`` (the last one repeats),
    ``randrange(n)`` → ``pick`` clamped to n-1, ``randint(a, b)`` → ``a`` (or ``b`` when ``high``), ``shuffle`` keeps
    the order."""

    def __init__(self, *values, pick=0, high=False):
        self.values = list(values) or [0.5]
        self.pick = pick
        self.high = high
        self.calls = 0

    def random(self):
        self.calls += 1
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]

    def randrange(self, n):
        return min(int(self.pick), int(n) - 1)

    def randint(self, a, b):
        return b if self.high else a

    def shuffle(self, seq):
        return None


class FakeCas:
    """``sea_weather.http_post`` stand-in."""

    def __init__(self):
        self.calls = []
        self.status = 200
        self.error = None

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.error is not None:
            raise self.error
        applied = [{"character_id": i["character_id"], "health_before": 100, "health_after": 90,
                    "stamina_before": 50, "stamina_after": 40} for i in payload["items"]]
        return SimpleNamespace(status_code=self.status, json=lambda: {"applied": applied, "missing": []})

    @property
    def ids(self):
        return [i["character_id"] for _url, p in self.calls for i in p["items"]]


class FakeSeaBattle:
    """``battle_client.create_sea_raid_battle`` stand-in: battle ids 901, 902, …; ``placed`` filters the players."""

    def __init__(self):
        self.calls = []
        self.error = None
        self.skip = set()

    async def __call__(self, sea_raid_id, location_id, player_character_ids, mob_character_ids):
        self.calls.append({"raid_id": int(sea_raid_id), "location_id": int(location_id),
                           "players": [int(p) for p in player_character_ids],
                           "mobs": [int(m) for m in mob_character_ids]})
        if self.error is not None:
            raise self.error
        return {"battle_id": BATTLE_BASE + len(self.calls),
                "player_character_ids": [int(p) for p in player_character_ids if int(p) not in self.skip]}


class FakePoll:
    def __init__(self):
        self.calls = []
        self.answer = {"status": "in_progress"}

    def __call__(self, battle_id):
        self.calls.append(int(battle_id))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def storm(sea, monkeypatch):
    # pysqlite cannot bind Decimal in raw SQL (MySQL can) — scoped adapter, as in test_caravan_raids
    monkeypatch.setitem(sqlite3.adapters, (Decimal, sqlite3.PrepareProtocol), str)
    monkeypatch.setitem(sea_weather._available_cache, "ok", False)
    monkeypatch.setitem(sea_weather._warned, "missing", False)
    sea.rng = ScriptedRng(0.5)
    monkeypatch.setattr(sea_core, "weather_rng", lambda: sea.rng)
    sea.cas = FakeCas()
    monkeypatch.setattr(sea_weather, "http_post", sea.cas)
    sea.bs = FakeSeaBattle()
    monkeypatch.setattr(battle_client, "create_sea_raid_battle", sea.bs)
    sea.poll = FakePoll()
    monkeypatch.setattr(battle_client, "get_battle_result", sea.poll)
    sea.season = None
    monkeypatch.setattr(sea_weather, "current_season", lambda db, when: sea.season)
    monkeypatch.setattr(cs_crud, "_sync_send_attributes_request", lambda cid, attrs: None)
    # quiet defaults: no drift, no damage surprises; tests switch things on explicitly
    set_params(sea, storm_drift_pct=0)
    return sea


# --------------------------------------------------------------------------------------------- data helpers

def set_params(f, **cols):
    db = f()
    try:
        row = db.get(models.SeaSetting, 1)
        for k, v in cols.items():
            setattr(row, k, Decimal(str(v)) if isinstance(v, float) else v)
        db.commit()
    finally:
        db.close()


def set_sea(f, region_id, enabled=True, pct=100, radius=1):
    db = f()
    try:
        row = db.get(models.SeaStormSea, int(region_id))
        if row is None:
            row = models.SeaStormSea(region_id=int(region_id))
            db.add(row)
        row.is_enabled, row.chance_per_hour_pct, row.radius, row.updated_at = enabled, Decimal(str(pct)), radius, now()
        db.commit()
    finally:
        db.close()


def add_storm(f, zones, *, center=None, region=30, minutes=60, start=None, status="active", source="admin",
              moves=0, ends_at=None):
    start = start or now()
    db = f()
    try:
        s = models.SeaStorm(region_id=region, center_zone_id=center or zones[0], status=status, source=source,
                            moves=moves, started_at=start, ends_at=ends_at or start + timedelta(minutes=minutes))
        db.add(s)
        db.flush()
        for z in zones:
            db.add(models.SeaStormZone(storm_id=int(s.id), zone_id=int(z)))
        db.commit()
        return int(s.id)
    finally:
        db.close()


def storm_row(f, storm_id):
    db = f()
    try:
        s = db.get(models.SeaStorm, int(storm_id))
        db.expunge(s)
        return s
    finally:
        db.close()


def storm_zone_ids(f, storm_id):
    return [int(r[0]) for r in rows(f, "SELECT zone_id FROM sea_storm_zones WHERE storm_id = :s ORDER BY zone_id",
                                    s=storm_id)]


def add_monster(f, zone, *, tpl=MONSTER_TPL, name="Кракен", chance=100.0, max_active=5, enabled=True):
    db = f()
    try:
        if db.get(models.MobTemplate, tpl) is None:
            db.add(models.MobTemplate(id=tpl, name=name, level=3, id_race=1, id_subrace=1, id_class=1,
                                      base_attributes={"strength": 10, "max_health": 50}))
            db.flush()
        db.add(models.LocationMobSpawn(mob_template_id=tpl, location_id=zone, spawn_chance=chance,
                                       max_active=max_active, is_enabled=enabled))
        db.commit()
    finally:
        db.close()


def add_player(f, cid, user, location, name=None, hp=100):
    db = f()
    try:
        with econ_ledger.allow_direct_balance_write(db):
            db.add(models.Character(id=cid, name=name or f"Моряк {cid}", user_id=user, id_subrace=1, id_class=1,
                                    id_race=1, appearance="-", avatar="-", is_npc=False,
                                    current_location_id=location, level=5, currency_balance=0))
            db.flush()
        db.commit()
    finally:
        db.close()
    exec_(f, "INSERT INTO character_attributes (character_id, current_health) VALUES (:c, :h)", c=cid, h=hp)


def in_battle(f, character_id, battle_id):
    exec_(f, "INSERT OR IGNORE INTO battles (id, status) VALUES (:b, 'in_progress')", b=battle_id)
    exec_(f, "INSERT INTO battle_participants (battle_id, character_id) VALUES (:b, :c)", b=battle_id, c=character_id)


def raids(f, ship_id=None):
    db = f()
    try:
        qy = db.query(models.SeaRaid)
        if ship_id is not None:
            qy = qy.filter(models.SeaRaid.ship_id == int(ship_id))
        out = qy.order_by(models.SeaRaid.id).all()
        for r in out:
            db.expunge(r)
        return out
    finally:
        db.close()


def raid(f, raid_id):
    db = f()
    try:
        r = db.get(models.SeaRaid, int(raid_id))
        if r is not None:
            db.expunge(r)
        return r
    finally:
        db.close()


def active_mob_ids(f):
    return sorted(int(r[0]) for r in rows(f, "SELECT character_id FROM active_mobs WHERE spawn_type = 'dungeon'"))


def ws_events(stub, event):
    out = []
    for call in stub.call_args_list:
        out.extend(p for p in call.args[0] if p["ws_type"] == "sea" and p["ws_data"].get("event") == event)
    return out


def http_error():
    return httpx.ConnectError("down")
