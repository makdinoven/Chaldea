from typing import List

from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
import models
import schemas
import crud
from database import SessionLocal, engine
from fastapi.middleware.cors import CORSMiddleware


# Создаем экземпляр приложения FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем все таблицы в базе данных, если они еще не созданы
models.Base.metadata.create_all(bind=engine)




router = APIRouter(prefix="/inventory")


# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=schemas.InventoryResponse)
def create_inventory(inventory_request: schemas.InventoryRequest, db: Session = Depends(get_db)):
    """
    Создание инвентаря и слотов экипировки для персонажа.
    """
    character_id = inventory_request.character_id
    items_to_add = inventory_request.items

    # Создаём стандартные слоты экипировки для персонажа
    equipment_slots = crud.create_default_equipment_slots(db, character_id)
    print(f"[INFO] Созданы слоты экипировки для персонажа {character_id}: {equipment_slots}")

    inventory_data = []

    for item_request in items_to_add:
        item_id = item_request.item_id
        quantity = item_request.quantity

        # Проверяем, существует ли предмет в таблице items
        db_item = db.query(models.Items).filter(models.Items.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail=f"Предмет с ID {item_id} не найден в базе данных")

        # Проверяем возможность добавления предмета
        if db_item.max_stack_size == 1 and quantity > 1:
            raise HTTPException(status_code=400, detail=f"Предмет с ID {item_id} не может быть в количестве больше 1")

        # Добавляем запись в таблицу character_inventory
        new_inventory_item = models.CharacterInventory(
            character_id=character_id,
            item_id=item_id,
            quantity=quantity
        )
        db.add(new_inventory_item)

        # Собираем данные для ответа
        inventory_data.append({
            "item_id": db_item.id,
            "name": db_item.name,
            "max_stack_size": db_item.max_stack_size,
            "quantity": quantity,
            "description": db_item.description,
            "weight": db_item.weight,
        })

    db.commit()

    return {"character_id": character_id, "items": inventory_data}

@router.get("/{character_id}/items", response_model=List[schemas.CharacterInventory])
def get_character_inventory(character_id: int, db: Session = Depends(get_db)):
    """
    Получить все предметы в инвентаре персонажа.
    """
    inventory_items = crud.get_inventory_items(db, character_id)
    return inventory_items

@router.post("/{character_id}/items", response_model=List[schemas.CharacterInventory])
def add_item_to_inventory(
    character_id: int,
    item_data: schemas.InventoryItem,
    db: Session = Depends(get_db)
):
    """
    Добавить предмет в инвентарь персонажа с учётом максимального стека.
    """
    db_item = db.query(models.Items).filter(models.Items.id == item_data.item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if not db_item.max_stack_size and item_data.quantity > 1:
        raise HTTPException(status_code=400, detail="Нестакаемый предмет не может иметь количество больше 1")

    remaining_quantity = item_data.quantity
    inventory_items = []

    # Заполняем существующие слоты, где есть место
    existing_inventory_items = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_data.item_id,
        models.CharacterInventory.quantity < db_item.max_stack_size
    ).all()

    for inventory_item in existing_inventory_items:
        if remaining_quantity == 0:
            break

        available_space = db_item.max_stack_size - inventory_item.quantity
        quantity_to_add = min(available_space, remaining_quantity)
        inventory_item.quantity += quantity_to_add
        remaining_quantity -= quantity_to_add
        db.add(inventory_item)
        inventory_items.append(inventory_item)

    # Создаём новые слоты, если осталось количество
    while remaining_quantity > 0:
        quantity_to_add = min(remaining_quantity, db_item.max_stack_size)
        new_inventory_item = models.CharacterInventory(
            character_id=character_id,
            item_id=item_data.item_id,
            quantity=quantity_to_add
        )
        db.add(new_inventory_item)
        db.commit()
        db.refresh(new_inventory_item)
        inventory_items.append(new_inventory_item)
        remaining_quantity -= quantity_to_add

    return inventory_items


@router.delete("/{character_id}/items/{item_id}", response_model=List[schemas.CharacterInventory])
def remove_item_from_inventory(
    character_id: int,
    item_id: int,
    quantity: int = 1,
    db: Session = Depends(get_db)
):
    """
    Удалить определённое количество предметов из инвентаря персонажа.
    """
    total_quantity_to_remove = quantity
    inventory_items = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id
    ).order_by(models.CharacterInventory.quantity.desc()).all()

    if not inventory_items:
        raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

    updated_items = []

    for inventory_item in inventory_items:
        if total_quantity_to_remove == 0:
            break

        if inventory_item.quantity <= total_quantity_to_remove:
            total_quantity_to_remove -= inventory_item.quantity
            db.delete(inventory_item)
        else:
            inventory_item.quantity -= total_quantity_to_remove
            db.add(inventory_item)
            total_quantity_to_remove = 0
            updated_items.append(inventory_item)

    if total_quantity_to_remove > 0:
        raise HTTPException(status_code=400, detail="Недостаточно количества предметов для удаления")

    db.commit()
    return updated_items

@router.get("/{character_id}/equipment", response_model=List[schemas.EquipmentSlot])
def get_equipment_slots(character_id: int, db: Session = Depends(get_db)):
    """
    Получить все слоты экипировки персонажа.
    """
    equipment_slots = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id
    ).all()
    return equipment_slots


@router.post("/{character_id}/equip", response_model=schemas.EquipmentSlot)
def equip_item(
    character_id: int,
    equip_data: schemas.EquipmentSlotCreate,
    db: Session = Depends(get_db)
):
    """
    Экипировать предмет из инвентаря в слот экипировки.
    """
    item = db.query(models.Items).filter(models.Items.id == equip_data.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if not crud.is_item_compatible_with_slot(item.item_type, equip_data.slot_type):
        raise HTTPException(status_code=400, detail="Предмет несовместим со слотом")

    equipment_slot = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.slot_type == equip_data.slot_type
    ).first()

    if not equipment_slot:
        raise HTTPException(status_code=404, detail="Слот экипировки не найден")

    if equipment_slot.item_id:
        raise HTTPException(status_code=400, detail="Слот уже занят")

    # Ищем слот в инвентаре с этим предметом
    inventory_item = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == equip_data.item_id
    ).order_by(models.CharacterInventory.quantity.desc()).first()

    if not inventory_item:
        raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

    # Уменьшаем количество или удаляем слот, если количество стало 0
    inventory_item.quantity -= 1
    if inventory_item.quantity == 0:
        db.delete(inventory_item)
    else:
        db.add(inventory_item)

    equipment_slot.item_id = equip_data.item_id
    db.add(equipment_slot)
    db.commit()
    db.refresh(equipment_slot)
    return equipment_slot

@router.post("/{character_id}/unequip", response_model=schemas.EquipmentSlot)
def unequip_item(
    character_id: int,
    slot_type: str,
    db: Session = Depends(get_db)
):
    """
    Снять предмет из слота экипировки в инвентарь.
    """
    equipment_slot = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.slot_type == slot_type
    ).first()

    if not equipment_slot or not equipment_slot.item_id:
        raise HTTPException(status_code=404, detail="В этом слоте нет предмета")

    item_id = equipment_slot.item_id
    db_item = db.query(models.Items).filter(models.Items.id == item_id).first()

    remaining_quantity = 1

    # Заполняем существующие слоты, где есть место
    existing_inventory_items = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id,
        models.CharacterInventory.quantity < db_item.max_stack_size
    ).all()

    for inventory_item in existing_inventory_items:
        if remaining_quantity == 0:
            break

        available_space = db_item.max_stack_size - inventory_item.quantity
        quantity_to_add = min(available_space, remaining_quantity)
        inventory_item.quantity += quantity_to_add
        remaining_quantity -= quantity_to_add
        db.add(inventory_item)

    # Создаём новый слот, если осталось количество
    if remaining_quantity > 0:
        new_inventory_item = models.CharacterInventory(
            character_id=character_id,
            item_id=item_id,
            quantity=remaining_quantity
        )
        db.add(new_inventory_item)

    equipment_slot.item_id = None
    db.add(equipment_slot)

    db.commit()
    db.refresh(equipment_slot)
    return equipment_slot

app.include_router(router)
