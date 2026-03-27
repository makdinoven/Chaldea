import os
import asyncio
import math
import threading
import random
from datetime import datetime
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
from rabbitmq_consumer import start_consumer
from sqlalchemy import text
from auth_http import get_current_user_via_http, get_admin_user, require_permission
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inventory-service")

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _run_consumer_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_consumer())


@app.on_event("startup")
def startup():
    thread = threading.Thread(target=_run_consumer_thread, daemon=True)
    thread.start()


router = APIRouter(prefix="/inventory")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_character_ownership(db: Session, character_id: int, user_id: int):
    """Проверяет, что персонаж существует и принадлежит текущему пользователю."""
    result = db.execute(text("SELECT user_id FROM characters WHERE id = :cid"), {"cid": character_id}).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    if result[0] != user_id:
        raise HTTPException(status_code=403, detail="Вы можете управлять только своими персонажами")


def check_not_in_battle(db: Session, character_id: int, message: str = "Действие заблокировано во время боя"):
    """Raise 400 if character is in an active battle (shared DB query)."""
    if crud.is_character_in_battle(db, character_id):
        raise HTTPException(status_code=400, detail=message)


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


# --- Item catalog (must be BEFORE /{character_id}/... to avoid route conflict) ---

@router.get("/items", response_model=List[schemas.Item])
def list_items(
    q: Optional[str] = Query(None, description="Поиск по названию"),
    item_types: Optional[str] = Query(None, description="Фильтр по типам (через запятую)"),
    exclude_types: Optional[str] = Query(None, description="Исключить типы (через запятую)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Возвращает список предметов с поиском и пагинацией."""
    query = db.query(models.Items)
    if q:
        query = query.filter(models.Items.name.ilike(f"%{q}%"))
    if item_types:
        types_list = [t.strip() for t in item_types.split(",") if t.strip()]
        if types_list:
            query = query.filter(models.Items.item_type.in_(types_list))
    if exclude_types:
        exc_list = [t.strip() for t in exclude_types.split(",") if t.strip()]
        if exc_list:
            query = query.filter(models.Items.item_type.notin_(exc_list))
    items = (
        query
        .order_by(models.Items.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items

@router.post("/items", response_model=schemas.Item, status_code=201)
def create_item(item_in: schemas.ItemCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("items:create"))):
    """Создаёт новый предмет."""
    if db.query(models.Items).filter(models.Items.name == item_in.name).first():
        raise HTTPException(status_code=400, detail="Предмет с таким названием уже существует")
    db_item = models.Items(**item_in.dict(exclude_unset=True))
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.get("/items/{item_id}", response_model=schemas.Item)
def get_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.Items).get(item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    return db_item

@router.put("/items/{item_id}", response_model=schemas.Item)
def update_item(item_id: int, item_in: schemas.ItemCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("items:update"))):
    """Обновляет все переданные поля предмета."""
    db_item = db.query(models.Items).get(item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    if item_in.name and item_in.name != db_item.name:
        if db.query(models.Items).filter(models.Items.name == item_in.name).first():
            raise HTTPException(status_code=400, detail="Предмет с таким названием уже существует")
    for field, value in item_in.dict(exclude_unset=True).items():
        setattr(db_item, field, value)
    db.commit()
    db.refresh(db_item)
    return db_item


# --- Character inventory ---

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
        inventory_items.append(new_slot)
        remaining -= to_add

    db.commit()
    for item in inventory_items:
        db.refresh(item)

    return inventory_items


@router.delete("/{character_id}/items/{item_id}", response_model=List[schemas.CharacterInventory])
def remove_item_from_inventory(character_id: int, item_id: int, quantity: int = 1, db: Session = Depends(get_db), current_user = Depends(get_current_user_via_http)):
    """
    Удалить некоторое количество предметов из инвентаря персонажа.
    """
    verify_character_ownership(db, character_id, current_user.id)
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
async def equip_item(character_id: int, req: schemas.EquipItemRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user_via_http)):
    """
    Надеть предмет (транзакция):
      1) Проверяем, что предмет есть в инвентаре
      2) Если слот занят - снимаем старый предмет (и вычитаем его модификаторы)
      3) Уменьшаем инвентарь на 1, надеваем предмет
      4) Вызываем apply_modifiers с положительными значениями
      5) Если всё ОК — commit, иначе rollback
      6) По окончании — пересчитываем быстрые слоты (recalc_fast_slots).
    """
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Вы не можете менять экипировку во время боя")

    try:
        # 1) Проверяем предмет
        db_item = db.query(models.Items).filter(models.Items.id == req.item_id).first()
        if not db_item:
            db.rollback()
            raise HTTPException(status_code=404, detail="Предмет не найден")

        # 2) Проверяем наличие в инвентаре
        if req.inventory_item_id:
            # Конкретный экземпляр (с заточкой, камнями и т.д.)
            inv_slot = db.query(models.CharacterInventory).filter(
                models.CharacterInventory.id == req.inventory_item_id,
                models.CharacterInventory.character_id == character_id,
                models.CharacterInventory.item_id == req.item_id,
            ).with_for_update().first()
        else:
            # Любой экземпляр (обратная совместимость)
            inv_slot = db.query(models.CharacterInventory).filter(
                models.CharacterInventory.character_id == character_id,
                models.CharacterInventory.item_id == req.item_id
            ).order_by(models.CharacterInventory.quantity.desc()).with_for_update().first()

        if not inv_slot or inv_slot.quantity < 1:
            db.rollback()
            raise HTTPException(status_code=400, detail="Недостаточно предметов в инвентаре")

        # 2.5) Проверяем, что предмет опознан
        if not inv_slot.is_identified:
            db.rollback()
            raise HTTPException(status_code=400, detail="Предмет не опознан")

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
                # Copy enhancement data and socketed_gems from slot to the newly created inventory row
                old_enh_bonuses = crud.get_enhancement_bonuses(slot)
                old_socketed_gems = crud.get_socketed_gems(slot)
                old_current_durability = slot.current_durability
                if slot.enhancement_points_spent > 0 or old_socketed_gems or old_current_durability is not None:
                    new_inv_row = db.query(models.CharacterInventory).filter(
                        models.CharacterInventory.character_id == character_id,
                        models.CharacterInventory.item_id == old_item.id,
                    ).order_by(models.CharacterInventory.id.desc()).first()
                    if new_inv_row:
                        new_inv_row.enhancement_points_spent = slot.enhancement_points_spent
                        crud.set_enhancement_bonuses(new_inv_row, old_enh_bonuses)
                        crud.set_socketed_gems(new_inv_row, old_socketed_gems)
                        new_inv_row.current_durability = old_current_durability
                        db.flush()
                # вычитаем его бонусы (отправляем отрицательные значения)
                old_gem_items = crud.load_gem_items(db, old_socketed_gems) if old_socketed_gems else []
                minus_mods = crud.build_modifiers_dict(old_item, negative=True, enhancement_bonuses=old_enh_bonuses, gem_items=old_gem_items, current_durability=old_current_durability, max_durability=old_item.max_durability)
                if minus_mods:
                    await apply_modifiers_in_attributes_service(character_id, minus_mods)

            slot.item_id = None
            slot.enhancement_points_spent = 0
            slot.enhancement_bonuses = None
            slot.socketed_gems = None
            slot.current_durability = None
            db.add(slot)
            db.flush()

        # Save enhancement data, socketed_gems and durability from inventory before removing
        inv_enh_points = inv_slot.enhancement_points_spent
        inv_enh_bonuses = crud.get_enhancement_bonuses(inv_slot)
        inv_socketed_gems = crud.get_socketed_gems(inv_slot)
        inv_current_durability = inv_slot.current_durability

        # 4) Уменьшаем количество нового предмета
        inv_slot.quantity -= 1
        if inv_slot.quantity <= 0:
            db.delete(inv_slot)
        else:
            db.add(inv_slot)
        db.flush()

        # Надеваем предмет
        slot.item_id = db_item.id
        slot.enhancement_points_spent = inv_enh_points
        crud.set_enhancement_bonuses(slot, inv_enh_bonuses)
        crud.set_socketed_gems(slot, inv_socketed_gems)
        slot.current_durability = inv_current_durability
        db.add(slot)
        db.flush()

        # 5) Добавляем модификаторы (положительные)
        inv_gem_items = crud.load_gem_items(db, inv_socketed_gems) if inv_socketed_gems else []
        plus_mods = crud.build_modifiers_dict(db_item, negative=False, enhancement_bonuses=inv_enh_bonuses, gem_items=inv_gem_items, current_durability=inv_current_durability, max_durability=db_item.max_durability)
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

    # Trigger title evaluation after equip (non-fatal)
    try:
        httpx.post(
            f"{settings.CHARACTER_SERVICE_URL}/characters/internal/evaluate-titles",
            json={"character_id": character_id},
            timeout=5.0,
        )
    except Exception as e:
        logger.warning(f"Title evaluation error after equip for character {character_id}: {e}")

    return slot


# -----------------------------------------------------------------------------
# Снятие (unequip)
# -----------------------------------------------------------------------------
@router.post("/{character_id}/unequip", response_model=schemas.EquipmentSlot)
async def unequip_item(character_id: int, slot_type: str, db: Session = Depends(get_db), current_user = Depends(get_current_user_via_http)):
    """
    Снять предмет (транзакция):
      1) Возвращаем предмет в инвентарь
      2) Передаём отрицательные значения в apply_modifiers
      3) Очищаем слот
      4) rollback при ошибке, commit при успехе
      5) Вызываем recalc_fast_slots (после commit)
    """
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Вы не можете менять экипировку во время боя")
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

        # 1) Save enhancement data, socketed_gems and durability before clearing slot
        slot_enh_bonuses = crud.get_enhancement_bonuses(slot)
        slot_enh_points = slot.enhancement_points_spent
        slot_socketed_gems = crud.get_socketed_gems(slot)
        slot_current_durability = slot.current_durability

        # 2) Возвращаем предмет
        crud.return_item_to_inventory(db, character_id, old_item)
        db.flush()

        # Copy enhancement data, socketed_gems and durability to the newly created inventory row
        if slot_enh_points > 0 or slot_socketed_gems or slot_current_durability is not None:
            new_inv_row = db.query(models.CharacterInventory).filter(
                models.CharacterInventory.character_id == character_id,
                models.CharacterInventory.item_id == old_item.id,
            ).order_by(models.CharacterInventory.id.desc()).first()
            if new_inv_row:
                new_inv_row.enhancement_points_spent = slot_enh_points
                crud.set_enhancement_bonuses(new_inv_row, slot_enh_bonuses)
                crud.set_socketed_gems(new_inv_row, slot_socketed_gems)
                new_inv_row.current_durability = slot_current_durability
                db.flush()

        # 3) Убираем его бонусы => negative=True
        slot_gem_items = crud.load_gem_items(db, slot_socketed_gems) if slot_socketed_gems else []
        minus_mods = crud.build_modifiers_dict(old_item, negative=True, enhancement_bonuses=slot_enh_bonuses, gem_items=slot_gem_items, current_durability=slot_current_durability, max_durability=old_item.max_durability)
        if minus_mods:
            await apply_modifiers_in_attributes_service(character_id, minus_mods)

        # 4) Очищаем слот
        slot.item_id = None
        slot.enhancement_points_spent = 0
        slot.enhancement_bonuses = None
        slot.socketed_gems = None
        slot.current_durability = None
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

    # Trigger title evaluation after unequip (non-fatal)
    try:
        httpx.post(
            f"{settings.CHARACTER_SERVICE_URL}/characters/internal/evaluate-titles",
            json={"character_id": character_id},
            timeout=5.0,
        )
    except Exception as e:
        logger.warning(f"Title evaluation error after unequip for character {character_id}: {e}")

    return slot


# -----------------------------------------------------------------------------
# Использование предмета (use_item)
# -----------------------------------------------------------------------------
@router.post("/{character_id}/use_item")
async def use_item(character_id: int, req: schemas.InventoryItem, db: Session = Depends(get_db), current_user = Depends(get_current_user_via_http)):
    """
    Используем расходник:
      1) Уменьшаем quantity
      2) Если есть health_recovery и т.п., вызываем /recover
    """
    verify_character_ownership(db, character_id, current_user.id)
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

@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("items:delete"))):
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

@router.delete("/{character_id}/all")
def delete_all_inventory(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("items:delete")),
):
    """
    Bulk delete all inventory items and equipment slots for a character.
    Admin-only. Idempotent: returns 200 with counts=0 if no data found.
    Does NOT reverse attribute modifiers from equipped items.
    """
    result = crud.delete_all_inventory_for_character(db, character_id)
    return {
        "detail": "All inventory cleared",
        "items_deleted": result["items_deleted"],
        "slots_deleted": result["slots_deleted"],
    }



# ---------------------------------------------------------------------------
# Trade endpoints
# ---------------------------------------------------------------------------

from rabbitmq_publisher import publish_notification_sync


@router.post("/trade/propose", response_model=schemas.TradeProposeResponse, status_code=201)
def trade_propose(
    req: schemas.TradeProposeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Create a new trade offer between two characters on the same location."""
    # Ownership check
    verify_character_ownership(db, req.initiator_character_id, current_user.id)

    # Cannot trade with yourself
    if req.initiator_character_id == req.target_character_id:
        raise HTTPException(status_code=400, detail="Нельзя предложить обмен самому себе")

    # Target character must exist and belong to a user
    target_user_id = crud.get_character_user_id(db, req.target_character_id)
    if target_user_id is None:
        raise HTTPException(status_code=404, detail="Целевой персонаж не найден")

    # Same location check
    init_loc = crud.get_character_location(db, req.initiator_character_id)
    target_loc = crud.get_character_location(db, req.target_character_id)
    if init_loc is None or target_loc is None or init_loc != target_loc:
        raise HTTPException(status_code=400, detail="Персонажи должны находиться на одной локации")

    # Neither in battle
    if crud.is_character_in_battle(db, req.initiator_character_id):
        raise HTTPException(status_code=400, detail="Ваш персонаж сейчас в бою")
    if crud.is_character_in_battle(db, req.target_character_id):
        raise HTTPException(status_code=400, detail="Целевой персонаж сейчас в бою")

    # No existing active trade between them
    existing = crud.get_active_trade_between(db, req.initiator_character_id, req.target_character_id)
    if existing:
        raise HTTPException(status_code=400, detail="Между этими персонажами уже есть активное предложение обмена")

    trade = crud.create_trade_offer(db, req.initiator_character_id, req.target_character_id, init_loc)

    # Notify target user
    initiator_name = crud.get_character_name(db, req.initiator_character_id)
    try:
        publish_notification_sync(target_user_id, f"{initiator_name} предлагает вам обмен.")
    except Exception:
        pass  # Non-critical: trade is created even if notification fails

    return schemas.TradeProposeResponse(
        trade_id=trade.id,
        initiator_character_id=trade.initiator_character_id,
        target_character_id=trade.target_character_id,
        status=trade.status,
    )


@router.put("/trade/{trade_id}/items", response_model=schemas.TradeStateResponse)
def trade_update_items(
    trade_id: int,
    req: schemas.TradeUpdateItemsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Update items and gold for one side of the trade."""
    trade = crud.get_trade_offer(db, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Предложение обмена не найдено")

    if trade.status not in ('pending', 'negotiating'):
        raise HTTPException(status_code=400, detail="Этот обмен уже завершён или отменён")

    # Verify participant
    if req.character_id not in (trade.initiator_character_id, trade.target_character_id):
        raise HTTPException(status_code=403, detail="Вы не являетесь участником этого обмена")

    # Verify ownership of character
    verify_character_ownership(db, req.character_id, current_user.id)

    # Validate gold >= 0
    if req.gold < 0:
        raise HTTPException(status_code=400, detail="Количество золота не может быть отрицательным")

    # Validate character has enough gold
    if req.gold > 0:
        balance = crud.get_character_gold(db, req.character_id)
        if balance < req.gold:
            raise HTTPException(status_code=400, detail="Недостаточно золота")

    # Validate item ownership
    if req.items:
        error = crud.verify_item_ownership(db, req.character_id, req.items)
        if error:
            raise HTTPException(status_code=400, detail=error)

    trade = crud.update_trade_items(db, trade, req.character_id, req.items, req.gold)
    state = crud.build_trade_state(db, trade)
    return state


@router.post("/trade/{trade_id}/confirm", response_model=schemas.TradeConfirmResponse)
def trade_confirm(
    trade_id: int,
    req: schemas.TradeConfirmRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Confirm trade from one side. If both confirmed, execute atomically."""
    trade = crud.get_trade_offer(db, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Предложение обмена не найдено")

    if trade.status not in ('pending', 'negotiating'):
        raise HTTPException(status_code=400, detail="Этот обмен уже завершён или отменён")

    # Verify participant
    if req.character_id not in (trade.initiator_character_id, trade.target_character_id):
        raise HTTPException(status_code=403, detail="Вы не являетесь участником этого обмена")

    verify_character_ownership(db, req.character_id, current_user.id)

    both_confirmed = crud.confirm_trade(db, trade, req.character_id)

    if both_confirmed:
        # Execute trade atomically
        try:
            crud.execute_trade(db, trade)
            db.commit()
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Ошибка при выполнении обмена: {e}")

        # Notify both parties
        init_name = crud.get_character_name(db, trade.initiator_character_id)
        target_name = crud.get_character_name(db, trade.target_character_id)
        init_user = crud.get_character_user_id(db, trade.initiator_character_id)
        target_user = crud.get_character_user_id(db, trade.target_character_id)

        try:
            if init_user:
                publish_notification_sync(init_user, f"Обмен с {target_name} завершён успешно!")
            if target_user:
                publish_notification_sync(target_user, f"Обмен с {init_name} завершён успешно!")
        except Exception:
            pass

        return schemas.TradeConfirmResponse(
            trade_id=trade.id,
            status="completed",
            message="Обмен завершён успешно!",
        )
    else:
        db.commit()
        return schemas.TradeConfirmResponse(
            trade_id=trade.id,
            status=trade.status,
            message="Ожидание подтверждения второй стороны",
        )


@router.post("/trade/{trade_id}/cancel", response_model=schemas.TradeCancelResponse)
def trade_cancel(
    trade_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Cancel an active trade."""
    trade = crud.get_trade_offer(db, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Предложение обмена не найдено")

    if trade.status not in ('pending', 'negotiating'):
        raise HTTPException(status_code=400, detail="Этот обмен уже завершён или отменён")

    # Verify participant — check which character belongs to the current user
    init_user = crud.get_character_user_id(db, trade.initiator_character_id)
    target_user = crud.get_character_user_id(db, trade.target_character_id)

    if current_user.id not in (init_user, target_user):
        raise HTTPException(status_code=403, detail="Вы не являетесь участником этого обмена")

    trade.status = 'cancelled'
    db.commit()

    # Notify the other party
    if current_user.id == init_user:
        other_user_id = target_user
        canceller_char_id = trade.initiator_character_id
    else:
        other_user_id = init_user
        canceller_char_id = trade.target_character_id

    canceller_name = crud.get_character_name(db, canceller_char_id)
    try:
        if other_user_id:
            publish_notification_sync(other_user_id, f"{canceller_name} отменил предложение обмена.")
    except Exception:
        pass

    return schemas.TradeCancelResponse(trade_id=trade.id, status="cancelled")


@router.get("/trade/pending/{character_id}", response_model=schemas.PendingTradesResponse)
def trade_get_pending(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Get all pending/negotiating trades for a character."""
    verify_character_ownership(db, character_id, current_user.id)

    trades = crud.get_pending_trades_for_character(db, character_id)
    incoming = []
    outgoing = []

    for trade in trades:
        initiator_name = crud.get_character_name(db, trade.initiator_character_id)
        target_name = crud.get_character_name(db, trade.target_character_id)

        is_incoming = trade.target_character_id == character_id
        direction = "incoming" if is_incoming else "outgoing"

        entry = schemas.PendingTradeEntry(
            trade_id=trade.id,
            initiator_character_id=trade.initiator_character_id,
            initiator_name=initiator_name,
            target_character_id=trade.target_character_id,
            target_name=target_name,
            status=trade.status,
            created_at=trade.created_at.isoformat() if trade.created_at else "",
            direction=direction,
        )

        if is_incoming:
            incoming.append(entry)
        else:
            outgoing.append(entry)

    return schemas.PendingTradesResponse(incoming=incoming, outgoing=outgoing)


@router.get("/trade/{trade_id}", response_model=schemas.TradeStateResponse)
def trade_get_state(
    trade_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Get the full state of a trade offer."""
    trade = crud.get_trade_offer(db, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Предложение обмена не найдено")

    # Verify participant
    init_user = crud.get_character_user_id(db, trade.initiator_character_id)
    target_user = crud.get_character_user_id(db, trade.target_character_id)

    if current_user.id not in (init_user, target_user):
        raise HTTPException(status_code=403, detail="Вы не являетесь участником этого обмена")

    state = crud.build_trade_state(db, trade)
    return state


# -----------------------------------------------------------------------------
# Internal endpoints (service-to-service, no auth)
# -----------------------------------------------------------------------------

@router.post("/internal/characters/{character_id}/consume_item",
             response_model=schemas.ConsumeItemResponse)
def consume_item_internal(
    character_id: int,
    req: schemas.ConsumeItemRequest,
    db: Session = Depends(get_db),
):
    """
    Списывает 1 единицу предмета из инвентаря персонажа и очищает
    быстрый слот, если предмет закончился.
    Используется battle-service при применении расходника в бою.
    Без авторизации — только для межсервисных вызовов.
    """
    # Atomic decrement: only succeeds if quantity > 0
    result = db.execute(
        text(
            "UPDATE character_inventory "
            "SET quantity = quantity - 1 "
            "WHERE character_id = :cid AND item_id = :iid AND quantity > 0"
        ),
        {"cid": character_id, "iid": req.item_id},
    )
    db.commit()

    remaining = 0

    if result.rowcount > 0:
        # Read remaining quantity
        row = db.execute(
            text(
                "SELECT quantity FROM character_inventory "
                "WHERE character_id = :cid AND item_id = :iid"
            ),
            {"cid": character_id, "iid": req.item_id},
        ).fetchone()
        remaining = row[0] if row else 0

        # Clean up inventory row if quantity reached 0
        if remaining == 0:
            db.execute(
                text(
                    "DELETE FROM character_inventory "
                    "WHERE character_id = :cid AND item_id = :iid AND quantity = 0"
                ),
                {"cid": character_id, "iid": req.item_id},
            )
            db.commit()

    # Always clear fast slot for this item when quantity is 0 or item wasn't in inventory
    # This prevents the item from reappearing in future battles
    if remaining == 0:
        db.execute(
            text(
                "UPDATE equipment_slots SET item_id = NULL "
                "WHERE character_id = :cid AND item_id = :iid "
                "AND slot_type LIKE 'fast_slot_%%'"
            ),
            {"cid": character_id, "iid": req.item_id},
        )
        db.commit()

    return {"status": "ok", "remaining_quantity": remaining}


# ---------------------------------------------------------------------------
# Profession endpoints — PUBLIC
# ---------------------------------------------------------------------------

@router.get("/professions", response_model=List[schemas.ProfessionOut])
def list_professions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Список всех активных профессий с рангами."""
    return crud.get_active_professions(db)


@router.get("/professions/{character_id}/my")
def get_my_profession(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Получить текущую профессию персонажа."""
    verify_character_ownership(db, character_id, current_user.id)
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=404, detail="У персонажа нет профессии")

    # Find rank name
    rank_name = ""
    if cp.profession and cp.profession.ranks:
        for r in cp.profession.ranks:
            if r.rank_number == cp.current_rank:
                rank_name = r.name
                break

    return {
        "character_id": character_id,
        "profession": {
            "id": cp.profession.id,
            "name": cp.profession.name,
            "slug": cp.profession.slug,
            "description": cp.profession.description,
            "icon": cp.profession.icon,
            "sort_order": cp.profession.sort_order,
            "is_active": cp.profession.is_active,
            "ranks": [
                {
                    "id": r.id,
                    "rank_number": r.rank_number,
                    "name": r.name,
                    "description": r.description,
                    "required_experience": r.required_experience,
                    "icon": r.icon,
                }
                for r in sorted(cp.profession.ranks, key=lambda x: x.rank_number)
            ],
        },
        "current_rank": cp.current_rank,
        "rank_name": rank_name,
        "experience": cp.experience,
        "chosen_at": cp.chosen_at.isoformat() if cp.chosen_at else "",
    }


@router.post("/professions/{character_id}/choose")
def choose_profession(
    character_id: int,
    req: schemas.ChooseProfessionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Выбрать профессию для персонажа."""
    verify_character_ownership(db, character_id, current_user.id)

    # Check no existing profession
    existing = crud.get_character_profession(db, character_id)
    if existing:
        raise HTTPException(status_code=400, detail="У персонажа уже есть профессия. Используйте смену профессии.")

    # Verify profession exists and is active
    profession = crud.get_profession_by_id(db, req.profession_id)
    if not profession:
        raise HTTPException(status_code=404, detail="Профессия не найдена")
    if not profession.is_active:
        raise HTTPException(status_code=400, detail="Эта профессия сейчас недоступна")

    cp, auto_recipes = crud.choose_profession(db, character_id, req.profession_id)

    return {
        "character_id": character_id,
        "profession_id": cp.profession_id,
        "current_rank": cp.current_rank,
        "experience": cp.experience,
        "auto_learned_recipes": [
            {"id": r.id, "name": r.name} for r in auto_recipes
        ],
    }


@router.post("/professions/{character_id}/change")
def change_profession(
    character_id: int,
    req: schemas.ChangeProfessionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Сменить профессию персонажа (сброс ранга/опыта, рецепты сохраняются)."""
    verify_character_ownership(db, character_id, current_user.id)

    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=404, detail="У персонажа нет профессии")

    if cp.profession_id == req.profession_id:
        raise HTTPException(status_code=400, detail="Персонаж уже имеет эту профессию")

    # Verify new profession exists and is active
    new_profession = crud.get_profession_by_id(db, req.profession_id)
    if not new_profession:
        raise HTTPException(status_code=404, detail="Профессия не найдена")
    if not new_profession.is_active:
        raise HTTPException(status_code=400, detail="Эта профессия сейчас недоступна")

    old_name = cp.profession.name if cp.profession else "Неизвестная"
    cp, auto_recipes = crud.change_profession(db, cp, req.profession_id)

    return {
        "character_id": character_id,
        "old_profession": old_name,
        "new_profession": new_profession.name,
        "current_rank": cp.current_rank,
        "experience": cp.experience,
        "message": "Профессия изменена. Прогресс сброшен, выученные рецепты сохранены.",
        "auto_learned_recipes": [
            {"id": r.id, "name": r.name} for r in auto_recipes
        ],
    }


# ---------------------------------------------------------------------------
# Profession endpoints — ADMIN
# ---------------------------------------------------------------------------

@router.get("/admin/professions", response_model=List[schemas.ProfessionOut])
def admin_list_professions(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:read")),
):
    """Список всех профессий (включая неактивные) — админ."""
    return crud.get_all_professions(db)


@router.post("/admin/professions", response_model=schemas.ProfessionOut, status_code=201)
def admin_create_profession(
    data: schemas.ProfessionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:create")),
):
    """Создать профессию — админ."""
    existing = db.query(models.Profession).filter(
        (models.Profession.name == data.name) | (models.Profession.slug == data.slug)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Профессия с таким названием или slug уже существует")

    profession = crud.create_profession(db, data)
    # Reload with ranks
    return crud.get_profession_by_id(db, profession.id)


@router.put("/admin/professions/{profession_id}", response_model=schemas.ProfessionOut)
def admin_update_profession(
    profession_id: int,
    data: schemas.ProfessionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:update")),
):
    """Обновить профессию — админ."""
    profession = crud.get_profession_by_id(db, profession_id)
    if not profession:
        raise HTTPException(status_code=404, detail="Профессия не найдена")

    # Check unique constraints if name/slug changed
    if data.name and data.name != profession.name:
        if db.query(models.Profession).filter(models.Profession.name == data.name).first():
            raise HTTPException(status_code=400, detail="Профессия с таким названием уже существует")
    if data.slug and data.slug != profession.slug:
        if db.query(models.Profession).filter(models.Profession.slug == data.slug).first():
            raise HTTPException(status_code=400, detail="Профессия с таким slug уже существует")

    profession = crud.update_profession(db, profession, data)
    return crud.get_profession_by_id(db, profession.id)


@router.delete("/admin/professions/{profession_id}")
def admin_delete_profession(
    profession_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:delete")),
):
    """Удалить профессию — админ."""
    profession = crud.get_profession_by_id(db, profession_id)
    if not profession:
        raise HTTPException(status_code=404, detail="Профессия не найдена")
    crud.delete_profession(db, profession)
    return {"detail": "Профессия удалена"}


# Rank admin endpoints

@router.post("/admin/professions/{profession_id}/ranks", status_code=201)
def admin_create_rank(
    profession_id: int,
    data: schemas.ProfessionRankCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:create")),
):
    """Создать ранг для профессии — админ."""
    profession = crud.get_profession_by_id(db, profession_id)
    if not profession:
        raise HTTPException(status_code=404, detail="Профессия не найдена")

    # Check unique rank_number for this profession
    existing = db.query(models.ProfessionRank).filter(
        models.ProfessionRank.profession_id == profession_id,
        models.ProfessionRank.rank_number == data.rank_number,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ранг с таким номером уже существует для этой профессии")

    rank = crud.create_profession_rank(db, profession_id, data)
    return {
        "id": rank.id,
        "profession_id": rank.profession_id,
        "rank_number": rank.rank_number,
        "name": rank.name,
        "description": rank.description,
        "required_experience": rank.required_experience,
        "icon": rank.icon,
    }


@router.put("/admin/professions/ranks/{rank_id}")
def admin_update_rank(
    rank_id: int,
    data: schemas.ProfessionRankUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:update")),
):
    """Обновить ранг — админ."""
    rank = crud.get_rank_by_id(db, rank_id)
    if not rank:
        raise HTTPException(status_code=404, detail="Ранг не найден")
    rank = crud.update_profession_rank(db, rank, data)
    return {
        "id": rank.id,
        "profession_id": rank.profession_id,
        "rank_number": rank.rank_number,
        "name": rank.name,
        "description": rank.description,
        "required_experience": rank.required_experience,
        "icon": rank.icon,
    }


@router.delete("/admin/professions/ranks/{rank_id}")
def admin_delete_rank(
    rank_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:delete")),
):
    """Удалить ранг — админ."""
    rank = crud.get_rank_by_id(db, rank_id)
    if not rank:
        raise HTTPException(status_code=404, detail="Ранг не найден")
    crud.delete_profession_rank(db, rank)
    return {"detail": "Ранг удалён"}


@router.post("/admin/professions/{character_id}/set-rank")
def admin_set_rank(
    character_id: int,
    req: schemas.AdminSetRankRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:manage")),
):
    """Установить ранг профессии персонажа вручную — админ."""
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=404, detail="У персонажа нет профессии")

    # Verify rank exists for the profession
    rank = db.query(models.ProfessionRank).filter(
        models.ProfessionRank.profession_id == cp.profession_id,
        models.ProfessionRank.rank_number == req.rank_number,
    ).first()
    if not rank:
        raise HTTPException(status_code=400, detail="Такой ранг не существует для этой профессии")

    cp = crud.set_character_rank(db, cp, req.rank_number)
    return {
        "character_id": character_id,
        "profession_id": cp.profession_id,
        "current_rank": cp.current_rank,
        "rank_name": rank.name,
        "experience": cp.experience,
    }


# ---------------------------------------------------------------------------
# Crafting endpoints — PUBLIC
# ---------------------------------------------------------------------------

@router.get("/crafting/{character_id}/recipes")
def get_character_recipes(
    character_id: int,
    profession_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Список доступных рецептов персонажа (выученные + из чертежей)."""
    verify_character_ownership(db, character_id, current_user.id)
    return crud.get_available_recipes_for_character(db, character_id, profession_id)


@router.post("/crafting/{character_id}/craft")
def craft_item(
    character_id: int,
    req: schemas.CraftRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Выполнить крафт предмета."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя крафтить во время боя")

    # 1. Get character's profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")

    # 2. Get recipe
    recipe = crud.get_recipe_by_id(db, req.recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")
    if not recipe.is_active:
        raise HTTPException(status_code=400, detail="Этот рецепт неактивен")

    # 3. Verify profession matches
    if cp.profession_id != recipe.profession_id:
        prof_name = recipe.profession.name if recipe.profession else "другая"
        raise HTTPException(status_code=400, detail=f"Требуется профессия: {prof_name}")

    # 4. Verify rank
    if cp.current_rank < recipe.required_rank:
        raise HTTPException(status_code=400, detail=f"Недостаточный ранг. Требуется ранг {recipe.required_rank}, текущий: {cp.current_rank}")

    # 5. Verify recipe access (learned or blueprint)
    if req.blueprint_item_id is not None:
        # Blueprint-sourced: verify blueprint exists in inventory
        bp_inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.item_id == req.blueprint_item_id,
            models.CharacterInventory.quantity > 0,
        ).first()
        if not bp_inv:
            raise HTTPException(status_code=400, detail="Чертёж не найден в инвентаре")

        bp_item = db.query(models.Items).filter(models.Items.id == req.blueprint_item_id).first()
        if not bp_item or bp_item.item_type != 'blueprint' or bp_item.blueprint_recipe_id != req.recipe_id:
            raise HTTPException(status_code=400, detail="Этот предмет не является чертежом для данного рецепта")
    else:
        # Learned recipe: verify in character_recipes
        learned = db.query(models.CharacterRecipe).filter(
            models.CharacterRecipe.character_id == character_id,
            models.CharacterRecipe.recipe_id == req.recipe_id,
        ).first()
        if not learned:
            raise HTTPException(status_code=400, detail="Рецепт не изучен")

    # 6. Execute craft in transaction
    try:
        result = crud.execute_craft(db, character_id, recipe, req.blueprint_item_id, cp=cp)
        db.commit()
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Crafting error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании предмета")


@router.post("/crafting/{character_id}/learn-recipe")
def learn_recipe(
    character_id: int,
    req: schemas.LearnRecipeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Выучить рецепт навсегда."""
    verify_character_ownership(db, character_id, current_user.id)

    # Get recipe
    recipe = crud.get_recipe_by_id(db, req.recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")

    # Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession_id != recipe.profession_id:
        prof_name = recipe.profession.name if recipe.profession else "другая"
        raise HTTPException(status_code=400, detail=f"Требуется профессия: {prof_name}")

    # Check rank
    if cp.current_rank < recipe.required_rank:
        raise HTTPException(status_code=400, detail=f"Недостаточный ранг. Требуется ранг {recipe.required_rank}")

    # Check not already learned
    existing = db.query(models.CharacterRecipe).filter(
        models.CharacterRecipe.character_id == character_id,
        models.CharacterRecipe.recipe_id == req.recipe_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Рецепт уже выучен")

    crud.learn_recipe_for_character(db, character_id, req.recipe_id)
    return {"message": "Рецепт выучен", "recipe_id": recipe.id, "recipe_name": recipe.name}


@router.post("/crafting/{character_id}/learn-from-item")
def learn_recipe_from_item(
    character_id: int,
    req: schemas.LearnRecipeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Изучить рецепт из предмета-рецепта в инвентаре. Предмет расходуется."""
    verify_character_ownership(db, character_id, current_user.id)

    # Find the recipe item in items table
    recipe_item = (
        db.query(models.Items)
        .filter(
            models.Items.blueprint_recipe_id == req.recipe_id,
            models.Items.item_type == "recipe",
        )
        .first()
    )
    if not recipe_item:
        raise HTTPException(status_code=404, detail="Предмет-рецепт не найден")

    # Check character has it in inventory
    inv_entry = (
        db.query(models.CharacterInventory)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.item_id == recipe_item.id,
        )
        .first()
    )
    if not inv_entry or inv_entry.quantity < 1:
        raise HTTPException(status_code=400, detail="У вас нет этого рецепта в инвентаре")

    # Get recipe
    recipe = crud.get_recipe_by_id(db, req.recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")

    # Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession_id != recipe.profession_id:
        prof_name = recipe.profession.name if recipe.profession else "другая"
        raise HTTPException(status_code=400, detail=f"Требуется профессия: {prof_name}")

    # Check rank
    if cp.current_rank < recipe.required_rank:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточный ранг. Требуется ранг {recipe.required_rank}",
        )

    # Check not already learned
    existing = db.query(models.CharacterRecipe).filter(
        models.CharacterRecipe.character_id == character_id,
        models.CharacterRecipe.recipe_id == req.recipe_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Рецепт уже выучен")

    # Learn the recipe
    crud.learn_recipe_for_character(db, character_id, req.recipe_id)

    # Consume 1 recipe item from inventory
    if inv_entry.quantity > 1:
        inv_entry.quantity -= 1
    else:
        db.delete(inv_entry)
    db.commit()

    return {
        "message": "Рецепт выучен из предмета",
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
    }


# ---------------------------------------------------------------------------
# Recipe endpoints — ADMIN
# ---------------------------------------------------------------------------

@router.get("/admin/recipes")
def admin_list_recipes(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    profession_id: Optional[int] = Query(None),
    rarity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:read")),
):
    """Список рецептов с пагинацией и фильтрами — админ."""
    recipes, total = crud.get_recipes_admin(db, page, per_page, search, profession_id, rarity)

    items = []
    for recipe in recipes:
        ingredients = [
            {
                "item_id": ing.item_id,
                "item_name": ing.item.name if ing.item else "???",
                "item_image": ing.item.image if ing.item else None,
                "quantity": ing.quantity,
                "available": 0,
            }
            for ing in recipe.ingredients
        ]
        recipe_item = crud.get_recipe_item(db, recipe.id)
        items.append({
            "id": recipe.id,
            "name": recipe.name,
            "description": recipe.description,
            "profession_id": recipe.profession_id,
            "profession_name": recipe.profession.name if recipe.profession else "",
            "required_rank": recipe.required_rank,
            "result_item_id": recipe.result_item_id,
            "result_item_name": recipe.result_item.name if recipe.result_item else "",
            "result_quantity": recipe.result_quantity,
            "rarity": recipe.rarity,
            "icon": recipe.icon,
            "xp_reward": recipe.xp_reward,
            "is_blueprint_recipe": recipe.is_blueprint_recipe,
            "is_active": recipe.is_active,
            "auto_learn_rank": recipe.auto_learn_rank,
            "ingredients": ingredients,
            "recipe_item_id": recipe_item.id if recipe_item else None,
            "recipe_item_name": recipe_item.name if recipe_item else None,
        })

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.post("/admin/recipes", status_code=201)
def admin_create_recipe(
    data: schemas.RecipeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:create")),
):
    """Создать рецепт — админ."""
    # Verify profession exists
    profession = crud.get_profession_by_id(db, data.profession_id)
    if not profession:
        raise HTTPException(status_code=400, detail="Профессия не найдена")

    # Verify result item exists
    result_item = db.query(models.Items).filter(models.Items.id == data.result_item_id).first()
    if not result_item:
        raise HTTPException(status_code=400, detail="Результирующий предмет не найден")

    # Verify unique name
    existing = db.query(models.Recipe).filter(models.Recipe.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Рецепт с таким названием уже существует")

    # Verify all ingredient items exist
    for ing in data.ingredients:
        item = db.query(models.Items).filter(models.Items.id == ing.item_id).first()
        if not item:
            raise HTTPException(status_code=400, detail=f"Ингредиент с id={ing.item_id} не найден")

    recipe = crud.create_recipe(db, data)
    recipe = crud.get_recipe_by_id(db, recipe.id)
    recipe_item = crud.get_recipe_item(db, recipe.id)

    return {
        "id": recipe.id,
        "name": recipe.name,
        "description": recipe.description,
        "profession_id": recipe.profession_id,
        "profession_name": recipe.profession.name if recipe.profession else "",
        "required_rank": recipe.required_rank,
        "result_item_id": recipe.result_item_id,
        "result_item_name": recipe.result_item.name if recipe.result_item else "",
        "result_quantity": recipe.result_quantity,
        "rarity": recipe.rarity,
        "icon": recipe.icon,
        "xp_reward": recipe.xp_reward,
        "is_blueprint_recipe": recipe.is_blueprint_recipe,
        "is_active": recipe.is_active,
        "auto_learn_rank": recipe.auto_learn_rank,
        "ingredients": [
            {
                "item_id": ing.item_id,
                "item_name": ing.item.name if ing.item else "???",
                "item_image": ing.item.image if ing.item else None,
                "quantity": ing.quantity,
                "available": 0,
            }
            for ing in recipe.ingredients
        ],
        "recipe_item_id": recipe_item.id if recipe_item else None,
        "recipe_item_name": recipe_item.name if recipe_item else None,
    }


@router.put("/admin/recipes/{recipe_id}")
def admin_update_recipe(
    recipe_id: int,
    data: schemas.RecipeUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:update")),
):
    """Обновить рецепт — админ."""
    recipe = crud.get_recipe_by_id(db, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")

    # Validate name uniqueness if changed
    if data.name and data.name != recipe.name:
        existing = db.query(models.Recipe).filter(models.Recipe.name == data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Рецепт с таким названием уже существует")

    # Validate profession if changed
    if data.profession_id is not None:
        profession = crud.get_profession_by_id(db, data.profession_id)
        if not profession:
            raise HTTPException(status_code=400, detail="Профессия не найдена")

    # Validate result item if changed
    if data.result_item_id is not None:
        result_item = db.query(models.Items).filter(models.Items.id == data.result_item_id).first()
        if not result_item:
            raise HTTPException(status_code=400, detail="Результирующий предмет не найден")

    # Validate ingredients if provided
    if data.ingredients is not None:
        for ing in data.ingredients:
            item = db.query(models.Items).filter(models.Items.id == ing.item_id).first()
            if not item:
                raise HTTPException(status_code=400, detail=f"Ингредиент с id={ing.item_id} не найден")

    recipe = crud.update_recipe(db, recipe, data)
    recipe = crud.get_recipe_by_id(db, recipe.id)
    recipe_item = crud.get_recipe_item(db, recipe.id)

    return {
        "id": recipe.id,
        "name": recipe.name,
        "description": recipe.description,
        "profession_id": recipe.profession_id,
        "profession_name": recipe.profession.name if recipe.profession else "",
        "required_rank": recipe.required_rank,
        "result_item_id": recipe.result_item_id,
        "result_item_name": recipe.result_item.name if recipe.result_item else "",
        "result_quantity": recipe.result_quantity,
        "rarity": recipe.rarity,
        "icon": recipe.icon,
        "xp_reward": recipe.xp_reward,
        "is_blueprint_recipe": recipe.is_blueprint_recipe,
        "is_active": recipe.is_active,
        "auto_learn_rank": recipe.auto_learn_rank,
        "ingredients": [
            {
                "item_id": ing.item_id,
                "item_name": ing.item.name if ing.item else "???",
                "item_image": ing.item.image if ing.item else None,
                "quantity": ing.quantity,
                "available": 0,
            }
            for ing in recipe.ingredients
        ],
        "recipe_item_id": recipe_item.id if recipe_item else None,
        "recipe_item_name": recipe_item.name if recipe_item else None,
    }


@router.delete("/admin/recipes/{recipe_id}")
def admin_delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("professions:delete")),
):
    """Удалить рецепт — админ."""
    recipe = crud.get_recipe_by_id(db, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")
    crud.delete_recipe(db, recipe)
    return {"detail": "Рецепт удалён"}


# ---------------------------------------------------------------------------
# Sharpening endpoints — PUBLIC
# ---------------------------------------------------------------------------

@router.get("/crafting/{character_id}/sharpen-info/{item_row_id}")
def get_sharpen_info(
    character_id: int,
    item_row_id: int,
    source: str = Query("inventory", regex="^(inventory|equipment)$"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Получить информацию о заточке предмета: текущие бонусы, доступные статы, точильные камни.
    source=inventory для предмета в инвентаре, source=equipment для экипированного."""
    verify_character_ownership(db, character_id, current_user.id)

    # Get the row depending on source
    if source == "equipment":
        row = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == item_row_id,
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.item_id.isnot(None),
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Экипированный предмет не найден")
        item_id = row.item_id
    else:
        row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == item_row_id,
            models.CharacterInventory.character_id == character_id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        item_id = row.item_id

    item_obj = db.query(models.Items).filter(models.Items.id == item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if item_obj.item_type not in crud.SHARPENABLE_TYPES:
        raise HTTPException(status_code=400, detail="Этот тип предмета нельзя затачивать")

    bonuses = crud.get_enhancement_bonuses(row)
    points_spent = row.enhancement_points_spent
    points_remaining = crud.MAX_ENHANCEMENT_POINTS - points_spent

    # Build stats list
    SHARPEN_INCREMENT_INFO = {
        'critical_hit_chance_modifier': 0.5,
        'critical_damage_modifier': 1.0,
    }
    stats = []
    for field in crud.ALL_SHARPENABLE_FIELDS:
        base_val = getattr(item_obj, field, 0) or 0
        is_existing = base_val != 0
        sharpened_count = bonuses.get(field, 0)
        point_cost = 1
        can_sharpen = (sharpened_count < crud.MAX_STAT_SHARPEN) and (points_spent + point_cost <= crud.MAX_ENHANCEMENT_POINTS)

        if field in SHARPEN_INCREMENT_INFO:
            increment = SHARPEN_INCREMENT_INFO[field]
        elif field in crud.MAIN_STAT_FIELDS:
            increment = 1.0
        else:
            increment = 0.1

        stats.append({
            "field": field,
            "name": crud.STAT_DISPLAY_NAMES.get(field, field),
            "base_value": float(base_val),
            "sharpened_count": sharpened_count,
            "max": crud.MAX_STAT_SHARPEN,
            "is_existing": is_existing,
            "point_cost": point_cost,
            "can_sharpen": can_sharpen,
            "increment": increment,
        })

    # Get whetstones from inventory
    whetstones = []
    whetstone_inv_rows = (
        db.query(models.CharacterInventory)
        .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.Items.whetstone_level.isnot(None),
        )
        .all()
    )
    for ws_row in whetstone_inv_rows:
        ws_item = ws_row.item
        chance_pct = int(crud.WHETSTONE_CHANCE.get(ws_item.whetstone_level, 0) * 100)
        whetstones.append({
            "inventory_item_id": ws_row.id,
            "name": ws_item.name,
            "quantity": ws_row.quantity,
            "success_chance": chance_pct,
        })

    return {
        "item_name": item_obj.name,
        "item_type": item_obj.item_type,
        "points_spent": points_spent,
        "points_remaining": points_remaining,
        "stats": stats,
        "whetstones": whetstones,
    }


@router.post("/crafting/{character_id}/sharpen")
async def sharpen_item(
    character_id: int,
    req: schemas.SharpenRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Заточить конкретный стат предмета с помощью точильного камня."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя затачивать предметы во время боя")

    # 1. Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession.slug != "blacksmith":
        raise HTTPException(status_code=400, detail="Только кузнец может затачивать предметы")

    # 2. Get item row (inventory or equipment)
    is_equipped = req.source == "equipment"
    eq_slot = None

    if is_equipped:
        eq_slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == req.inventory_item_id,
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.item_id.isnot(None),
        ).with_for_update().first()
        if not eq_slot:
            raise HTTPException(status_code=404, detail="Экипированный предмет не найден")
        item_row = eq_slot
        item_id = eq_slot.item_id
    else:
        inv_row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.inventory_item_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if not inv_row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        item_row = inv_row
        item_id = inv_row.item_id

    item_obj = db.query(models.Items).filter(models.Items.id == item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    # 2.5. Check identification (only for inventory items — equipped items are always identified)
    if not is_equipped:
        if not inv_row.is_identified:
            raise HTTPException(status_code=400, detail="Предмет не опознан")

    # 3. Validate item type
    if item_obj.item_type not in crud.SHARPENABLE_TYPES:
        raise HTTPException(status_code=400, detail="Этот тип предмета нельзя затачивать")

    # 4. Validate stat_field
    if req.stat_field not in crud.ALL_SHARPENABLE_FIELDS:
        raise HTTPException(status_code=400, detail="Недопустимый стат для заточки")

    # 5. Parse enhancement data
    bonuses = crud.get_enhancement_bonuses(item_row)
    current_count = bonuses.get(req.stat_field, 0)

    # 6. Check max per stat
    if current_count >= crud.MAX_STAT_SHARPEN:
        raise HTTPException(status_code=400, detail="Этот стат уже заточен до максимума (+5)")

    # 7. Calculate point cost
    base_val = getattr(item_obj, req.stat_field, 0) or 0
    is_existing = base_val != 0
    point_cost = 1

    # 8. Check points budget
    if item_row.enhancement_points_spent + point_cost > crud.MAX_ENHANCEMENT_POINTS:
        raise HTTPException(status_code=400, detail="Недостаточно поинтов заточки")

    # 9. Find and validate whetstone
    whetstone_inv = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.whetstone_item_id,
        models.CharacterInventory.character_id == character_id,
    ).with_for_update().first()
    if not whetstone_inv or whetstone_inv.quantity < 1:
        raise HTTPException(status_code=400, detail="Точильный камень не найден в инвентаре")

    whetstone_item = db.query(models.Items).filter(models.Items.id == whetstone_inv.item_id).first()
    if not whetstone_item or whetstone_item.whetstone_level is None:
        raise HTTPException(status_code=400, detail="Этот предмет не является точильным камнем")

    success_chance = crud.WHETSTONE_CHANCE.get(whetstone_item.whetstone_level, 0)

    try:
        # 10. Consume whetstone (always)
        whetstone_inv.quantity -= 1
        if whetstone_inv.quantity <= 0:
            db.delete(whetstone_inv)
        db.flush()

        # 11. Roll for success
        success = random.random() < success_chance

        stat_display = crud.STAT_DISPLAY_NAMES.get(req.stat_field, req.stat_field)
        old_value = float(current_count)

        if success:
            # Increment the stat count in bonuses
            bonuses[req.stat_field] = current_count + 1
            crud.set_enhancement_bonuses(item_row, bonuses)
            item_row.enhancement_points_spent += point_cost
            db.flush()

            new_value = float(current_count + 1)

            # 12. If item is equipped, apply the stat delta to character attributes
            if is_equipped:
                # Item is already the equipment slot row — apply delta directly
                SHARPEN_INCREMENT = {
                    'critical_hit_chance_modifier': 0.5,
                    'critical_damage_modifier': 1.0,
                }
                delta = {}
                key = req.stat_field.replace('_modifier', '')
                if req.stat_field in SHARPEN_INCREMENT:
                    delta[key] = SHARPEN_INCREMENT[req.stat_field]
                elif req.stat_field in crud.MAIN_STAT_FIELDS:
                    delta[key] = 1
                elif req.stat_field in crud.FLOAT_STAT_FIELDS:
                    delta[key] = 0.1
                if delta:
                    await apply_modifiers_in_attributes_service(character_id, delta)
        else:
            new_value = old_value

        # 13. Award XP (regardless of success/failure)
        base_xp = 10
        multiplier = crud.get_xp_multiplier(db, character_id)
        xp_earned = int(base_xp * multiplier)
        rank_up = False
        new_rank_name = None

        cp.experience += xp_earned
        new_total_xp = cp.experience

        # Check rank-up
        all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
        while True:
            next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
            if not next_ranks:
                break
            next_rank = next_ranks[0]
            if cp.experience >= next_rank.required_experience:
                cp.current_rank = next_rank.rank_number
                rank_up = True
                new_rank_name = next_rank.name
                crud.auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
            else:
                break

        db.commit()

        return {
            "success": success,
            "item_name": item_obj.name,
            "stat_field": req.stat_field,
            "stat_display_name": stat_display,
            "old_value": old_value,
            "new_value": new_value,
            "points_spent": item_row.enhancement_points_spent,
            "points_remaining": crud.MAX_ENHANCEMENT_POINTS - item_row.enhancement_points_spent,
            "point_cost": point_cost,
            "whetstone_consumed": True,
            "xp_earned": xp_earned,
            "new_total_xp": new_total_xp,
            "rank_up": rank_up,
            "new_rank_name": new_rank_name,
        }

    except HTTPException:
        db.rollback()
        raise
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка обращения к сервису атрибутов: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Sharpening error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при заточке предмета")


# ---------------------------------------------------------------------------
# Essence extraction endpoints — PUBLIC
# ---------------------------------------------------------------------------

@router.get("/crafting/{character_id}/extract-info")
def get_extract_info(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Get list of crystals in character's inventory available for essence extraction."""
    verify_character_ownership(db, character_id, current_user.id)

    # Find all inventory items that have essence_result_item_id set (crystals)
    crystal_rows = (
        db.query(models.CharacterInventory)
        .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.Items.essence_result_item_id.isnot(None),
        )
        .all()
    )

    crystals = []
    for inv_row in crystal_rows:
        crystal_item = inv_row.item
        # Load the essence item
        essence_item = db.query(models.Items).filter(
            models.Items.id == crystal_item.essence_result_item_id
        ).first()
        if not essence_item:
            continue

        crystals.append({
            "inventory_item_id": inv_row.id,
            "item_id": crystal_item.id,
            "name": crystal_item.name,
            "image": crystal_item.image,
            "quantity": inv_row.quantity,
            "essence_name": essence_item.name,
            "essence_image": essence_item.image,
            "success_chance": 75,
        })

    return {"crystals": crystals}


@router.post("/crafting/{character_id}/extract-essence")
def extract_essence(
    character_id: int,
    req: schemas.ExtractEssenceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Extract an essence from a crystal. Alchemist only. 75% success chance."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя извлекать эссенции во время боя")

    # 1. Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession.slug != "alchemist":
        raise HTTPException(status_code=400, detail="Только алхимик может извлекать эссенции")

    # 2. Find crystal in inventory
    crystal_inv = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.crystal_item_id,
        models.CharacterInventory.character_id == character_id,
    ).with_for_update().first()
    if not crystal_inv or crystal_inv.quantity < 1:
        raise HTTPException(status_code=404, detail="Кристалл не найден в инвентаре")

    # 3. Validate it's a crystal (has essence_result_item_id)
    crystal_item = db.query(models.Items).filter(
        models.Items.id == crystal_inv.item_id
    ).first()
    if not crystal_item or crystal_item.essence_result_item_id is None:
        raise HTTPException(status_code=400, detail="Этот предмет не является кристаллом для извлечения")

    # 4. Load essence item info
    essence_item = db.query(models.Items).filter(
        models.Items.id == crystal_item.essence_result_item_id
    ).first()
    if not essence_item:
        raise HTTPException(status_code=500, detail="Эссенция не найдена в базе данных")

    try:
        # 5. Consume 1 crystal
        crystal_inv.quantity -= 1
        if crystal_inv.quantity <= 0:
            db.delete(crystal_inv)
        db.flush()

        # 6. Roll 75% chance
        success = random.random() < 0.75

        essence_name = None
        if success:
            # Add 1 essence to inventory
            existing_essence = db.query(models.CharacterInventory).filter(
                models.CharacterInventory.character_id == character_id,
                models.CharacterInventory.item_id == essence_item.id,
            ).with_for_update().first()

            if existing_essence:
                existing_essence.quantity += 1
            else:
                new_inv = models.CharacterInventory(
                    character_id=character_id,
                    item_id=essence_item.id,
                    quantity=1,
                )
                db.add(new_inv)
            db.flush()
            essence_name = essence_item.name

        # 7. Award XP (always, regardless of success)
        base_xp = 10
        multiplier = crud.get_xp_multiplier(db, character_id)
        xp_earned = int(base_xp * multiplier)
        rank_up = False
        new_rank_name = None

        cp.experience += xp_earned
        new_total_xp = cp.experience

        # Check rank-up
        all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
        while True:
            next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
            if not next_ranks:
                break
            next_rank = next_ranks[0]
            if cp.experience >= next_rank.required_experience:
                cp.current_rank = next_rank.rank_number
                rank_up = True
                new_rank_name = next_rank.name
                crud.auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
            else:
                break

        db.commit()

        return {
            "success": success,
            "crystal_name": crystal_item.name,
            "essence_name": essence_name,
            "crystal_consumed": True,
            "xp_earned": xp_earned,
            "new_total_xp": new_total_xp,
            "rank_up": rank_up,
            "new_rank_name": new_rank_name,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Essence extraction error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при извлечении эссенции")


# ---------------------------------------------------------------------------
# Transmutation endpoints — PUBLIC
# ---------------------------------------------------------------------------

RARITY_CHAIN = {
    'common': 'rare',
    'rare': 'epic',
    'epic': 'legendary',
    'legendary': 'mythical',
}

TRANSMUTE_RESULT_NAMES = {
    'rare': 'Трансмутированный ресурс (редкий)',
    'epic': 'Трансмутированный ресурс (эпический)',
    'legendary': 'Трансмутированный ресурс (легендарный)',
    'mythical': 'Трансмутированный ресурс (мифический)',
}

TRANSMUTE_COST = 5
TRANSMUTE_XP = 15


@router.get("/crafting/{character_id}/transmute-info")
def get_transmute_info(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Get list of resource items available for transmutation."""
    verify_character_ownership(db, character_id, current_user.id)

    # Find all resource items with transmutable rarity
    resource_rows = (
        db.query(models.CharacterInventory)
        .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.Items.item_type == 'resource',
            models.Items.item_rarity.in_(list(RARITY_CHAIN.keys())),
        )
        .all()
    )

    items = []
    for inv_row in resource_rows:
        item = inv_row.item
        next_rarity = RARITY_CHAIN.get(item.item_rarity)
        if not next_rarity:
            continue

        items.append({
            "inventory_item_id": inv_row.id,
            "item_id": item.id,
            "name": item.name,
            "image": item.image,
            "quantity": inv_row.quantity,
            "item_rarity": item.item_rarity,
            "next_rarity": next_rarity,
            "can_transmute": inv_row.quantity >= TRANSMUTE_COST,
            "required_quantity": TRANSMUTE_COST,
        })

    return {"items": items}


@router.post("/crafting/{character_id}/transmute")
def transmute_item(
    character_id: int,
    req: schemas.TransmuteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Transmute 5 resource items into 1 of the next rarity. Alchemist only."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя трансмутировать предметы во время боя")

    # 1. Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession.slug != "alchemist":
        raise HTTPException(status_code=400, detail="Только алхимик может трансмутировать ресурсы")

    # 2. Find resource in inventory
    inv_row = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.inventory_item_id,
        models.CharacterInventory.character_id == character_id,
    ).with_for_update().first()
    if not inv_row:
        raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

    # 3. Validate it's a resource with transmutable rarity
    item = db.query(models.Items).filter(models.Items.id == inv_row.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    if item.item_type != 'resource':
        raise HTTPException(status_code=400, detail="Трансмутировать можно только ресурсы")

    next_rarity = RARITY_CHAIN.get(item.item_rarity)
    if not next_rarity:
        raise HTTPException(status_code=400, detail="Этот ресурс уже максимальной редкости для трансмутации")

    if inv_row.quantity < TRANSMUTE_COST:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно ресурсов. Нужно минимум {TRANSMUTE_COST}, у вас {inv_row.quantity}"
        )

    # 4. Find result item
    result_name = TRANSMUTE_RESULT_NAMES.get(next_rarity)
    if not result_name:
        raise HTTPException(status_code=500, detail="Ошибка: результат трансмутации не найден")

    result_item = db.query(models.Items).filter(
        models.Items.name == result_name
    ).first()
    if not result_item:
        raise HTTPException(status_code=500, detail="Ошибка: предмет результата трансмутации не найден в базе")

    try:
        # 5. Consume resources
        inv_row.quantity -= TRANSMUTE_COST
        if inv_row.quantity <= 0:
            db.delete(inv_row)
        db.flush()

        # 6. Add result item to inventory
        existing_result = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.item_id == result_item.id,
        ).with_for_update().first()

        if existing_result:
            existing_result.quantity += 1
        else:
            new_inv = models.CharacterInventory(
                character_id=character_id,
                item_id=result_item.id,
                quantity=1,
            )
            db.add(new_inv)
        db.flush()

        # 7. Award XP
        multiplier = crud.get_xp_multiplier(db, character_id)
        xp_earned = int(TRANSMUTE_XP * multiplier)
        rank_up = False
        new_rank_name = None

        cp.experience += xp_earned
        new_total_xp = cp.experience

        # Check rank-up
        all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
        while True:
            next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
            if not next_ranks:
                break
            next_rank = next_ranks[0]
            if cp.experience >= next_rank.required_experience:
                cp.current_rank = next_rank.rank_number
                rank_up = True
                new_rank_name = next_rank.name
                crud.auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
            else:
                break

        db.commit()

        return {
            "success": True,
            "consumed_item_name": item.name,
            "consumed_quantity": TRANSMUTE_COST,
            "result_item_name": result_item.name,
            "result_item_rarity": result_item.item_rarity,
            "xp_earned": xp_earned,
            "new_total_xp": new_total_xp,
            "rank_up": rank_up,
            "new_rank_name": new_rank_name,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Transmutation error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при трансмутации")


# ---------------------------------------------------------------------------
# Gem socket endpoints — PUBLIC (jeweler only)
# ---------------------------------------------------------------------------

@router.get("/crafting/{character_id}/socket-info/{item_row_id}")
def get_socket_info(
    character_id: int,
    item_row_id: int,
    source: str = Query("inventory", regex="^(inventory|equipment)$"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Получить информацию о слотах камней/рун предмета."""
    verify_character_ownership(db, character_id, current_user.id)

    # 1. Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession.slug not in ("jeweler", "enchanter"):
        raise HTTPException(status_code=400, detail="Только ювелир или зачарователь могут работать со слотами")

    # 2. Load item row
    if source == "equipment":
        row = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == item_row_id,
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.item_id.isnot(None),
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Экипированный предмет не найден")
        item_id = row.item_id
    else:
        row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == item_row_id,
            models.CharacterInventory.character_id == character_id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        item_id = row.item_id

    item_obj = db.query(models.Items).filter(models.Items.id == item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    # Validate item type matches profession
    if cp.profession.slug == "jeweler":
        if item_obj.item_type not in crud.JEWELRY_TYPES:
            raise HTTPException(status_code=400, detail="Ювелир может работать только с украшениями")
    elif cp.profession.slug == "enchanter":
        if item_obj.item_type not in crud.ARMOR_WEAPON_TYPES:
            raise HTTPException(status_code=400, detail="Зачарователь может работать только с оружием и бронёй")

    # 3. Parse socketed_gems
    socketed = crud.get_socketed_gems(row)
    socket_count = item_obj.socket_count or 0

    # Ensure socketed array matches socket_count
    while len(socketed) < socket_count:
        socketed.append(None)

    # Load gem items for filled slots
    gem_items_map = {}
    gem_ids = [gid for gid in socketed if gid is not None]
    if gem_ids:
        gem_items_list = db.query(models.Items).filter(models.Items.id.in_(gem_ids)).all()
        gem_items_map = {g.id: g for g in gem_items_list}

    slots = []
    for i in range(socket_count):
        gem_id = socketed[i] if i < len(socketed) else None
        gem_item = gem_items_map.get(gem_id) if gem_id else None
        slots.append({
            "slot_index": i,
            "gem_item_id": gem_id,
            "gem_name": gem_item.name if gem_item else None,
            "gem_image": gem_item.image if gem_item else None,
            "gem_modifiers": crud.get_gem_modifiers_dict(gem_item) if gem_item else {},
        })

    # 4. Find available gems/runes in inventory based on target item type
    if item_obj.item_type in crud.JEWELRY_TYPES:
        insertable_type = 'gem'
    else:
        insertable_type = 'rune'

    gem_inv_rows = (
        db.query(models.CharacterInventory)
        .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.Items.item_type == insertable_type,
        )
        .all()
    )

    available_gems = []
    for inv_row in gem_inv_rows:
        gem = inv_row.item
        available_gems.append({
            "inventory_item_id": inv_row.id,
            "item_id": gem.id,
            "name": gem.name,
            "image": gem.image,
            "quantity": inv_row.quantity,
            "modifiers": crud.get_gem_modifiers_dict(gem),
        })

    return {
        "item_name": item_obj.name,
        "item_type": item_obj.item_type,
        "socket_count": socket_count,
        "slots": slots,
        "available_gems": available_gems,
    }


@router.post("/crafting/{character_id}/insert-gem")
async def insert_gem(
    character_id: int,
    req: schemas.InsertGemRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Вставить камень/руну в слот предмета."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя вставлять камни/руны во время боя")

    # 1. Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")

    # 2. Load item row
    is_equipped = req.source == "equipment"
    if is_equipped:
        row = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == req.item_row_id,
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.item_id.isnot(None),
        ).with_for_update().first()
        if not row:
            raise HTTPException(status_code=404, detail="Экипированный предмет не найден")
        item_id = row.item_id
    else:
        row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.item_row_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if not row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        item_id = row.item_id

    item_obj = db.query(models.Items).filter(models.Items.id == item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    # 2.5. Check identification (only for inventory items — equipped items are always identified)
    if not is_equipped:
        if not row.is_identified:
            raise HTTPException(status_code=400, detail="Предмет не опознан")

    # Profession-specific validation
    if cp.profession.slug == "jeweler":
        if item_obj.item_type not in crud.JEWELRY_TYPES:
            raise HTTPException(status_code=400, detail="Ювелир может работать только с украшениями")
    elif cp.profession.slug == "enchanter":
        if item_obj.item_type not in crud.ARMOR_WEAPON_TYPES:
            raise HTTPException(status_code=400, detail="Зачарователь может работать только с оружием и бронёй")
    else:
        raise HTTPException(status_code=400, detail="Только ювелир или зачарователь могут вставлять предметы в слоты")

    # 3. Validate slot_index
    socket_count = item_obj.socket_count or 0
    if req.slot_index < 0 or req.slot_index >= socket_count:
        raise HTTPException(status_code=400, detail="Недопустимый индекс слота")

    socketed = crud.get_socketed_gems(row)
    while len(socketed) < socket_count:
        socketed.append(None)

    if socketed[req.slot_index] is not None:
        raise HTTPException(status_code=400, detail="Этот слот уже занят")

    # 4. Load gem/rune from inventory
    gem_inv = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.gem_inventory_id,
        models.CharacterInventory.character_id == character_id,
    ).with_for_update().first()
    if not gem_inv or gem_inv.quantity < 1:
        raise HTTPException(status_code=404, detail="Предмет для вставки не найден в инвентаре")

    gem_item = db.query(models.Items).filter(models.Items.id == gem_inv.item_id).first()

    # Validate insertable item type matches profession
    if cp.profession.slug == "jeweler":
        if not gem_item or gem_item.item_type != 'gem':
            raise HTTPException(status_code=400, detail="Ювелир может вставлять только камни")
    elif cp.profession.slug == "enchanter":
        if not gem_item or gem_item.item_type != 'rune':
            raise HTTPException(status_code=400, detail="Зачарователь может вставлять только руны")

    try:
        # 5. Consume gem
        gem_inv.quantity -= 1
        if gem_inv.quantity <= 0:
            db.delete(gem_inv)
        db.flush()

        # 6. Update socketed_gems
        socketed[req.slot_index] = gem_item.id
        crud.set_socketed_gems(row, socketed)
        db.flush()

        # 7. If equipped, apply gem modifiers
        if is_equipped:
            gem_mods = crud.build_modifiers_dict(gem_item, negative=False)
            # Only include the gem's own modifiers (not base item)
            gem_only_mods = {}
            for field in crud.ALL_MODIFIER_FIELDS:
                val = getattr(gem_item, field, 0) or 0
                if val:
                    key = field.replace('_modifier', '')
                    gem_only_mods[key] = val
            if gem_only_mods:
                await apply_modifiers_in_attributes_service(character_id, gem_only_mods)

        # 8. Award XP
        multiplier = crud.get_xp_multiplier(db, character_id)
        xp_earned = int(crud.GEM_XP_REWARD * multiplier)
        rank_up = False
        new_rank_name = None

        cp.experience += xp_earned
        new_total_xp = cp.experience

        all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
        while True:
            next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
            if not next_ranks:
                break
            next_rank = next_ranks[0]
            if cp.experience >= next_rank.required_experience:
                cp.current_rank = next_rank.rank_number
                rank_up = True
                new_rank_name = next_rank.name
                crud.auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
            else:
                break

        db.commit()

        return {
            "success": True,
            "item_name": item_obj.name,
            "gem_name": gem_item.name,
            "slot_index": req.slot_index,
            "xp_earned": xp_earned,
            "new_total_xp": new_total_xp,
            "rank_up": rank_up,
            "new_rank_name": new_rank_name,
        }

    except HTTPException:
        db.rollback()
        raise
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка обращения к сервису атрибутов: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Insert gem error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при вставке камня")


@router.post("/crafting/{character_id}/extract-gem")
async def extract_gem(
    character_id: int,
    req: schemas.ExtractGemRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Извлечь камень/руну из слота предмета."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя извлекать камни/руны во время боя")

    # 1. Check profession + get rank
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")

    # Profession-specific validation
    if cp.profession.slug == "jeweler":
        allowed_types = crud.JEWELRY_TYPES
    elif cp.profession.slug == "enchanter":
        allowed_types = crud.ARMOR_WEAPON_TYPES
    else:
        raise HTTPException(status_code=400, detail="Только ювелир или зачарователь могут извлекать предметы из слотов")

    # 2. Load item row
    is_equipped = req.source == "equipment"
    if is_equipped:
        row = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == req.item_row_id,
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.item_id.isnot(None),
        ).with_for_update().first()
        if not row:
            raise HTTPException(status_code=404, detail="Экипированный предмет не найден")
        item_id = row.item_id
    else:
        row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.item_row_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if not row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        item_id = row.item_id

    item_obj = db.query(models.Items).filter(models.Items.id == item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if item_obj.item_type not in allowed_types:
        if cp.profession.slug == "jeweler":
            raise HTTPException(status_code=400, detail="Ювелир может извлекать только из украшений")
        else:
            raise HTTPException(status_code=400, detail="Зачарователь может извлекать только из оружия и брони")

    # 3. Validate slot_index has a gem
    socket_count = item_obj.socket_count or 0
    socketed = crud.get_socketed_gems(row)
    while len(socketed) < socket_count:
        socketed.append(None)

    if req.slot_index < 0 or req.slot_index >= socket_count:
        raise HTTPException(status_code=400, detail="Недопустимый индекс слота")

    gem_item_id = socketed[req.slot_index]
    if gem_item_id is None:
        raise HTTPException(status_code=400, detail="В этом слоте нет камня")

    gem_item = db.query(models.Items).filter(models.Items.id == gem_item_id).first()
    if not gem_item:
        raise HTTPException(status_code=400, detail="Камень не найден в базе данных")

    # 4. Determine preservation chance
    preservation_pct = crud.GEM_PRESERVATION_CHANCES.get(cp.current_rank, 10)

    try:
        # 5. Roll for preservation
        gem_preserved = random.random() < (preservation_pct / 100.0)

        if gem_preserved:
            # Return gem to inventory
            crud.return_item_to_inventory(db, character_id, gem_item)
            db.flush()

        # 6. Clear slot
        socketed[req.slot_index] = None
        crud.set_socketed_gems(row, socketed)
        db.flush()

        # 7. If equipped, remove gem modifiers
        if is_equipped:
            gem_neg_mods = {}
            for field in crud.ALL_MODIFIER_FIELDS:
                val = getattr(gem_item, field, 0) or 0
                if val:
                    key = field.replace('_modifier', '')
                    gem_neg_mods[key] = -val
            if gem_neg_mods:
                await apply_modifiers_in_attributes_service(character_id, gem_neg_mods)

        # 8. Award XP
        multiplier = crud.get_xp_multiplier(db, character_id)
        xp_earned = int(crud.GEM_XP_REWARD * multiplier)
        rank_up = False
        new_rank_name = None

        cp.experience += xp_earned
        new_total_xp = cp.experience

        all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
        while True:
            next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
            if not next_ranks:
                break
            next_rank = next_ranks[0]
            if cp.experience >= next_rank.required_experience:
                cp.current_rank = next_rank.rank_number
                rank_up = True
                new_rank_name = next_rank.name
                crud.auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
            else:
                break

        db.commit()

        return {
            "success": True,
            "item_name": item_obj.name,
            "gem_name": gem_item.name,
            "gem_preserved": gem_preserved,
            "preservation_chance": preservation_pct,
            "slot_index": req.slot_index,
            "xp_earned": xp_earned,
            "new_total_xp": new_total_xp,
            "rank_up": rank_up,
            "new_rank_name": new_rank_name,
        }

    except HTTPException:
        db.rollback()
        raise
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка обращения к сервису атрибутов: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Extract gem error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при извлечении камня")


# ---------------------------------------------------------------------------
# Smelting endpoints — PUBLIC (jeweler only)
# ---------------------------------------------------------------------------

@router.get("/crafting/{character_id}/smelt-info/{item_row_id}")
def get_smelt_info(
    character_id: int,
    item_row_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Получить информацию о переплавке украшения."""
    verify_character_ownership(db, character_id, current_user.id)

    # 1. Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession.slug != "jeweler":
        raise HTTPException(status_code=400, detail="Только ювелир может переплавлять украшения")

    # 2. Load item from inventory (NOT equipment)
    inv_row = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == item_row_id,
        models.CharacterInventory.character_id == character_id,
    ).first()
    if not inv_row:
        raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

    item_obj = db.query(models.Items).filter(models.Items.id == inv_row.item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if item_obj.item_type not in crud.JEWELRY_TYPES:
        raise HTTPException(status_code=400, detail="Переплавлять можно только украшения (кольца, ожерелья, браслеты)")

    # 3. Check socketed gems
    socketed = crud.get_socketed_gems(inv_row)
    gem_count = sum(1 for g in socketed if g is not None)
    has_gems = gem_count > 0

    # 4. Find recipe
    recipe = crud.find_recipe_for_item(db, item_obj.id)
    has_recipe = recipe is not None

    if has_recipe:
        ingredients = crud.calculate_smelt_returns(recipe)
    else:
        junk_item = crud.get_junk_item(db)
        if junk_item:
            ingredients = [{
                "item_id": junk_item.id,
                "name": junk_item.name,
                "image": junk_item.image,
                "quantity": 1,
            }]
        else:
            ingredients = [{"item_id": 0, "name": "Ювелирный лом", "image": None, "quantity": 1}]

    return {
        "item_name": item_obj.name,
        "item_type": item_obj.item_type,
        "has_gems": has_gems,
        "gem_count": gem_count,
        "has_recipe": has_recipe,
        "ingredients": ingredients,
    }


@router.post("/crafting/{character_id}/smelt")
def smelt_item(
    character_id: int,
    req: schemas.SmeltRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Переплавить украшение в материалы."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя переплавлять предметы во время боя")

    # 1. Check profession
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")
    if cp.profession.slug != "jeweler":
        raise HTTPException(status_code=400, detail="Только ювелир может переплавлять украшения")

    # 2. Load item from inventory (NOT equipment)
    inv_row = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.inventory_item_id,
        models.CharacterInventory.character_id == character_id,
    ).with_for_update().first()
    if not inv_row:
        raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

    item_obj = db.query(models.Items).filter(models.Items.id == inv_row.item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if item_obj.item_type not in crud.JEWELRY_TYPES:
        raise HTTPException(status_code=400, detail="Переплавлять можно только украшения")

    try:
        # 3. Count socketed gems (will be destroyed)
        socketed = crud.get_socketed_gems(inv_row)
        gems_destroyed = sum(1 for g in socketed if g is not None)

        # 4. Find recipe and calculate returns
        recipe = crud.find_recipe_for_item(db, item_obj.id)
        materials_returned = []

        if recipe:
            returns = crud.calculate_smelt_returns(recipe)
            for ret in returns:
                # Add materials to inventory
                crud._add_items_to_inventory(db, character_id, ret["item_id"], ret["quantity"])
                materials_returned.append({"name": ret["name"], "quantity": ret["quantity"]})
        else:
            # Return junk item
            junk_item = crud.get_junk_item(db)
            if not junk_item:
                raise HTTPException(status_code=500, detail="Ювелирный лом не найден в базе данных")
            crud._add_items_to_inventory(db, character_id, junk_item.id, 1)
            materials_returned.append({"name": junk_item.name, "quantity": 1})

        # 5. Delete the jewelry item from inventory
        inv_row.quantity -= 1
        if inv_row.quantity <= 0:
            db.delete(inv_row)
        db.flush()

        # 6. Award XP
        multiplier = crud.get_xp_multiplier(db, character_id)
        xp_earned = int(crud.GEM_XP_REWARD * multiplier)
        rank_up = False
        new_rank_name = None

        cp.experience += xp_earned
        new_total_xp = cp.experience

        all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
        while True:
            next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
            if not next_ranks:
                break
            next_rank = next_ranks[0]
            if cp.experience >= next_rank.required_experience:
                cp.current_rank = next_rank.rank_number
                rank_up = True
                new_rank_name = next_rank.name
                crud.auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
            else:
                break

        db.commit()

        return {
            "success": True,
            "item_name": item_obj.name,
            "gems_destroyed": gems_destroyed,
            "materials_returned": materials_returned,
            "xp_earned": xp_earned,
            "new_total_xp": new_total_xp,
            "rank_up": rank_up,
            "new_rank_name": new_rank_name,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Smelting error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при переплавке украшения")


# ---------------------------------------------------------------------------
# Identification endpoint
# ---------------------------------------------------------------------------

@router.post("/{character_id}/identify", response_model=schemas.IdentifyResult)
async def identify_item(
    character_id: int,
    req: schemas.IdentifyRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Опознать предмет в инвентаре, расходуя свиток идентификации."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя опознавать предметы во время боя")

    try:
        # 1. Find inventory row
        inv_row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.inventory_item_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if not inv_row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

        # 2. Check already identified
        if inv_row.is_identified:
            raise HTTPException(status_code=400, detail="Предмет уже опознан")

        # 3. Load item definition
        item_obj = db.query(models.Items).filter(models.Items.id == inv_row.item_id).first()
        if not item_obj:
            raise HTTPException(status_code=404, detail="Предмет не найден")

        # 4. Determine required identify level from rarity
        required_level = crud.RARITY_IDENTIFY_LEVEL.get(item_obj.item_rarity)
        if required_level is None:
            raise HTTPException(status_code=400, detail="Этот предмет не требует опознания")

        # 5. Find matching scroll
        scroll_inv = crud.find_identification_scroll(db, character_id, required_level)
        if not scroll_inv:
            raise HTTPException(
                status_code=400,
                detail="Нет подходящего свитка идентификации для этой редкости"
            )
        scroll_item = scroll_inv.item

        # 6. Consume 1 scroll
        if scroll_inv.quantity > 1:
            scroll_inv.quantity -= 1
        else:
            db.delete(scroll_inv)

        # 7. Mark item as identified
        inv_row.is_identified = True

        db.commit()

        return {
            "success": True,
            "item_name": item_obj.name,
            "scroll_used": scroll_item.name,
            "item_rarity": item_obj.item_rarity,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Identification error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при опознании предмета")


# ---------------------------------------------------------------------------
# Buff endpoints
# ---------------------------------------------------------------------------

@router.post("/{character_id}/use-buff-item", response_model=schemas.UseBuffItemResult)
def use_buff_item(
    character_id: int,
    req: schemas.UseBuffItemRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Использовать баффовый предмет (книгу опыта и т.д.)."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя использовать предметы во время боя")

    try:
        # 1. Find inventory row
        inv_row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.inventory_item_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if not inv_row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

        # 2. Load item definition
        item_obj = db.query(models.Items).filter(models.Items.id == inv_row.item_id).first()
        if not item_obj:
            raise HTTPException(status_code=404, detail="Предмет не найден")

        # 3. Validate it's a buff item
        if not item_obj.buff_type or item_obj.buff_value is None or item_obj.buff_duration_minutes is None:
            raise HTTPException(status_code=400, detail="Этот предмет не является баффовым")

        # 4. Consume 1 item
        inv_row.quantity -= 1
        if inv_row.quantity <= 0:
            db.delete(inv_row)
        db.flush()

        # 5. Apply buff (upsert)
        crud.apply_buff(
            db,
            character_id=character_id,
            buff_type=item_obj.buff_type,
            value=item_obj.buff_value,
            duration_minutes=item_obj.buff_duration_minutes,
            source_name=item_obj.name,
        )

        db.commit()

        bonus_pct = int(item_obj.buff_value * 100)
        return {
            "success": True,
            "buff_type": item_obj.buff_type,
            "value": item_obj.buff_value,
            "duration_minutes": item_obj.buff_duration_minutes,
            "source_item_name": item_obj.name,
            "message": f"Бафф активирован: +{bonus_pct}% XP на {item_obj.buff_duration_minutes} мин",
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Use buff item error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при использовании баффового предмета")


@router.get("/{character_id}/active-buffs", response_model=schemas.ActiveBuffsResponse)
def get_active_buffs(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Получить список активных баффов персонажа."""
    verify_character_ownership(db, character_id, current_user.id)

    now = datetime.utcnow()
    buffs = crud.get_active_buffs(db, character_id)

    result = []
    for b in buffs:
        remaining = max(0, int((b.expires_at - now).total_seconds()))
        result.append({
            "id": b.id,
            "character_id": b.character_id,
            "buff_type": b.buff_type,
            "value": b.value,
            "expires_at": b.expires_at.isoformat(),
            "source_item_name": b.source_item_name,
            "remaining_seconds": remaining,
        })

    return {"buffs": result}


# -----------------------------------------------------------------------------
# Durability: Repair item
# -----------------------------------------------------------------------------

@router.post("/{character_id}/repair-item", response_model=schemas.RepairItemResponse)
async def repair_item(
    character_id: int,
    req: schemas.RepairItemRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Починить предмет с помощью ремонт-комплекта.
    """
    verify_character_ownership(db, character_id, current_user.id)

    # 1) Find repair kit in inventory
    kit_inv = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == req.repair_kit_item_id,
        models.CharacterInventory.quantity > 0,
    ).with_for_update().first()

    if not kit_inv:
        raise HTTPException(status_code=404, detail="Ремонт-комплект не найден в инвентаре")

    kit_item = db.query(models.Items).filter(models.Items.id == req.repair_kit_item_id).first()
    if not kit_item or kit_item.repair_power is None:
        raise HTTPException(status_code=400, detail="Этот предмет не является ремонт-комплектом")

    # 2) Find target item by source
    if req.source == "inventory":
        row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.inventory_item_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if not row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        item_template = db.query(models.Items).filter(models.Items.id == row.item_id).first()
    elif req.source == "equipment":
        row = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == req.inventory_item_id,
            models.EquipmentSlot.character_id == character_id,
        ).with_for_update().first()
        if not row or not row.item_id:
            raise HTTPException(status_code=404, detail="Предмет не найден в экипировке")
        item_template = db.query(models.Items).filter(models.Items.id == row.item_id).first()
    else:
        raise HTTPException(status_code=400, detail="Параметр source должен быть 'inventory' или 'equipment'")

    if not item_template:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    # 3) Validate durability
    if item_template.max_durability <= 0:
        raise HTTPException(status_code=400, detail="Предмет не имеет прочности")

    old_durability = row.current_durability if row.current_durability is not None else item_template.max_durability

    if old_durability >= item_template.max_durability:
        raise HTTPException(status_code=400, detail="Предмет уже имеет полную прочность")

    # 4) Calculate restore
    restore_amount = math.ceil(item_template.max_durability * kit_item.repair_power / 100)
    new_durability = min(old_durability + restore_amount, item_template.max_durability)

    was_broken = old_durability <= 0

    # 5) Update durability
    row.current_durability = new_durability

    # 6) Consume 1 repair kit
    kit_inv.quantity -= 1
    if kit_inv.quantity <= 0:
        db.delete(kit_inv)
    db.flush()

    # 7) If item was broken and now repaired and is equipped — re-apply modifiers
    if was_broken and new_durability > 0 and req.source == "equipment":
        try:
            enh_bonuses = crud.get_enhancement_bonuses(row)
            socketed_gems = crud.get_socketed_gems(row)
            gem_items = crud.load_gem_items(db, socketed_gems) if socketed_gems else []
            plus_mods = crud.build_modifiers_dict(
                item_template, negative=False,
                enhancement_bonuses=enh_bonuses, gem_items=gem_items,
                current_durability=new_durability, max_durability=item_template.max_durability,
            )
            if plus_mods:
                await apply_modifiers_in_attributes_service(character_id, plus_mods)
        except Exception as e:
            logger.error(f"Ошибка применения модификаторов после ремонта: {e}")

    db.commit()

    return {
        "success": True,
        "new_durability": new_durability,
        "max_durability": item_template.max_durability,
        "repair_kit_consumed": True,
    }


# -----------------------------------------------------------------------------
# Durability: Item detail card
# -----------------------------------------------------------------------------

@router.get("/{character_id}/item-detail/{inventory_item_id}", response_model=schemas.ItemDetailResponse)
def get_item_detail(
    character_id: int,
    inventory_item_id: int,
    source: str = Query("inventory", regex="^(inventory|equipment)$"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Полная карточка предмета для модального окна.
    """
    verify_character_ownership(db, character_id, current_user.id)

    if source == "inventory":
        row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == inventory_item_id,
            models.CharacterInventory.character_id == character_id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        item_template = db.query(models.Items).filter(models.Items.id == row.item_id).first()
        is_identified = row.is_identified
    elif source == "equipment":
        row = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == inventory_item_id,
            models.EquipmentSlot.character_id == character_id,
        ).first()
        if not row or not row.item_id:
            raise HTTPException(status_code=404, detail="Предмет не найден в экипировке")
        item_template = db.query(models.Items).filter(models.Items.id == row.item_id).first()
        is_identified = True  # equipped items are always identified
    else:
        raise HTTPException(status_code=400, detail="Параметр source должен быть 'inventory' или 'equipment'")

    if not item_template:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    enh_bonuses = crud.get_enhancement_bonuses(row)
    socketed_gems_raw = crud.get_socketed_gems(row)

    # Build rich socketed items info
    socketed_items = []
    socket_count = item_template.socket_count or 0
    if socket_count > 0:
        gem_items_map = {}
        valid_ids = [gid for gid in socketed_gems_raw if gid is not None]
        if valid_ids:
            for g in db.query(models.Items).filter(models.Items.id.in_(set(valid_ids))).all():
                gem_items_map[g.id] = g
        for i in range(socket_count):
            gid = socketed_gems_raw[i] if i < len(socketed_gems_raw) else None
            if gid is not None and gid in gem_items_map:
                gem = gem_items_map[gid]
                mods = {}
                for field in crud.ALL_MODIFIER_FIELDS:
                    val = getattr(gem, field, 0) or 0
                    if val:
                        key = field.replace('_modifier', '')
                        mods[key] = val
                socketed_items.append({
                    "slot_index": i,
                    "item_id": gem.id,
                    "name": gem.name,
                    "image": gem.image,
                    "item_type": gem.item_type,
                    "modifiers": mods,
                })
            else:
                socketed_items.append({
                    "slot_index": i,
                    "item_id": None,
                    "name": None,
                    "image": None,
                    "item_type": None,
                    "modifiers": {},
                })

    return {
        "item": item_template,
        "current_durability": row.current_durability,
        "max_durability": item_template.max_durability,
        "enhancement_points_spent": row.enhancement_points_spent,
        "enhancement_bonuses": enh_bonuses if enh_bonuses else None,
        "socketed_gems": socketed_gems_raw if socketed_gems_raw else None,
        "socketed_items": socketed_items,
        "is_identified": is_identified,
        "source": source,
    }


# -----------------------------------------------------------------------------
# Internal: Update durability after battle
# -----------------------------------------------------------------------------

@router.post("/internal/update-durability", response_model=schemas.UpdateDurabilityResponse)
async def update_durability_internal(
    req: schemas.UpdateDurabilityRequest,
    db: Session = Depends(get_db),
):
    """
    Обновить прочность экипировки после боя (internal, service-to-service).
    Если прочность падает до 0 — снять модификаторы через apply_modifiers.
    """
    updated = 0
    mods_removed_for = []

    for entry in req.entries:
        slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == req.character_id,
            models.EquipmentSlot.slot_type == entry.slot_type,
        ).with_for_update().first()

        if not slot or not slot.item_id:
            continue

        old_durability = slot.current_durability
        item_template = db.query(models.Items).filter(models.Items.id == slot.item_id).first()
        if not item_template or item_template.max_durability <= 0:
            continue

        # Determine if modifiers were active before
        was_active = old_durability is None or old_durability > 0

        slot.current_durability = max(0, entry.new_durability)
        updated += 1

        # If item just broke (was active, now 0) — remove modifiers
        if was_active and slot.current_durability <= 0:
            try:
                enh_bonuses = crud.get_enhancement_bonuses(slot)
                socketed_gems = crud.get_socketed_gems(slot)
                gem_items = crud.load_gem_items(db, socketed_gems) if socketed_gems else []
                minus_mods = crud.build_modifiers_dict(
                    item_template, negative=True,
                    enhancement_bonuses=enh_bonuses, gem_items=gem_items,
                    # Pass durability that makes it NOT broken for the negative calc
                    current_durability=1, max_durability=item_template.max_durability,
                )
                if minus_mods:
                    await apply_modifiers_in_attributes_service(req.character_id, minus_mods)
                mods_removed_for.append(entry.slot_type)
            except Exception as e:
                logger.error(f"Ошибка снятия модификаторов при поломке {entry.slot_type} для персонажа {req.character_id}: {e}")

    db.commit()

    return {
        "status": "ok",
        "updated": updated,
        "mods_removed_for": mods_removed_for,
    }


# ---------------------------------------------------------------------------
# Auction endpoints
# ---------------------------------------------------------------------------

@router.get("/auction/listings", response_model=schemas.AuctionListingsPageResponse)
def auction_browse_listings(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    item_type: Optional[str] = Query(None, description="Фильтр по типу предмета"),
    rarity: Optional[str] = Query(None, description="Фильтр по редкости"),
    sort: str = Query("time_asc", description="Сортировка: price_asc, price_desc, time_asc, time_desc, name_asc, name_desc"),
    search: Optional[str] = Query(None, description="Поиск по названию предмета"),
    db: Session = Depends(get_db),
):
    """Просмотр лотов аукциона с фильтрацией, сортировкой и пагинацией."""
    return crud.get_listings_page(
        db,
        page=page,
        per_page=per_page,
        item_type=item_type,
        rarity=rarity,
        sort=sort,
        search=search,
    )


@router.get("/auction/my-listings", response_model=schemas.AuctionMyListingsResponse)
def auction_my_listings(
    character_id: int = Query(..., description="ID персонажа"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Мои лоты на аукционе (активные и завершённые)."""
    return crud.get_my_listings(db, character_id=character_id, user_id=current_user.id)


@router.get("/auction/storage", response_model=schemas.AuctionStorageResponse)
def auction_storage(
    character_id: int = Query(..., description="ID персонажа"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Склад аукциона — купленные и непроданные предметы."""
    return crud.get_auction_storage(db, character_id=character_id, user_id=current_user.id)


@router.get("/auction/check-auctioneer")
def auction_check_auctioneer(
    character_id: int = Query(..., description="ID персонажа"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Проверка наличия НПС-Аукциониста в локации персонажа."""
    return crud.check_auctioneer_endpoint(db, character_id=character_id, user_id=current_user.id)


@router.get("/auction/listings/{listing_id}", response_model=schemas.AuctionListingResponse)
def auction_get_listing(
    listing_id: int,
    db: Session = Depends(get_db),
):
    """Получить один лот по ID."""
    result = crud.get_single_listing(db, listing_id=listing_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Лот не найден")
    return result


@router.post("/auction/listings", response_model=schemas.AuctionCreateListingResponse, status_code=201)
def auction_create_listing(
    req: schemas.AuctionCreateListingRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Выставить предмет на аукцион."""
    return crud.create_auction_listing(db, data=req, user_id=current_user.id)


@router.post("/auction/listings/{listing_id}/bid", response_model=schemas.AuctionBidResponse)
def auction_place_bid(
    listing_id: int,
    req: schemas.AuctionBidRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Сделать ставку на лот."""
    return crud.place_bid(db, listing_id=listing_id, data=req, user_id=current_user.id)


@router.post("/auction/listings/{listing_id}/buyout", response_model=schemas.AuctionBuyoutResponse)
def auction_buyout(
    listing_id: int,
    req: schemas.AuctionBuyoutRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Мгновенный выкуп лота."""
    return crud.execute_buyout(db, listing_id=listing_id, data=req, user_id=current_user.id)


@router.post("/auction/listings/{listing_id}/cancel", response_model=schemas.AuctionCancelResponse)
def auction_cancel_listing(
    listing_id: int,
    req: schemas.AuctionCancelRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Отменить лот на аукционе."""
    return crud.cancel_listing(db, listing_id=listing_id, data=req, user_id=current_user.id)


@router.post("/auction/storage/deposit", status_code=201)
def auction_deposit_to_storage(
    req: schemas.AuctionDepositRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Сдать предмет из инвентаря на склад аукциона (требуется НПС-Аукционист)."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        result = crud.deposit_to_auction_storage(db, data=req, user_id=current_user.id)
        logger.info(f"Auction deposit success: {result}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Auction deposit error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")


@router.post("/auction/storage/claim", response_model=schemas.AuctionClaimResponse)
def auction_claim_storage(
    req: schemas.AuctionClaimRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Забрать предметы/золото со склада аукциона."""
    return crud.claim_from_storage(db, data=req, user_id=current_user.id)


app.include_router(router)
