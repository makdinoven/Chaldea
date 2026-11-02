import math
from datetime import datetime
from sqlalchemy.orm import Session
import models, schemas
import regen
import traceback
from sqlalchemy import text as sa_text
from constants import (
    BASE_DODGE, BASE_CRIT, BASE_CRIT_DMG,
    CLASS_MAIN_ATTRIBUTE,
    PRIMARY_DERIVED_EFFECTS, PRIMARY_ATTRIBUTE_KEYS, RESOURCE_STATS,
    FLAT_MODIFIER_KEYS, DERIVED_FLAT_KEYS, LEVEL_RESOURCE_GROWTH,
)
from stat_caps import effective_stat, effective_delta

# Stored float derived fields are rounded to this many decimals by the absolute
# formulas (creation / rebuild). eff() of an integer is a multiple of 0.25, so
# 0.1 * eff needs 3 decimals; 4 keeps a margin and stays readable.
DERIVED_ROUND_DIGITS = 4


def level_resource_bonus(resource: str, class_id, level) -> int:
    """FEAT-196: level * rate(class, resource). Unknown/None class or a
    missing/non-positive level -> 0 (never raises)."""
    rates = LEVEL_RESOURCE_GROWTH.get(class_id)
    if not rates or level is None or level < 1:
        return 0
    return int(level) * rates.get(resource, 0)


def resource_max(resource: str, value, level=None, class_id=None) -> int:
    """FEAT-195/196: max_R = BASE_R + floor(m_R * eff(R)) + level * rate(class, R).
    The level term is outside eff (not a stat, not capped)."""
    base, multiplier = RESOURCE_STATS[resource]
    return int(base + math.floor(multiplier * effective_stat(value or 0))
               + level_resource_bonus(resource, class_id, level))


def get_level_and_class(db: Session, character_id: int):
    """FEAT-196: (level, id_class) from the shared `characters` table;
    (None, None) when the row is missing. SQL errors propagate."""
    row = db.execute(
        sa_text("SELECT level, id_class FROM characters WHERE id = :cid"),
        {"cid": character_id},
    ).fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def sync_level_resources(attr, level, class_id) -> None:
    """FEAT-196: set every max_R to its absolute target for (stats, level,
    class). Growth moves current by the same amount (like investing points, no
    extra top-up); a drop clamps current down to the new max. Idempotent.
    No commit."""
    for resource in RESOURCE_STATS:
        target = resource_max(resource, getattr(attr, resource), level, class_id)
        old_max = getattr(attr, f"max_{resource}") or 0
        diff = target - old_max
        if diff == 0:
            continue
        current = getattr(attr, f"current_{resource}") or 0
        if diff > 0:
            current += diff
        current = max(0, min(current, target))
        setattr(attr, f"max_{resource}", target)
        setattr(attr, f"current_{resource}", current)


def _derived_from_primaries(attr, flat: dict) -> dict:
    """Absolute derived values: BASE + flat + sum(k * eff(primary total))."""
    values = {field: float(flat.get(field, 0) or 0) for field in DERIVED_FLAT_KEYS}
    values["dodge"] += BASE_DODGE
    values["critical_hit_chance"] += BASE_CRIT
    for primary, effects in PRIMARY_DERIVED_EFFECTS.items():
        eff = effective_stat(getattr(attr, primary, 0) or 0)
        for field, per_point in effects.items():
            values[field] += per_point * eff
    return {field: round(value, DERIVED_ROUND_DIGITS) for field, value in values.items()}


def compute_derived_stats(attr, class_id=None, level=None):
    """
    Compute all derived stats on a FRESH CharacterAttributes ORM object
    (creation: no gear, perks or food yet) from its base (upgradeable) stats.
    Sets resource maximums, combat stats and resistances in-place, and clears
    the `damage` bonus field. FEAT-195: every primary converts through
    stat_caps.effective_stat (soft cap 100, hard cap 200).

    :param class_id, level: FEAT-196 per-level resource growth
        (level * rate(class)); the class's main attribute itself is applied
        by the damage formula, not here.
    """
    # Resource stats; clamp current to not exceed new max
    for resource in RESOURCE_STATS:
        new_max = resource_max(resource, getattr(attr, resource), level, class_id)
        setattr(attr, f"max_{resource}", new_max)
        current = getattr(attr, f"current_{resource}")
        setattr(attr, f"current_{resource}", new_max if current is None else min(current, new_max))

    # Combat stats and resistances (no flat sources on a fresh row)
    for field, value in _derived_from_primaries(attr, {}).items():
        setattr(attr, field, value)
    attr.critical_damage = BASE_CRIT_DMG  # Only modified by items

    # `damage` is a PURE BONUS field: equipment, sharpening and perks only.
    #
    # It used to be seeded with the class's main attribute, but the damage
    # formula adds that attribute itself — `base = base_stat + damage + weapon`
    # (battle-service/app/battle_engine.py) and the same shape on the profile
    # (frontend .../StatsTab/damage.ts). A warrior's point of strength therefore
    # bought two points of damage. One strength = one damage, so the attribute
    # is counted once, on the formula's side, and nothing seeds it here.
    attr.damage = 0


def apply_attribute_modifiers(attr, modifiers: dict) -> None:
    """FEAT-195: the ONE way to add modifiers to an already-locked
    CharacterAttributes row (stat upgrade, equipment, perks, food).

    - Resources (health/mana/energy/stamina): value += delta (clamped >= 0);
      max/current move by floor(m*eff(new)) - floor(m*eff(old)); current is
      clamped to [0, max].
    - Primaries: value += delta; every derived field of that primary gets
      k * (eff(new) - eff(old)). eff is a function of the TOTAL, so the deltas
      telescope: equip -> anything -> unequip returns exactly to eff of the rest.
    - Everything else in FLAT_MODIFIER_KEYS: plain add.
    No commit/flush.
    """
    if not modifiers:
        return

    for resource in RESOURCE_STATS:
        delta = modifiers.get(resource, 0)
        if not delta:
            continue
        old_val = getattr(attr, resource) or 0
        new_val = old_val + delta
        if new_val < 0:
            new_val = 0
        diff = resource_max(resource, new_val) - resource_max(resource, old_val)
        new_max = (getattr(attr, f"max_{resource}") or 0) + diff
        new_current = (getattr(attr, f"current_{resource}") or 0) + diff
        new_current = max(0, min(new_current, new_max))
        setattr(attr, resource, new_val)
        setattr(attr, f"max_{resource}", new_max)
        setattr(attr, f"current_{resource}", new_current)

    for key in PRIMARY_ATTRIBUTE_KEYS:
        delta = modifiers.get(key, 0)
        if not delta:
            continue
        old_val = getattr(attr, key) or 0
        new_val = old_val + delta
        setattr(attr, key, new_val)
        effects = PRIMARY_DERIVED_EFFECTS.get(key)
        if effects:
            worth = effective_delta(old_val, new_val)
            for field, per_point in effects.items():
                setattr(attr, field, (getattr(attr, field) or 0) + per_point * worth)

    for key in FLAT_MODIFIER_KEYS:
        value = modifiers.get(key, 0)
        if value:
            setattr(attr, key, (getattr(attr, key) or 0) + value)


def _sum_derived_flats(sources) -> dict:
    """Sum the derived-field keys (res_*, dodge, crit chance) of modifier dicts."""
    flat = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in DERIVED_FLAT_KEYS:
            value = source.get(key)
            if not value:
                continue
            try:
                flat[key] = flat.get(key, 0.0) + float(value)
            except (TypeError, ValueError):
                continue
    return flat


def rebuild_derived_stats(db: Session, attr, equipment_mods: dict) -> None:
    """FEAT-195: absolute, idempotent, gear/perk/food-aware rebuild of the
    stored derived stats.

    The caller has locked the row and called regen.settle_regen (expired food
    is already removed). Derived = BASE + flats (equipment + perks + active
    food) + k*eff(primary total). Resource max = BASE + floor(m*eff(R))
    + level*rate(class) (FEAT-196, level/class read from `characters`),
    current is only clamped down (no top-up).
    Untouched: the 10 primaries (already totals), damage, critical_damage,
    vul_*, experience, regen fields. No commit.
    """
    sources = [equipment_mods or {}]
    perks = (
        db.query(models.Perk)
        .join(models.CharacterPerk, models.CharacterPerk.perk_id == models.Perk.id)
        .filter(models.CharacterPerk.character_id == attr.character_id)
        .all()
    )
    for perk in perks:
        sources.append(build_perk_modifiers_dict(perk))
    satiety = regen.get_satiety(db, attr.character_id)
    if satiety is not None:
        sources.append(satiety.modifiers or {})

    for field, value in _derived_from_primaries(attr, _sum_derived_flats(sources)).items():
        setattr(attr, field, value)

    level, class_id = get_level_and_class(db, attr.character_id)
    for resource in RESOURCE_STATS:
        new_max = resource_max(resource, getattr(attr, resource), level, class_id)
        setattr(attr, f"max_{resource}", new_max)
        current = getattr(attr, f"current_{resource}") or 0
        setattr(attr, f"current_{resource}", max(0, min(current, new_max)))


# Функция для создания атрибутов персонажа

def create_character_attributes(db: Session, attributes: schemas.CharacterAttributesCreate):
    """
    Создает атрибуты персонажа с учетом переданных stat-поинтов.
    Derived stats (resistances, dodge, crit, resources) are computed
    from the base stats before committing.
    """
    # Создаем атрибуты персонажа с base stats
    db_attributes = models.CharacterAttributes(
        character_id=attributes.character_id,
        strength=attributes.strength,
        agility=attributes.agility,
        intelligence=attributes.intelligence,
        endurance=attributes.endurance,
        health=attributes.health,
        mana=attributes.mana,
        energy=attributes.energy,
        stamina=attributes.stamina,
        charisma=attributes.charisma,
        luck=attributes.luck,
    )

    # FEAT-196: level/class for the per-level resource growth. The caller's
    # `characters` row is usually only flushed (invisible to this connection),
    # so the body wins; the DB is a fallback for old callers; else no bonus.
    level, class_id = attributes.level, attributes.id_class
    if level is None or class_id is None:
        db_level, db_class = get_level_and_class(db, attributes.character_id)
        level = db_level if level is None else level
        class_id = db_class if class_id is None else class_id

    # Set current resources to max before compute (so clamp works correctly)
    for resource in RESOURCE_STATS:
        setattr(db_attributes, f"current_{resource}",
                resource_max(resource, getattr(attributes, resource), level, class_id))

    # Compute all derived stats (resources, combat, resistances, damage)
    compute_derived_stats(db_attributes, class_id=class_id, level=level)

    # FEAT-164: start the passive-regen clock at creation.
    db_attributes.regen_anchor_at = datetime.utcnow()

    db.add(db_attributes)
    db.commit()
    db.refresh(db_attributes)
    return db_attributes
def get_passive_experience(db: Session, character_id: int):
    """
    Получает passive_experience персонажа.
    """
    attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).first()
    if not attr:
        return None
    return attr.passive_experience

def update_passive_experience(db: Session, character_id: int, new_passive_experience: int):
    """
    Обновляет passive_experience персонажа.
    """
    attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).first()
    if not attr:
        return None
    attr.passive_experience = new_passive_experience
    db.commit()
    db.refresh(attr)
    return attr.passive_experience


def grant_active_experience(db: Session, character_id: int, delta: int):
    """
    Админская операция: выдать/снять активный опыт персонажу.
    Итоговое значение клампается до 0 (не может быть отрицательным).
    Возвращает новое значение active_experience или None, если атрибуты не найдены.
    """
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).with_for_update().first()
    if not attr:
        return None
    new_value = (attr.active_experience or 0) + delta
    if new_value < 0:
        new_value = 0
    attr.active_experience = new_value
    db.commit()
    db.refresh(attr)
    return attr.active_experience


def refund_stamina(db: Session, character_id: int, amount: int):
    """
    Возвращает (рефандит) указанное количество выносливости персонажу (FEAT-128).
    Использует with_for_update() — конкурентные рефанды не должны двойно начислять.
    Кэп: current_stamina не может превысить max_stamina (избыточный рефанд молча обрезается).

    :return: tuple (attr, refunded) если успех, или (None, 0) если атрибуты не найдены.
             refunded — фактически зачисленная величина (с учётом cap).
    """
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).with_for_update().first()
    if not attr:
        return None, 0

    # FEAT-164: credit passive regen before changing the value.
    stats_changed = regen.settle_regen(db, attr)

    before = int(attr.current_stamina or 0)
    max_st = int(attr.max_stamina or 0)
    new_value = before + int(amount)
    if new_value > max_st:
        new_value = max_st
    refunded = new_value - before
    attr.current_stamina = new_value
    db.commit()
    if stats_changed:
        regen.reconcile_perks_after_expiry(db, character_id)
    db.refresh(attr)
    return attr, refunded


# --- Cumulative Stats ---

# Valid counter columns (excludes id/character_id which are not incrementable)
CUMULATIVE_STATS_COLUMNS = {
    c.name for c in models.CharacterCumulativeStats.__table__.columns
    if c.name not in ("id", "character_id")
}


def get_cumulative_stats(db: Session, character_id: int):
    """Returns the cumulative stats row for a character, or None."""
    return db.query(models.CharacterCumulativeStats).filter(
        models.CharacterCumulativeStats.character_id == character_id
    ).first()


def get_or_create_cumulative_stats(db: Session, character_id: int):
    """Returns existing row or lazily creates one with defaults."""
    row = get_cumulative_stats(db, character_id)
    if row is None:
        row = models.CharacterCumulativeStats(character_id=character_id)
        db.add(row)
        db.flush()
    return row


def increment_cumulative_stats(
    db: Session,
    character_id: int,
    increments: dict,
    set_max: dict,
    resets: dict = None,
):
    """
    Atomically increments cumulative stat counters, applies set_max (GREATEST),
    and resets fields to fixed values.
    Creates the row lazily if it doesn't exist.
    Returns the updated row.
    """
    from sqlalchemy import text as sa_text

    row = get_or_create_cumulative_stats(db, character_id)

    # Build atomic UPDATE SET clauses
    set_clauses = []
    params = {"cid": character_id}

    # Resets are applied first (before increments) so that
    # e.g. reset current_win_streak=0 then increment it by 1 is not possible
    # in a single call. Resets simply set the field to the given value.
    if resets:
        for field, value in resets.items():
            param_name = f"rst_{field}"
            set_clauses.append(f"`{field}` = :{param_name}")
            params[param_name] = value

    for field, delta in increments.items():
        if delta == 0:
            continue
        param_name = f"inc_{field}"
        set_clauses.append(f"`{field}` = `{field}` + :{param_name}")
        params[param_name] = delta

    for field, value in set_max.items():
        param_name = f"max_{field}"
        set_clauses.append(f"`{field}` = GREATEST(`{field}`, :{param_name})")
        params[param_name] = value

    if set_clauses:
        sql = sa_text(
            f"UPDATE character_cumulative_stats SET {', '.join(set_clauses)} "
            f"WHERE character_id = :cid"
        )
        db.execute(sql, params)

    # Auto-sync max_win_streak with current_win_streak after increment
    if "current_win_streak" in increments:
        db.execute(sa_text(
            "UPDATE character_cumulative_stats "
            "SET max_win_streak = GREATEST(max_win_streak, current_win_streak) "
            "WHERE character_id = :cid"
        ), {"cid": character_id})

    db.commit()
    db.refresh(row)
    return row


# --- Perks CRUD ---


def _resolve_quest_name(quest_id: int) -> str | None:
    """Resolve quest title directly from the shared DB (quests table)."""
    from database import SessionLocal
    try:
        db = SessionLocal()
        row = db.execute(
            sa_text("SELECT title FROM quests WHERE id = :qid"),
            {"qid": quest_id},
        ).fetchone()
        db.close()
        return row[0] if row else None
    except Exception:
        return None


# Valid attribute keys for flat bonuses (same as simple_keys in apply_modifiers + resource keys)
VALID_FLAT_BONUS_KEYS = {
    "health", "mana", "energy", "stamina",
    "strength", "agility", "intelligence", "endurance", "charisma", "luck",
    "damage", "dodge", "res_effects",
    "res_physical", "res_catting", "res_crushing", "res_piercing",
    "res_magic", "res_fire", "res_ice", "res_watering",
    "res_electricity", "res_wind", "res_sainting", "res_damning",
    "critical_hit_chance", "critical_damage",
    "vul_effects", "vul_physical", "vul_catting", "vul_crushing", "vul_piercing",
    "vul_magic", "vul_fire", "vul_ice", "vul_watering",
    "vul_electricity", "vul_sainting", "vul_wind", "vul_damning",
}

VALID_CATEGORIES = {"combat", "trade", "exploration", "progression", "usage"}
VALID_RARITIES = {"common", "rare", "legendary"}
VALID_CONDITION_TYPES = {
    "cumulative_stat", "character_level", "attribute", "quest", "admin_grant",
    "perk_count", "has_perk", "gold_balance",
}
VALID_OPERATORS = {">=", "<=", "==", ">", "<"}


def validate_perk_data(category: str = None, rarity: str = None, conditions=None, bonuses=None):
    """
    Validate perk fields. Raises ValueError with Russian message on invalid data.
    """
    if category is not None and category not in VALID_CATEGORIES:
        raise ValueError(
            f"Недопустимая категория '{category}'. "
            f"Допустимые: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    if rarity is not None and rarity not in VALID_RARITIES:
        raise ValueError(
            f"Недопустимая редкость '{rarity}'. "
            f"Допустимые: {', '.join(sorted(VALID_RARITIES))}"
        )
    if conditions is not None:
        for i, cond in enumerate(conditions):
            cond_dict = cond if isinstance(cond, dict) else cond.dict()
            ctype = cond_dict.get("type")
            if ctype not in VALID_CONDITION_TYPES:
                raise ValueError(
                    f"Условие #{i + 1}: неизвестный тип '{ctype}'. "
                    f"Допустимые: {', '.join(sorted(VALID_CONDITION_TYPES))}"
                )
            operator = cond_dict.get("operator")
            if operator not in VALID_OPERATORS:
                raise ValueError(
                    f"Условие #{i + 1}: неизвестный оператор '{operator}'. "
                    f"Допустимые: {', '.join(sorted(VALID_OPERATORS))}"
                )
    if bonuses is not None:
        bonuses_dict = bonuses if isinstance(bonuses, dict) else bonuses.dict()
        flat = bonuses_dict.get("flat", {})
        for key in flat:
            if key not in VALID_FLAT_BONUS_KEYS:
                raise ValueError(
                    f"Недопустимый ключ бонуса '{key}'. "
                    f"Допустимые: {', '.join(sorted(VALID_FLAT_BONUS_KEYS))}"
                )


def get_perk_by_id(db: Session, perk_id: int):
    """Returns a Perk by ID, or None."""
    return db.query(models.Perk).filter(models.Perk.id == perk_id).first()


def create_perk(db: Session, perk_data: schemas.PerkCreate) -> models.Perk:
    """Create a new perk after validation."""
    validate_perk_data(
        category=perk_data.category,
        rarity=perk_data.rarity,
        conditions=perk_data.conditions,
        bonuses=perk_data.bonuses,
    )

    conditions_json = [c.dict() for c in perk_data.conditions]
    bonuses_json = perk_data.bonuses.dict()

    perk = models.Perk(
        name=perk_data.name,
        description=perk_data.description,
        category=perk_data.category,
        rarity=perk_data.rarity,
        icon=perk_data.icon,
        conditions=conditions_json,
        bonuses=bonuses_json,
        sort_order=perk_data.sort_order,
    )
    db.add(perk)
    db.commit()
    db.refresh(perk)
    return perk


def update_perk(db: Session, perk_id: int, perk_data: schemas.PerkUpdate):
    """
    Update perk fields. Returns (perk, old_bonuses_flat) tuple.
    old_bonuses_flat is non-None only when bonuses.flat changed and the perk has holders.
    """
    perk = get_perk_by_id(db, perk_id)
    if perk is None:
        return None, None

    update_dict = perk_data.dict(exclude_unset=True)

    # Validate changed fields
    validate_perk_data(
        category=update_dict.get("category"),
        rarity=update_dict.get("rarity"),
        conditions=perk_data.conditions if "conditions" in update_dict else None,
        bonuses=perk_data.bonuses if "bonuses" in update_dict else None,
    )

    old_flat = dict(perk.bonuses.get("flat", {})) if perk.bonuses else {}
    new_flat = None

    for field, value in update_dict.items():
        if field == "conditions":
            setattr(perk, field, [c if isinstance(c, dict) else c.dict() for c in value])
        elif field == "bonuses":
            new_flat = value.flat if hasattr(value, "flat") else value.get("flat", {})
            if hasattr(new_flat, "copy"):
                new_flat = dict(new_flat)
            setattr(perk, field, value.dict() if hasattr(value, "dict") else value)
        else:
            setattr(perk, field, value)

    # Determine if flat bonuses changed and perk has holders
    bonuses_changed = False
    if new_flat is not None and new_flat != old_flat:
        holder_count = db.query(models.CharacterPerk).filter(
            models.CharacterPerk.perk_id == perk_id
        ).count()
        if holder_count > 0:
            bonuses_changed = True

    db.commit()
    db.refresh(perk)

    if bonuses_changed:
        return perk, old_flat
    return perk, None


def delete_perk(db: Session, perk_id: int):
    """
    Delete a perk. Reverses flat bonuses for all holders first.
    Returns (affected_characters_count, perk_bonuses_flat) or (None, None) if not found.
    """
    perk = get_perk_by_id(db, perk_id)
    if perk is None:
        return None, None

    flat_bonuses = perk.bonuses.get("flat", {}) if perk.bonuses else {}

    # Get all holders
    holders = db.query(models.CharacterPerk).filter(
        models.CharacterPerk.perk_id == perk_id
    ).all()

    affected = len(holders)

    # Delete perk (CASCADE deletes character_perks)
    db.delete(perk)
    db.commit()

    return affected, flat_bonuses, [h.character_id for h in holders]


def get_perks_paginated(
    db: Session,
    page: int = 1,
    per_page: int = 20,
    category: str = None,
    rarity: str = None,
    search: str = None,
):
    """Returns paginated perks list with total count."""
    query = db.query(models.Perk)

    if category:
        query = query.filter(models.Perk.category == category)
    if rarity:
        query = query.filter(models.Perk.rarity == rarity)
    if search:
        query = query.filter(models.Perk.name.ilike(f"%{search}%"))

    total = query.count()
    items = query.order_by(models.Perk.sort_order, models.Perk.id).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return items, total


def build_perk_modifiers_dict(perk, negative: bool = False) -> dict:
    """
    Build a modifiers dict from perk flat bonuses, suitable for apply_modifiers.
    If negative=True, values are inverted (for bonus reversal).
    """
    flat = {}
    if perk.bonuses and isinstance(perk.bonuses, dict):
        flat = perk.bonuses.get("flat", {})
    elif hasattr(perk, "bonuses") and perk.bonuses:
        flat = perk.bonuses.get("flat", {})

    result = {}
    for key, value in flat.items():
        if key in VALID_FLAT_BONUS_KEYS and value != 0:
            result[key] = -value if negative else value
    return result


def _apply_modifiers_internal(db: Session, character_id: int, modifiers: dict):
    """
    Apply modifiers to character attributes. Internal version that works
    directly with the DB session instead of making an HTTP call — same logic
    as the apply_modifiers endpoint in main.py (both go through
    apply_attribute_modifiers, FEAT-195): primary-attribute bonuses always
    carry their derived effects (resists / dodge / crit / res_effects) via
    eff(new) - eff(old), so a negated dict reverses them exactly.
    """
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).with_for_update().first()

    if not attr:
        return False

    apply_attribute_modifiers(attr, modifiers)
    db.flush()
    return True


def get_character_perks(db: Session, character_id: int):
    """
    Returns all active perks merged with character unlock status and progress data.
    Efficient: uses 3 queries max (all perks, character_perks, cumulative_stats + attributes).
    """
    # 1. Get all active perks
    all_perks = db.query(models.Perk).filter(
        models.Perk.is_active == True
    ).order_by(models.Perk.sort_order, models.Perk.id).all()

    if not all_perks:
        return []

    # 2. Get character's unlocked perks (keyed by perk_id)
    char_perks = db.query(models.CharacterPerk).filter(
        models.CharacterPerk.character_id == character_id
    ).all()
    char_perks_map = {cp.perk_id: cp for cp in char_perks}

    # 3. Get cumulative stats for progress computation
    cumulative = get_cumulative_stats(db, character_id)
    # Build a dict of stat_name -> value for easy lookup
    cumulative_dict = {}
    if cumulative:
        for col_name in CUMULATIVE_STATS_COLUMNS:
            cumulative_dict[col_name] = getattr(cumulative, col_name, 0) or 0

    # 4. Get character attributes for 'attribute' type conditions
    char_attrs = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).first()

    # Build attribute lookup dict
    attr_dict = {}
    if char_attrs:
        attr_fields = [
            "strength", "agility", "intelligence", "endurance",
            "health", "mana", "energy", "stamina", "charisma", "luck",
            "damage", "dodge", "critical_hit_chance", "critical_damage",
            "res_effects", "res_physical", "res_catting", "res_crushing",
            "res_piercing", "res_magic", "res_fire", "res_ice",
            "res_watering", "res_electricity", "res_sainting", "res_wind", "res_damning",
            "vul_effects", "vul_physical", "vul_catting", "vul_crushing",
            "vul_piercing", "vul_magic", "vul_fire", "vul_ice",
            "vul_watering", "vul_electricity", "vul_sainting", "vul_wind", "vul_damning",
        ]
        for field in attr_fields:
            attr_dict[field] = getattr(char_attrs, field, 0) or 0

    # 5. Merge perks with unlock status and progress
    result = []
    for perk in all_perks:
        cp = char_perks_map.get(perk.id)
        is_unlocked = cp is not None
        unlocked_at = cp.unlocked_at if cp else None
        is_custom = cp.is_custom if cp else False

        # Compute progress for each condition
        progress = {}
        conditions = perk.conditions if isinstance(perk.conditions, list) else []
        for cond in conditions:
            cond_type = cond.get("type")
            stat_name = cond.get("stat")
            required_value = cond.get("value")

            if cond_type == "cumulative_stat" and stat_name:
                current_value = cumulative_dict.get(stat_name, 0)
                # Freeze the shown progress at the threshold (e.g. 1000/1000)
                # once reached — the underlying cumulative stat keeps growing, so
                # a different perk with a higher threshold still counts up on its
                # own required value (FEAT-143 bug 2).
                if required_value is not None:
                    try:
                        current_value = min(current_value, required_value)
                    except TypeError:
                        pass
                progress[stat_name] = {
                    "current": current_value,
                    "required": required_value,
                }
            elif cond_type == "attribute" and stat_name:
                current_value = attr_dict.get(stat_name, 0)
                progress[stat_name] = {
                    "current": current_value,
                    "required": required_value,
                }
            elif cond_type == "quest" and stat_name == "completed_count":
                current_value = cumulative_dict.get("quests_completed", 0)
                progress["completed_count"] = {
                    "current": current_value,
                    "required": required_value,
                }
            elif cond_type == "quest" and stat_name == "quest_id":
                # Check if this specific quest is completed
                quest_done = 0
                if required_value:
                    from perk_evaluator import _fetch_quest_completed
                    if _fetch_quest_completed(character_id, int(required_value)):
                        quest_done = 1
                progress["quest_id"] = {
                    "current": quest_done,
                    "required": 1,
                    "label": _resolve_quest_name(int(required_value)) if required_value else None,
                }
            elif cond_type == "has_perk":
                target_perk_id = int(required_value) if required_value else None
                target_perk_name = None
                has_it = 0
                if target_perk_id:
                    for p in all_perks:
                        if p.id == target_perk_id:
                            target_perk_name = p.name
                            break
                    if target_perk_id in char_perks_map:
                        has_it = 1
                progress["has_perk"] = {
                    "current": has_it,
                    "required": 1,
                    "label": target_perk_name,
                }
            elif cond_type == "perk_count":
                perk_count = len(char_perks_map)
                progress["perk_count"] = {
                    "current": perk_count,
                    "required": required_value,
                }
            # character_level, quest/quest_id, has_perk, skill_level,
            # gold_balance, admin_grant — no progress bar

        result.append({
            "id": perk.id,
            "name": perk.name,
            "description": perk.description,
            "category": perk.category,
            "rarity": perk.rarity,
            "icon": perk.icon,
            "conditions": conditions,
            "bonuses": perk.bonuses if isinstance(perk.bonuses, dict) else {},
            "is_unlocked": is_unlocked,
            "unlocked_at": unlocked_at,
            "is_custom": is_custom,
            "progress": progress,
        })

    return result


def grant_perk(db: Session, character_id: int, perk_id: int):
    """
    Grant a perk to a character. Uses ON DUPLICATE KEY (idempotent).
    Applies flat bonuses. Returns (success, already_had, perk).
    """
    perk = get_perk_by_id(db, perk_id)
    if perk is None:
        return None, False, None

    # Check if already has the perk
    existing = db.query(models.CharacterPerk).filter(
        models.CharacterPerk.character_id == character_id,
        models.CharacterPerk.perk_id == perk_id,
    ).first()

    if existing:
        return True, True, perk  # Already has the perk

    # Insert new character_perk
    cp = models.CharacterPerk(
        character_id=character_id,
        perk_id=perk_id,
        is_custom=True,
    )
    db.add(cp)
    db.flush()

    # Apply flat bonuses
    modifiers = build_perk_modifiers_dict(perk, negative=False)
    if modifiers:
        _apply_modifiers_internal(db, character_id, modifiers)

    db.commit()
    return True, False, perk


def revoke_perk(db: Session, character_id: int, perk_id: int):
    """
    Revoke a perk from a character. Reverses flat bonuses.
    Returns (success, perk) or (None, None) if not found.
    """
    cp = db.query(models.CharacterPerk).filter(
        models.CharacterPerk.character_id == character_id,
        models.CharacterPerk.perk_id == perk_id,
    ).first()

    if cp is None:
        return None, None

    perk = get_perk_by_id(db, perk_id)
    if perk is None:
        return None, None

    # Reverse flat bonuses
    modifiers = build_perk_modifiers_dict(perk, negative=True)
    if modifiers:
        _apply_modifiers_internal(db, character_id, modifiers)

    db.delete(cp)
    db.commit()
    return True, perk