from typing import Dict, Any

from sqlalchemy.orm import Session
import models
import schemas


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
    """
    slot_types = [
        'head', 'body', 'cloak', 'belt', 'ring','necklace',
        'main_weapon', 'additional_weapons','fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4'
    ]
    equipment_slots = []
    for slot_type in slot_types:
        equipment_slot = models.EquipmentSlot(
            character_id=character_id,
            slot_type=slot_type,
            item_id=None
        )
        db.add(equipment_slot)
        equipment_slots.append(equipment_slot)
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
        'main_weapon': ['main_weapon'],
        'additional_weapons': ['additional_weapons'],
        'fast_slot_1': ['consumable'],
        'fast_slot_2': ['consumable'],
        'fast_slot_3': ['consumable'],
        'fast_slot_4': ['consumable'],
    }
    return item_type in slot_to_item_mapping.get(slot_type, [])

def find_equipment_slot_for_item(db: Session, character_id: int, item_obj: models.Items):
    """
    Логика автоматического подбора слота (если item_type = head -> head, и т.д.
    Если consumable/scroll/misc -> первый свободный fast_slot).
    """
    # Для фиксированных типов
    fixed_types_map = {
        'head': 'head',
        'body': 'body',
        'cloak': 'cloak',
        'belt': 'belt',
        'ring': 'ring',
        'necklace': 'necklace',
        'main_weapon': 'main_weapon',
        'additional_weapons': 'additional_weapons'
    }
    slot_type = fixed_types_map.get(item_obj.item_type)

    if slot_type:
        slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.slot_type == slot_type
        ).first()
        return slot
    else:
        # Ищем первый свободный fast_slot
        fast_slots = ['fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4']
        slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.slot_type.in_(fast_slots),
            models.EquipmentSlot.item_id.is_(None)
        ).first()
        return slot

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
        ).order_by(models.CharacterInventory.quantity.asc()).first()
        if inv_slot:
            inv_slot.quantity += 1
            db.add(inv_slot)
            db.commit()
            return

    # Если предмет нестекаемый или все стеки заполнены — создаём новый
    new_inv = models.CharacterInventory(
        character_id=character_id,
        item_id=item_obj.id,
        quantity=1
    )
    db.add(new_inv)
    db.commit()

def build_modifiers_dict(item_obj: models.Items, negative: bool = False) -> dict:
    """
    Формируем словарь модификаторов (ключ -> величина),
    основываясь на полях *_modifier у объекта Items.
    Если negative=True, то все значения умножаем на -1.
    """

    def val(x: int | float) -> int | float:
        return -x if negative else x

    mods = {}

    if item_obj.strength_modifier:
        mods["strength"] = val(item_obj.strength_modifier)
    if item_obj.agility_modifier:
        mods["agility"] = val(item_obj.agility_modifier)
    if item_obj.intelligence_modifier:
        mods["intelligence"] = val(item_obj.intelligence_modifier)
    if item_obj.endurance_modifier:
        mods["endurance"] = val(item_obj.endurance_modifier)
    if item_obj.health_modifier:
        mods["health"] = val(item_obj.health_modifier)
    if item_obj.energy_modifier:
        mods["energy"] = val(item_obj.energy_modifier)
    if item_obj.mana_modifier:
        mods["mana"] = val(item_obj.mana_modifier)
    if item_obj.stamina_modifier:
        mods["stamina"] = val(item_obj.stamina_modifier)
    if item_obj.charisma_modifier:
        mods["charisma"] = val(item_obj.charisma_modifier)
    if item_obj.luck_modifier:
        mods["luck"] = val(item_obj.luck_modifier)
    if item_obj.damage_modifier:
        mods["damage"] = val(item_obj.damage_modifier)
    if item_obj.dodge_modifier:
        mods["dodge"] = val(item_obj.dodge_modifier)

    # Сопротивления:
    if item_obj.res_effects_modifier:
        mods["res_effects"] = val(item_obj.res_effects_modifier)
    if item_obj.res_physical_modifier:
        mods["res_physical"] = val(item_obj.res_physical_modifier)
    if item_obj.res_cutting_modifier:
        mods["res_cutting"] = val(item_obj.res_cutting_modifier)
    if item_obj.res_crushing_modifier:
        mods["res_crushing"] = val(item_obj.res_crushing_modifier)
    if item_obj.res_piercing_modifier:
        mods["res_piercing"] = val(item_obj.res_piercing_modifier)
    if item_obj.res_magic_modifier:
        mods["res_magic"] = val(item_obj.res_magic_modifier)
    if item_obj.res_fire_modifier:
        mods["res_fire"] = val(item_obj.res_fire_modifier)
    if item_obj.res_ice_modifier:
        mods["res_ice"] = val(item_obj.res_ice_modifier)
    if item_obj.res_water_modifier:
        # В модели CharacterAttributes это поле называется res_watering
        mods["res_watering"] = val(item_obj.res_water_modifier)
    if item_obj.res_electricity_modifier:
        mods["res_electricity"] = val(item_obj.res_electricity_modifier)
    if item_obj.res_wind_modifier:
        mods["res_wind"] = val(item_obj.res_wind_modifier)
    if item_obj.res_holy_modifier:
        # В модели атрибутов "res_sainting"
        mods["res_sainting"] = val(item_obj.res_holy_modifier)
    if item_obj.res_cursed_modifier:
        # В модели атрибутов "res_damning"
        mods["res_damning"] = val(item_obj.res_cursed_modifier)

    if item_obj.critical_hit_chance_modifier:
        mods["critical_hit_chance"] = val(item_obj.critical_hit_chance_modifier)
    if item_obj.critical_damage_modifier:
        mods["critical_damage"] = val(item_obj.critical_damage_modifier)

    # ПРИМЕЧАНИЕ: поля типа health_recovery / mana_recovery - это "расход" (consume)
    # Мы их используем только при "use_item", а не при "apply_modifiers" для экипировки.
    # Соответственно, здесь не добавляем их.
    return mods
