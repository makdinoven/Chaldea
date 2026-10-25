from pydantic import BaseModel, validator
from typing import Optional, List, Any, Dict
from datetime import datetime


# ---------- Dungeon ----------

FLOOR_STEP_MAX = 2.0


def validate_floor_step(v):
    if v is not None and not 0.0 <= v <= FLOOR_STEP_MAX:
        raise ValueError(f"Прибавка за этаж должна быть от 0 до {FLOOR_STEP_MAX}")
    return v


MAX_FLOOR = 20
PASSAGE_TYPES = ("corridor", "stairs", "drop", "lift")


def validate_floor(v):
    if v is not None and not 1 <= v <= MAX_FLOOR:
        raise ValueError(f"Этаж должен быть от 1 до {MAX_FLOOR}")
    return v


SECRET_KINDS = ("mechanism", "illusion", "rubble")
SECRET_HINT_MAX = 300
# A portcullis or a slab across a corridor, held up and propped by someone strong.
GATE_LOOKS = ("grate", "slab")


def _non_negative_ints(obj: dict, fields, where: str) -> None:
    for field in fields:
        n = obj.get(field)
        if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 0):
            raise ValueError(f"{where}.{field} должен быть неотрицательным числом")


def validate_loot_list(v, where: str):
    """[{item_id, quantity, chance}] — a stash's or a dungeon's random finds."""
    if v is None:
        return v
    if not isinstance(v, list):
        raise ValueError(f"{where} должен быть списком")
    for idx, e in enumerate(v):
        if not isinstance(e, dict):
            raise ValueError(f"{where}: запись {idx + 1} должна быть объектом")
        item_id = e.get("item_id")
        if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id <= 0:
            raise ValueError(f"{where}: запись {idx + 1} — укажите ID предмета")
        q = e.get("quantity", 1)
        if not isinstance(q, int) or isinstance(q, bool) or q < 1:
            raise ValueError(f"{where}: запись {idx + 1} — количество от 1")
        c = e.get("chance", 1)
        if not isinstance(c, (int, float)) or isinstance(c, bool) or not 0 <= c <= 1:
            raise ValueError(f"{where}: запись {idx + 1} — шанс от 0 до 1")
    return v


def validate_passage_config(v):
    """A drop's hidden trap: {hidden, stat_check, difficulty, fail_damage}; None = a plain way down."""
    if v is None:
        return v
    if not isinstance(v, dict):
        raise ValueError("passage_config должен быть объектом")
    if "hidden" in v and not isinstance(v["hidden"], bool):
        raise ValueError("passage_config.hidden должен быть true или false")
    for field in ("difficulty", "fail_damage"):
        n = v.get(field)
        if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 0):
            raise ValueError(f"passage_config.{field} должен быть неотрицательным числом")
    if v.get("stat_check") is not None and not isinstance(v["stat_check"], str):
        raise ValueError("passage_config.stat_check должен быть строкой")
    secret = v.get("secret")
    if secret is not None:
        # A secret way out (FEAT-176): {kind, difficulty, cost, fail_damage, hint}.
        if not isinstance(secret, dict) or secret.get("kind") not in SECRET_KINDS:
            raise ValueError("passage_config.secret: неизвестный вид тайника")
        for field in ("difficulty", "cost", "fail_damage"):
            n = secret.get(field)
            if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 0):
                raise ValueError(f"passage_config.secret.{field} должен быть неотрицательным числом")
        hint = secret.get("hint")
        if hint is not None and (not isinstance(hint, str) or len(hint) > SECRET_HINT_MAX):
            raise ValueError(f"passage_config.secret.hint — строка до {SECRET_HINT_MAX} символов")
    gate = v.get("gate")
    if gate is not None:
        # A gate down across the corridor (FEAT-176): {look, difficulty, cost, fail_damage}.
        if not isinstance(gate, dict) or gate.get("look") not in GATE_LOOKS:
            raise ValueError("passage_config.gate: укажите решётку или плиту")
        if secret is not None:
            raise ValueError("Тайный проход не может быть ещё и перекрыт решёткой")
        _non_negative_ints(gate, ("difficulty", "cost", "fail_damage"), "passage_config.gate")
    seal = v.get("seal")
    if seal is not None:
        # A magic seal on the corridor (FEAT-176): {difficulty, cost, fail_damage}.
        if not isinstance(seal, dict):
            raise ValueError("passage_config.seal должен быть объектом")
        if secret is not None or gate is not None:
            raise ValueError("Печать не ставится на тайный проход или решётку")
        _non_negative_ints(seal, ("difficulty", "cost", "fail_damage"), "passage_config.seal")
    return v


# The looks of the 3D miniature (walls, floor, light), as the frontend draws them.
DUNGEON_THEMES = ("stone", "temple", "cave", "ice", "volcano", "catacombs", "mine", "sewer")


def validate_theme(v):
    if v is not None and v not in DUNGEON_THEMES:
        raise ValueError(f"theme должен быть одним из: {', '.join(DUNGEON_THEMES)}")
    return v


def validate_floor_themes(v):
    """{floor: theme} with floors from 1; an empty map is stored as none."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError("floor_themes должен быть объектом {этаж: оформление}")
    out = {}
    for floor, theme in v.items():
        try:
            n = int(floor)
        except (TypeError, ValueError):
            raise ValueError("floor_themes: этаж должен быть числом")
        if n < 1:
            raise ValueError("floor_themes: этажи считаются с 1")
        validate_theme(theme)
        out[str(n)] = theme
    return out or None


class DungeonCreate(BaseModel):
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str = "static"
    danger_level: str = "safe"
    location_id: int
    recommended_level: Optional[int] = 1
    recommended_party_size: Optional[int] = 1
    cooldown_hours: int = 24
    mob_multiplier: float = 1.0
    loot_multiplier: float = 1.0
    stamina_multiplier: float = 1.0
    difficulty_modifier: float = 1.0
    disable_rest_rooms: bool = False
    disable_merchants: bool = False
    mana_core_chance: float = 0.0
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None
    floor_mob_step: float = 0.2
    floor_loot_step: float = 0.15
    floor_flee_step: float = 0.1
    search_loot: Optional[List[dict]] = None
    theme: str = "stone"
    floor_themes: Optional[Dict[str, str]] = None

    _floor_steps = validator("floor_mob_step", "floor_loot_step", "floor_flee_step", allow_reuse=True)(
        lambda v: validate_floor_step(v))
    _search_loot = validator("search_loot", pre=True, allow_reuse=True)(
        lambda v: validate_loot_list(v, "search_loot"))
    _theme = validator("theme", allow_reuse=True)(validate_theme)
    _floor_themes = validator("floor_themes", pre=True, allow_reuse=True)(validate_floor_themes)

    @validator("stability_type")
    def validate_stability_type(cls, v):
        allowed = ("static", "unstable", "chaotic")
        if v not in allowed:
            raise ValueError(f"stability_type должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("danger_level")
    def validate_danger_level(cls, v):
        allowed = ("safe", "deadly")
        if v not in allowed:
            raise ValueError(f"danger_level должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("mana_core_chance")
    def validate_mana_core_chance(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("mana_core_chance должен быть от 0.0 до 1.0")
        return v


class DungeonUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    lore_text: Optional[str] = None
    stability_type: Optional[str] = None
    danger_level: Optional[str] = None
    location_id: Optional[int] = None
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: Optional[int] = None
    is_active: Optional[bool] = None
    mob_multiplier: Optional[float] = None
    loot_multiplier: Optional[float] = None
    stamina_multiplier: Optional[float] = None
    difficulty_modifier: Optional[float] = None
    disable_rest_rooms: Optional[bool] = None
    disable_merchants: Optional[bool] = None
    mana_core_chance: Optional[float] = None
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None
    floor_mob_step: Optional[float] = None
    floor_loot_step: Optional[float] = None
    floor_flee_step: Optional[float] = None
    search_loot: Optional[List[dict]] = None
    theme: Optional[str] = None
    floor_themes: Optional[Dict[str, str]] = None

    _floor_steps = validator("floor_mob_step", "floor_loot_step", "floor_flee_step", allow_reuse=True)(
        lambda v: validate_floor_step(v))
    _search_loot = validator("search_loot", pre=True, allow_reuse=True)(
        lambda v: validate_loot_list(v, "search_loot"))
    _theme = validator("theme", allow_reuse=True)(validate_theme)

    @validator("theme", pre=True)
    def theme_not_null(cls, v):
        # Left out = unchanged; an explicit null would empty a NOT NULL column.
        if v is None:
            raise ValueError("theme не может быть пустым — уберите поле, чтобы не менять")
        return v
    _floor_themes = validator("floor_themes", pre=True, allow_reuse=True)(validate_floor_themes)

    @validator("stability_type")
    def validate_stability_type(cls, v):
        if v is None:
            return v
        allowed = ("static", "unstable", "chaotic")
        if v not in allowed:
            raise ValueError(f"stability_type должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("danger_level")
    def validate_danger_level(cls, v):
        if v is None:
            return v
        allowed = ("safe", "deadly")
        if v not in allowed:
            raise ValueError(f"danger_level должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("mana_core_chance")
    def validate_mana_core_chance(cls, v):
        if v is None:
            return v
        if not 0.0 <= v <= 1.0:
            raise ValueError("mana_core_chance должен быть от 0.0 до 1.0")
        return v


class DungeonResponse(BaseModel):
    id: int
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str
    danger_level: str
    location_id: int
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: int
    is_active: bool
    mob_multiplier: float
    loot_multiplier: float
    stamina_multiplier: float
    difficulty_modifier: float
    disable_rest_rooms: bool
    disable_merchants: bool
    mana_core_chance: float
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None
    floor_mob_step: float = 0.2
    floor_loot_step: float = 0.15
    floor_flee_step: float = 0.1
    search_loot: Optional[List[dict]] = None
    theme: str = "stone"
    floor_themes: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class DungeonListResponse(BaseModel):
    id: int
    name: str
    stability_type: str
    danger_level: str
    location_id: int
    is_active: bool
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: int
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class DungeonAdminStatusResponse(BaseModel):
    """What keeps players out of a dungeon right now (admin view)."""
    is_on_cooldown: bool
    cooldown_remaining_seconds: int = 0
    # The run inside, if any (one group at a time).
    occupied_session_id: Optional[int] = None


class DungeonAtLocationResponse(BaseModel):
    id: int
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str
    danger_level: str
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    is_on_cooldown: bool = False
    cooldown_remaining_seconds: int = 0
    # FEAT-175: one group per dungeon
    is_occupied: bool = False
    image_url: Optional[str] = None

    class Config:
        orm_mode = True


# ---------- DungeonRoom ----------

VALID_ROOM_TYPES = (
    "battle", "boss", "treasure", "trap", "event",
    "rest", "merchant", "fork", "teleport", "deadend",
)

GRID_MIN, GRID_MAX = 2, 8


def validate_grid_size(v):
    """3D diorama footprint (FEAT-175): None = default, else 2..8 squares."""
    if v is None:
        return v
    if isinstance(v, bool) or not isinstance(v, int) or not GRID_MIN <= v <= GRID_MAX:
        raise ValueError("Размер комнаты должен быть от 2 до 8 клеток")
    return v


VALID_OUTCOME_TYPES = ("nothing", "reward", "damage", "heal", "teleport", "battle", "key")

# Keys of locked doors: found and used only inside one run of one dungeon.
DUNGEON_KEYS = {
    "copper": "Медный ключ",
    "silver": "Серебряный ключ",
    "gold": "Золотой ключ",
    "bone": "Костяной ключ",
    "obsidian": "Обсидиановый ключ",
    "crimson": "Багровый ключ",
}


def validate_lock_config(v):
    """A corridor's lock: None (open) or a known key plus optional picking settings."""
    if v is None:
        return v
    if not isinstance(v, dict):
        raise ValueError("lock_config должен быть объектом")
    if "lever" in v and not isinstance(v["lever"], bool):
        raise ValueError("lock_config.lever должен быть true или false")
    if v.get("key") is None and not v.get("lever"):
        raise ValueError("lock_config: укажите ключ или рычаг")
    if v.get("key") is not None and v["key"] not in DUNGEON_KEYS:
        raise ValueError("lock_config.key: неизвестный ключ")
    if "pickable" in v and not isinstance(v["pickable"], bool):
        raise ValueError("lock_config.pickable должен быть true или false")
    for field in ("difficulty", "pick_cost"):
        n = v.get(field)
        if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 0):
            raise ValueError(f"lock_config.{field} должен быть неотрицательным числом")
    if v.get("stat_check") is not None and not isinstance(v["stat_check"], str):
        raise ValueError("lock_config.stat_check должен быть строкой")
    return v


def _parse_outcome_data(raw) -> dict:
    """outcome_data is saved by the admin editor as a JSON string."""
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw or "{}")
        except (ValueError, TypeError):
            raise ValueError("outcome_data должен быть корректным JSON")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("outcome_data должен быть объектом")
    return raw


def validate_room_config(room_type, v):
    """Shape checks for room_config, shared by create AND update (FEAT-175).
    Cross-row checks (teleport targets in the same dungeon) live in crud."""
    if v is None or room_type is None:
        return v
    if not isinstance(v, dict):
        raise ValueError("room_config должен быть объектом")
    lever = v.get("lever_corridor_id")
    if lever is not None and (not isinstance(lever, int) or isinstance(lever, bool) or lever <= 0):
        raise ValueError("room_config.lever_corridor_id должен быть ID коридора")
    if room_type in ("battle", "boss"):
        ids = v.get("mob_template_ids")
        if ids is not None and (
            not isinstance(ids, list) or not all(isinstance(i, int) and i > 0 for i in ids)
        ):
            raise ValueError("room_config.mob_template_ids должен быть списком положительных ID")
    if room_type == "teleport" and v.get("target_room_id") is not None:
        t = v["target_room_id"]
        if not isinstance(t, int) or isinstance(t, bool) or t <= 0:
            raise ValueError("room_config.target_room_id должен быть положительным ID комнаты")
    if room_type == "teleport":
        if v.get("portal") not in (None, "blue", "red"):
            raise ValueError("room_config.portal должен быть «blue» или «red»")
        ids = v.get("target_room_ids")
        if ids is not None and (
            not isinstance(ids, list)
            or not all(isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in ids)
        ):
            raise ValueError("room_config.target_room_ids должен быть списком положительных ID комнат")
        if "stat_check" in v and v["stat_check"] is not None and not isinstance(v["stat_check"], str):
            raise ValueError("room_config.stat_check должен быть строкой")
        d = v.get("difficulty")
        if d is not None and (not isinstance(d, int) or isinstance(d, bool) or d < 0):
            raise ValueError("room_config.difficulty должен быть неотрицательным числом")
    if room_type in ("treasure", "battle") and v.get("key_reward") is not None \
            and v["key_reward"] not in DUNGEON_KEYS:
        raise ValueError("room_config.key_reward: неизвестный ключ")
    if room_type == "treasure" and "loot_table" in v and not isinstance(v["loot_table"], list):
        raise ValueError("room_config.loot_table должен быть списком")
    if room_type == "boss" and "boss_loot" in v and not isinstance(v["boss_loot"], list):
        raise ValueError("room_config.boss_loot должен быть списком")
    if room_type == "event" and "choices" in v:
        if not isinstance(v["choices"], list):
            raise ValueError("room_config.choices должен быть списком")
        for idx, c in enumerate(v["choices"]):
            if not isinstance(c, dict):
                raise ValueError(f"Вариант {idx + 1}: должен быть объектом")
            otype = c.get("outcome_type", "nothing")
            if otype not in VALID_OUTCOME_TYPES:
                raise ValueError(f"Вариант {idx + 1}: неизвестный тип исхода «{otype}»")
            data = _parse_outcome_data(c.get("outcome_data"))
            if otype == "teleport":
                t = data.get("target_room_id")
                if not isinstance(t, int) or isinstance(t, bool) or t <= 0:
                    raise ValueError(f"Вариант {idx + 1}: укажите ID комнаты для телепорта")
            if otype == "key" and data.get("key") not in DUNGEON_KEYS:
                raise ValueError(f"Вариант {idx + 1}: выберите ключ")
            if otype == "battle":
                ids = data.get("mob_template_ids")
                if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and i > 0 for i in ids):
                    raise ValueError(f"Вариант {idx + 1}: укажите ID мобов для боя")
    if room_type == "merchant" and "items" in v and not isinstance(v["items"], list):
        raise ValueError("room_config.items должен быть списком")
    if room_type == "trap" and "stat_check" in v and not isinstance(v["stat_check"], str):
        raise ValueError("room_config.stat_check должен быть строкой")
    # FEAT-176: a dark room, a stash to search for, a raid on the rest.
    if "dark" in v and not isinstance(v["dark"], bool):
        raise ValueError("room_config.dark должен быть true или false")
    stash = v.get("stash")
    if stash is not None:
        if not isinstance(stash, dict):
            raise ValueError("room_config.stash должен быть объектом")
        validate_loot_list(stash.get("items") or [], "room_config.stash.items")
        _non_negative_ints(stash, ("difficulty",), "room_config.stash")
    if room_type == "rest":
        chance = v.get("ambush_chance")
        if chance is not None and (not isinstance(chance, (int, float)) or isinstance(chance, bool)
                                   or not 0 <= chance <= 1):
            raise ValueError("room_config.ambush_chance должен быть от 0 до 1")
        ids = v.get("ambush_mob_ids")
        if ids is not None and (
            not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in ids)
        ):
            raise ValueError("room_config.ambush_mob_ids должен быть списком положительных ID")
    return v


class DungeonRoomCreate(BaseModel):
    room_type: str
    name: str
    description: str
    image_url: Optional[str] = None
    sort_order: int = 0
    is_entrance: bool = False
    is_boss_room: bool = False
    is_mana_core_room: bool = False
    room_config: Optional[Any] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    grid_w: Optional[int] = None
    grid_d: Optional[int] = None
    floor: int = 1

    _floor = validator("floor", allow_reuse=True)(validate_floor)

    @validator("grid_w", "grid_d")
    def validate_grid(cls, v):
        return validate_grid_size(v)

    @validator("room_type")
    def validate_room_type(cls, v):
        if v not in VALID_ROOM_TYPES:
            raise ValueError(f"room_type должен быть одним из: {', '.join(VALID_ROOM_TYPES)}")
        return v

    @validator("room_config")
    def validate_room_config(cls, v, values):
        return validate_room_config(values.get("room_type"), v)


class DungeonRoomUpdate(BaseModel):
    room_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_entrance: Optional[bool] = None
    is_boss_room: Optional[bool] = None
    is_mana_core_room: Optional[bool] = None
    room_config: Optional[Any] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    grid_w: Optional[int] = None
    grid_d: Optional[int] = None
    floor: Optional[int] = None

    _floor = validator("floor", allow_reuse=True)(validate_floor)

    @validator("grid_w", "grid_d")
    def validate_grid(cls, v):
        return validate_grid_size(v)

    @validator("room_type")
    def validate_room_type(cls, v):
        if v is None:
            return v
        if v not in VALID_ROOM_TYPES:
            raise ValueError(f"room_type должен быть одним из: {', '.join(VALID_ROOM_TYPES)}")
        return v

    @validator("room_config")
    def validate_room_config(cls, v, values):
        # room_type may be absent on update — crud re-validates against the
        # stored type.
        return validate_room_config(values.get("room_type"), v)


class DungeonRoomResponse(BaseModel):
    id: int
    dungeon_id: int
    room_type: str
    name: str
    description: str
    image_url: Optional[str] = None
    sort_order: int
    is_entrance: bool
    is_boss_room: bool
    is_mana_core_room: bool
    room_config: Optional[Any] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    grid_w: Optional[int] = None
    grid_d: Optional[int] = None
    floor: int = 1
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# ---------- Bulk Room Position Update ----------

class RoomPositionItem(BaseModel):
    room_id: int
    position_x: float
    position_y: float

class BulkRoomPositionUpdate(BaseModel):
    positions: List[RoomPositionItem]

    @validator("positions")
    def validate_not_empty(cls, v):
        if not v:
            raise ValueError("positions list must not be empty")
        return v

class BulkPositionUpdateResponse(BaseModel):
    updated: int


# ---------- DungeonCorridor ----------

class DungeonCorridorCreate(BaseModel):
    from_room_id: int
    to_room_id: int
    stamina_cost: int = 5
    is_bidirectional: bool = True
    random_battle_chance: float = 0.0
    random_battle_mob_ids: Optional[Any] = None
    trap_chance: float = 0.0
    trap_config: Optional[Any] = None
    lock_config: Optional[Any] = None
    passage_type: str = "corridor"
    passage_config: Optional[Any] = None
    description: Optional[str] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None

    _lock = validator("lock_config", allow_reuse=True)(validate_lock_config)
    _passage_cfg = validator("passage_config", allow_reuse=True)(validate_passage_config)

    @validator("passage_type")
    def validate_passage_type(cls, v):
        if v not in PASSAGE_TYPES:
            raise ValueError("passage_type: corridor, stairs, drop или lift")
        return v

    @validator("random_battle_chance", "trap_chance")
    def validate_chance(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("Шанс должен быть от 0.0 до 1.0")
        return v

    @validator("from_room_id")
    def validate_not_self_loop(cls, v, values):
        return v

    @validator("to_room_id")
    def validate_to_room(cls, v, values):
        from_id = values.get("from_room_id")
        if from_id is not None and v == from_id:
            raise ValueError("Коридор не может вести из комнаты в саму себя")
        return v


class DungeonCorridorUpdate(BaseModel):
    stamina_cost: Optional[int] = None
    is_bidirectional: Optional[bool] = None
    random_battle_chance: Optional[float] = None
    random_battle_mob_ids: Optional[Any] = None
    trap_chance: Optional[float] = None
    trap_config: Optional[Any] = None
    lock_config: Optional[Any] = None
    passage_type: Optional[str] = None
    passage_config: Optional[Any] = None
    description: Optional[str] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None

    _lock = validator("lock_config", allow_reuse=True)(validate_lock_config)
    _passage_cfg = validator("passage_config", allow_reuse=True)(validate_passage_config)

    @validator("passage_type")
    def validate_passage_type(cls, v):
        if v is not None and v not in PASSAGE_TYPES:
            raise ValueError("passage_type: corridor, stairs, drop или lift")
        return v

    @validator("random_battle_chance", "trap_chance")
    def validate_chance(cls, v):
        if v is None:
            return v
        if not 0.0 <= v <= 1.0:
            raise ValueError("Шанс должен быть от 0.0 до 1.0")
        return v


class DungeonCorridorResponse(BaseModel):
    id: int
    dungeon_id: int
    from_room_id: int
    to_room_id: int
    stamina_cost: int
    is_bidirectional: bool
    random_battle_chance: float
    random_battle_mob_ids: Optional[Any] = None
    trap_chance: float
    trap_config: Optional[Any] = None
    lock_config: Optional[Any] = None
    passage_type: str = "corridor"
    passage_config: Optional[Any] = None
    description: Optional[str] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# ---------- Dungeon Detail (dungeon + rooms + corridors) ----------

class DungeonDetailResponse(BaseModel):
    id: int
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str
    danger_level: str
    location_id: int
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: int
    is_active: bool
    mob_multiplier: float
    loot_multiplier: float
    stamina_multiplier: float
    difficulty_modifier: float
    disable_rest_rooms: bool
    disable_merchants: bool
    mana_core_chance: float
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None
    floor_mob_step: float = 0.2
    floor_loot_step: float = 0.15
    floor_flee_step: float = 0.1
    search_loot: Optional[List[dict]] = None
    theme: str = "stone"
    floor_themes: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    rooms: List[DungeonRoomResponse] = []
    corridors: List[DungeonCorridorResponse] = []

    class Config:
        orm_mode = True


# ---------- Dungeon Validation ----------

class DungeonValidationResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


# ---------- Dungeon Generator (FEAT-177) ----------

GEN_MAX_FLOORS = 5
GEN_ROOMS_MIN, GEN_ROOMS_MAX = 4, 20
GEN_LEVEL_MAX = 200
GEN_PARTY_MAX = 4
GEN_POOL_MAX = 50
GEN_DIFFICULTIES = ("easy", "normal", "hard")


def _id_pool(v):
    if v is None:
        return v
    if len(v) > GEN_POOL_MAX:
        raise ValueError(f"Не больше {GEN_POOL_MAX} ID в списке")
    if not all(isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in v):
        raise ValueError("Список должен состоять из положительных ID")
    return list(dict.fromkeys(v)) or None


class DungeonGenerateRequest(BaseModel):
    floors: int = 1
    rooms_per_floor: int = 8
    level: Optional[int] = None          # the dungeon's recommended level if not given
    party_size: Optional[int] = None     # the dungeon's recommended party size if not given
    difficulty: str = "normal"
    theme: Optional[str] = None          # the dungeon's theme if not given
    locks: bool = True
    secrets: bool = True
    seed: Optional[int] = None           # random if not given; the same seed, the same dungeon
    mob_pool: Optional[List[int]] = None
    boss_pool: Optional[List[int]] = None
    loot_pool: Optional[List[int]] = None
    # The dungeon already has rooms: they are deleted only when this is set.
    replace: bool = False

    _theme = validator("theme", allow_reuse=True)(validate_theme)
    _pools = validator("mob_pool", "boss_pool", "loot_pool", allow_reuse=True)(_id_pool)

    @validator("floors")
    def validate_floors(cls, v):
        if not 1 <= v <= GEN_MAX_FLOORS:
            raise ValueError(f"Этажей — от 1 до {GEN_MAX_FLOORS}")
        return v

    @validator("rooms_per_floor")
    def validate_rooms(cls, v):
        if not GEN_ROOMS_MIN <= v <= GEN_ROOMS_MAX:
            raise ValueError(f"Комнат на этаже — от {GEN_ROOMS_MIN} до {GEN_ROOMS_MAX}")
        return v

    @validator("level")
    def validate_level(cls, v):
        if v is not None and not 1 <= v <= GEN_LEVEL_MAX:
            raise ValueError(f"Уровень — от 1 до {GEN_LEVEL_MAX}")
        return v

    @validator("party_size")
    def validate_party(cls, v):
        if v is not None and not 1 <= v <= GEN_PARTY_MAX:
            raise ValueError(f"Размер группы — от 1 до {GEN_PARTY_MAX}")
        return v

    @validator("difficulty")
    def validate_difficulty(cls, v):
        if v not in GEN_DIFFICULTIES:
            raise ValueError("Сложность: easy, normal или hard")
        return v

    @validator("seed")
    def validate_seed(cls, v):
        if v is not None and not 0 <= v < 2 ** 31:
            raise ValueError("seed — число от 0 до 2147483647")
        return v


class DungeonGenerateResponse(BaseModel):
    seed: int
    rooms: int
    corridors: int
    # What the generator could not do (no mobs of the level, no room for a key…).
    warnings: List[str] = []
    validation: DungeonValidationResponse


# ---------- Session / Party ----------

class SessionCreateRequest(BaseModel):
    character_id: int


class SessionEnterRequest(BaseModel):
    character_id: int


class SessionMemberResponse(BaseModel):
    character_id: int
    name: str
    status: str
    is_leader: bool
    user_id: int
    # Unit frame on the run page (FEAT-175). None when a neighbour service didn't answer.
    avatar: Optional[str] = None
    level: Optional[int] = None
    # The miniature on the board: 1 warrior, 2 rogue, 3 mage.
    class_id: Optional[int] = None
    current_health: Optional[int] = None
    max_health: Optional[int] = None
    current_mana: Optional[int] = None
    max_mana: Optional[int] = None
    current_energy: Optional[int] = None
    max_energy: Optional[int] = None
    current_stamina: Optional[int] = None
    max_stamina: Optional[int] = None
    # The minigame the member is playing right now (its kind), shown over the figurine (FEAT-176).
    busy: Optional[str] = None

    class Config:
        orm_mode = True


class SessionResponse(BaseModel):
    session_id: int
    dungeon_id: int
    status: str
    leader_character_id: int
    members: List[SessionMemberResponse] = []

    class Config:
        orm_mode = True


class RoomExitResponse(BaseModel):
    corridor_id: int
    to_room_id: int
    to_room_name: str
    stamina_cost: int
    explored: bool
    # "reliable" (static dungeon) | "uncertain" (unstable) | "memory_only" (chaotic, explored)
    reliability: str = "reliable"
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    grid_w: Optional[int] = None
    grid_d: Optional[int] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    # A locked door: the key that opens it, whether it is still shut for this run, whether it can be picked.
    lock_key: Optional[str] = None
    locked: bool = False
    lock_pickable: bool = False
    # Opened by a lever somewhere in the dungeon (with or without a key).
    lock_lever: bool = False
    # corridor | stairs | drop | lift, and the floor it leads to.
    passage: str = "corridor"
    to_floor: int = 1
    # A gate still down across the way: "grate" or "slab" (FEAT-176).
    gate: Optional[str] = None
    # A magic seal not broken yet.
    sealed: bool = False
    # What a rogue's scouting learnt of the way (FEAT-176).
    scout: Optional["ScoutInfo"] = None


class RoomViewResponse(BaseModel):
    id: int
    room_type: str
    name: str
    description: str
    image_url: Optional[str] = None
    is_entrance: bool
    is_boss_room: bool
    is_mana_core_room: bool = False
    is_cleared: bool = False
    room_config_visible: Optional[Any] = None
    exits: List[RoomExitResponse] = []
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    grid_w: Optional[int] = None
    grid_d: Optional[int] = None
    floor: int = 1
    # Secret ways out not found yet: what hints at them, and who could open them (FEAT-176).
    secrets: List["SecretInfo"] = []
    # A dark room: `dark_room` always, `dark` while no light burns in it (exits are unknown).
    dark_room: bool = False
    dark: bool = False
    # Searched already in this run (one search a room).
    searched: bool = False
    # Who stands watch over the rest, and whether they are up to it.
    watch: Optional["WatchInfo"] = None

    class Config:
        orm_mode = True


class SecretInfo(BaseModel):
    corridor_id: int
    # mechanism / illusion / rubble
    kind: str
    hint: str


class ScoutInfo(BaseModel):
    """A corridor scouted: what waits at its end and on the way."""
    room_type: str
    room_name: Optional[str] = None
    mob_count: Optional[int] = None
    trap: bool = False
    ambush: bool = False
    disarmed: bool = False


class WatchInfo(BaseModel):
    character_id: int
    passed: bool


RoomExitResponse.update_forward_refs()
RoomViewResponse.update_forward_refs()


class ExploredRoomInfo(BaseModel):
    id: int
    name: str
    room_type: str
    is_cleared: bool
    is_entrance: bool = False
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    grid_w: Optional[int] = None
    grid_d: Optional[int] = None
    # How many enemies stand in a battle/boss room (figurines on the 3D table).
    mob_count: Optional[int] = None
    # A teleport room's portal: "blue" (step in at will) or "red" (a trap).
    portal: Optional[str] = None
    floor: int = 1
    # Its one-off use is spent: the chest emptied (treasure) or the rest taken
    # (the 3D table shows the chest open, the fire burnt down).
    used: bool = False
    # A dark room left unlit (no mage's light in it).
    dark: bool = False


class ExploredCorridorInfo(BaseModel):
    corridor_id: int
    from_room_id: int
    to_room_id: int
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    lock_key: Optional[str] = None
    locked: bool = False
    passage: str = "corridor"


class SeenDoorInfo(BaseModel):
    """A corridor from a visited room into one not yet entered: the party has
    seen its door, so the map keeps it. Only where the room lies and how big
    it is — never what it is."""
    corridor_id: int
    from_room_id: int
    to_room_id: int
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    grid_w: Optional[int] = None
    grid_d: Optional[int] = None
    lock_key: Optional[str] = None
    locked: bool = False
    passage: str = "corridor"
    floor: int = 1


class GroupInventoryItemResponse(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int
    source_description: Optional[str] = None

    class Config:
        orm_mode = True


class ManaCoreInfo(BaseModel):
    revealed: bool = False
    room_id: Optional[int] = None
    room_name: Optional[str] = None
    # True when the party can go there now (boss beaten, core not yet searched)
    accessible: bool = False
    searched: bool = False
    destroyed: bool = False


class SkippedMemberInfo(BaseModel):
    character_id: int
    name: Optional[str] = None
    reason: str


class PartyVote(BaseModel):
    """A member's say on where the party goes next: a door, the blue portal, or "as the leader decides"."""
    character_id: int
    corridor_id: Optional[int] = None
    portal: bool = False


class VoteRequest(BaseModel):
    character_id: int
    # Neither set: "as the leader decides".
    corridor_id: Optional[int] = None
    portal: bool = False


class PartyVotesResponse(BaseModel):
    room_id: Optional[int] = None
    votes: List[PartyVote] = []
    # Living members (not the leader) who have not had their say in this room yet.
    waiting_for: List[int] = []


CHALLENGE_KINDS = ("lockpick",) + SECRET_KINDS + ("shield", "gate", "seal", "search", "watch", "scout", "disarm",
                                                 "insight")
CHALLENGE_MODES = ("game", "roll")


class ChallengeStartRequest(BaseModel):
    character_id: int
    kind: str
    # What it is tried on: the corridor (none for the party shield).
    corridor_id: Optional[int] = None
    # "game" — the minigame, "roll" — a plain roll instead.
    mode: str = "game"

    @validator("kind")
    def _known_kind(cls, v):
        if v not in CHALLENGE_KINDS:
            raise ValueError("Неизвестное испытание")
        return v

    @validator("mode")
    def _known_mode(cls, v):
        if v not in CHALLENGE_MODES:
            raise ValueError("Неизвестный способ")
        return v


class ChallengeResult(BaseModel):
    passed: bool
    kind: str
    # open / broke / time / short (the game) or rolled (a plain roll).
    outcome: str
    message: str
    corridor_id: Optional[int] = None
    character_id: int
    # A plain roll: what was rolled against the difficulty.
    rolled: Optional[int] = None
    difficulty: Optional[int] = None
    # The party shield: how firmly it is held, 0..1.
    block: Optional[float] = None
    # A search: what was found.
    loot: Optional[List[dict]] = None


class FloorExtent(BaseModel):
    """The span of a floor on the editor's grid (cells of 180 px), every room counted, known or not.
    Only the frame: the 3D table lays its rock under all of it from the start."""
    floor: int
    min_col: int
    max_col: int
    min_row: int
    max_row: int


class AmbushInfo(BaseModel):
    """A corridor ambush being fought: the party was caught in this corridor, on its way to `to_room_id`."""
    corridor_id: int
    from_room_id: int
    to_room_id: int


class ShieldInfo(BaseModel):
    """The party shield raised in this room until the party moves on."""
    character_id: int
    block: float


class ChallengeStartResponse(BaseModel):
    kind: str
    # The member is not of the craft: the game is harder.
    off_class: bool
    stamina_consumed: int
    # The game to play (mode "game")…
    challenge_id: Optional[str] = None
    params: Optional[dict] = None
    # …or the roll's outcome at once (mode "roll").
    result: Optional[ChallengeResult] = None


class ChallengeFinishRequest(BaseModel):
    character_id: int
    challenge_id: str
    # The lock: ms from the start at each press. The runes: the runes touched, in order.
    presses: List[int] = []


class ChallengeStepRequest(BaseModel):
    """One move of a game played with the server: a stone pressed (x, y) or pulled (index)."""
    character_id: int
    challenge_id: str
    x: Optional[int] = None
    y: Optional[int] = None
    index: Optional[int] = None


class ChallengeStepResponse(BaseModel):
    kind: str
    # The mechanism: steps from the pressed stone to the lever.
    distance: Optional[int] = None
    # The cave-in: the stone came out without bringing anything down.
    # The seal: the touched node was the true one.
    safe: Optional[bool] = None
    # The seal: the nodes resonating next, and how far off the circle's beat each pulses (0 — in time).
    pulsing: Optional[List[int]] = None
    offsets: Optional[List[float]] = None
    # A search: the way the traces point (0 up, clockwise by eighths).
    way: Optional[int] = None
    # Disarming: the rod was slack, and how many of its neighbours are taut.
    near: Optional[int] = None
    # Set once the game is over.
    result: Optional[ChallengeResult] = None


class LightRequest(BaseModel):
    character_id: int


class LightResponse(BaseModel):
    # "spell" — a mage's light, for the rest of the run; "torch" — until the party leaves.
    how: str
    message: str
    stamina_consumed: int


class ChatSayRequest(BaseModel):
    character_id: int
    text: str


class ChatEntry(BaseModel):
    """A line of the run's chat: a member's ("say") or the log's ("log")."""
    id: str
    # ms since the epoch
    at: int
    kind: str
    text: str
    # info / good / bad (the log's colour)
    tone: str = "info"
    character_id: Optional[int] = None
    name: Optional[str] = None


PING_KINDS = ("go", "danger", "look")


class PingRequest(BaseModel):
    character_id: int
    # "go" — this way, "danger" — careful, "look" — look here.
    kind: str
    room_id: Optional[int] = None
    corridor_id: Optional[int] = None

    @validator("kind")
    def _known_kind(cls, v):
        if v not in PING_KINDS:
            raise ValueError("Неизвестная метка")
        return v


class SessionStateResponse(BaseModel):
    session_id: int
    dungeon_id: int
    dungeon_name: str
    location_id: int = 0
    stability_type: str = "static"
    danger_level: str = "safe"
    status: str
    phase: str
    current_room: Optional[RoomViewResponse] = None
    members: List[SessionMemberResponse] = []
    group_inventory: List[GroupInventoryItemResponse] = []
    active_battle_id: Optional[int] = None
    explored_rooms: List[ExploredRoomInfo] = []
    explored_corridors: List[ExploredCorridorInfo] = []
    seen_doors: List[SeenDoorInfo] = []
    # Keys the party has found this run (kinds of DUNGEON_KEYS).
    keys: List[str] = []
    # How many floors the dungeon has (the current one is current_room.floor).
    floors: int = 1
    # FEAT-175
    mana_core: Optional[ManaCoreInfo] = None
    finalized: bool = False
    cooldown_until: Optional[datetime] = None
    knocked_out_until: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    abandon_at: Optional[datetime] = None
    skipped_members: List[SkippedMemberInfo] = []
    # Where the party goes next is decided together (FEAT-176).
    votes: List[PartyVote] = []
    waiting_for: List[int] = []
    shield: Optional[ShieldInfo] = None
    ambush: Optional[AmbushInfo] = None
    extents: List[FloorExtent] = []
    # How the miniature looks: the dungeon's theme and each floor's own, if set.
    theme: str = "stone"
    floor_themes: Dict[str, str] = {}

    class Config:
        orm_mode = True


# ---------- Movement ----------

class MoveRequest(BaseModel):
    character_id: int
    corridor_id: int


class PickLockRequest(BaseModel):
    character_id: int
    corridor_id: int


class PickLockResponse(BaseModel):
    passed: bool
    message: str
    stat_check: str
    difficulty: int
    best_character: Optional[str] = None
    best_value: Optional[int] = None
    stamina_consumed: int


class CorridorEventResponse(BaseModel):
    type: str  # "battle", "trap", "safe"
    details: Optional[dict] = None
    message: str
    # Flat copies of the most used `details` fields (the frontend reads them
    # at top level).
    battle_id: Optional[int] = None
    mob_names: Optional[List[str]] = None
    stat_check: Optional[str] = None
    difficulty: Optional[int] = None
    best_character: Optional[str] = None
    best_value: Optional[int] = None
    passed: Optional[bool] = None
    damage: Optional[int] = None


class MoveResponse(BaseModel):
    corridor_event: Optional[CorridorEventResponse] = None
    new_room: Optional[RoomViewResponse] = None
    stamina_consumed: int
    room_event: Optional[dict] = None


# ---------- Battle Callback (internal) ----------

class BattleCallbackRequest(BaseModel):
    battle_id: int
    session_id: int
    winner_team: Optional[int] = None
    defeated_characters: List[int] = []
    battle_loot: Optional[List[dict]] = None
    # True when the battle was force-finished (admin / abandonment): no winner.
    aborted: bool = False


# ---------- Room Interaction ----------

class InteractRequest(BaseModel):
    character_id: int
    action: str
    choice_index: Optional[int] = None
    target_character_id: Optional[int] = None
    item_id: Optional[int] = None
    quantity: Optional[int] = None


class InteractResponse(BaseModel):
    action: str
    success: bool
    message: str
    loot_gained: Optional[List[dict]] = None
    damage_taken: Optional[int] = None
    effect_applied: Optional[str] = None
    gold_spent: Optional[int] = None
    teleported_to: Optional[dict] = None
    key_found: Optional[str] = None


# ---------- Flee ----------

class FleeRequest(BaseModel):
    character_id: int


class FleeItemInfo(BaseModel):
    item_id: int
    quantity: int
    item_name: Optional[str] = None


class FleeResponse(BaseModel):
    status: str
    items_lost: List[FleeItemInfo] = []
    items_remaining: List[FleeItemInfo] = []
    message: str


# ---------- Loot Distribution ----------

class LootDistributionItem(BaseModel):
    item_id: int
    quantity: int
    to_character_id: int


class GiveItemRequest(BaseModel):
    """FEAT-178: the leader hands a found consumable to a member's camp backpack mid-run."""
    character_id: int
    target_character_id: int
    item_id: int
    quantity: int = 1

    @validator("quantity")
    def _positive(cls, v):
        if not 1 <= v <= 999:
            raise ValueError("Количество — от 1 до 999")
        return v


class GiveItemResponse(BaseModel):
    message: str
    group_inventory: List[GroupInventoryItemResponse] = []


class DistributeLootRequest(BaseModel):
    character_id: int
    distributions: List[LootDistributionItem] = []


class DistributeLootResponse(BaseModel):
    success: bool
    message: str
    remaining_inventory: List[GroupInventoryItemResponse] = []
    # Deliveries inventory-service refused; those items were put back into the
    # group inventory.
    failed: List[dict] = []


# ---------- Finalize ----------

class FinalizeRequest(BaseModel):
    character_id: int
    force: bool = False


class FinalizeResponse(BaseModel):
    message: str
    cooldown_until: Optional[datetime] = None
    items_lost: int = 0


# ---------- Admin: Sessions ----------

class AdminSessionMemberResponse(BaseModel):
    character_id: int
    user_id: int
    status: str

    class Config:
        orm_mode = True


class AdminSessionResponse(BaseModel):
    id: int
    dungeon_id: int
    dungeon_name: Optional[str] = None
    leader_character_id: int
    status: str
    current_room_id: Optional[int] = None
    started_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    finalized_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    members: List[AdminSessionMemberResponse] = []

    class Config:
        orm_mode = True
