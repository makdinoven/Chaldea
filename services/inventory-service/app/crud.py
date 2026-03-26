from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import random

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, and_, or_, func
import models
import schemas


# ---------------------------------------------------------------------------
# XP reward defaults by recipe rarity
# ---------------------------------------------------------------------------

RARITY_XP_MAP = {
    "common": 10,
    "rare": 25,
    "epic": 50,
    "legendary": 100,
    "mythical": 200,
    "divine": 500,
    "demonic": 500,
}


# ---------------------------------------------------------------------------
# Sharpening constants
# ---------------------------------------------------------------------------

MAX_ENHANCEMENT_POINTS = 15
MAX_STAT_SHARPEN = 5
WHETSTONE_CHANCE = {1: 0.25, 2: 0.50, 3: 0.75}

SHARPENABLE_TYPES = {'head', 'body', 'cloak', 'belt', 'main_weapon', 'additional_weapons', 'shield'}

# ---------------------------------------------------------------------------
# Gem socket constants
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Durability constants
# ---------------------------------------------------------------------------

DURABILITY_SLOT_TYPES = {'head', 'body', 'cloak', 'main_weapon', 'additional_weapons'}

JEWELRY_TYPES = {'ring', 'necklace', 'bracelet'}
ARMOR_WEAPON_TYPES = {'head', 'body', 'cloak', 'belt', 'main_weapon', 'additional_weapons', 'shield'}
SOCKETABLE_TYPES = JEWELRY_TYPES | ARMOR_WEAPON_TYPES
GEM_PRESERVATION_CHANCES = {1: 10, 2: 40, 3: 70}  # % chance gem/rune survives extraction, by profession rank
GEM_XP_REWARD = 10

MAIN_STAT_FIELDS = [
    'strength_modifier', 'agility_modifier', 'intelligence_modifier', 'endurance_modifier',
    'health_modifier', 'energy_modifier', 'mana_modifier', 'stamina_modifier',
    'charisma_modifier', 'luck_modifier', 'damage_modifier', 'dodge_modifier',
]

FLOAT_STAT_FIELDS = [
    'res_physical_modifier', 'res_catting_modifier', 'res_crushing_modifier',
    'res_piercing_modifier', 'res_magic_modifier', 'res_fire_modifier',
    'res_ice_modifier', 'res_watering_modifier', 'res_electricity_modifier',
    'res_wind_modifier', 'res_sainting_modifier', 'res_damning_modifier',
    'res_effects_modifier', 'critical_hit_chance_modifier', 'critical_damage_modifier',
]

ALL_SHARPENABLE_FIELDS = MAIN_STAT_FIELDS + FLOAT_STAT_FIELDS

STAT_DISPLAY_NAMES = {
    'strength_modifier': 'Сила', 'agility_modifier': 'Ловкость',
    'intelligence_modifier': 'Интеллект', 'endurance_modifier': 'Выносливость',
    'health_modifier': 'Здоровье', 'energy_modifier': 'Энергия',
    'mana_modifier': 'Мана', 'stamina_modifier': 'Выносливость (стамина)',
    'charisma_modifier': 'Харизма', 'luck_modifier': 'Удача',
    'damage_modifier': 'Урон', 'dodge_modifier': 'Уклонение',
    'res_physical_modifier': 'Сопр. физическому', 'res_catting_modifier': 'Сопр. режущему',
    'res_crushing_modifier': 'Сопр. дробящему', 'res_piercing_modifier': 'Сопр. колющему',
    'res_magic_modifier': 'Сопр. магическому', 'res_fire_modifier': 'Сопр. огненному',
    'res_ice_modifier': 'Сопр. ледяному', 'res_watering_modifier': 'Сопр. водяному',
    'res_electricity_modifier': 'Сопр. электрическому', 'res_wind_modifier': 'Сопр. воздушному',
    'res_sainting_modifier': 'Сопр. святому', 'res_damning_modifier': 'Сопр. тёмному',
    'res_effects_modifier': 'Сопр. эффектам',
    'critical_hit_chance_modifier': 'Шанс крита', 'critical_damage_modifier': 'Крит. урон',
}


def get_enhancement_bonuses(row) -> dict:
    """Parse enhancement_bonuses JSON from inventory/equipment row."""
    if row.enhancement_bonuses:
        return json.loads(row.enhancement_bonuses)
    return {}


def set_enhancement_bonuses(row, bonuses: dict):
    """Serialize enhancement_bonuses to JSON on inventory/equipment row."""
    row.enhancement_bonuses = json.dumps(bonuses) if bonuses else None


# ---------------------------------------------------------------------------
# Vulnerability stat fields (for gem modifier extraction)
# ---------------------------------------------------------------------------

VUL_STAT_FIELDS = [
    'vul_effects_modifier', 'vul_physical_modifier', 'vul_catting_modifier',
    'vul_crushing_modifier', 'vul_piercing_modifier', 'vul_magic_modifier',
    'vul_fire_modifier', 'vul_ice_modifier', 'vul_watering_modifier',
    'vul_electricity_modifier', 'vul_sainting_modifier', 'vul_wind_modifier',
    'vul_damning_modifier',
]

RECOVERY_FIELDS = [
    'health_recovery', 'energy_recovery', 'mana_recovery', 'stamina_recovery',
]

ALL_MODIFIER_FIELDS = MAIN_STAT_FIELDS + FLOAT_STAT_FIELDS + VUL_STAT_FIELDS


# ---------------------------------------------------------------------------
# Gem socket helpers
# ---------------------------------------------------------------------------

def get_socketed_gems(row) -> list:
    """Parse socketed_gems JSON from inventory/equipment row. Returns list like [42, None, 15]."""
    if row.socketed_gems:
        return json.loads(row.socketed_gems)
    return []


def set_socketed_gems(row, gems: list):
    """Serialize socketed_gems to JSON on inventory/equipment row."""
    row.socketed_gems = json.dumps(gems) if gems else None


def load_gem_items(db: Session, gem_ids: list) -> list:
    """Load Items objects for non-null gem IDs. Returns list of Items (with duplicates for same gem type)."""
    valid_ids = [gid for gid in gem_ids if gid is not None]
    if not valid_ids:
        return []
    # Load unique gem items
    unique_ids = set(valid_ids)
    gem_map = {g.id: g for g in db.query(models.Items).filter(models.Items.id.in_(unique_ids)).all()}
    # Return one entry per socket (duplicates if same gem type in multiple slots)
    return [gem_map[gid] for gid in valid_ids if gid in gem_map]


def get_gem_modifiers_dict(gem_item: models.Items) -> dict:
    """Extract non-zero modifiers from a gem item as a display dict."""
    mods = {}
    for field in ALL_MODIFIER_FIELDS:
        val = getattr(gem_item, field, 0) or 0
        if val:
            display_name = STAT_DISPLAY_NAMES.get(field, field)
            mods[display_name] = val
    return mods


def find_recipe_for_item(db: Session, item_id: int, profession_slug: str = 'jeweler'):
    """Find recipe where result_item_id == item_id and profession matches."""
    return (
        db.query(models.Recipe)
        .join(models.Profession, models.Recipe.profession_id == models.Profession.id)
        .filter(
            models.Recipe.result_item_id == item_id,
            models.Profession.slug == profession_slug,
            models.Recipe.is_active == True,
        )
        .options(joinedload(models.Recipe.ingredients).joinedload(models.RecipeIngredient.item))
        .first()
    )


def calculate_smelt_returns(recipe: models.Recipe) -> list:
    """For each ingredient in recipe, return ~50% (floor, min 1)."""
    results = []
    for ing in recipe.ingredients:
        qty = max(1, ing.quantity // 2)
        results.append({
            "item_id": ing.item_id,
            "name": ing.item.name if ing.item else "Неизвестный",
            "image": ing.item.image if ing.item else None,
            "quantity": qty,
        })
    return results


def get_junk_item(db: Session) -> models.Items:
    """Find 'Ювелирный лом' item."""
    return db.query(models.Items).filter(models.Items.name == "Ювелирный лом").first()


# Получить инвентарь по ID персонажа
def get_inventory_by_character_id(db: Session, character_id: int):
    return db.query(models.CharacterInventory).filter(models.CharacterInventory.character_id == character_id).first()


# Функция для создания инвентаря персонажа
def create_character_inventory(db: Session, inventory_data: schemas.CharacterInventoryBase):
    """
    Создает запись CharacterInventory и сохраняет ее в базе данных.
    """
    db_inventory = models.CharacterInventory(
        character_id=inventory_data.character_id,
        item_id=inventory_data.item_id,
        quantity=inventory_data.quantity
    )
    db.add(db_inventory)
    db.commit()
    db.refresh(db_inventory)
    return db_inventory


def create_default_equipment_slots(db: Session, character_id: int):
    """
    Создает стандартные слоты экипировки для персонажа.
    Все слоты, кроме fast_slot_X, включены (is_enabled=True).
    Все fast_slot_X по умолчанию отключены (is_enabled=False).
    """
    slot_types = [
        'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
        'main_weapon', 'additional_weapons', 'shield',
        'fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4',
        'fast_slot_5', 'fast_slot_6', 'fast_slot_7', 'fast_slot_8',
        'fast_slot_9', 'fast_slot_10'
    ]

    equipment_slots = []

    for slot_type in slot_types:
        if slot_type.startswith("fast_slot_"):
            # Если это быстрый слот, делаем is_enabled = False
            new_slot = models.EquipmentSlot(
                character_id=character_id,
                slot_type=slot_type,
                item_id=None,
                is_enabled=False
            )
        else:
            # Все остальные слоты включаем
            new_slot = models.EquipmentSlot(
                character_id=character_id,
                slot_type=slot_type,
                item_id=None,
                is_enabled=True
            )

        db.add(new_slot)
        equipment_slots.append(new_slot)

    db.commit()
    return equipment_slots


def get_inventory_items(db: Session, character_id: int):
    return db.query(models.CharacterInventory).filter(models.CharacterInventory.character_id == character_id).all()

def get_equipment_slots(db: Session, character_id: int):
    return db.query(models.EquipmentSlot).filter(models.EquipmentSlot.character_id == character_id).all()

def is_item_compatible_with_slot(item_type: str, slot_type: str) -> bool:
    """
    Проверяет, совместим ли тип предмета с типом слота.
    """
    slot_to_item_mapping = {
        'head': ['head'],
        'body': ['body'],
        'cloak': ['cloak'],
        'belt': ['belt'],
        'ring': ['ring'],
        'necklace': ['necklace'],
        'bracelet': ['bracelet'],
        'main_weapon': ['main_weapon'],
        'additional_weapons': ['additional_weapons'],
        'shield': ['shield'],
        'fast_slot_1': ['consumable'],
        'fast_slot_2': ['consumable'],
        'fast_slot_3': ['consumable'],
        'fast_slot_4': ['consumable'],
    }
    return item_type in slot_to_item_mapping.get(slot_type, [])

def find_equipment_slot_for_item(db: Session, character_id: int, item_obj: models.Items):
    fixed = {
        'head': 'head', 'body': 'body', 'cloak': 'cloak', 'belt': 'belt',
        'ring': 'ring', 'necklace': 'necklace', 'bracelet': 'bracelet',
        'main_weapon': 'main_weapon', 'additional_weapons': 'additional_weapons',
        'shield': 'shield',
    }
    if item_obj.item_type in fixed:
        return db.query(models.EquipmentSlot).filter_by(
            character_id=character_id,
            slot_type=fixed[item_obj.item_type]
        ).with_for_update().first()

    # для consumable/scroll/misc
    fast_slots = [f"fast_slot_{i}" for i in range(1, 11)]

    # 1) пробуем активные
    slot = (
        db.query(models.EquipmentSlot)
          .filter(
              models.EquipmentSlot.character_id == character_id,
              models.EquipmentSlot.slot_type.in_(fast_slots),
              models.EquipmentSlot.is_enabled == True,
              models.EquipmentSlot.item_id.is_(None),
          )
          .order_by(models.EquipmentSlot.slot_type)
          .with_for_update()
          .first()
    )
    if slot:
        return slot

    # 2) если нет активных — берём _первый_ свободный и включаем его
    slot = (
        db.query(models.EquipmentSlot)
          .filter(
              models.EquipmentSlot.character_id == character_id,
              models.EquipmentSlot.slot_type.in_(fast_slots),
              models.EquipmentSlot.item_id.is_(None),
          )
          .order_by(models.EquipmentSlot.slot_type)
          .with_for_update()
          .first()
    )
    if slot:
        slot.is_enabled = True
        db.add(slot)
        db.flush()
        return slot

    return None


def return_item_to_inventory(db: Session, character_id: int, item_obj: models.Items):
    """
    Возвращаем 1 шт. предмета в инвентарь.
    Если max_stack_size>1, стакаем в существующий слот, иначе создаём новую запись.
    """
    if item_obj.max_stack_size > 1:
        # Ищем подходящий слот в инвентаре
        inv_slot = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.item_id == item_obj.id,
            models.CharacterInventory.quantity < item_obj.max_stack_size
        ).order_by(models.CharacterInventory.quantity.desc()).first()
        if inv_slot:
            inv_slot.quantity += 1
            db.add(inv_slot)
            db.flush()
            return

    # Если предмет нестекаемый или все стеки заполнены — создаём новый
    new_inv = models.CharacterInventory(
        character_id=character_id,
        item_id=item_obj.id,
        quantity=1
    )
    db.add(new_inv)
    db.flush()

def build_modifiers_dict(item_obj: models.Items, negative: bool = False, enhancement_bonuses: dict = None, gem_items: list = None, current_durability: int = None, max_durability: int = 0) -> dict:
    """
    Формируем словарь модификаторов (ключ -> величина),
    основываясь на полях *_modifier у объекта Items.
    Если negative=True, то все значения умножаем на -1.
    enhancement_bonuses: dict of {stat_field: sharpened_count} — per-stat sharpening counts.
    gem_items: list of Items objects for gems in sockets — their modifiers are added to the total.
    current_durability: current durability of the item instance (None = full).
    max_durability: max durability from item template (0 = no durability system).
    """

    # If item has durability system and is broken, return empty dict (no modifiers)
    if max_durability > 0 and current_durability is not None and current_durability <= 0:
        return {}

    mods = {}

    if item_obj.strength_modifier:
        mods["strength"] = item_obj.strength_modifier
    if item_obj.agility_modifier:
        mods["agility"] = item_obj.agility_modifier
    if item_obj.intelligence_modifier:
        mods["intelligence"] = item_obj.intelligence_modifier
    if item_obj.endurance_modifier:
        mods["endurance"] = item_obj.endurance_modifier
    if item_obj.health_modifier:
        mods["health"] = item_obj.health_modifier
    if item_obj.energy_modifier:
        mods["energy"] = item_obj.energy_modifier
    if item_obj.mana_modifier:
        mods["mana"] = item_obj.mana_modifier
    if item_obj.stamina_modifier:
        mods["stamina"] = item_obj.stamina_modifier
    if item_obj.charisma_modifier:
        mods["charisma"] = item_obj.charisma_modifier
    if item_obj.luck_modifier:
        mods["luck"] = item_obj.luck_modifier
    if item_obj.damage_modifier:
        mods["damage"] = item_obj.damage_modifier
    if item_obj.dodge_modifier:
        mods["dodge"] = item_obj.dodge_modifier

    # Сопротивления:
    if item_obj.res_effects_modifier:
        mods["res_effects"] = item_obj.res_effects_modifier
    if item_obj.res_physical_modifier:
        mods["res_physical"] = item_obj.res_physical_modifier
    if item_obj.res_catting_modifier:
        mods["res_catting"] = item_obj.res_catting_modifier
    if item_obj.res_crushing_modifier:
        mods["res_crushing"] = item_obj.res_crushing_modifier
    if item_obj.res_piercing_modifier:
        mods["res_piercing"] = item_obj.res_piercing_modifier
    if item_obj.res_magic_modifier:
        mods["res_magic"] = item_obj.res_magic_modifier
    if item_obj.res_fire_modifier:
        mods["res_fire"] = item_obj.res_fire_modifier
    if item_obj.res_ice_modifier:
        mods["res_ice"] = item_obj.res_ice_modifier
    if item_obj.res_watering_modifier:
        mods["res_watering"] = item_obj.res_watering_modifier
    if item_obj.res_electricity_modifier:
        mods["res_electricity"] = item_obj.res_electricity_modifier
    if item_obj.res_wind_modifier:
        mods["res_wind"] = item_obj.res_wind_modifier
    if item_obj.res_sainting_modifier:
        mods["res_sainting"] = item_obj.res_sainting_modifier
    if item_obj.res_damning_modifier:
        mods["res_damning"] = item_obj.res_damning_modifier

    if item_obj.critical_hit_chance_modifier:
        mods["critical_hit_chance"] = item_obj.critical_hit_chance_modifier
    if item_obj.critical_damage_modifier:
        mods["critical_damage"] = item_obj.critical_damage_modifier

    if item_obj.vul_effects_modifier:
        mods["vul_effects"] = item_obj.vul_effects_modifier
    if item_obj.vul_physical_modifier:
        mods["vul_physical"] = item_obj.vul_physical_modifier
    if item_obj.vul_catting_modifier:
        mods["vul_catting"] = item_obj.vul_catting_modifier
    if item_obj.vul_crushing_modifier:
        mods["vul_crushing"] = item_obj.vul_crushing_modifier
    if item_obj.vul_piercing_modifier:
        mods["vul_piercing"] = item_obj.vul_piercing_modifier
    if item_obj.vul_magic_modifier:
        mods["vul_magic"] = item_obj.vul_magic_modifier
    if item_obj.vul_fire_modifier:
        mods["vul_fire"] = item_obj.vul_fire_modifier
    if item_obj.vul_ice_modifier:
        mods["vul_ice"] = item_obj.vul_ice_modifier
    if item_obj.vul_watering_modifier:
        mods["vul_watering"] = item_obj.vul_watering_modifier
    if item_obj.vul_electricity_modifier:
        mods["vul_electricity"] = item_obj.vul_electricity_modifier
    if item_obj.vul_sainting_modifier:
        mods["vul_sainting"] = item_obj.vul_sainting_modifier
    if item_obj.vul_wind_modifier:
        mods["vul_wind"] = item_obj.vul_wind_modifier
    if item_obj.vul_damning_modifier:
        mods["vul_damning"] = item_obj.vul_damning_modifier

    # Add enhancement bonuses from sharpening
    # Per-stat increment overrides
    SHARPEN_INCREMENT = {
        'critical_hit_chance_modifier': 0.5,   # +0.5% per point
        'critical_damage_modifier': 1.0,       # +1% per point
    }
    if enhancement_bonuses:
        for field, count in enhancement_bonuses.items():
            key = field.replace('_modifier', '')
            if field in SHARPEN_INCREMENT:
                increment = round(count * SHARPEN_INCREMENT[field], 2)
            elif field in MAIN_STAT_FIELDS:
                increment = count * 1  # +1 per sharpening for main stats
            elif field in FLOAT_STAT_FIELDS:
                increment = round(count * 0.1, 2)  # +0.1 per sharpening for resistances
            else:
                continue
            mods[key] = mods.get(key, 0) + increment

    # Add gem bonuses from socketed gems
    if gem_items:
        for gem in gem_items:
            for field in ALL_MODIFIER_FIELDS:
                val = getattr(gem, field, 0) or 0
                if val:
                    key = field.replace('_modifier', '')
                    mods[key] = mods.get(key, 0) + val

    if negative:
        mods = {k: -v for k, v in mods.items()}

    # ПРИМЕЧАНИЕ: поля типа health_recovery / mana_recovery - это "расход" (consume)
    # Мы их используем только при "use_item", а не при "apply_modifiers" для экипировки.
    # Соответственно, здесь не добавляем их.
    return mods

def delete_all_inventory_for_character(db: Session, character_id: int) -> dict:
    """
    Bulk delete all equipment_slots and character_inventory rows for a character.
    Returns counts of deleted rows.
    """
    slots_deleted = (
        db.query(models.EquipmentSlot)
        .filter(models.EquipmentSlot.character_id == character_id)
        .delete(synchronize_session="fetch")
    )
    items_deleted = (
        db.query(models.CharacterInventory)
        .filter(models.CharacterInventory.character_id == character_id)
        .delete(synchronize_session="fetch")
    )
    db.commit()
    return {"items_deleted": items_deleted, "slots_deleted": slots_deleted}


def recalc_fast_slots(db: Session, character_id: int):
    # 1) Смотрим, какие предметы надеты
    eq_slots = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.item_id.isnot(None)
    ).all()

    # 2) Суммируем бонусы
    BASE_FAST_SLOTS = 4  # если хотите, что по умолчанию 4 слота, то ставьте 4
    total_bonus = 0
    for s in eq_slots:
        # Находим item_id => item => item.fast_slot_bonus
        item_obj = db.query(models.Items).filter(models.Items.id == s.item_id).first()
        if item_obj and item_obj.fast_slot_bonus:
            total_bonus += item_obj.fast_slot_bonus

    available_fast_slots = BASE_FAST_SLOTS + total_bonus
    # Не больше 10
    if available_fast_slots > 10:
        available_fast_slots = 10
    if available_fast_slots < 0:
        available_fast_slots = 0

    # 3) Получаем все fast_slot_* (1..10)
    fast_slots = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.slot_type.in_([f"fast_slot_{i}" for i in range(1, 11)])
    ).order_by(models.EquipmentSlot.slot_type.asc()).all()

    # Сортировка: fast_slot_1, fast_slot_2, ...
    # Активируем первые N, остальные деактивируем
    count_enabled = 0
    for slot in fast_slots:
        count_enabled += 1
        if count_enabled <= available_fast_slots:
            # Включаем
            slot.is_enabled = True
        else:
            # Выключаем
            slot.is_enabled = False
            # если там что-то лежит -> снимаем
            if slot.item_id is not None:
                old_item = db.query(models.Items).filter(models.Items.id == slot.item_id).first()
                # возвращаем в инвентарь
                return_item_to_inventory(db, character_id, old_item)
                slot.item_id = None
        db.add(slot)

    db.commit()


# ---------------------------------------------------------------------------
# Trade CRUD
# ---------------------------------------------------------------------------

def get_character_location(db: Session, character_id: int) -> Optional[int]:
    """Get character's current_location from shared DB."""
    row = db.execute(
        text("SELECT current_location_id FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return row[0] if row else None


def get_character_name(db: Session, character_id: int) -> str:
    """Get character name from shared DB."""
    row = db.execute(
        text("SELECT name FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return row[0] if row else "Неизвестный"


def get_character_user_id(db: Session, character_id: int) -> Optional[int]:
    """Get user_id who owns the character."""
    row = db.execute(
        text("SELECT user_id FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return row[0] if row else None


def get_character_gold(db: Session, character_id: int) -> int:
    """Get character currency_balance from shared DB."""
    row = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def is_character_in_battle(db: Session, character_id: int) -> bool:
    """Check if character is in an active battle via shared DB."""
    row = db.execute(
        text(
            "SELECT 1 FROM battle_participants bp "
            "JOIN battles b ON bp.battle_id = b.id "
            "WHERE bp.character_id = :cid AND b.status IN ('pending', 'in_progress') "
            "LIMIT 1"
        ),
        {"cid": character_id}
    ).fetchone()
    return row is not None


def get_active_trade_between(
    db: Session, char_a: int, char_b: int
) -> Optional[models.TradeOffer]:
    """Find an existing active (non-terminal) trade between two characters."""
    return db.query(models.TradeOffer).filter(
        models.TradeOffer.status.in_(['pending', 'negotiating']),
        or_(
            and_(
                models.TradeOffer.initiator_character_id == char_a,
                models.TradeOffer.target_character_id == char_b,
            ),
            and_(
                models.TradeOffer.initiator_character_id == char_b,
                models.TradeOffer.target_character_id == char_a,
            ),
        )
    ).first()


def create_trade_offer(
    db: Session, initiator_id: int, target_id: int, location_id: int
) -> models.TradeOffer:
    trade = models.TradeOffer(
        initiator_character_id=initiator_id,
        target_character_id=target_id,
        location_id=location_id,
        status='pending',
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def get_trade_offer(db: Session, trade_id: int) -> Optional[models.TradeOffer]:
    return db.query(models.TradeOffer).filter(
        models.TradeOffer.id == trade_id
    ).first()


def update_trade_items(
    db: Session,
    trade: models.TradeOffer,
    character_id: int,
    items: List[schemas.TradeItemEntry],
    gold: int,
) -> models.TradeOffer:
    """Replace all items for one side and update gold. Resets both confirmed flags."""
    # Remove existing items for this character in this trade
    db.query(models.TradeOfferItem).filter(
        models.TradeOfferItem.trade_offer_id == trade.id,
        models.TradeOfferItem.character_id == character_id,
    ).delete(synchronize_session="fetch")

    # Add new items
    for entry in items:
        item_row = models.TradeOfferItem(
            trade_offer_id=trade.id,
            character_id=character_id,
            item_id=entry.item_id,
            quantity=entry.quantity,
        )
        db.add(item_row)

    # Update gold for the correct side
    if character_id == trade.initiator_character_id:
        trade.initiator_gold = gold
    else:
        trade.target_gold = gold

    # Reset confirmations
    trade.initiator_confirmed = False
    trade.target_confirmed = False

    # Move to negotiating if still pending
    if trade.status == 'pending':
        trade.status = 'negotiating'

    db.commit()
    db.refresh(trade)
    return trade


def confirm_trade(db: Session, trade: models.TradeOffer, character_id: int) -> bool:
    """Set confirmed flag for one side. Returns True if both sides now confirmed."""
    if character_id == trade.initiator_character_id:
        trade.initiator_confirmed = True
    else:
        trade.target_confirmed = True
    db.flush()
    return trade.initiator_confirmed and trade.target_confirmed


def execute_trade(db: Session, trade: models.TradeOffer) -> None:
    """
    Execute trade atomically: transfer items and gold between characters.
    Assumes caller manages the transaction (no commit here, caller commits).
    """
    initiator_id = trade.initiator_character_id
    target_id = trade.target_character_id

    # 1. Verify gold balances
    if trade.initiator_gold > 0:
        balance = get_character_gold(db, initiator_id)
        if balance < trade.initiator_gold:
            raise ValueError("У инициатора недостаточно золота для обмена")

    if trade.target_gold > 0:
        balance = get_character_gold(db, target_id)
        if balance < trade.target_gold:
            raise ValueError("У второго участника недостаточно золота для обмена")

    # 2. Verify items
    trade_items = db.query(models.TradeOfferItem).filter(
        models.TradeOfferItem.trade_offer_id == trade.id
    ).all()

    for ti in trade_items:
        total_qty = db.execute(
            text(
                "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
                "WHERE character_id = :cid AND item_id = :iid"
            ),
            {"cid": ti.character_id, "iid": ti.item_id}
        ).scalar()
        if total_qty < ti.quantity:
            char_name = get_character_name(db, ti.character_id)
            item_obj = db.query(models.Items).get(ti.item_id)
            item_name = item_obj.name if item_obj else f"#{ti.item_id}"
            raise ValueError(
                f"У {char_name} недостаточно предмета \"{item_name}\" "
                f"(нужно {ti.quantity}, есть {total_qty})"
            )

    # 3. Transfer items
    for ti in trade_items:
        # Determine sender and receiver
        if ti.character_id == initiator_id:
            receiver_id = target_id
        else:
            receiver_id = initiator_id

        # Remove from sender
        _remove_items_from_inventory(db, ti.character_id, ti.item_id, ti.quantity)
        # Add to receiver
        _add_items_to_inventory(db, receiver_id, ti.item_id, ti.quantity)

    # 4. Transfer gold
    if trade.initiator_gold > 0:
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance - :gold WHERE id = :cid"),
            {"gold": trade.initiator_gold, "cid": initiator_id}
        )
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance + :gold WHERE id = :cid"),
            {"gold": trade.initiator_gold, "cid": target_id}
        )

    if trade.target_gold > 0:
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance - :gold WHERE id = :cid"),
            {"gold": trade.target_gold, "cid": target_id}
        )
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance + :gold WHERE id = :cid"),
            {"gold": trade.target_gold, "cid": initiator_id}
        )

    # 5. Mark trade as completed
    trade.status = 'completed'


def _remove_items_from_inventory(
    db: Session, character_id: int, item_id: int, quantity: int
) -> None:
    """Remove quantity of item from character inventory, respecting stacks."""
    remaining = quantity
    slots = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id,
    ).order_by(models.CharacterInventory.quantity.asc()).all()

    for slot in slots:
        if remaining <= 0:
            break
        if slot.quantity <= remaining:
            remaining -= slot.quantity
            db.delete(slot)
        else:
            slot.quantity -= remaining
            remaining = 0
    db.flush()


def _add_items_to_inventory(
    db: Session, character_id: int, item_id: int, quantity: int
) -> None:
    """Add quantity of item to character inventory, respecting stacks."""
    item_obj = db.query(models.Items).get(item_id)
    if not item_obj:
        return
    max_stack = item_obj.max_stack_size
    remaining = quantity

    # Fill existing stacks first
    existing = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id,
        models.CharacterInventory.quantity < max_stack,
    ).all()

    for slot in existing:
        if remaining <= 0:
            break
        space = max_stack - slot.quantity
        to_add = min(space, remaining)
        slot.quantity += to_add
        remaining -= to_add

    # Create new stacks
    while remaining > 0:
        to_add = min(remaining, max_stack)
        new_slot = models.CharacterInventory(
            character_id=character_id,
            item_id=item_id,
            quantity=to_add,
        )
        db.add(new_slot)
        remaining -= to_add

    db.flush()


def build_trade_state(db: Session, trade: models.TradeOffer) -> dict:
    """Build the full trade state response dict."""
    initiator_name = get_character_name(db, trade.initiator_character_id)
    target_name = get_character_name(db, trade.target_character_id)

    initiator_items = _get_trade_side_items(db, trade.id, trade.initiator_character_id)
    target_items = _get_trade_side_items(db, trade.id, trade.target_character_id)

    return {
        "trade_id": trade.id,
        "status": trade.status,
        "initiator": {
            "character_id": trade.initiator_character_id,
            "character_name": initiator_name,
            "items": initiator_items,
            "gold": trade.initiator_gold,
            "confirmed": trade.initiator_confirmed,
        },
        "target": {
            "character_id": trade.target_character_id,
            "character_name": target_name,
            "items": target_items,
            "gold": trade.target_gold,
            "confirmed": trade.target_confirmed,
        },
    }


def _get_trade_side_items(
    db: Session, trade_offer_id: int, character_id: int
) -> List[dict]:
    """Get item details for one side of a trade."""
    trade_items = db.query(models.TradeOfferItem).filter(
        models.TradeOfferItem.trade_offer_id == trade_offer_id,
        models.TradeOfferItem.character_id == character_id,
    ).all()

    result = []
    for ti in trade_items:
        item_obj = db.query(models.Items).get(ti.item_id)
        result.append({
            "item_id": ti.item_id,
            "item_name": item_obj.name if item_obj else "Неизвестный предмет",
            "item_image": item_obj.image if item_obj else None,
            "quantity": ti.quantity,
        })
    return result


def get_pending_trades_for_character(
    db: Session, character_id: int
) -> List[models.TradeOffer]:
    """Get all active (pending/negotiating) trades involving a character."""
    return db.query(models.TradeOffer).filter(
        models.TradeOffer.status.in_(['pending', 'negotiating']),
        or_(
            models.TradeOffer.initiator_character_id == character_id,
            models.TradeOffer.target_character_id == character_id,
        )
    ).order_by(models.TradeOffer.created_at.desc()).all()


def verify_item_ownership(
    db: Session, character_id: int, items: List[schemas.TradeItemEntry]
) -> Optional[str]:
    """
    Verify character owns all items in sufficient quantity.
    Returns error message string or None if all OK.
    """
    for entry in items:
        total_qty = db.execute(
            text(
                "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
                "WHERE character_id = :cid AND item_id = :iid"
            ),
            {"cid": character_id, "iid": entry.item_id}
        ).scalar()
        if total_qty < entry.quantity:
            item_obj = db.query(models.Items).get(entry.item_id)
            item_name = item_obj.name if item_obj else f"#{entry.item_id}"
            return (
                f"Недостаточно предмета \"{item_name}\" "
                f"(нужно {entry.quantity}, есть {total_qty})"
            )
    return None


# ---------------------------------------------------------------------------
# Profession CRUD
# ---------------------------------------------------------------------------

def get_active_professions(db: Session) -> List[models.Profession]:
    """Get all active professions with their ranks (for public listing)."""
    return (
        db.query(models.Profession)
        .filter(models.Profession.is_active == True)
        .options(joinedload(models.Profession.ranks))
        .order_by(models.Profession.sort_order.asc())
        .all()
    )


def get_all_professions(db: Session) -> List[models.Profession]:
    """Get all professions including inactive (admin view)."""
    return (
        db.query(models.Profession)
        .options(joinedload(models.Profession.ranks))
        .order_by(models.Profession.sort_order.asc())
        .all()
    )


def get_profession_by_id(db: Session, profession_id: int) -> Optional[models.Profession]:
    return (
        db.query(models.Profession)
        .options(joinedload(models.Profession.ranks))
        .filter(models.Profession.id == profession_id)
        .first()
    )


def create_profession(db: Session, data: schemas.ProfessionCreate) -> models.Profession:
    profession = models.Profession(**data.dict())
    db.add(profession)
    db.commit()
    db.refresh(profession)
    return profession


def update_profession(db: Session, profession: models.Profession, data: schemas.ProfessionUpdate) -> models.Profession:
    for field, value in data.dict(exclude_unset=True).items():
        if value is not None:
            setattr(profession, field, value)
    profession.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profession)
    return profession


def delete_profession(db: Session, profession: models.Profession) -> None:
    db.delete(profession)
    db.commit()


# Profession Ranks

def get_rank_by_id(db: Session, rank_id: int) -> Optional[models.ProfessionRank]:
    return db.query(models.ProfessionRank).filter(models.ProfessionRank.id == rank_id).first()


def create_profession_rank(db: Session, profession_id: int, data: schemas.ProfessionRankCreate) -> models.ProfessionRank:
    rank = models.ProfessionRank(profession_id=profession_id, **data.dict())
    db.add(rank)
    db.commit()
    db.refresh(rank)
    return rank


def update_profession_rank(db: Session, rank: models.ProfessionRank, data: schemas.ProfessionRankUpdate) -> models.ProfessionRank:
    for field, value in data.dict(exclude_unset=True).items():
        if value is not None:
            setattr(rank, field, value)
    db.commit()
    db.refresh(rank)
    return rank


def delete_profession_rank(db: Session, rank: models.ProfessionRank) -> None:
    db.delete(rank)
    db.commit()


# Character Profession

def get_character_profession(db: Session, character_id: int) -> Optional[models.CharacterProfession]:
    return (
        db.query(models.CharacterProfession)
        .options(joinedload(models.CharacterProfession.profession).joinedload(models.Profession.ranks))
        .filter(models.CharacterProfession.character_id == character_id)
        .first()
    )


def choose_profession(db: Session, character_id: int, profession_id: int) -> Tuple[models.CharacterProfession, List[models.Recipe]]:
    """
    Create character_professions row and auto-learn rank-1 recipes.
    Returns (character_profession, auto_learned_recipes).
    """
    cp = models.CharacterProfession(
        character_id=character_id,
        profession_id=profession_id,
        current_rank=1,
        experience=0,
        chosen_at=datetime.utcnow(),
    )
    db.add(cp)
    db.flush()

    # Auto-learn rank-1 recipes
    auto_recipes = (
        db.query(models.Recipe)
        .filter(
            models.Recipe.profession_id == profession_id,
            models.Recipe.auto_learn_rank == 1,
            models.Recipe.is_active == True,
        )
        .all()
    )

    for recipe in auto_recipes:
        existing = db.query(models.CharacterRecipe).filter(
            models.CharacterRecipe.character_id == character_id,
            models.CharacterRecipe.recipe_id == recipe.id,
        ).first()
        if not existing:
            cr = models.CharacterRecipe(
                character_id=character_id,
                recipe_id=recipe.id,
                learned_at=datetime.utcnow(),
            )
            db.add(cr)

    db.commit()
    db.refresh(cp)
    return cp, auto_recipes


def change_profession(db: Session, cp: models.CharacterProfession, new_profession_id: int) -> Tuple[models.CharacterProfession, List[models.Recipe]]:
    """
    Change character's profession. Reset rank/XP, keep learned recipes.
    Auto-learn rank-1 recipes for the new profession.
    """
    cp.profession_id = new_profession_id
    cp.current_rank = 1
    cp.experience = 0
    cp.chosen_at = datetime.utcnow()
    db.flush()

    # Auto-learn rank-1 recipes for new profession
    auto_recipes = (
        db.query(models.Recipe)
        .filter(
            models.Recipe.profession_id == new_profession_id,
            models.Recipe.auto_learn_rank == 1,
            models.Recipe.is_active == True,
        )
        .all()
    )

    for recipe in auto_recipes:
        existing = db.query(models.CharacterRecipe).filter(
            models.CharacterRecipe.character_id == cp.character_id,
            models.CharacterRecipe.recipe_id == recipe.id,
        ).first()
        if not existing:
            cr = models.CharacterRecipe(
                character_id=cp.character_id,
                recipe_id=recipe.id,
                learned_at=datetime.utcnow(),
            )
            db.add(cr)

    db.commit()
    db.refresh(cp)
    return cp, auto_recipes


def set_character_rank(db: Session, cp: models.CharacterProfession, rank_number: int) -> models.CharacterProfession:
    """Admin: manually set character's profession rank. Auto-learn recipes for the new rank."""
    cp.current_rank = rank_number
    db.flush()

    # Auto-learn recipes for the new rank and below
    auto_recipes = (
        db.query(models.Recipe)
        .filter(
            models.Recipe.profession_id == cp.profession_id,
            models.Recipe.auto_learn_rank.isnot(None),
            models.Recipe.auto_learn_rank <= rank_number,
            models.Recipe.is_active == True,
        )
        .all()
    )

    for recipe in auto_recipes:
        existing = db.query(models.CharacterRecipe).filter(
            models.CharacterRecipe.character_id == cp.character_id,
            models.CharacterRecipe.recipe_id == recipe.id,
        ).first()
        if not existing:
            cr = models.CharacterRecipe(
                character_id=cp.character_id,
                recipe_id=recipe.id,
                learned_at=datetime.utcnow(),
            )
            db.add(cr)

    db.commit()
    db.refresh(cp)
    return cp


def auto_learn_recipes_for_rank(
    db: Session, character_id: int, profession_id: int, rank_number: int
) -> List[dict]:
    """Auto-learn recipes that have auto_learn_rank == rank_number. Returns list of {"id", "name"}."""
    auto_recipes = (
        db.query(models.Recipe)
        .filter(
            models.Recipe.profession_id == profession_id,
            models.Recipe.auto_learn_rank == rank_number,
            models.Recipe.is_active == True,
        )
        .all()
    )

    learned = []
    for recipe in auto_recipes:
        existing = db.query(models.CharacterRecipe).filter(
            models.CharacterRecipe.character_id == character_id,
            models.CharacterRecipe.recipe_id == recipe.id,
        ).first()
        if not existing:
            cr = models.CharacterRecipe(
                character_id=character_id,
                recipe_id=recipe.id,
                learned_at=datetime.utcnow(),
            )
            db.add(cr)
            learned.append({"id": recipe.id, "name": recipe.name})

    return learned


# ---------------------------------------------------------------------------
# Recipe CRUD
# ---------------------------------------------------------------------------

def get_recipe_by_id(db: Session, recipe_id: int) -> Optional[models.Recipe]:
    return (
        db.query(models.Recipe)
        .options(
            joinedload(models.Recipe.ingredients).joinedload(models.RecipeIngredient.item),
            joinedload(models.Recipe.result_item),
            joinedload(models.Recipe.profession),
        )
        .filter(models.Recipe.id == recipe_id)
        .first()
    )


def get_recipes_admin(
    db: Session,
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    profession_id: Optional[int] = None,
    rarity: Optional[str] = None,
) -> Tuple[List[models.Recipe], int]:
    """Admin paginated recipe list with filters."""
    # Count without joinedload
    count_query = db.query(func.count(models.Recipe.id))
    if search:
        count_query = count_query.filter(models.Recipe.name.ilike(f"%{search}%"))
    if profession_id is not None:
        count_query = count_query.filter(models.Recipe.profession_id == profession_id)
    if rarity:
        count_query = count_query.filter(models.Recipe.rarity == rarity)
    total = count_query.scalar()

    query = db.query(models.Recipe).options(
        joinedload(models.Recipe.ingredients).joinedload(models.RecipeIngredient.item),
        joinedload(models.Recipe.result_item),
        joinedload(models.Recipe.profession),
    )

    if search:
        query = query.filter(models.Recipe.name.ilike(f"%{search}%"))
    if profession_id is not None:
        query = query.filter(models.Recipe.profession_id == profession_id)
    if rarity:
        query = query.filter(models.Recipe.rarity == rarity)

    items = (
        query.order_by(models.Recipe.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return items, total


def create_recipe(db: Session, data: schemas.RecipeCreate) -> models.Recipe:
    recipe = models.Recipe(
        name=data.name,
        description=data.description,
        profession_id=data.profession_id,
        required_rank=data.required_rank,
        result_item_id=data.result_item_id,
        result_quantity=data.result_quantity,
        rarity=data.rarity,
        icon=data.icon,
        auto_learn_rank=data.auto_learn_rank,
        is_blueprint_recipe=data.is_blueprint_recipe,
        xp_reward=data.xp_reward,
    )
    db.add(recipe)
    db.flush()

    for ing in data.ingredients:
        ingredient = models.RecipeIngredient(
            recipe_id=recipe.id,
            item_id=ing.item_id,
            quantity=ing.quantity,
        )
        db.add(ingredient)

    # Auto-create recipe item if not auto-learn
    if not data.auto_learn_rank:
        recipe_item = models.Items(
            name=f"Рецепт: {data.name}",
            item_type="recipe",
            item_rarity=data.rarity or "common",
            item_level=0,
            max_stack_size=99,
            is_unique=False,
            description=data.description or f"Рецепт для изучения: {data.name}",
            blueprint_recipe_id=recipe.id,
            image=data.icon,
        )
        db.add(recipe_item)

    db.commit()
    db.refresh(recipe)
    return recipe


def update_recipe(db: Session, recipe: models.Recipe, data: schemas.RecipeUpdate) -> models.Recipe:
    update_data = data.dict(exclude_unset=True)
    ingredients_data = update_data.pop("ingredients", None)

    for field, value in update_data.items():
        if value is not None:
            setattr(recipe, field, value)
    recipe.updated_at = datetime.utcnow()

    if ingredients_data is not None:
        # Replace all ingredients
        db.query(models.RecipeIngredient).filter(
            models.RecipeIngredient.recipe_id == recipe.id
        ).delete(synchronize_session="fetch")
        for ing in ingredients_data:
            ingredient = models.RecipeIngredient(
                recipe_id=recipe.id,
                item_id=ing["item_id"],
                quantity=ing["quantity"],
            )
            db.add(ingredient)

    # Sync corresponding recipe item (if exists)
    recipe_item = (
        db.query(models.Items)
        .filter(models.Items.blueprint_recipe_id == recipe.id, models.Items.item_type == "recipe")
        .first()
    )

    new_auto_learn = update_data.get("auto_learn_rank")
    # If recipe becomes auto-learn, delete the recipe item
    if new_auto_learn and recipe_item:
        db.delete(recipe_item)
    # If recipe becomes non-auto-learn, create the recipe item
    elif not recipe.auto_learn_rank and not recipe_item:
        recipe_item = models.Items(
            name=f"Рецепт: {recipe.name}",
            item_type="recipe",
            item_rarity=recipe.rarity or "common",
            item_level=0,
            max_stack_size=99,
            is_unique=False,
            description=recipe.description or f"Рецепт для изучения: {recipe.name}",
            blueprint_recipe_id=recipe.id,
            image=recipe.icon,
        )
        db.add(recipe_item)
    # If recipe item exists and recipe is still non-auto-learn, update it
    elif recipe_item and not recipe.auto_learn_rank:
        recipe_item.name = f"Рецепт: {recipe.name}"
        recipe_item.item_rarity = recipe.rarity or "common"
        recipe_item.description = recipe.description or f"Рецепт для изучения: {recipe.name}"
        recipe_item.image = recipe.icon

    db.commit()
    db.refresh(recipe)
    return recipe


def delete_recipe(db: Session, recipe: models.Recipe) -> None:
    # Delete corresponding recipe item (if exists)
    recipe_item = (
        db.query(models.Items)
        .filter(models.Items.blueprint_recipe_id == recipe.id, models.Items.item_type == "recipe")
        .first()
    )
    if recipe_item:
        # Remove from all inventories first
        db.query(models.CharacterInventory).filter(
            models.CharacterInventory.item_id == recipe_item.id
        ).delete(synchronize_session="fetch")
        db.delete(recipe_item)

    db.delete(recipe)
    db.commit()


# ---------------------------------------------------------------------------
# Crafting logic
# ---------------------------------------------------------------------------

def get_available_recipes_for_character(
    db: Session, character_id: int, profession_id: Optional[int] = None
) -> List[dict]:
    """
    Get union of learned recipes + blueprint-sourced recipes for a character.
    Returns list of dicts ready for RecipeOut schema.
    """
    cp = get_character_profession(db, character_id)
    char_profession_id = cp.profession_id if cp else None
    char_rank = cp.current_rank if cp else 0

    # Filter by profession: use explicit param or default to character's current profession
    filter_profession_id = profession_id if profession_id is not None else char_profession_id

    results = []

    # 1. Learned recipes
    learned = (
        db.query(models.CharacterRecipe)
        .filter(models.CharacterRecipe.character_id == character_id)
        .all()
    )
    learned_recipe_ids = {lr.recipe_id for lr in learned}

    for lr in learned:
        recipe = (
            db.query(models.Recipe)
            .options(
                joinedload(models.Recipe.ingredients).joinedload(models.RecipeIngredient.item),
                joinedload(models.Recipe.result_item),
                joinedload(models.Recipe.profession),
            )
            .filter(models.Recipe.id == lr.recipe_id, models.Recipe.is_active == True)
            .first()
        )
        if not recipe:
            continue
        if filter_profession_id is not None and recipe.profession_id != filter_profession_id:
            continue

        recipe_dict = _build_recipe_out(db, recipe, character_id, char_profession_id, char_rank, "learned", None)
        results.append(recipe_dict)

    # 2. Blueprint-sourced recipes (blueprint items in inventory)
    blueprint_items = (
        db.query(models.CharacterInventory)
        .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.Items.item_type == 'blueprint',
            models.Items.blueprint_recipe_id.isnot(None),
        )
        .all()
    )

    for bp_inv in blueprint_items:
        bp_item = db.query(models.Items).filter(models.Items.id == bp_inv.item_id).first()
        if not bp_item or not bp_item.blueprint_recipe_id:
            continue
        # Skip if already shown as a learned recipe
        if bp_item.blueprint_recipe_id in learned_recipe_ids:
            continue

        recipe = (
            db.query(models.Recipe)
            .options(
                joinedload(models.Recipe.ingredients).joinedload(models.RecipeIngredient.item),
                joinedload(models.Recipe.result_item),
                joinedload(models.Recipe.profession),
            )
            .filter(models.Recipe.id == bp_item.blueprint_recipe_id, models.Recipe.is_active == True)
            .first()
        )
        if not recipe:
            continue
        if profession_id is not None and recipe.profession_id != profession_id:
            continue

        recipe_dict = _build_recipe_out(db, recipe, character_id, char_profession_id, char_rank, "blueprint", bp_inv.item_id)
        results.append(recipe_dict)

    return results


def _build_recipe_out(
    db: Session,
    recipe: models.Recipe,
    character_id: int,
    char_profession_id: Optional[int],
    char_rank: int,
    source: str,
    blueprint_item_id: Optional[int],
) -> dict:
    """Build a recipe dict for public listing."""
    ingredients = []
    all_materials_available = True

    for ing in recipe.ingredients:
        available_qty = db.execute(
            text(
                "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
                "WHERE character_id = :cid AND item_id = :iid"
            ),
            {"cid": character_id, "iid": ing.item_id}
        ).scalar()

        if available_qty < ing.quantity:
            all_materials_available = False

        ingredients.append({
            "item_id": ing.item_id,
            "item_name": ing.item.name if ing.item else "???",
            "item_image": ing.item.image if ing.item else None,
            "quantity": ing.quantity,
            "available": int(available_qty),
        })

    # can_craft: correct profession, sufficient rank, all materials present
    profession_matches = char_profession_id == recipe.profession_id
    rank_sufficient = char_rank >= recipe.required_rank
    can_craft = profession_matches and rank_sufficient and all_materials_available

    result_item = recipe.result_item
    result_item_out = {
        "id": result_item.id,
        "name": result_item.name,
        "image": result_item.image,
        "item_type": result_item.item_type,
        "item_rarity": result_item.item_rarity,
    } if result_item else {"id": 0, "name": "???", "image": None, "item_type": "misc", "item_rarity": "common"}

    return {
        "id": recipe.id,
        "name": recipe.name,
        "description": recipe.description,
        "profession_id": recipe.profession_id,
        "profession_name": recipe.profession.name if recipe.profession else "",
        "required_rank": recipe.required_rank,
        "result_item": result_item_out,
        "result_quantity": recipe.result_quantity,
        "rarity": recipe.rarity,
        "icon": recipe.icon,
        "xp_reward": recipe.xp_reward,
        "ingredients": ingredients,
        "can_craft": can_craft,
        "source": source,
        "blueprint_item_id": blueprint_item_id,
    }


def execute_craft(
    db: Session,
    character_id: int,
    recipe: models.Recipe,
    blueprint_item_id: Optional[int],
    cp: Optional[models.CharacterProfession] = None,
) -> dict:
    """
    Execute crafting within a DB transaction.
    Consumes materials, consumes blueprint if applicable, creates result item.
    Uses SELECT ... FOR UPDATE on inventory rows for race condition prevention.
    """
    consumed_materials = []

    # 1. Consume materials
    for ing in recipe.ingredients:
        remaining = ing.quantity
        slots = (
            db.query(models.CharacterInventory)
            .filter(
                models.CharacterInventory.character_id == character_id,
                models.CharacterInventory.item_id == ing.item_id,
            )
            .order_by(models.CharacterInventory.quantity.asc())
            .with_for_update()
            .all()
        )

        total_available = sum(s.quantity for s in slots)
        if total_available < ing.quantity:
            raise ValueError(
                f"Недостаточно материала \"{ing.item.name if ing.item else ing.item_id}\" "
                f"(нужно {ing.quantity}, есть {total_available})"
            )

        for slot in slots:
            if remaining <= 0:
                break
            if slot.quantity <= remaining:
                remaining -= slot.quantity
                db.delete(slot)
            else:
                slot.quantity -= remaining
                remaining = 0

        consumed_materials.append({
            "item_id": ing.item_id,
            "name": ing.item.name if ing.item else str(ing.item_id),
            "quantity": ing.quantity,
        })

    # 2. Consume blueprint if applicable
    blueprint_consumed = False
    if blueprint_item_id is not None:
        bp_slot = (
            db.query(models.CharacterInventory)
            .filter(
                models.CharacterInventory.character_id == character_id,
                models.CharacterInventory.item_id == blueprint_item_id,
            )
            .with_for_update()
            .first()
        )
        if bp_slot:
            bp_slot.quantity -= 1
            if bp_slot.quantity <= 0:
                db.delete(bp_slot)
            blueprint_consumed = True

    # 3. Create result item in inventory
    _add_items_to_inventory(db, character_id, recipe.result_item_id, recipe.result_quantity)

    db.flush()

    result_item = db.query(models.Items).filter(models.Items.id == recipe.result_item_id).first()

    # 4. Award XP and check rank-up
    xp_earned = 0
    new_total_xp = 0
    rank_up = False
    new_rank_name = None
    auto_learned = []

    if cp is not None:
        base_xp = recipe.xp_reward if recipe.xp_reward is not None else RARITY_XP_MAP.get(recipe.rarity, 10)
        multiplier = get_xp_multiplier(db, character_id)
        xp_earned = int(base_xp * multiplier)
        cp.experience += xp_earned
        new_total_xp = cp.experience

        # Check for rank-up (handle multi-rank jumps)
        all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
        while True:
            next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
            if not next_ranks:
                break  # Already at max rank
            next_rank = next_ranks[0]
            if cp.experience >= next_rank.required_experience:
                cp.current_rank = next_rank.rank_number
                rank_up = True
                new_rank_name = next_rank.name
                # Auto-learn recipes for the new rank
                new_recipes = auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
                auto_learned.extend(new_recipes)
            else:
                break

    return {
        "success": True,
        "crafted_item": {
            "item_id": recipe.result_item_id,
            "name": result_item.name if result_item else "???",
            "image": result_item.image if result_item else None,
            "quantity": recipe.result_quantity,
        },
        "consumed_materials": consumed_materials,
        "blueprint_consumed": blueprint_consumed,
        "xp_earned": xp_earned,
        "new_total_xp": new_total_xp,
        "rank_up": rank_up,
        "new_rank_name": new_rank_name,
        "auto_learned_recipes": auto_learned,
    }


def learn_recipe_for_character(db: Session, character_id: int, recipe_id: int) -> models.CharacterRecipe:
    """Learn a recipe permanently for a character."""
    cr = models.CharacterRecipe(
        character_id=character_id,
        recipe_id=recipe_id,
        learned_at=datetime.utcnow(),
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def get_recipe_item(db: Session, recipe_id: int) -> Optional[models.Items]:
    """Get the recipe-type item linked to a given recipe."""
    return (
        db.query(models.Items)
        .filter(models.Items.blueprint_recipe_id == recipe_id, models.Items.item_type == "recipe")
        .first()
    )


# ---------------------------------------------------------------------------
# Identification system
# ---------------------------------------------------------------------------

RARITY_IDENTIFY_LEVEL = {
    'common': 1, 'rare': 1,
    'epic': 2, 'mythical': 2,
    'legendary': 3, 'divine': 3, 'demonic': 3,
}


def find_identification_scroll(
    db: Session,
    character_id: int,
    required_level: int,
) -> Optional[models.CharacterInventory]:
    """Find the cheapest matching identification scroll in character inventory.

    A scroll matches if its identify_level >= required_level.
    Returns the inventory row (with quantity >= 1) or None.
    Prefers the lowest identify_level that still satisfies the requirement.
    """
    return (
        db.query(models.CharacterInventory)
        .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.quantity >= 1,
            models.Items.item_type == 'scroll',
            models.Items.identify_level.isnot(None),
            models.Items.identify_level >= required_level,
        )
        .order_by(models.Items.identify_level.asc())
        .first()
    )


# ---------------------------------------------------------------------------
# Time buff helpers
# ---------------------------------------------------------------------------

def get_active_buff(db: Session, character_id: int, buff_type: str) -> Optional[models.ActiveBuff]:
    """Returns active buff if not expired, deletes if expired."""
    buff = db.query(models.ActiveBuff).filter(
        models.ActiveBuff.character_id == character_id,
        models.ActiveBuff.buff_type == buff_type,
    ).first()
    if buff is None:
        return None
    if buff.expires_at <= datetime.utcnow():
        db.delete(buff)
        db.flush()
        return None
    return buff


def apply_buff(
    db: Session,
    character_id: int,
    buff_type: str,
    value: float,
    duration_minutes: int,
    source_name: str,
) -> models.ActiveBuff:
    """Upsert: replace existing buff of the same type or create new."""
    existing = db.query(models.ActiveBuff).filter(
        models.ActiveBuff.character_id == character_id,
        models.ActiveBuff.buff_type == buff_type,
    ).first()

    expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)

    if existing:
        existing.value = value
        existing.expires_at = expires_at
        existing.source_item_name = source_name
        existing.created_at = datetime.utcnow()
        db.flush()
        return existing
    else:
        buff = models.ActiveBuff(
            character_id=character_id,
            buff_type=buff_type,
            value=value,
            expires_at=expires_at,
            source_item_name=source_name,
        )
        db.add(buff)
        db.flush()
        return buff


def get_active_buffs(db: Session, character_id: int) -> List[models.ActiveBuff]:
    """Returns all active (non-expired) buffs, cleaning up expired ones."""
    now = datetime.utcnow()
    # Delete expired
    db.query(models.ActiveBuff).filter(
        models.ActiveBuff.character_id == character_id,
        models.ActiveBuff.expires_at <= now,
    ).delete(synchronize_session=False)
    db.flush()

    return db.query(models.ActiveBuff).filter(
        models.ActiveBuff.character_id == character_id,
        models.ActiveBuff.expires_at > now,
    ).all()


def get_xp_multiplier(db: Session, character_id: int) -> float:
    """Returns XP multiplier: 1.0 + buff_value if active xp_bonus exists, else 1.0."""
    buff = get_active_buff(db, character_id, "xp_bonus")
    if buff:
        return 1.0 + buff.value
    return 1.0
