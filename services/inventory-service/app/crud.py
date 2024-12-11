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
