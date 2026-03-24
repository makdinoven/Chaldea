import os
import asyncio
import threading
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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Возвращает список предметов с поиском и пагинацией."""
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
        inv_slot = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.item_id == req.item_id
        ).order_by(models.CharacterInventory.quantity.desc()).with_for_update().first()

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


app.include_router(router)
