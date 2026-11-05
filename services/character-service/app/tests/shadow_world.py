"""FEAT-199 QA: helpers for the shadow / renown tests (not a test module).

Built on :mod:`tests.law_world` (rep_world + law extras: characters, regions, locations, character_attributes,
battles, items / equipment_slots, tree_nodes / character_tree_progress, Locations.marker_type).

Randomness: ``law_crud.rng`` is THE seam of both the witness roll and the reveal roll; :func:`set_roll` installs a
fixed value, :class:`CountingRng` counts the calls, :class:`ExplodingRng` proves no roll happened.
RabbitMQ: ``law_notify._send`` is stubbed by the conftest autouse fixture (``stub_law_notify_send``),
``reputation_notify._send`` by ``rep_world``.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import law_crud
import models
from tests.law_world import exec_, now, q, rows

MARKET = 100          # location of the merchant / bandit / guard 52 (region 10 «Ост»)


class FixedRng:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def random(self):
        self.calls += 1
        return self.value


class ExplodingRng:
    """Any roll fails the test: proves the path never rolls."""

    def random(self):
        raise AssertionError("no roll expected on this path")


def set_roll(monkeypatch, value):
    rng = FixedRng(value)
    monkeypatch.setattr(law_crud, "rng", lambda: rng)
    return rng


def no_roll(monkeypatch):
    monkeypatch.setattr(law_crud, "rng", lambda: ExplodingRng())


# --------------------------------------------------------------------------------------------- world setters

def shadow_settings(f, **overrides):
    """Write the shadow_settings row (id=1) = ORM defaults + ``overrides``."""
    db = f()
    try:
        row = db.get(models.ShadowSettings, 1)
        if row is None:
            row = models.ShadowSettings(id=1, updated_at=now())
            db.add(row)
            db.flush()
        for name, value in overrides.items():
            setattr(row, name, value)
        db.commit()
    finally:
        db.close()


def set_marker(f, location_id, marker):
    exec_(f, "UPDATE Locations SET marker_type = :m WHERE id = :l", m=marker, l=location_id)


def set_attrs(f, character_id, agility=0, luck=0, stealth=0):
    if q(f, "SELECT COUNT(*) FROM character_attributes WHERE character_id = :c", c=character_id):
        exec_(f, "UPDATE character_attributes SET agility = :a, luck = :l, stealth = :s WHERE character_id = :c",
              a=agility, l=luck, s=stealth, c=character_id)
    else:
        exec_(f, "INSERT INTO character_attributes (character_id, agility, luck, stealth) VALUES (:c, :a, :l, :s)",
              c=character_id, a=agility, l=luck, s=stealth)


_ITEM_SEQ = {"n": 900}


def give_mask(f, character_id, is_mask=1, slot="head"):
    """Equip a head item (``is_mask`` flag) on the character."""
    _ITEM_SEQ["n"] += 1
    item_id = _ITEM_SEQ["n"]
    exec_(f, "INSERT INTO items (id, name, item_type, is_mask) VALUES (:i, 'Маска', 'head', :m)",
          i=item_id, m=is_mask)
    exec_(f, "INSERT INTO equipment_slots (character_id, slot_type, item_id) VALUES (:c, :s, :i)",
          c=character_id, s=slot, i=item_id)
    return item_id


_NODE_SEQ = {"n": 500}


def set_subclass(f, character_id, key):
    _NODE_SEQ["n"] += 1
    node = _NODE_SEQ["n"]
    exec_(f, "INSERT INTO tree_nodes (id, node_type, subclass_key) VALUES (:n, 'subclass_choice', :k)", n=node, k=key)
    exec_(f, "INSERT INTO character_tree_progress (character_id, node_id) VALUES (:c, :n)", c=character_id, n=node)


def set_renown(f, character_id, fame=0, infamy=0):
    exec_(f, "DELETE FROM character_renown WHERE character_id = :c", c=character_id)
    exec_(f, "INSERT INTO character_renown (character_id, fame, infamy, updated_at) VALUES (:c, :fa, :i, :u)",
          c=character_id, fa=fame, i=infamy, u=now())


def renown(f, character_id):
    r = rows(f, "SELECT fame, infamy FROM character_renown WHERE character_id = :c", c=character_id)
    return (int(r[0][0]), int(r[0][1])) if r else (0, 0)


def set_suspicion(f, region_id, value, decay_at=None):
    exec_(f, "DELETE FROM region_suspicion WHERE region_id = :r", r=region_id)
    exec_(f, "INSERT INTO region_suspicion (region_id, value, decay_at, updated_at) VALUES (:r, :v, :d, :u)",
          r=region_id, v=value, d=decay_at if decay_at is not None else (now() if value else None), u=now())


def suspicion(f, region_id):
    v = q(f, "SELECT value FROM region_suspicion WHERE region_id = :r", r=region_id)
    return None if v is None else int(v)


def guard_encounter_battle(f, battle_id, encounter_id=5):
    exec_(f, "INSERT INTO battles (id, status, law_encounter_id) VALUES (:b, 'finished', :e)", b=battle_id,
          e=encounter_id)


# --------------------------------------------------------------------------------------------- readers

CRIME_COLS = ("id", "character_id", "crime_type", "status", "masked", "witness_chance_pct", "witness_roll_pct",
              "reputation_delta", "reputation_key", "reputation_reason", "wanted_floor", "wanted_points",
              "wanted_applied", "reveal_until", "next_roll_at", "reveal_attempts", "revealed_at", "resolved_at",
              "created_at", "region_id", "event_key", "stealth_reduction_pct")


def crimes(f, character_id=None):
    sql = "SELECT " + ", ".join(CRIME_COLS) + " FROM law_crimes"
    params = {}
    if character_id is not None:
        sql += " WHERE character_id = :c"
        params["c"] = character_id
    return [dict(zip(CRIME_COLS, r)) for r in rows(f, sql + " ORDER BY id", **params)]


def crime(f, crime_id):
    return [c for c in crimes(f) if c["id"] == crime_id][0]


def dec(v):
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


def dt(v):
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v))


def renown_log(f, character_id=None):
    sql = "SELECT event_key, scale, source, delta, value_after, tier_before, tier_after, actor_user_id FROM renown_log"
    params = {}
    if character_id is not None:
        sql += " WHERE character_id = :c"
        params["c"] = character_id
    return rows(f, sql + " ORDER BY id", **params)


def payloads(stub):
    out = []
    for call in stub.call_args_list:
        out.extend(call.args[0])
    return out


def ws_types(stub):
    return [p["ws_type"] for p in payloads(stub)]


def kill(api, npc_id, killers, battle_id=77):
    from tests.law_world import INTERNAL
    body = {"status": "dead", "killer_character_ids": killers}
    if battle_id is not None:
        body["battle_id"] = battle_id
    return api.put(f"/characters/internal/npc-status/{npc_id}", json=body, headers=INTERNAL)


def make_deferred(f, character_id=1, npc_id=50, *, masked=False, floor=None, points=150, rep_delta=-150,
                  region_id=10, created=None, battle=77, crime_type="npc_kill", reveal_days=3):
    """Insert a deferred crime directly through law_crud.register_crime (the orchestrator path is tested apart)."""
    created = created or now()
    db = f()
    try:
        res = law_crud.register_crime(
            db, crime_type=crime_type, character_id=character_id, region_id=region_id, points=points,
            event_key=f"crime:npc_kill:{npc_id}:{battle}:{character_id}", location_id=MARKET, victim_id=npc_id,
            battle_id=battle, floor=floor, now=created,
            status="masked" if masked else "unwitnessed", reputation_delta=rep_delta,
            reputation_key=f"npc_kill:{npc_id}:{battle}:{character_id}",
            reputation_reason=f"Убит NPC (#{npc_id}) в бою #{battle}", masked=masked,
            witness_chance_pct=Decimal("40"), witness_roll_pct=Decimal("77.7"),
            reveal_until=created + timedelta(days=reveal_days), next_roll_at=created + timedelta(days=1))
        db.commit()
        return res.crime_id
    finally:
        db.close()
