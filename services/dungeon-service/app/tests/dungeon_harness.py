"""FEAT-175 test harness: real gameplay code on SQLite + an in-memory Redis +
fake neighbour services.

* `FakeRedis` implements the handful of redis.asyncio calls session_state.py
  makes, so the REAL session_state module runs.
* `FakeWorld` stands in for character-service / attributes / inventory /
  battle-service / party-service / locations-service by replacing the
  functions in `http_clients` (gameplay calls them through the module).
* WebSocket broadcasts are captured in `world.events`.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytest
import pytest_asyncio
from fastapi import HTTPException

import gameplay
import http_clients
import session_state
import ws_manager
from models import (
    Dungeon, DungeonRoom, DungeonCorridor, DungeonSession, DungeonSessionMember,
    DungeonSessionInventory, DungeonRoomState,
)


class FakeRedis:
    def __init__(self):
        self.data: Dict[str, str] = {}
        self.expiry: Dict[str, float] = {}

    def _alive(self, key):
        exp = self.expiry.get(key)
        if exp is not None and exp <= time.time():
            self.data.pop(key, None)
            self.expiry.pop(key, None)
        return key in self.data

    async def get(self, key):
        return self.data[key] if self._alive(key) else None

    async def set(self, key, value, ex=None):
        self.data[key] = value
        if ex is not None:
            self.expiry[key] = time.time() + ex
        else:
            self.expiry.pop(key, None)
        return True

    async def delete(self, *keys):
        n = 0
        for k in keys:
            if self._alive(k):
                n += 1
            self.data.pop(k, None)
            self.expiry.pop(k, None)
        return n

    async def ttl(self, key):
        if not self._alive(key):
            return -2
        exp = self.expiry.get(key)
        return -1 if exp is None else int(exp - time.time())

    async def rpush(self, key, value):
        lst = self.data.get(key) if self._alive(key) else None
        if not isinstance(lst, list):
            lst = []
        lst.append(value)
        self.data[key] = lst
        return len(lst)

    async def ltrim(self, key, start, end):
        lst = self.data.get(key) if self._alive(key) else None
        if isinstance(lst, list):
            n = len(lst)
            s = start if start >= 0 else max(0, n + start)
            e = end if end >= 0 else n + end
            self.data[key] = lst[s:e + 1]
        return True

    async def lrange(self, key, start, end):
        lst = self.data.get(key) if self._alive(key) else None
        if not isinstance(lst, list):
            return []
        n = len(lst)
        s = start if start >= 0 else max(0, n + start)
        e = end if end >= 0 else n + end
        return lst[s:e + 1]

    async def expire(self, key, seconds):
        if self._alive(key):
            self.expiry[key] = time.time() + seconds
        return True

    def flush(self):
        self.data.clear()
        self.expiry.clear()


class FakeWorld:
    """Neighbour services. Characters: id -> dict(user_id, location, hp, ...)."""

    def __init__(self, location_id=100):
        self.location_id = location_id
        self.characters: Dict[int, dict] = {}
        self.locks: Dict[int, dict] = {}         # character_id -> {"session": id, "unconscious": dt}
        self.party: dict = {}
        self.gate_ok = True
        self.battle_fail: Optional[HTTPException] = None
        self.next_battle_id = 500
        self.next_mob_id = 9000
        self.battles: List[dict] = []
        self.battle_states: Dict[int, Optional[dict]] = {}
        self.battle_results: Dict[int, Optional[dict]] = {}
        self.spawned: List[dict] = []
        self.despawned: List[int] = []
        self.given: List[tuple] = []             # (character_id, item_id, qty)
        self.give_fail_items: set = set()
        self.gold: Dict[int, int] = {}
        self.stamina_spent: Dict[int, int] = {}
        self.knockouts: List[dict] = []
        self.events: List[dict] = []
        self.busy: Dict[int, str] = {}           # character_id -> "в бою" / "занят добычей"

    # --- setup helpers --------------------------------------------------------
    def add_character(self, cid, user_id, location=None, hp=100, max_hp=100, stamina=100,
                      stats=None, name=None, gold=1000):
        self.characters[cid] = {
            "user_id": user_id, "location": self.location_id if location is None else location,
            "hp": hp, "max_hp": max_hp, "stamina": stamina, "stats": stats or {},
            "name": name or f"Герой{cid}",
        }
        self.gold[cid] = gold

    def lock_of(self, cid) -> dict:
        lk = self.locks.get(cid, {})
        unc = lk.get("unconscious")
        if unc and unc > datetime.utcnow():
            return {"locked": True, "reason": "unconscious", "until": unc.isoformat(), "dungeon_session_id": None}
        if lk.get("session"):
            return {"locked": True, "reason": "dungeon", "until": None, "dungeon_session_id": lk["session"]}
        return {"locked": False, "reason": None, "until": None, "dungeon_session_id": None}

    def events_of(self, etype):
        return [e for e in self.events if e.get("type") == etype]

    # --- fakes ----------------------------------------------------------------
    async def get_character_profile(self, cid):
        if cid >= 9000:
            return {"character_name": f"Моб{cid}", "user_id": None}
        c = self.characters.get(cid)
        if c is None:
            raise HTTPException(status_code=404, detail="Персонаж не найден")
        return {
            "character_name": c["name"], "user_id": c["user_id"],
            "current_location_id": c["location"], "activity_lock": self.lock_of(cid),
            "character_class_id": c.get("class_id", 1),
        }

    async def get_activity_lock(self, cid):
        return self.lock_of(cid)

    async def set_dungeon_lock(self, ids, session_id):
        for cid in ids:
            lk = self.lock_of(cid)
            if lk["locked"] and lk.get("dungeon_session_id") != session_id:
                raise HTTPException(status_code=409, detail=f"{self.characters[cid]['name']} находится в подземелье")
        for cid in ids:
            self.locks.setdefault(cid, {})["session"] = session_id

    async def clear_dungeon_lock(self, ids, session_id):
        for cid in ids:
            lk = self.locks.get(cid, {})
            if lk.get("session") == session_id:
                lk["session"] = None
        return True

    async def knockout_characters(self, ids, seconds, session_id, return_location_id):
        until = datetime.utcnow() + timedelta(seconds=seconds)
        self.knockouts.append({"ids": list(ids), "seconds": seconds, "session_id": session_id,
                               "return_location_id": return_location_id})
        for cid in ids:
            lk = self.locks.setdefault(cid, {})
            if lk.get("session") == session_id:
                lk["session"] = None
            lk["unconscious"] = until
            if return_location_id is not None:
                self.characters[cid]["location"] = return_location_id
        return {"until": until.isoformat()}

    async def get_party_active_members(self, cid, location_id):
        return self.party

    async def consume_dungeon_gate(self, cid, location_id, dungeon_id):
        return self.gate_ok

    async def spawn_dungeon_mobs(self, template_ids, location_id, stat_multiplier=1.0):
        ids = []
        for _ in template_ids:
            self.next_mob_id += 1
            ids.append(self.next_mob_id)
        self.spawned.append({"templates": list(template_ids), "ids": ids, "multiplier": stat_multiplier})
        return ids

    async def despawn_dungeon_mobs(self, ids):
        self.despawned.extend(ids or [])

    async def create_dungeon_battle(self, session_id, players):
        if self.battle_fail is not None:
            raise self.battle_fail
        for p in players:
            if p["team"] == 1:
                lk = self.lock_of(p["character_id"])
                assert lk.get("dungeon_session_id") == session_id, "party member not locked to this run"
        self.next_battle_id += 1
        self.battles.append({"battle_id": self.next_battle_id, "session_id": session_id, "players": players})
        return {"battle_id": self.next_battle_id}

    async def get_battle_state(self, battle_id):
        return self.battle_states.get(battle_id)

    async def get_battle_result(self, battle_id):
        return self.battle_results.get(battle_id)

    async def get_character_attributes(self, cid):
        c = self.characters[cid]
        return {"current_health": c["hp"], "max_health": c["max_hp"],
                "current_stamina": c["stamina"], **c["stats"]}

    async def consume_stamina(self, cid, amount):
        c = self.characters[cid]
        if c["stamina"] < amount:
            return False
        c["stamina"] -= amount
        self.stamina_spent[cid] = self.stamina_spent.get(cid, 0) + amount
        return True

    async def recover_character(self, cid, health=0, stamina=0, **kw):
        c = self.characters[cid]
        c["hp"] = max(0, min(c["max_hp"], c["hp"] + health))
        if stamina:
            c["stamina"] += stamina
            self.stamina_spent[cid] = self.stamina_spent.get(cid, 0) - stamina
            if self.stamina_spent[cid] == 0:
                del self.stamina_spent[cid]
        return {}

    async def surface_busy(self, db, cid):
        return self.busy.get(cid)

    # Gold is posted in dungeon-service's own transaction (FEAT-181, gameplay._charge_gold /
    # _pay_gold). The harness keeps it in `self.gold`; test_econ_dungeon.py runs the real ledger.
    async def charge_gold(self, db, dungeon, cid, amount, **kw):
        if self.gold.get(cid, 0) < amount:
            return False
        self.gold[cid] -= amount
        return True

    async def pay_gold(self, db, dungeon, cid, amount, **kw):
        self.gold[cid] = self.gold.get(cid, 0) + amount

    async def add_item_to_character(self, cid, item_id, quantity):
        if item_id in self.give_fail_items:
            raise HTTPException(status_code=502, detail="Ошибка при добавлении предмета в инвентарь")
        self.given.append((cid, item_id, quantity))
        return {}

    async def get_item_info(self, item_id):
        return {"name": f"Предмет{item_id}"}

    async def broadcast(self, session_id, data):
        self.events.append(dict(data, session_id=session_id))
        # As the real broadcast: every event is offered to the listeners (the run's log).
        for listener in ws_manager.listeners:
            await listener(session_id, data)

    def install(self, monkeypatch):
        for name in (
            "get_character_profile", "get_activity_lock", "set_dungeon_lock", "clear_dungeon_lock",
            "knockout_characters", "get_party_active_members", "consume_dungeon_gate",
            "spawn_dungeon_mobs", "despawn_dungeon_mobs", "create_dungeon_battle",
            "get_battle_state", "get_battle_result", "get_character_attributes",
            "consume_stamina", "recover_character",
            "add_item_to_character", "get_item_info",
        ):
            monkeypatch.setattr(http_clients, name, getattr(self, name))
        monkeypatch.setattr(ws_manager, "broadcast_to_session", self.broadcast)
        monkeypatch.setattr(gameplay, "_surface_busy", self.surface_busy)
        monkeypatch.setattr(gameplay, "_charge_gold", self.charge_gold)
        monkeypatch.setattr(gameplay, "_pay_gold", self.pay_gold)

        async def _noop(*a, **kw):
            return None
        monkeypatch.setattr(ws_manager, "cleanup_session", _noop)


@pytest.fixture()
def fake_redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(session_state, "_redis_client", r)
    return r


@pytest.fixture()
def world(monkeypatch, fake_redis):
    w = FakeWorld()
    w.install(monkeypatch)
    w.add_character(10, user_id=1)
    w.add_character(11, user_id=2)
    w.add_character(12, user_id=3)
    return w


async def build_dungeon(db, *, location_id=100, mana_core=False, mana_core_chance=0.0,
                        mana_core_item_id=None, cooldown_hours=24, mob_multiplier=1.0, **dungeon_kw):
    """entrance(fork) -c1- battle -c2- boss ; entrance -c3- event ; entrance -c4- treasure
    ; entrance -c5- trap ; entrance -c6- teleport(->battle) ; entrance -c7- rest ; entrance -c8- merchant
    (+ optional mana core room, not connected)."""
    d = Dungeon(name="Склеп", description="desc", location_id=location_id, cooldown_hours=cooldown_hours,
                mob_multiplier=mob_multiplier, mana_core_chance=mana_core_chance,
                mana_core_item_id=mana_core_item_id, is_active=True, stability_type="static",
                danger_level="safe", loot_multiplier=1.0, stamina_multiplier=1.0,
                difficulty_modifier=1.0, disable_rest_rooms=False, disable_merchants=False,
                recommended_level=1, recommended_party_size=1, **dungeon_kw)
    db.add(d)
    await db.flush()
    rooms = {}

    def room(key, rtype, cfg=None, **kw):
        r = DungeonRoom(dungeon_id=d.id, room_type=rtype, name=key.capitalize(), description=key,
                        room_config=cfg or {}, sort_order=0, is_entrance=kw.get("is_entrance", False),
                        is_boss_room=kw.get("is_boss_room", False),
                        is_mana_core_room=kw.get("is_mana_core_room", False),
                        position_x=kw.get("x"), position_y=kw.get("y"),
                        grid_w=kw.get("grid_w"), grid_d=kw.get("grid_d"))
        db.add(r)
        rooms[key] = r
        return r

    room("entrance", "fork", is_entrance=True, x=0.0, y=0.0, grid_w=3, grid_d=4)
    room("battle", "battle", {"mob_template_ids": [1, 2]}, x=100.0, y=0.0)
    room("boss", "boss", {"mob_template_ids": [5], "boss_loot": [{"item_id": 77, "quantity": 2, "chance": 1}]},
         is_boss_room=True)
    room("event", "event", {"text": "?", "choices": [
        {"text": "Взять", "outcome_type": "reward", "outcome_data": '{"gold": 100, "items": [{"item_id": 5, "quantity": 1}]}'},
        {"text": "Ткнуть", "outcome_type": "damage", "outcome_data": '{"damage": 30}'},
        {"text": "Испить", "outcome_type": "heal", "outcome_data": '{"heal_percent": 50}'},
        {"text": "Старое лечение", "outcome_type": "heal", "outcome_data": {"heal_amount": 7}},
        {"text": "Драка", "outcome_type": "battle", "outcome_data": '{"mob_template_ids": [3]}'},
        {"text": "Портал", "outcome_type": "teleport", "outcome_data": '{"target_room_id": 0}'},
    ]})
    room("treasure", "treasure", {"loot_table": [{"item_id": 10, "quantity": 5, "chance": 1}]})
    room("trap", "trap", {"stat_check": "agility", "difficulty": 50, "fail_damage": 30})
    room("teleport", "teleport", {"target_room_id": None})
    room("rest", "rest", {"heal_percent": 30, "wait_seconds": 0, "gold_cost": 0, "revive_gold_cost": 100})
    room("merchant", "merchant", {"items": [{"item_id": 33, "price": 10, "stock": 1}]})
    if mana_core:
        room("core", "deadend", {}, is_mana_core_room=True)
    await db.flush()
    # teleport -> battle room; event teleport -> treasure
    rooms["teleport"].room_config = {"target_room_id": rooms["battle"].id}
    choices = list(rooms["event"].room_config["choices"])
    choices[5] = dict(choices[5], outcome_data='{"target_room_id": %d}' % rooms["treasure"].id)
    rooms["event"].room_config = dict(rooms["event"].room_config, choices=choices)

    corridors = {}

    def corr(key, a, b, **kw):
        c = DungeonCorridor(dungeon_id=d.id, from_room_id=rooms[a].id, to_room_id=rooms[b].id,
                            stamina_cost=kw.get("cost", 5), is_bidirectional=True,
                            random_battle_chance=kw.get("battle", 0.0),
                            random_battle_mob_ids=kw.get("mobs"), trap_chance=kw.get("trap", 0.0),
                            trap_config=kw.get("trap_config"))
        db.add(c)
        corridors[key] = c

    corr("c1", "entrance", "battle")
    corr("c2", "battle", "boss")
    corr("c3", "entrance", "event")
    corr("c4", "entrance", "treasure")
    corr("c5", "entrance", "trap")
    corr("c6", "entrance", "teleport")
    corr("c7", "entrance", "rest")
    corr("c8", "entrance", "merchant")
    await db.commit()
    # Plain snapshots: ORM objects expire on any rollback inside gameplay.
    from types import SimpleNamespace as NS
    ref = NS(id=d.id, location_id=d.location_id)
    return (
        ref,
        {k: NS(id=r.id, name=r.name) for k, r in rooms.items()},
        {k: NS(id=c.id) for k, c in corridors.items()},
    )


async def enter_solo(db, dungeon, character_id=10, user_id=1):
    return await gameplay.start_run(db, dungeon.id, character_id, user_id, party=False)


def finish_battle(world, battle_id, party_won=True, dead=()):
    """Make GET /battles/internal/{id}/state report a finished battle."""
    battle = next(b for b in world.battles if b["battle_id"] == battle_id)
    participants = {}
    for i, p in enumerate(battle["players"]):
        team = p["team"]
        alive = (team == 1 and party_won and p["character_id"] not in dead) or (team == 2 and not party_won)
        participants[str(i)] = {"character_id": p["character_id"], "team": team, "hp": 10 if alive else 0}
    world.battle_states[battle_id] = {"runtime": {"participants": participants}}


async def reload_session(db, session_id):
    db.expire_all()
    return await gameplay._get_session(db, session_id)
