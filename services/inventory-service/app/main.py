import httpx
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, APIRouter, Query
from sqlalchemy.orm import Session
import models
import schemas
import crud
from database import SessionLocal, engine
from fastapi.middleware.cors import CORSMiddleware
from config import settings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://4452515-co41851.twc1.net",
        "http://4452515-co41851.twc1.net:5173",
        "http://4452515-co41851.twc1.net:5555",
        "http://4452515-co41851.twc1.net:8005",
        "http://4452515-co41851.twc1.net:8004",
        "http://4452515-co41851.twc1.net:8003",
        "http://4452515-co41851.twc1.net:8002",
        "http://4452515-co41851.twc1.net:8001",
        "http://4452515-co41851.twc1.net:8000",
        "http://localhost",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:8002",
        "http://localhost:8003",
        "http://localhost:8004",
        "http://localhost:8005",
        "http://localhost:5555",
                    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем таблицы, если не существуют
models.Base.metadata.create_all(bind=engine)

router = APIRouter(prefix="/inventory")

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

    # Создаём стандартные слоты
    equipment_slots = crud.create_default_equipment_slots(db, character_id)

    inventory_data = []
    for item_req in items_to_add:
        db_item = db.query(models.Items).filter(models.Items.id == item_req.item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail=f"Предмет {item_req.item_id} не найден")

        new_inv = models.CharacterInventory(
            character_id=character_id,
            item_id=item_req.item_id,
            quantity=item_req.quantity
        )
        db.add(new_inv)
        db.commit()

        inventory_data.append({
            "item_id": db_item.id,
            "name": db_item.name,
            "max_stack_size": db_item.max_stack_size,
            "quantity": item_req.quantity,
            "description": db_item.description,
        })

    return {"character_id": character_id, "items": inventory_data}


@router.get("/{character_id}/items", response_model=List[schemas.CharacterInventory])
def get_character_inventory(character_id: int, db: Session = Depends(get_db)):
    """
    Получить все предметы в инвентаре персонажа.
    """
    return crud.get_inventory_items(db, character_id)


@router.post("/{character_id}/items", response_model=List[schemas.CharacterInventory])
def add_item_to_inventory(character_id: int, item_data: schemas.InventoryItem, db: Session = Depends(get_db)):
    """
    Добавить предмет в инвентарь персонажа с учётом максимального стека.
    """
    db_item = db.query(models.Items).filter(models.Items.id == item_data.item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")


    remaining = item_data.quantity
    inventory_items = []

    # Заполняем имеющиеся слоты
    existing_slots = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_data.item_id,
        models.CharacterInventory.quantity < db_item.max_stack_size
    ).all()

    for slot in existing_slots:
        if remaining == 0:
            break
        space = db_item.max_stack_size - slot.quantity
        to_add = min(space, remaining)
        slot.quantity += to_add
        remaining -= to_add
        db.add(slot)
        inventory_items.append(slot)

    # Если ещё осталось - создаём новые записи
    while remaining > 0:
        to_add = min(remaining, db_item.max_stack_size)
        new_slot = models.CharacterInventory(
            character_id=character_id,
            item_id=item_data.item_id,
            quantity=to_add
        )
        db.add(new_slot)
        db.commit()
        db.refresh(new_slot)
        inventory_items.append(new_slot)
        remaining -= to_add

    return inventory_items


@router.delete("/{character_id}/items/{item_id}", response_model=List[schemas.CharacterInventory])
def remove_item_from_inventory(character_id: int, item_id: int, quantity: int = 1, db: Session = Depends(get_db)):
    """
    Удалить некоторое количество предметов из инвентаря персонажа.
    """
    total_remove = quantity
    slots = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id
    ).order_by(models.CharacterInventory.quantity.desc()).all()

    if not slots:
        raise HTTPException(status_code=404, detail="Нет такого предмета в инвентаре")

    updated_items = []
    for s in slots:
        if total_remove == 0:
            break
        if s.quantity <= total_remove:
            total_remove -= s.quantity
            db.delete(s)
        else:
            s.quantity -= total_remove
            total_remove = 0
            updated_items.append(s)

    if total_remove > 0:
        raise HTTPException(status_code=400, detail="Недостаточно предметов для удаления")

    db.commit()
    return updated_items


@router.get("/{character_id}/equipment", response_model=List[schemas.EquipmentSlot])
def get_equipment_slots(character_id: int, db: Session = Depends(get_db)):
    return crud.get_equipment_slots(db, character_id)


# -----------------------------------------------------------------------------
# Вспомогательные функции для обращений к сервису атрибутов
# -----------------------------------------------------------------------------
async def apply_modifiers_in_attributes_service(character_id: int, modifiers: dict):
    """
    Единственная функция, которая будет вызывать /apply_modifiers (с любым знаком).
    """
    url = f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/apply_modifiers"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=modifiers)
        resp.raise_for_status()


async def recover_in_attributes_service(character_id: int, recovery: dict):
    """
    Для восстановления ресурсов (health_recovery, mana_recovery и т.д.).
    """
    url = f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/recover"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=recovery)
        resp.raise_for_status()


# -----------------------------------------------------------------------------
# Экипировка (equip)
# -----------------------------------------------------------------------------
@router.post("/{character_id}/equip", response_model=schemas.EquipmentSlot)
async def equip_item(character_id: int, req: schemas.EquipItemRequest, db: Session = Depends(get_db)):
    """
    Надеть предмет (транзакция):
      1) Проверяем, что предмет есть в инвентаре
      2) Если слот занят - снимаем старый предмет (и вычитаем его модификаторы)
      3) Уменьшаем инвентарь на 1, надеваем предмет
      4) Вызываем apply_modifiers с положительными значениями
      5) Если всё ОК — commit, иначе rollback
      6) По окончании — пересчитываем быстрые слоты (recalc_fast_slots).
    """
    db.begin()  # начинаем транзакцию вручную

    try:
        # 1) Проверяем предмет
        db_item = db.query(models.Items).filter(models.Items.id == req.item_id).first()
        if not db_item:
            db.rollback()
            raise HTTPException(status_code=404, detail="Предмет не найден")

        # 2) Проверяем наличие в инвентаре
        inv_slot = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.item_id == req.item_id
        ).order_by(models.CharacterInventory.quantity.desc()).first()

        if not inv_slot or inv_slot.quantity < 1:
            db.rollback()
            raise HTTPException(status_code=400, detail="Недостаточно предметов в инвентаре")

        # 3) Ищем слот
        slot = crud.find_equipment_slot_for_item(db, character_id, db_item)
        if not slot:
            db.rollback()
            raise HTTPException(status_code=404, detail="Нет подходящего слота для этого предмета")

        # Если слот уже занят => снимаем старый предмет
        if slot.item_id:
            old_item = db.query(models.Items).filter(models.Items.id == slot.item_id).first()
            if old_item:
                # возвращаем старый предмет в инвентарь
                crud.return_item_to_inventory(db, character_id, old_item)
                db.flush()
                # вычитаем его бонусы (отправляем отрицательные значения)
                minus_mods = crud.build_modifiers_dict(old_item, negative=True)
                if minus_mods:
                    await apply_modifiers_in_attributes_service(character_id, minus_mods)

            slot.item_id = None
            db.add(slot)
            db.flush()

        # 4) Уменьшаем количество нового предмета
        inv_slot.quantity -= 1
        if inv_slot.quantity <= 0:
            db.delete(inv_slot)
        else:
            db.add(inv_slot)
        db.flush()

        # Надеваем предмет
        slot.item_id = db_item.id
        db.add(slot)
        db.flush()

        # 5) Добавляем модификаторы (положительные)
        plus_mods = crud.build_modifiers_dict(db_item, negative=False)
        if plus_mods:
            await apply_modifiers_in_attributes_service(character_id, plus_mods)

        # Всё прошло успешно — commit
        db.commit()
        db.refresh(slot)

    except HTTPException:
        db.rollback()
        raise
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка обращения к сервису атрибутов: {e}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {e}")

    # ---------------------------------------
    # 6) После успешной транзакции пересчитываем быстрые слоты
    # (вне try/except, т.к. мы уже закоммитили изменения)
    # Если recalc_fast_slots тоже должно быть атомарным, можно вызвать его ДО коммита.
    crud.recalc_fast_slots(db, character_id)
    # ---------------------------------------

    return slot


# -----------------------------------------------------------------------------
# Снятие (unequip)
# -----------------------------------------------------------------------------
@router.post("/{character_id}/unequip", response_model=schemas.EquipmentSlot)
async def unequip_item(character_id: int, slot_type: str, db: Session = Depends(get_db)):
    """
    Снять предмет (транзакция):
      1) Возвращаем предмет в инвентарь
      2) Передаём отрицательные значения в apply_modifiers
      3) Очищаем слот
      4) rollback при ошибке, commit при успехе
      5) Вызываем recalc_fast_slots (после commit)
    """
    db.begin()
    try:
        slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.slot_type == slot_type
        ).with_for_update().first()

        if not slot or not slot.item_id:
            db.rollback()
            raise HTTPException(status_code=404, detail="Слот пуст или не найден")

        old_item = db.query(models.Items).filter(models.Items.id == slot.item_id).first()
        if not old_item:
            db.rollback()
            raise HTTPException(status_code=404, detail="Предмет в слоте не найден")

        # 1) Возвращаем предмет
        crud.return_item_to_inventory(db, character_id, old_item)
        db.flush()

        # 2) Убираем его бонусы => negative=True
        minus_mods = crud.build_modifiers_dict(old_item, negative=True)
        if minus_mods:
            await apply_modifiers_in_attributes_service(character_id, minus_mods)

        # 3) Очищаем слот
        slot.item_id = None
        db.add(slot)
        db.flush()

        db.commit()
        db.refresh(slot)

    except HTTPException:
        db.rollback()
        raise
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка обращения к сервису атрибутов: {e}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {e}")

    # 5) После коммита пересчитываем быстрые слоты
    crud.recalc_fast_slots(db, character_id)

    return slot


# -----------------------------------------------------------------------------
# Использование предмета (use_item)
# -----------------------------------------------------------------------------
@router.post("/{character_id}/use_item")
async def use_item(character_id: int, req: schemas.InventoryItem, db: Session = Depends(get_db)):
    """
    Используем расходник:
      1) Уменьшаем quantity
      2) Если есть health_recovery и т.п., вызываем /recover
    """
    db_item = db.query(models.Items).filter(models.Items.id == req.item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if db_item.item_type not in ("consumable", "scroll", "misc", "resource"):
        raise HTTPException(status_code=400, detail="Нельзя использовать этот предмет")

    inv_slot = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == req.item_id
    ).first()
    if not inv_slot or inv_slot.quantity < req.quantity:
        raise HTTPException(status_code=400, detail="Недостаточно предметов в инвентаре")

    inv_slot.quantity -= req.quantity
    if inv_slot.quantity <= 0:
        db.delete(inv_slot)
    else:
        db.add(inv_slot)
    db.commit()

    # Поля восстановления
    recover_payload = {}
    if db_item.health_recovery and db_item.health_recovery > 0:
        recover_payload["health_recovery"] = db_item.health_recovery * req.quantity
    if db_item.energy_recovery and db_item.energy_recovery > 0:
        recover_payload["energy_recovery"] = db_item.energy_recovery * req.quantity
    if db_item.mana_recovery and db_item.mana_recovery > 0:
        recover_payload["mana_recovery"] = db_item.mana_recovery * req.quantity
    if db_item.stamina_recovery and db_item.stamina_recovery > 0:
        recover_payload["stamina_recovery"] = db_item.stamina_recovery * req.quantity

    if recover_payload:
        await recover_in_attributes_service(character_id, recover_payload)

    return {"status": "ok", "detail": "Предмет использован"}

@router.get("/items", response_model=List[schemas.Item])
def list_items(
    q: Optional[str] = Query(None, description="Поиск по названию"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Возвращает список предметов.

    * q — подстрочный поиск по полю name (ILIKE %q%).
    * page, page_size — пагинация.
    """
    query = db.query(models.Items)

    if q:
        query = query.filter(models.Items.name.ilike(f"%{q}%"))

    items = (
        query
        .order_by(models.Items.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return items

@router.post("/items", response_model=schemas.Item, status_code=201)
def create_item(item_in: schemas.ItemCreate, db: Session = Depends(get_db)):
    """
    Создаёт новый предмет.

    • Проверяет уникальность `name`.
    • При успехе возвращает сохранённый объект.
    """

    # 1) проверяем дубликат имени
    if db.query(models.Items).filter(models.Items.name == item_in.name).first():
        raise HTTPException(
            status_code=400,
            detail="Предмет с таким названием уже существует",
        )

    # 2) создаём объект (Pydantic → SQLAlchemy), пропуская неуказанные поля
    db_item = models.Items(**item_in.dict(exclude_unset=True))
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    return db_item

@router.get("/items/{item_id}", response_model=schemas.Item)
def get_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.Items).get(item_id)          # .get = by PK
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    return db_item

@router.put("/items/{item_id}", response_model=schemas.Item)
def update_item(item_id: int, item_in: schemas.ItemCreate, db: Session = Depends(get_db)):
    """
    Обновляет все переданные поля предмета (exclude_unset=True).
    Проверка уникальности имени сохраняется.
    """
    db_item = db.query(models.Items).get(item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    # если меняем name – проверяем дубликат
    if item_in.name and item_in.name != db_item.name:
        if db.query(models.Items).filter(models.Items.name == item_in.name).first():
            raise HTTPException(
                status_code=400,
                detail="Предмет с таким названием уже существует",
            )

    # частичное обновление
    for field, value in item_in.dict(exclude_unset=True).items():
        setattr(db_item, field, value)

    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    """
    Удаляет предмет. При необходимости можно добавить проверки на то,
    используется ли предмет в инвентарях/слотах.
    """
    db_item = db.query(models.Items).get(item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    db.delete(db_item)
    db.commit()

@router.get(
    "/characters/{character_id}/fast_slots",
    response_model=List[schemas.FastSlot]
)
def get_fast_slots(
    character_id: int,
    db: Session = Depends(get_db),
):
    """
    Возвращает список включённых fast_slot_* для этого персонажа.
    Для каждого слота отдаёт:
      - slot_type: fast_slot_1…fast_slot_10
      - item_id   : id надетого consumable
      - quantity  : сколько штук этого item_id осталось в инвентаре
    """
    # 1) Берём все enabled fast-слоты
    slots = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.slot_type.like("fast_slot_%"),
        models.EquipmentSlot.is_enabled == True,
    ).all()

    result = []
    for slot in slots:
        if not slot.item_id:
            # пропускаем пустые
            continue

        # 2) Считаем в инвентаре оставшееся количество этого item_id
        total_qty = (
            db.query(models.CharacterInventory)
              .filter(
                  models.CharacterInventory.character_id == character_id,
                  models.CharacterInventory.item_id == slot.item_id,
              )
              .with_entities(models.CharacterInventory.quantity)
              .all()
        )
        # total_qty — список кортежей [(qty1,), (qty2,), …]
        qty = sum(q[0] for q in total_qty)
        item = slot.item  # благодаря relationship
        if not item:
            continue  # на всякий случай

        # 3) Добавляем в ответ
        result.append(schemas.FastSlot(
            slot_type=slot.slot_type,
            item_id=slot.item_id,
            quantity=qty,
            name=item.name,
            image=item.image or "",
        ))

    return result

app.include_router(router)
