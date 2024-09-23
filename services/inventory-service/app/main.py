from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
import models
import schemas
import crud
from database import SessionLocal, engine

# Создаем все таблицы в базе данных, если они еще не созданы
models.Base.metadata.create_all(bind=engine)

# Создаем экземпляр приложения FastAPI
app = FastAPI()

router = APIRouter(prefix="/inventory")


# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=schemas.CharacterInventory)
def generate_character_inventory(inventory_request: schemas.CharacterInventoryCreate, db: Session = Depends(get_db)):
    """
    Эндпоинт для генерации инвентаря персонажа на основе ID персонажа.
    """
    existing_inventory = crud.get_inventory_by_character_id(db, inventory_request.character_id)
    if existing_inventory:
        raise HTTPException(status_code=400, detail="Инвентарь для данного персонажа уже существует")

    # Создаем инвентарь для каждого предмета
    for item in inventory_request.items:
        db_item = db.query(models.Items).filter(models.Items.id == item.id).first()  # Поиск предмета по ID
        if not db_item:
            raise HTTPException(status_code=404, detail=f"Предмет с ID {item.id} не найден")

        # Создаем запись в CharacterInventory
        db_inventory = models.CharacterInventory(
            character_id=inventory_request.character_id,
            item_id=item.id,
            slot_type='bag',  # Или другое значение в зависимости от вашей логики
            quantity=item.quantity
        )
        db.add(db_inventory)

    db.commit()  # Фиксируем изменения

    # Создаем записи в таблице слотов экипировки, оставляя их пустыми
    equipment_slots_data = [
        {"character_id": inventory_request.character_id, "slot_type": "head", "item_id": None},
        {"character_id": inventory_request.character_id, "slot_type": "chest", "item_id": None},
        {"character_id": inventory_request.character_id, "slot_type": "legs", "item_id": None},
        {"character_id": inventory_request.character_id, "slot_type": "feet", "item_id": None},
        {"character_id": inventory_request.character_id, "slot_type": "weapon", "item_id": None},
        {"character_id": inventory_request.character_id, "slot_type": "accessory", "item_id": None},
    ]

    # Создаем записи в таблице слотов экипировки
    for slot_data in equipment_slots_data:
        crud.create_equipment_slot(db, slot_data)

    # Формируем ответ
    return {
        "id": db_inventory.id,  # Возвращаем ID созданного инвентаря
        "character_id": inventory_request.character_id,
        "items": inventory_request.items,
        "equipment_slots": equipment_slots_data  # Возвращаем пустые слоты
    }

app.include_router(router)
