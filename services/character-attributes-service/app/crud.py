from sqlalchemy.orm import Session
import models, schemas
import traceback
from constants import (
    BASE_HEALTH, BASE_MANA, BASE_ENERGY, BASE_STAMINA,
    BASE_DODGE, BASE_CRIT, BASE_CRIT_DMG,
    HEALTH_MULTIPLIER, MANA_MULTIPLIER, ENERGY_MULTIPLIER, STAMINA_MULTIPLIER,
    STAT_BONUS_PER_POINT, ALL_RESISTANCE_FIELDS,
    PHYSICAL_RESISTANCE_FIELDS, MAGICAL_RESISTANCE_FIELDS,
    ENDURANCE_RES_EFFECTS_MULTIPLIER,
)


def compute_derived_stats(attr):
    """
    Compute all derived stats on a CharacterAttributes ORM object
    from its base (upgradeable) stats. Sets resource maximums,
    combat stats, and resistances in-place.
    """
    b = STAT_BONUS_PER_POINT

    # Resource stats
    attr.max_health = int(BASE_HEALTH + attr.health * HEALTH_MULTIPLIER)
    attr.max_mana = int(BASE_MANA + attr.mana * MANA_MULTIPLIER)
    attr.max_energy = int(BASE_ENERGY + attr.energy * ENERGY_MULTIPLIER)
    attr.max_stamina = int(BASE_STAMINA + attr.stamina * STAMINA_MULTIPLIER)

    # Clamp current to not exceed new max
    attr.current_health = min(attr.current_health, attr.max_health)
    attr.current_mana = min(attr.current_mana, attr.max_mana)
    attr.current_energy = min(attr.current_energy, attr.max_energy)
    attr.current_stamina = min(attr.current_stamina, attr.max_stamina)

    # Combat stats
    attr.dodge = round(BASE_DODGE + attr.agility * b + attr.luck * b, 2)
    attr.critical_hit_chance = round(BASE_CRIT + attr.luck * b, 2)
    attr.critical_damage = BASE_CRIT_DMG  # Only modified by items

    # Physical resistances (boosted by Strength)
    for field in PHYSICAL_RESISTANCE_FIELDS:
        setattr(attr, field, round(attr.strength * b, 2))

    # Magical resistances (boosted by Intelligence)
    for field in MAGICAL_RESISTANCE_FIELDS:
        setattr(attr, field, round(attr.intelligence * b, 2))

    # res_effects: endurance * 0.2 + luck * 0.1
    attr.res_effects = round(
        attr.endurance * ENDURANCE_RES_EFFECTS_MULTIPLIER + attr.luck * b, 2
    )


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

    # Set current resources to max before compute (so clamp works correctly)
    db_attributes.current_health = int(BASE_HEALTH + attributes.health * HEALTH_MULTIPLIER)
    db_attributes.current_mana = int(BASE_MANA + attributes.mana * MANA_MULTIPLIER)
    db_attributes.current_energy = int(BASE_ENERGY + attributes.energy * ENERGY_MULTIPLIER)
    db_attributes.current_stamina = int(BASE_STAMINA + attributes.stamina * STAMINA_MULTIPLIER)

    # Compute all derived stats (resources, combat, resistances)
    compute_derived_stats(db_attributes)

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


def recalculate_attributes(db: Session, character_id: int):
    """
    Пересчитывает все производные статы из базовых значений (10 прокачиваемых статов).
    Не учитывает модификаторы экипировки — предназначен для админского использования
    при изменении формул.
    """
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).with_for_update().first()

    if not attr:
        return None

    compute_derived_stats(attr)

    db.commit()
    db.refresh(attr)
    return attr


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
):
    """
    Atomically increments cumulative stat counters and applies set_max (GREATEST).
    Creates the row lazily if it doesn't exist.
    Returns the updated row.
    """
    from sqlalchemy import text as sa_text

    row = get_or_create_cumulative_stats(db, character_id)

    # Build atomic UPDATE SET clauses
    set_clauses = []
    params = {"cid": character_id}

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

    db.commit()
    db.refresh(row)
    return row


# --- Perks CRUD ---

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
VALID_CONDITION_TYPES = {"cumulative_stat", "character_level", "attribute", "quest", "admin_grant"}
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
            setattr(perk, field, [c.dict() for c in value])
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
    directly with the DB session instead of making an HTTP call.
    Same logic as the apply_modifiers endpoint in main.py.
    """
    from constants import HEALTH_MULTIPLIER, MANA_MULTIPLIER, ENERGY_MULTIPLIER, STAMINA_MULTIPLIER

    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).with_for_update().first()

    if not attr:
        return False

    # Resource stats with max/current recalculation
    for resource, multiplier in [
        ("health", HEALTH_MULTIPLIER),
        ("mana", MANA_MULTIPLIER),
        ("energy", ENERGY_MULTIPLIER),
        ("stamina", STAMINA_MULTIPLIER),
    ]:
        delta = modifiers.get(resource, 0)
        if delta != 0:
            old_val = getattr(attr, resource)
            new_val = old_val + delta
            if new_val < 0:
                new_val = 0

            diff = (new_val - old_val) * multiplier
            old_max = getattr(attr, f"max_{resource}")
            new_max = old_max + diff

            new_current = getattr(attr, f"current_{resource}") + diff
            if new_current < 0:
                new_current = 0
            if new_current > new_max:
                new_current = new_max

            setattr(attr, resource, new_val)
            setattr(attr, f"max_{resource}", new_max)
            setattr(attr, f"current_{resource}", new_current)

    # Simple additive keys
    simple_keys = [
        "strength", "agility", "intelligence", "endurance", "charisma", "luck",
        "damage", "dodge", "res_effects",
        "res_physical", "res_catting", "res_crushing", "res_piercing",
        "res_magic", "res_fire", "res_ice", "res_watering",
        "res_electricity", "res_wind", "res_sainting", "res_damning",
        "critical_hit_chance", "critical_damage",
        "vul_effects", "vul_physical", "vul_catting", "vul_crushing", "vul_piercing",
        "vul_magic", "vul_fire", "vul_ice", "vul_watering",
        "vul_electricity", "vul_sainting", "vul_wind", "vul_damning",
    ]

    for key in simple_keys:
        if key in modifiers and modifiers[key] != 0:
            old_val = getattr(attr, key, 0)
            setattr(attr, key, old_val + modifiers[key])

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
            # character_level, quest, admin_grant — no progress data

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