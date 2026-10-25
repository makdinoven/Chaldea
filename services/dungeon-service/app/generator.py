"""
Dungeon generator (FEAT-177): builds a draft — rooms and corridors — from a few
parameters, for the admin to finish in the editor.

Pure rules, no I/O: `generate(params, catalog)` returns a plan; crud writes it.
The same seed gives the same dungeon.

How a floor is built:
  1. The main path: a walk over the grid from the floor's start (the entrance,
     or the foot of the stairs from above) to its end (the stairs down, or the
     boss on the last floor). Rooms are neighbouring grid cells, so corridors
     are short and straight, on the editor's map and on the 3D board alike.
  2. Branches hang off the path; the deepest room of a branch is a treasure,
     a dead end with a stash, or something worth the detour.
  3. A few loops join neighbouring rooms of the same region.

What makes it always passable:
  - the main path is never locked or hidden;
  - a locked or hidden door only ever closes a branch off the path (and the
    boss's door may be locked), and loops never cross into such a branch;
  - every key lies in a room reachable without any locked door, on the door's
    floor or above; doors stay pickable all the same.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import generator_texts as texts
from schemas import DUNGEON_KEYS

# The editor's grid step, in px (frontend LAYOUT_SPACING / ROOM_CELL_PX).
CELL_PX = 180

DIFFICULTIES = ("easy", "normal", "hard")
DIFFICULTY_FACTOR = {"easy": 0.8, "normal": 1.0, "hard": 1.25}
# Stat checks and challenges are won by a member whose stat beats the difficulty. A character
# puts ~10 points a level into stats, so the specialist's main stat runs about 10 + 4 x level;
# a check of 8 + 3.5 x level is theirs to pass and hard for anyone else.
CHECK_BASE, CHECK_PER_LEVEL = 8, 3.5
# Damage of a failed check: a few per cent of a character's health at the level.
DAMAGE_BASE, DAMAGE_PER_LEVEL = 8, 2
GOLD_BASE, GOLD_PER_LEVEL = 10, 4
CHECK_STATS = ("strength", "agility", "intelligence", "endurance")

STAMINA_CORRIDOR = 3
STAMINA_STAIRS = 5
REST_HEAL_PERCENT = 30
REST_AMBUSH_CHANCE = 0.2
EVENT_HEAL_PERCENT = 25

# Of a floor's rooms, this share goes to the main path (the rest to branches).
PATH_SHARE = 0.55
MAX_BRANCH_LEN = 3
MAX_BRANCH_DEPTH = 3
MAX_WALK_TRIES = 60
LOCKS_PER_ROOMS = 8
MAX_LOCKS = 4
BOSS_LOCK_CHANCE = 0.6
SECRET_BRANCH_CHANCE = 0.35
SECRET_LOOP_CHANCE = 0.6
GATE_CHANCE = 0.2
SEAL_CHANCE = 0.2
MAX_GATES = 2
MAX_SEALS = 2
DARK_CHANCE = 0.12
DROP_CHANCE = 0.6
PORTAL_MIN_ROOMS = 10
PORTAL_CHANCE = 0.5
MERCHANT_MIN_ROOMS = 8
PATH_TRAP_CHANCE = 0.15
BRANCH_TRAP_CHANCE = 0.2
CORRIDOR_BATTLE_CHANCE = 0.15
CORRIDOR_BATTLE_ROLL = 0.35
TRAP_ROLLS = (0.6, 0.8, 1.0)
LOOT_CHANCES = (0.5, 0.75, 1.0)
ELITE_CHANCE = {"easy": 0.1, "normal": 0.2, "hard": 0.35}
MAX_PACK = 6

# Weights of what a room is, by where it stands.
PATH_WEIGHTS = {"battle": 45, "trap": 12, "event": 18, "fork": 20, "rest": 5}
PATH_BATTLE_WEIGHT = {"easy": 35, "normal": 45, "hard": 55}
BRANCH_TIP_WEIGHTS = {"treasure": 45, "deadend": 25, "event": 15, "battle": 15}
BRANCH_INNER_WEIGHTS = {"battle": 40, "trap": 20, "event": 25, "fork": 15}

# Mobs within this many levels of the dungeon's; widened step by step if there are too few.
MOB_LEVEL_BELOW, MOB_LEVEL_ABOVE = 4, 2
MOB_LEVEL_WIDEN = 5
MIN_MOB_CHOICE = 2
# Finds: no recipes or one-of-a-kind items; rarer things deeper in the levels.
LOOT_TYPES = ("consumable", "resource", "scroll", "gem", "rune", "misc")
GEAR_TYPES = ("head", "body", "cloak", "belt", "ring", "necklace", "bracelet", "weapon")
RARE_FROM_LEVEL = 10
EPIC_FROM_LEVEL = 25
GEAR_LEVELS_BELOW = 8
ITEM_LEVELS_ABOVE = 2
MERCHANT_MARKUP = 1.5
MERCHANT_PRICE_PER_LEVEL = 5

DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
# Editor handles for a corridor between grid neighbours, by direction (from -> to).
HANDLES = {(1, 0): ("r-2", "l-2"), (-1, 0): ("l-2", "r-2"), (0, 1): ("b-2", "t-2"), (0, -1): ("t-2", "b-2")}

Cell = Tuple[int, int]


@dataclass
class GenParams:
    floors: int = 1
    rooms_per_floor: int = 8
    level: int = 1
    party_size: int = 2
    difficulty: str = "normal"
    theme: str = "stone"
    locks: bool = True
    secrets: bool = True
    disable_rest_rooms: bool = False
    disable_merchants: bool = False
    seed: int = 0
    mob_pool: Optional[List[int]] = None
    boss_pool: Optional[List[int]] = None
    loot_pool: Optional[List[int]] = None


@dataclass
class Catalog:
    """What the dungeon can be filled with: mob templates and items (dicts from the DB)."""
    mobs: List[dict] = field(default_factory=list)   # {id, tier, level}
    items: List[dict] = field(default_factory=list)  # {id, item_type, item_rarity, item_level, price, max_stack_size}


@dataclass
class GenRoom:
    idx: int
    floor: int
    cell: Cell
    on_path: bool
    parent: Optional[int] = None
    top_branch: Optional[int] = None  # the branch root hanging off the path; None on the path
    depth: int = 0  # rooms from the path
    room_type: str = "fork"
    role: str = ""  # entrance / stairs_down / stairs_up / boss
    name: str = ""
    description: str = ""
    config: dict = field(default_factory=dict)


@dataclass
class GenCorridor:
    a: int
    b: int
    passage_type: str = "corridor"
    is_bidirectional: bool = True
    stamina_cost: int = STAMINA_CORRIDOR
    lock_config: Optional[dict] = None
    passage_config: Optional[dict] = None
    trap_chance: float = 0.0
    trap_config: Optional[dict] = None
    random_battle_chance: float = 0.0
    random_battle_mob_ids: Optional[List[int]] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    loop: bool = False


@dataclass
class GenPlan:
    seed: int
    rooms: List[GenRoom]
    corridors: List[GenCorridor]
    # Blue portals: room idx -> target room idx (room ids exist only once written).
    portals: Dict[int, int]
    warnings: List[str]


def _weighted(rng: random.Random, weights: Dict[str, int]) -> str:
    keys = [k for k, w in weights.items() if w > 0]
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


class _Builder:
    def __init__(self, params: GenParams, catalog: Catalog):
        self.p = params
        self.rng = random.Random(params.seed)
        self.factor = DIFFICULTY_FACTOR.get(params.difficulty, 1.0)
        self.rooms: List[GenRoom] = []
        self.corridors: List[GenCorridor] = []
        self.portals: Dict[int, int] = {}
        self.warnings: List[str] = []
        self.paths: Dict[int, List[int]] = {}
        self.cells: Dict[int, Dict[Cell, int]] = {}
        self.used_names: Dict[str, int] = {}
        self.keys: List[str] = []
        self.closed: set = set()
        # Branches a key lies in (None = the path): nothing may bar the way to them.
        self.key_branches: set = set()
        self._pick_mobs(catalog)
        self._pick_items(catalog)

    # ---------- numbers ----------

    def check(self) -> int:
        return max(1, round((CHECK_BASE + CHECK_PER_LEVEL * self.p.level) * self.factor))

    def damage(self) -> int:
        return max(1, round((DAMAGE_BASE + DAMAGE_PER_LEVEL * self.p.level) * self.factor))

    def gold(self) -> int:
        return max(1, round((GOLD_BASE + GOLD_PER_LEVEL * self.p.level) * self.rng.uniform(0.7, 1.3)))

    # ---------- catalog ----------

    def _near_level(self, mobs: List[dict]) -> List[int]:
        lvl = self.p.level
        below, above = MOB_LEVEL_BELOW, MOB_LEVEL_ABOVE
        while True:
            near = [m["id"] for m in mobs if lvl - below <= m["level"] <= lvl + above]
            if len(near) >= MIN_MOB_CHOICE or (below > lvl + 100):
                break
            below += MOB_LEVEL_WIDEN
            above += MOB_LEVEL_WIDEN
        if len(near) < MIN_MOB_CHOICE:
            near = [m["id"] for m in sorted(mobs, key=lambda m: abs(m["level"] - lvl))[:MIN_MOB_CHOICE]]
        return near

    def _pick_mobs(self, catalog: Catalog) -> None:
        by_id = {m["id"]: m for m in catalog.mobs}
        pool = [by_id[i] for i in (self.p.mob_pool or []) if i in by_id] if self.p.mob_pool else catalog.mobs
        normals = [m for m in pool if m["tier"] == "normal"]
        elites = [m for m in pool if m["tier"] == "elite"]
        if self.p.mob_pool:
            # The admin's own list: every mob in it fights in ordinary rooms.
            self.normals = [m["id"] for m in pool if m["tier"] != "boss"] or [m["id"] for m in pool]
            self.elites = [m["id"] for m in elites]
        else:
            self.normals = self._near_level(normals) if normals else []
            self.elites = self._near_level(elites) if elites else []
        if self.p.boss_pool:
            self.bosses = [i for i in self.p.boss_pool if i in by_id]
        else:
            lvl = self.p.level
            for tier in ("boss", "elite", "normal"):
                cands = [m for m in catalog.mobs if m["tier"] == tier]
                if cands:
                    best = min(abs(m["level"] - lvl) for m in cands)
                    self.bosses = [m["id"] for m in cands if abs(m["level"] - lvl) == best]
                    break
            else:
                self.bosses = []
        if not self.normals:
            self.warnings.append("Не нашлось мобов для обычных боёв — укажите их в комнатах вручную")
        if not self.bosses:
            self.warnings.append("Не нашлось босса — укажите его в комнате босса вручную")

    def _pick_items(self, catalog: Catalog) -> None:
        lvl = self.p.level
        rarities = {"common"}
        if lvl >= RARE_FROM_LEVEL:
            rarities.add("rare")
        if lvl >= EPIC_FROM_LEVEL:
            rarities.add("epic")
        items = catalog.items
        if self.p.loot_pool:
            wanted = set(self.p.loot_pool)
            chosen = [i for i in items if i["id"] in wanted]
            self.loot = [i for i in chosen if i["item_type"] not in GEAR_TYPES] or chosen
            self.gear = [i for i in chosen if i["item_type"] in GEAR_TYPES]
        else:
            self.loot = [i for i in items if i["item_type"] in LOOT_TYPES and i["item_rarity"] in rarities
                         and (i.get("item_level") or 0) <= lvl + ITEM_LEVELS_ABOVE]
            self.gear = [i for i in items if i["item_type"] in GEAR_TYPES and i["item_rarity"] in rarities
                         and lvl - GEAR_LEVELS_BELOW <= (i.get("item_level") or 0) <= lvl + ITEM_LEVELS_ABOVE]
        self.wares = [i for i in self.loot if i["item_type"] == "consumable"] or self.loot
        if not self.loot:
            self.warnings.append("Не нашлось предметов для добычи — сундуки и тайники остались пустыми")

    def pack(self, size: int) -> List[int]:
        if not self.normals:
            return []
        ids = [self.rng.choice(self.normals) for _ in range(size)]
        if self.elites and self.rng.random() < ELITE_CHANCE.get(self.p.difficulty, 0.2):
            ids[0] = self.rng.choice(self.elites)
        return ids

    def room_pack(self) -> List[int]:
        n = self.p.party_size
        lo, hi = {"easy": (max(1, n - 1), n), "hard": (n + 1, n + 2)}.get(self.p.difficulty, (n, n + 1))
        return self.pack(min(MAX_PACK, self.rng.randint(lo, hi)))

    def loot_list(self, count: int, pool: Optional[List[dict]] = None, chances=LOOT_CHANCES) -> List[dict]:
        pool = pool if pool is not None else self.loot
        if not pool:
            return []
        picks = self.rng.sample(pool, min(count, len(pool)))
        out = []
        for item in picks:
            stack = item.get("max_stack_size") or 1
            out.append({
                "item_id": item["id"],
                "quantity": self.rng.randint(1, min(3, stack)) if stack > 1 else 1,
                "chance": self.rng.choice(chances),
            })
        return out

    # ---------- layout ----------

    def _free(self, floor: int, cell: Cell) -> bool:
        return cell not in self.cells[floor]

    def _walk(self, floor: int, start: Cell, length: int) -> Optional[List[Cell]]:
        """`length` new free cells in a row from `start` (which is not included)."""
        for _ in range(MAX_WALK_TRIES):
            taken = set(self.cells[floor])
            cur, cells, heading = start, [], None
            for step in range(length):
                last = step == length - 1
                options = []
                for d in DIRS:
                    nxt = (cur[0] + d[0], cur[1] + d[1])
                    if nxt in taken:
                        continue
                    room_ahead = any((nxt[0] + e[0], nxt[1] + e[1]) not in taken and
                                     (nxt[0] + e[0], nxt[1] + e[1]) != cur for e in DIRS)
                    if not last and not room_ahead:
                        continue
                    options.append((d, 3 if d == heading else 1))
                if not options:
                    break
                d = self.rng.choices([o[0] for o in options], weights=[o[1] for o in options])[0]
                cur = (cur[0] + d[0], cur[1] + d[1])
                taken.add(cur)
                cells.append(cur)
                heading = d
            if len(cells) == length:
                return cells
        return None

    def _add_room(self, floor: int, cell: Cell, on_path: bool, parent: Optional[int] = None) -> GenRoom:
        room = GenRoom(idx=len(self.rooms), floor=floor, cell=cell, on_path=on_path, parent=parent)
        if parent is not None and not on_path:
            pr = self.rooms[parent]
            room.top_branch = pr.top_branch if pr.top_branch is not None else room.idx
            room.depth = pr.depth + 1
        self.rooms.append(room)
        self.cells[floor][cell] = room.idx
        return room

    def _connect(self, a: int, b: int, **kw) -> GenCorridor:
        ra, rb = self.rooms[a], self.rooms[b]
        c = GenCorridor(a=a, b=b, **kw)
        dx, dy = rb.cell[0] - ra.cell[0], rb.cell[1] - ra.cell[1]
        # The editor's own rule for a corridor without handles (stairs, drops: other floors).
        d = ((1 if dx > 0 else -1), 0) if abs(dx) > abs(dy) else (0, (1 if dy > 0 else -1))
        c.source_handle, c.target_handle = HANDLES[d]
        self.corridors.append(c)
        return c

    def _connected(self, a: int, b: int) -> bool:
        return any({c.a, c.b} == {a, b} for c in self.corridors)

    def build_floor(self, floor: int, start: Cell, last: bool) -> None:
        self.cells[floor] = {}
        n = self.p.rooms_per_floor
        path_len = max(3, min(n, round(n * PATH_SHARE)))
        first = self._add_room(floor, start, True)
        cells = None
        while cells is None and path_len > 1:
            cells = self._walk(floor, start, path_len - 1)
            if cells is None:
                path_len -= 1
        path = [first.idx]
        for cell in cells or []:
            path.append(self._add_room(floor, cell, True, parent=path[-1]).idx)
            self._connect(path[-2], path[-1])
        self.paths[floor] = path

        # Branches off the path (and off other branches, not too deep).
        left = n - len(path)
        stalls = 0
        while left > 0 and stalls < MAX_WALK_TRIES:
            parents = [i for i in path[:-1]] + [
                r.idx for r in self.rooms if r.floor == floor and not r.on_path and r.depth < MAX_BRANCH_DEPTH
            ]
            parent = self.rng.choice(parents)
            length = min(left, self.rng.choice((1, 1, 2, 2, 3)), MAX_BRANCH_LEN)
            cells = self._walk(floor, self.rooms[parent].cell, length)
            if cells is None:
                stalls += 1
                continue
            prev = parent
            for cell in cells:
                room = self._add_room(floor, cell, False, parent=prev)
                self._connect(prev, room.idx)
                prev = room.idx
            left -= length
        if left > 0:
            self.warnings.append(f"Этаж {floor}: не хватило места на сетке — комнат меньше на {left}")

        # Loops: neighbours of one region (the path, or one branch) join up.
        end = path[-1] if last else None
        pairs = []
        for cell, i in self.cells[floor].items():
            for d in ((1, 0), (0, 1)):
                j = self.cells[floor].get((cell[0] + d[0], cell[1] + d[1]))
                if j is None or j == end or i == end or self._connected(i, j):
                    continue
                if self.rooms[i].top_branch != self.rooms[j].top_branch:
                    continue
                pairs.append((i, j))
        self.rng.shuffle(pairs)
        for i, j in pairs[: self.rng.randint(0, max(1, n // 6))]:
            self._connect(i, j, loop=True)

    def degree(self, idx: int) -> int:
        return sum(1 for c in self.corridors if idx in (c.a, c.b))

    # ---------- what the rooms are ----------

    def assign_types(self) -> None:
        last_floor = self.p.floors
        path_weights = dict(PATH_WEIGHTS)
        path_weights["battle"] = PATH_BATTLE_WEIGHT.get(self.p.difficulty, PATH_WEIGHTS["battle"])
        if self.p.disable_rest_rooms:
            path_weights["rest"] = 0
        for floor, path in self.paths.items():
            for pos, idx in enumerate(path):
                room = self.rooms[idx]
                if pos == 0:
                    room.role = "entrance" if floor == 1 else "stairs_up"
                    room.room_type = "fork"
                elif pos == len(path) - 1:
                    room.role = "boss" if floor == last_floor else "stairs_down"
                    room.room_type = "boss" if floor == last_floor else "fork"
                elif floor == last_floor and pos == len(path) - 2 and not self.p.disable_rest_rooms:
                    room.room_type = "rest"
                else:
                    room.room_type = _weighted(self.rng, path_weights)
        for room in self.rooms:
            if room.on_path:
                continue
            tip = self.degree(room.idx) == 1
            room.room_type = _weighted(self.rng, BRANCH_TIP_WEIGHTS if tip else BRANCH_INNER_WEIGHTS)
        if not any(r.room_type == "treasure" for r in self.rooms):
            spare = [r for r in self.rooms if not r.on_path] or [r for r in self.rooms if not r.role]
            if spare:
                self.rng.choice(spare).room_type = "treasure"
        # The way to the boss is fought through: every floor's path has a battle on it.
        for path in self.paths.values():
            middle = [i for i in path[1:-1] if self.rooms[i].room_type != "rest"]
            if middle and not any(self.rooms[i].room_type == "battle" for i in middle):
                self.rooms[self.rng.choice(middle)].room_type = "battle"
        if not self.p.disable_merchants and len(self.rooms) >= MERCHANT_MIN_ROOMS:
            mid = self.paths[(self.p.floors + 1) // 2]
            spots = [i for i in mid[1:-1] if self.rooms[i].room_type not in ("rest", "battle")]
            if spots:
                self.rooms[spots[len(spots) // 2]].room_type = "merchant"

    def add_portal(self) -> None:
        """A blue portal at the end of a long branch, back to the path: a way home."""
        for floor, path in self.paths.items():
            if len(self.cells[floor]) < PORTAL_MIN_ROOMS or self.rng.random() >= PORTAL_CHANCE:
                continue
            tips = [r for r in self.rooms if r.floor == floor and not r.on_path and r.depth >= 2
                    and self.degree(r.idx) == 1 and r.room_type != "treasure"]
            targets = [i for i in path[:-1] if self.rooms[i].room_type not in ("boss",)]
            if tips and targets:
                tip = self.rng.choice(tips)
                tip.room_type = "teleport"
                self.portals[tip.idx] = targets[0] if len(targets) == 1 else self.rng.choice(targets[: len(targets) // 2 + 1])

    def link_floors(self) -> None:
        for floor in range(1, self.p.floors):
            down, up = self.paths[floor][-1], self.paths[floor + 1][0]
            self._connect(down, up, passage_type="stairs", stamina_cost=STAMINA_STAIRS)
            if self.p.secrets and self.rng.random() < DROP_CHANCE:
                sources = [r.idx for r in self.rooms if r.floor == floor and r.idx != down and r.room_type != "boss"]
                # Never straight into the boss's lair (past its door).
                targets = [i for i in self.paths[floor + 1][1:] if self.rooms[i].room_type != "boss"]
                if sources and targets:
                    self._connect(
                        self.rng.choice(sources), self.rng.choice(targets),
                        passage_type="drop", is_bidirectional=False, stamina_cost=STAMINA_STAIRS,
                        passage_config={"hidden": True, "stat_check": "intelligence",
                                        "difficulty": self.check(), "fail_damage": self.damage()},
                    )

    # ---------- doors, keys and secrets ----------

    def _branch_door(self, root: int) -> Optional[GenCorridor]:
        parent = self.rooms[root].parent
        for c in self.corridors:
            if c.a == parent and c.b == root and not c.loop:
                return c
        return None

    def place_locks_and_secrets(self) -> None:
        roots = [r.idx for r in self.rooms if not r.on_path and r.top_branch == r.idx]
        self.rng.shuffle(roots)
        closed = set()  # branch roots behind a lock or a secret: no key may lie there
        key_kinds = list(DUNGEON_KEYS)
        self.rng.shuffle(key_kinds)
        locks: List[Tuple[GenCorridor, int]] = []  # (door, floor)
        if self.p.locks:
            want = min(MAX_LOCKS, len(key_kinds) - 1, max(1, len(self.rooms) // LOCKS_PER_ROOMS))
            # Branches worth locking: those with a treasure.
            worth = [r for r in roots if any(x.top_branch == r and x.room_type == "treasure" for x in self.rooms)]
            for root in worth[:want]:
                door = self._branch_door(root)
                if door is not None:
                    locks.append((door, self.rooms[root].floor))
                    closed.add(root)
            boss = next((r for r in self.rooms if r.room_type == "boss"), None)
            if boss is not None and len(locks) < len(key_kinds) and self.rng.random() < BOSS_LOCK_CHANCE:
                door = next((c for c in self.corridors if c.b == boss.idx and c.a == boss.parent), None)
                if door is not None:
                    locks.append((door, boss.floor))
        if self.p.secrets:
            for root in roots:
                if root in closed or self.rng.random() >= SECRET_BRANCH_CHANCE:
                    continue
                door = self._branch_door(root)
                if door is not None:
                    door.passage_config = self._secret()
                    closed.add(root)
            for c in self.corridors:
                if c.loop and c.passage_config is None and self.rng.random() < SECRET_LOOP_CHANCE:
                    c.passage_config = self._secret()

        # Keys: one per lock, in a battle or a treasure room outside every closed branch.
        holders = [r for r in self.rooms
                   if r.room_type in ("battle", "treasure") and r.top_branch not in closed]
        used = set()
        placed_keys = []
        self.closed = closed
        for door, floor in locks:
            cands = [r for r in holders if r.idx not in used and r.floor <= floor
                     and r.idx not in (door.a, door.b)]
            if not cands:
                self.warnings.append("Маленькая карта: для одной двери не нашлось места под ключ — она оставлена открытой")
                continue
            holder = self.rng.choice(cands)
            used.add(holder.idx)
            kind = key_kinds[len(placed_keys)]
            placed_keys.append(kind)
            holder.config["key_reward"] = kind
            self.key_branches.add(holder.top_branch)
            door.lock_config = {"key": kind, "pickable": True, "difficulty": self.check()}
        self.keys = placed_keys

    def _secret(self) -> dict:
        kind = self.rng.choice(("mechanism", "illusion", "rubble"))
        return {"secret": {"kind": kind, "difficulty": self.check(), "fail_damage": self.damage(),
                           "hint": texts.SECRET_HINTS[kind]}}

    def corridor_features(self) -> None:
        gates = seals = 0
        for c in self.corridors:
            if c.passage_type != "corridor":
                continue
            on_path = self.rooms[c.a].on_path and self.rooms[c.b].on_path
            if self.rng.random() < (PATH_TRAP_CHANCE if on_path else BRANCH_TRAP_CHANCE) * self.factor:
                c.trap_chance = self.rng.choice(TRAP_ROLLS)
                c.trap_config = {"stat_check": self.rng.choice(CHECK_STATS), "difficulty": self.check(),
                                 "fail_damage": self.damage()}
            if on_path and self.normals and self.rng.random() < CORRIDOR_BATTLE_CHANCE:
                c.random_battle_chance = CORRIDOR_BATTLE_ROLL
                c.random_battle_mob_ids = self.pack(max(1, self.p.party_size - 1))
            # A gate or a seal is a warrior's or a mage's job: a party without one may never get
            # past it, so they only bar a branch off the path that holds no key.
            if not self.p.secrets or c.lock_config or c.passage_config or c.loop:
                continue
            root = self.rooms[c.b]
            if root.on_path or root.top_branch != root.idx or root.idx in self.closed                     or root.idx in self.key_branches:
                continue
            if gates < MAX_GATES and self.rng.random() < GATE_CHANCE:
                c.passage_config = {"gate": {"look": self.rng.choice(("grate", "slab")),
                                             "difficulty": self.check(), "fail_damage": self.damage()}}
                gates += 1
            elif seals < MAX_SEALS and self.rng.random() < SEAL_CHANCE:
                c.passage_config = {"seal": {"difficulty": self.check(), "fail_damage": self.damage()}}
                seals += 1

    # ---------- contents and texts ----------

    def _name(self, kind: str) -> str:
        names = texts.ROOM_NAMES.get(kind) or texts.ROOM_NAMES["fork"]
        fresh = [n for n in names if n not in self.used_names]
        name = self.rng.choice(fresh or names)
        count = self.used_names.get(name, 0) + 1
        self.used_names[name] = count
        return name if count == 1 else f"{name} {count}"

    def _describe(self, kind: str) -> str:
        lines = texts.ROOM_DESCRIPTIONS.get(kind) or texts.ROOM_DESCRIPTIONS["fork"]
        detail = texts.THEME_DETAILS.get(self.p.theme) or texts.THEME_DETAILS["stone"]
        return f"{self.rng.choice(lines)} {self.rng.choice(detail)}"

    def _event(self, room: GenRoom, events: List[dict]) -> None:
        event = events.pop() if events else self.rng.choice(texts.EVENTS)
        room.name = self._unique(event["name"])
        detail = texts.THEME_DETAILS.get(self.p.theme) or texts.THEME_DETAILS["stone"]
        room.description = f"{event['text']} {self.rng.choice(detail)}"
        choices = []
        for ch in event["choices"]:
            kind, text = ch["outcome"], ch["outcome_text"]
            if kind == "reward_or_damage":
                if self.rng.random() < 0.5:
                    kind = "reward"
                else:
                    kind, text = "damage", ch.get("fail_text", text)
            if kind == "key":
                if self.keys:
                    data = {"key": self.rng.choice(self.keys)}
                else:
                    kind, data = "reward", {"gold": self.gold()}
            elif kind == "battle":
                pack = self.room_pack()
                if pack:
                    data = {"mob_template_ids": pack}
                else:
                    kind, data = "damage", {"damage": self.damage()}
            elif kind == "reward":
                data = {"gold": self.gold()}
            elif kind == "heal":
                data = {"heal_percent": EVENT_HEAL_PERCENT}
            elif kind == "damage":
                data = {"damage": self.damage()}
            else:
                data = {}
            choices.append({"text": ch["text"], "outcome_type": kind,
                            "outcome_data": json.dumps(data, ensure_ascii=False), "outcome_text": text})
        room.config.update({"text": event["text"], "choices": choices})

    def _unique(self, name: str) -> str:
        count = self.used_names.get(name, 0) + 1
        self.used_names[name] = count
        return name if count == 1 else f"{name} {count}"

    def fill_rooms(self) -> None:
        events = list(texts.EVENTS)
        self.rng.shuffle(events)
        for room in self.rooms:
            t = room.room_type
            cfg = room.config
            if room.role in ("entrance", "stairs_up", "stairs_down"):
                room.name = self._name(room.role if room.role != "entrance" else "fork") \
                    if room.role != "entrance" else self.rng.choice(texts.ENTRANCE_NAMES)
                self.used_names.setdefault(room.name, 1)
                room.description = self._describe(room.role)
            elif t == "event":
                self._event(room, events)
                continue
            else:
                room.name = self._name(t)
                room.description = self._describe(t)
            if t == "battle":
                cfg["mob_template_ids"] = self.room_pack()
            elif t == "boss":
                escorts = self.pack(self.rng.randint(1, 2)) if self.p.party_size >= 3 else []
                cfg["mob_template_ids"] = ([self.rng.choice(self.bosses)] if self.bosses else []) + escorts
                cfg["boss_loot"] = self.loot_list(2, chances=(1.0,)) + self.loot_list(1, self.gear, chances=(0.5,))
            elif t == "treasure":
                cfg["loot_table"] = self.loot_list(self.rng.randint(2, 3))
            elif t == "trap":
                cfg.update({"stat_check": self.rng.choice(CHECK_STATS), "difficulty": self.check(),
                            "fail_damage": self.damage()})
            elif t == "rest":
                cfg["heal_percent"] = REST_HEAL_PERCENT
                ambush = self.pack(max(1, self.p.party_size - 1))
                if ambush:
                    cfg.update({"ambush_chance": REST_AMBUSH_CHANCE, "ambush_mob_ids": ambush})
            elif t == "merchant":
                cfg["items"] = [
                    {"item_id": i["id"], "stock": self.rng.randint(1, 3),
                     "price": max(1, round((i.get("price") or MERCHANT_PRICE_PER_LEVEL * self.p.level)
                                           * MERCHANT_MARKUP))}
                    for i in self.rng.sample(self.wares, min(self.rng.randint(3, 4), len(self.wares)))
                ]
            elif t == "teleport":
                cfg["portal"] = "blue"
            elif t == "deadend":
                stash = self.loot_list(self.rng.randint(1, 2))
                if stash:
                    cfg["stash"] = {"items": stash, "difficulty": self.check()}
            if self.p.secrets and t in ("fork", "battle", "trap", "deadend", "treasure") \
                    and not room.role and not room.on_path and self.rng.random() < DARK_CHANCE:
                cfg["dark"] = True

    # ---------- all together ----------

    def build(self) -> GenPlan:
        start: Cell = (0, 0)
        for floor in range(1, self.p.floors + 1):
            self.build_floor(floor, start, last=floor == self.p.floors)
            start = self.rooms[self.paths[floor][-1]].cell
        self.assign_types()
        self.add_portal()
        self.link_floors()
        self.place_locks_and_secrets()
        self.corridor_features()
        self.fill_rooms()
        return GenPlan(seed=self.p.seed, rooms=self.rooms, corridors=self.corridors,
                       portals=self.portals, warnings=self.warnings)


def generate(params: GenParams, catalog: Catalog) -> GenPlan:
    return _Builder(params, catalog).build()


def position(room: GenRoom) -> Tuple[float, float]:
    return float(room.cell[0] * CELL_PX), float(room.cell[1] * CELL_PX)
