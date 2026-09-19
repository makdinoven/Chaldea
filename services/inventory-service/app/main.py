import os
import json
import asyncio
import math
import threading
import random
from datetime import datetime
import httpx
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, APIRouter, Query, BackgroundTasks, Response
from sqlalchemy.orm import Session, selectinload
import models
import schemas
import crud
import equipment_rules
from database import SessionLocal, engine
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from rabbitmq_consumer import start_consumer
from sqlalchemy import text
from auth_http import get_current_user_via_http, get_admin_user, require_permission, verify_internal_token
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inventory-service")


def _internal_token_headers() -> dict:
    """Headers for outgoing internal service-to-service calls (FEAT-162 §3.4).

    Read from env at call time (not import time) so tests can set it up.
    """
    return {"X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", "")}

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


def check_not_gathering(db: Session, character_id: int, message: str = "Действие заблокировано во время добычи"):
    """Raise 400 if character has an active gathering session (shared DB query)."""
    if crud.is_character_gathering(db, character_id):
        raise HTTPException(status_code=400, detail=message)


@router.post("/", response_model=schemas.InventoryResponse)
def create_inventory(
    inventory_request: schemas.InventoryRequest,
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """
    Создание инвентаря и слотов экипировки для персонажа.

    Только для межсервисных вызовов (FEAT-167 #18): требуется заголовок
    `X-Internal-Token`. Единственный вызывающий — character-service при
    создании персонажа.
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
    resource_subcategory: Optional[schemas.ResourceSubcategory] = Query(None, description="Подкатегория ресурса"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Возвращает список предметов с поиском и пагинацией."""
    # FEAT-168: effects/damage_entries/xp_buffs едут в ответе — грузим их пачкой,
    # иначе на странице в 500 предметов получится 1500 лишних запросов.
    # Любая новая связь в schemas.Item обязана попасть и сюда.
    query = db.query(models.Items).options(
        selectinload(models.Items.effects),
        selectinload(models.Items.damage_entries),
        selectinload(models.Items.xp_buffs),
    )
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
    if resource_subcategory is not None:
        query = query.filter(models.Items.resource_subcategory == resource_subcategory.value)
    items = (
        query
        .order_by(models.Items.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items

def _ensure_linked_recipe_exists(db: Session, item_in: schemas.ItemCreate):
    if item_in.blueprint_recipe_id is None:
        return
    if not db.query(models.Recipe.id).filter(models.Recipe.id == item_in.blueprint_recipe_id).first():
        raise HTTPException(status_code=400, detail="Рецепт для предмета-рецепта не найден")


@router.post("/items", response_model=schemas.Item, status_code=201)
def create_item(item_in: schemas.ItemCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("items:create"))):
    """Создаёт новый предмет."""
    if db.query(models.Items).filter(models.Items.name == item_in.name).first():
        raise HTTPException(status_code=400, detail="Предмет с таким названием уже существует")
    _ensure_linked_recipe_exists(db, item_in)
    # FEAT-168: `effects` / `damage_entries` are child tables, not item columns.
    payload = item_in.dict(exclude_unset=True)
    for field in crud.ITEM_NESTED_EFFECT_FIELDS:
        payload.pop(field, None)
    db_item = models.Items(**payload)
    db.add(db_item)
    db.flush()
    crud.replace_item_effects(db, db_item, item_in.effects)
    crud.replace_item_damage_entries(db, db_item, item_in.damage_entries)
    # Only when the client actually submitted the list: `replace_item_xp_buffs`
    # clears the legacy buff triple, and a client that posts only the old
    # `buff_type/buff_value/buff_duration_minutes` must keep working.
    if "xp_buffs" in item_in.__fields_set__:
        crud.replace_item_xp_buffs(db, db_item, item_in.xp_buffs)
    db.commit()
    db.refresh(db_item)
    return db_item

MAX_BULK_IDS = 100


def _parse_bulk_ids(raw: str) -> List[int]:
    """
    Разбирает параметр ?ids=1,2,3 в дедуплицированный список int.
    Бросает HTTPException(400) при некорректном вводе или превышении лимита.
    """
    parts = [p.strip() for p in (raw or "").split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise HTTPException(status_code=400, detail="Параметр ids не должен быть пустым")

    # Лимит считается по сырым токенам (до дедупликации), иначе строка вида
    # ?ids=1,1,1,... любой длины проходила бы проверку.
    if len(parts) > MAX_BULK_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Слишком много идентификаторов: максимум {MAX_BULK_IDS}",
        )

    seen = set()
    ids: List[int] = []
    for part in parts:
        try:
            value = int(part)
        except ValueError:
            raise HTTPException(status_code=400, detail="Параметр ids должен содержать только целые числа через запятую")
        if value <= 0:
            raise HTTPException(status_code=400, detail="Идентификаторы должны быть положительными числами")
        if value not in seen:
            seen.add(value)
            ids.append(value)

    return ids


# Registered BEFORE "/items/{item_id}" so "bulk" is not parsed as an item id.
@router.get("/items/bulk", response_model=List[schemas.ItemBulkResponse])
def get_items_bulk(
    ids: str = Query(..., description="Идентификаторы предметов через запятую, максимум 100"),
    db: Session = Depends(get_db),
):
    """
    Массовый резолв предметов по списку id (публичный эндпоинт).
    Неизвестные id молча опускаются. Запрос параметризован (IN), SQL не строится строками.
    """
    item_ids = _parse_bulk_ids(ids)
    rows = (
        db.query(models.Items)
        .filter(models.Items.id.in_(item_ids))
        .order_by(models.Items.id.asc())
        .all()
    )
    return [
        schemas.ItemBulkResponse(
            id=row.id,
            name=row.name,
            description=row.description,
            image_url=row.image,
            rarity=row.item_rarity,
            type=row.item_type,
        )
        for row in rows
    ]


@router.get("/items/{item_id}", response_model=schemas.Item)
def get_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.Items).get(item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    return db_item

@router.put("/items/{item_id}", response_model=schemas.Item)
def update_item(item_id: int, item_in: schemas.ItemCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user = Depends(require_permission("items:update"))):
    """Обновляет все переданные поля предмета."""
    db_item = db.query(models.Items).get(item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    if item_in.name and item_in.name != db_item.name:
        if db.query(models.Items).filter(models.Items.name == item_in.name).first():
            raise HTTPException(status_code=400, detail="Предмет с таким названием уже существует")
    _ensure_linked_recipe_exists(db, item_in)
    wearability_before = (db_item.item_type, db_item.weapon_subclass, db_item.armor_subclass)
    for field, value in item_in.dict(exclude_unset=True).items():
        if field in crud.ITEM_NESTED_EFFECT_FIELDS:
            continue  # FEAT-168: child tables, written below
        setattr(db_item, field, value)
    db.flush()
    # FEAT-168: replace-all, but only for the lists the client actually sent —
    # a payload that omits them leaves the existing rows untouched.
    if "effects" in item_in.__fields_set__:
        crud.replace_item_effects(db, db_item, item_in.effects)
    if "damage_entries" in item_in.__fields_set__:
        crud.replace_item_damage_entries(db, db_item, item_in.damage_entries)
    if "xp_buffs" in item_in.__fields_set__:
        crud.replace_item_xp_buffs(db, db_item, item_in.xp_buffs)
    # FEAT-165: refining config must keep matching the item's subcategory
    crud.delete_stale_conversions(db, db_item)
    db.commit()
    db.refresh(db_item)

    if (db_item.item_type, db_item.weapon_subclass, db_item.armor_subclass) != wearability_before:
        wearer_ids = [
            row[0] for row in db.query(models.EquipmentSlot.character_id)
            .filter(models.EquipmentSlot.item_id == db_item.id).distinct().all()
        ]
        if wearer_ids:
            background_tasks.add_task(_revalidate_characters, wearer_ids)
    return db_item


# --- Refining config (FEAT-165) ---

@router.get("/admin/items/{item_id}/conversions", response_model=schemas.ItemConversionsResponse)
def admin_get_item_conversions(
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("items:read")),
):
    """Настройки переработки сырья — админ."""
    if not db.query(models.Items.id).filter(models.Items.id == item_id).first():
        raise HTTPException(status_code=404, detail="Предмет не найден")
    return crud.build_item_conversions_response(db, item_id)


@router.put("/admin/items/{item_id}/conversions", response_model=schemas.ItemConversionsResponse)
def admin_put_item_conversions(
    item_id: int,
    payload: schemas.ItemConversionsPayload,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("items:update")),
):
    """Заменить все настройки переработки сырья (пустой список — удалить) — админ."""
    source_item = db.query(models.Items).filter(models.Items.id == item_id).first()
    if not source_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    try:
        crud.replace_item_conversions(db, source_item, payload.conversions)
    except crud.RefineNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        db.rollback()
        logger.exception("Saving refining config for item %s failed", item_id)
        raise HTTPException(status_code=500, detail="Не удалось сохранить настройки переработки")
    return crud.build_item_conversions_response(db, item_id)


# --- Character inventory ---

@router.get("/{character_id}/items", response_model=List[schemas.CharacterInventory])
def get_character_inventory(
    character_id: int,
    item_type: Optional[str] = Query(None, description="Фильтр по типу предмета (например 'gathering_tool')"),
    category: Optional[str] = Query(None, description="Фильтр по категории инструмента: pickaxe|sickle|axe (только при item_type=gathering_tool)"),
    db: Session = Depends(get_db),
):
    """
    Получить все предметы в инвентаре персонажа.

    Дополнительные фильтры:
    - item_type — например 'gathering_tool' оставит только инструменты сбора.
    - category — фильтрация по категории инструмента (только если item_type='gathering_tool').
    """
    # Validate category early — only allowed when item_type == 'gathering_tool'.
    if category is not None:
        allowed_categories = {"pickaxe", "sickle", "axe"}
        if category not in allowed_categories:
            raise HTTPException(
                status_code=422,
                detail="Недопустимая категория инструмента. Допустимы: pickaxe, sickle, axe",
            )
        if item_type != "gathering_tool":
            raise HTTPException(
                status_code=422,
                detail="Параметр 'category' доступен только при item_type='gathering_tool'",
            )

    query = (
        db.query(models.CharacterInventory)
        .filter(models.CharacterInventory.character_id == character_id)
    )

    if item_type is not None or category is not None:
        # Join with items to filter by item-template fields.
        query = query.join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        if item_type is not None:
            query = query.filter(models.Items.item_type == item_type)
        if category is not None:
            query = query.filter(models.Items.tool_category == category)

    return query.all()


def _add_item_to_inventory_core(character_id: int, item_data: schemas.InventoryItem, db: Session):
    """Положить предмет в инвентарь персонажа с учётом максимального стека.

    Общее тело для админского (`POST /inventory/{cid}/items`) и внутреннего
    (`POST /inventory/internal/characters/{cid}/items`) роутов — FEAT-167 §3.2.
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

    # Quest auto-progress: collect (non-fatal)
    try:
        url = f"{settings.LOCATIONS_SERVICE_URL}/locations/quests/internal/auto-progress"
        httpx.post(url, json={
            "character_id": character_id,
            "event_type": "collect",
            "increment": item_data.quantity,
            "target_id": item_data.item_id,
        }, timeout=5.0)
    except Exception as e:
        logger.warning(f"Quest auto-progress (collect) error for char {character_id}: {e}")

    return inventory_items


@router.post("/internal/characters/{character_id}/items", response_model=List[schemas.CharacterInventory])
def add_item_to_inventory_internal(
    character_id: int,
    item_data: schemas.InventoryItem,
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """Выдача предмета персонажу для межсервисных вызовов (FEAT-167 §3.2.2).

    Только service-to-service: требует заголовок `X-Internal-Token`.
    """
    return _add_item_to_inventory_core(character_id, item_data, db)


@router.post("/{character_id}/items", response_model=List[schemas.CharacterInventory])
def add_item_to_inventory(
    character_id: int,
    item_data: schemas.InventoryItem,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("items:update")),
):
    """Админская выдача предмета в инвентарь персонажа (FEAT-167 §3.2.3).

    Требует JWT и разрешение `items:update`.
    """
    return _add_item_to_inventory_core(character_id, item_data, db)


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


# ---------------------------------------------------------------------------
# Class / subclass equipment rules
# ---------------------------------------------------------------------------

def _scope_word(rules: "equipment_rules.EffectiveRules") -> str:
    return "подкласс" if rules.subclass_key else "класс"


async def _move_slot_item_to_inventory(db: Session, character_id: int, slot: models.EquipmentSlot):
    """Take the item off a slot into the bag, keeping its enhancements, and remove
    its modifiers. No commit — the caller owns the transaction."""
    old_item = db.query(models.Items).filter(models.Items.id == slot.item_id).first()
    if old_item:
        enh_bonuses = crud.get_enhancement_bonuses(slot)
        enh_points = slot.enhancement_points_spent
        socketed_gems = crud.get_socketed_gems(slot)
        current_durability = slot.current_durability

        crud.return_item_to_inventory(db, character_id, old_item)
        db.flush()
        if enh_points > 0 or socketed_gems or current_durability is not None:
            new_inv_row = db.query(models.CharacterInventory).filter(
                models.CharacterInventory.character_id == character_id,
                models.CharacterInventory.item_id == old_item.id,
            ).order_by(models.CharacterInventory.id.desc()).first()
            if new_inv_row:
                new_inv_row.enhancement_points_spent = enh_points
                crud.set_enhancement_bonuses(new_inv_row, enh_bonuses)
                crud.set_socketed_gems(new_inv_row, socketed_gems)
                new_inv_row.current_durability = current_durability
                db.flush()

        gem_items = crud.load_gem_items(db, socketed_gems) if socketed_gems else []
        minus_mods = crud.build_modifiers_dict(
            old_item, negative=True, enhancement_bonuses=enh_bonuses, gem_items=gem_items,
            current_durability=current_durability, max_durability=old_item.max_durability,
            slot_type=slot.slot_type,
        )
        if minus_mods:
            await apply_modifiers_in_attributes_service(character_id, minus_mods)

    slot.item_id = None
    slot.enhancement_points_spent = 0
    slot.enhancement_bonuses = None
    slot.socketed_gems = None
    slot.current_durability = None
    db.add(slot)
    db.flush()


def _pick_weapon_slot(
    db: Session,
    character_id: int,
    item: models.Items,
    rules: "equipment_rules.EffectiveRules",
    requested: Optional[str],
) -> models.EquipmentSlot:
    """Choose the hand for a weapon, enforcing class rules and the two-handed lock."""
    MAIN, OFF = equipment_rules.MAIN_HAND, equipment_rules.OFF_HAND
    hands = equipment_rules.allowed_hands(rules, item)

    if requested == OFF and equipment_rules.is_two_handed(item):
        raise HTTPException(status_code=400, detail="Двуручное оружие берётся только в основную руку")
    if requested and requested not in hands:
        hand = "основной" if requested == MAIN else "доп."
        raise HTTPException(
            status_code=400,
            detail=f"Ваш {_scope_word(rules)} не может держать это оружие в {hand} руке",
        )
    if not hands:
        raise HTTPException(status_code=400, detail=f"Ваш {_scope_word(rules)} не может носить этот вид оружия")

    slots = {
        s.slot_type: s
        for s in db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.slot_type.in_([MAIN, OFF]),
        ).with_for_update().all()
    }
    main_slot = slots.get(MAIN)
    main_item = (
        db.query(models.Items).filter(models.Items.id == main_slot.item_id).first()
        if main_slot and main_slot.item_id else None
    )
    # Equipping a two-handed weapon frees the off-hand itself, so only other weapons see the lock
    off_locked = (
        main_item is not None
        and equipment_rules.is_two_handed(main_item)
        and not equipment_rules.is_two_handed(item)
    )

    if requested:
        candidates = [requested]
    else:
        usable = [h for h in hands if slots.get(h) is not None and not (h == OFF and off_locked)]
        free = [h for h in usable if not slots[h].item_id]
        candidates = free or usable or hands

    choice = candidates[0]
    if choice == OFF and off_locked:
        raise HTTPException(status_code=400, detail="Доп. рука занята двуручным оружием")
    slot = slots.get(choice)
    if slot is None:
        raise HTTPException(status_code=404, detail="Нет подходящего слота для этого предмета")
    return slot


async def _revalidate_equipment(db: Session, character_id: int) -> List[str]:
    """Take off everything the character may no longer wear. Returns freed slot types."""
    if crud.is_character_in_battle(db, character_id):
        # Changing gear mid-battle would desync the battle snapshot; the next
        # trigger (rules edit, subclass change) catches it after the battle.
        logger.info("Equipment revalidation skipped for character %s: in battle", character_id)
        return []

    rules = equipment_rules.rules_for_character(db, character_id)
    forbidden = equipment_rules.forbidden_equipped_slots(db, character_id, rules)
    if not forbidden:
        db.rollback()  # release the row locks taken while checking
        return []

    removed: List[str] = []
    try:
        for slot, _reason in forbidden:
            await _move_slot_item_to_inventory(db, character_id, slot)
            removed.append(slot.slot_type)
        db.commit()
    except Exception:
        db.rollback()
        raise

    crud.recalc_fast_slots(db, character_id)
    await _reconcile_perks_async(character_id)
    logger.info("Unequipped forbidden items for character %s: %s", character_id, removed)
    return removed


async def _revalidate_characters(character_ids: List[int]):
    """Background revalidation with its own session (the request session is closed)."""
    db = SessionLocal()
    try:
        for character_id in character_ids:
            try:
                await _revalidate_equipment(db, character_id)
            except Exception as e:
                # One character failing must not stop the rest; it is logged, not swallowed silently
                logger.error("Equipment revalidation failed for character %s: %s", character_id, e)
    finally:
        db.close()


def _player_ids_of_class(db: Session, class_id: int) -> List[int]:
    rows = db.execute(
        text("SELECT id FROM characters WHERE id_class = :cid AND is_npc = 0"),
        {"cid": class_id},
    ).fetchall()
    return [r[0] for r in rows]


@router.get("/admin/equipment-rules", response_model=List[schemas.EquipmentRuleOut])
def list_equipment_rules(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("items:read")),
):
    rules = db.query(models.EquipmentRule).order_by(models.EquipmentRule.class_id, models.EquipmentRule.id).all()
    return [equipment_rules.rule_to_dict(r) for r in rules]


@router.put("/admin/equipment-rules", response_model=schemas.EquipmentRuleOut)
def save_equipment_rule(
    body: schemas.EquipmentRuleIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("items:update")),
):
    """Create or replace the rule for a class (subclass_key null) or a subclass.
    Characters of that class then lose items they may no longer wear."""
    if not db.execute(text("SELECT 1 FROM classes WHERE id_class = :cid"), {"cid": body.class_id}).fetchone():
        raise HTTPException(status_code=400, detail="Класс не найден")
    try:
        main_hand = equipment_rules.validate_hand_tokens(body.main_hand, off_hand=False)
        off_hand = equipment_rules.validate_hand_tokens(body.off_hand, off_hand=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    key = equipment_rules.scope_key(body.class_id, body.subclass_key)
    rule = db.query(models.EquipmentRule).filter(models.EquipmentRule.scope_key == key).first()
    if rule is None:
        rule = models.EquipmentRule(scope_key=key, class_id=body.class_id, subclass_key=body.subclass_key)
        db.add(rule)
    rule.armor_classes = json.dumps(sorted({a.value for a in body.armor_classes}))
    rule.main_hand = json.dumps(main_hand)
    rule.off_hand = json.dumps(off_hand)
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)

    background_tasks.add_task(_revalidate_characters, _player_ids_of_class(db, body.class_id))
    return equipment_rules.rule_to_dict(rule)


@router.delete("/admin/equipment-rules", status_code=204)
def delete_equipment_rule(
    class_id: int = Query(...),
    subclass_key: Optional[str] = Query(None, regex=r"^[a-z][a-z_]{1,49}$"),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("items:update")),
):
    """Remove restrictions for a scope (everything becomes allowed)."""
    key = equipment_rules.scope_key(class_id, subclass_key)
    rule = db.query(models.EquipmentRule).filter(models.EquipmentRule.scope_key == key).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    db.delete(rule)
    db.commit()
    return Response(status_code=204)


@router.get("/{character_id}/equipment-rules", response_model=schemas.CharacterEquipmentRules)
def get_character_equipment_rules(character_id: int, db: Session = Depends(get_db)):
    """What this character may wear, for greying out items in the inventory."""
    return equipment_rules.rules_for_character(db, character_id).to_response()


@router.post(
    "/internal/characters/{character_id}/revalidate-equipment",
    response_model=schemas.RevalidateEquipmentResponse,
)
async def revalidate_equipment_internal(
    character_id: int,
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """Called by skills-service when a subclass is chosen or reset.

    Только service-to-service: требует заголовок `X-Internal-Token` (FEAT-169).
    """
    try:
        removed = await _revalidate_equipment(db, character_id)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ошибка обращения к сервису атрибутов: {e}")
    return {"character_id": character_id, "removed_slots": removed}


@router.get("/{character_id}/equipment", response_model=List[schemas.EquipmentSlot])
def get_equipment_slots(character_id: int, db: Session = Depends(get_db)):
    # FEAT-167: each slot carries `effective_damage` — the single source of the
    # weapon's damage for the battle engine and for the profile.
    return crud.get_equipment_slots_with_damage(db, character_id)


# -----------------------------------------------------------------------------
# Вспомогательные функции для обращений к сервису атрибутов
# -----------------------------------------------------------------------------
async def apply_modifiers_in_attributes_service(character_id: int, modifiers: dict):
    """
    Единственная функция, которая будет вызывать /apply_modifiers (с любым знаком).
    """
    url = f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/apply_modifiers"
    async with httpx.AsyncClient() as client:
        # FEAT-167: /apply_modifiers is internal-only now — send the shared token.
        resp = await client.post(url, json=modifiers, headers=_internal_token_headers())
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Fire-and-forget side calls (cumulative stats, perks, titles)
# ---------------------------------------------------------------------------
# Every one of these exists in two flavours. The rule is simple and not
# optional:
#
#   * a `def` handler runs in FastAPI's threadpool  -> use the SYNC variant;
#   * an `async def` handler runs ON the event loop -> use the `_async` variant.
#
# inventory-service runs a SINGLE uvicorn worker, so a blocking `httpx.post`
# inside an `async def` freezes the whole service for the duration of that call.
# That is not merely slow: character-service calls back into this service
# (`/inventory/internal/characters/{cid}/xp-multiplier`) while we are waiting on
# it, so the callback cannot be served, times out after 5 s and silently
# fails open to a multiplier of 1.0 — the player loses an XP book they paid for.
# Review #5 measured exactly that: 5429 ms for an equip that unlocks a
# passive-XP title. See docs/services/inventory-service.md.
FIRE_AND_FORGET_TIMEOUT = 5.0


def _cumulative_stats_request(character_id: int, increments: dict, set_max: dict = None):
    payload = {"character_id": character_id, "increments": increments}
    if set_max:
        payload["set_max"] = set_max
    # FEAT-167 #17: internal-only endpoint — send the shared token.
    return f"{settings.ATTRIBUTES_SERVICE_URL}cumulative_stats/increment", payload


def _track_cumulative_stats(character_id: int, increments: dict, set_max: dict = None):
    """Increment cumulative stats for perk tracking. **Sync handlers only.**

    Non-fatal — errors are logged but do not affect the main operation.
    """
    url, payload = _cumulative_stats_request(character_id, increments, set_max)
    try:
        resp = httpx.post(
            url, json=payload, headers=_internal_token_headers(),
            timeout=FIRE_AND_FORGET_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(f"Cumulative stats tracking failed for char {character_id}: {resp.text}")
    except Exception as e:
        logger.warning(f"Cumulative stats tracking error for char {character_id}: {e}")


async def _track_cumulative_stats_async(character_id: int, increments: dict, set_max: dict = None):
    """Same call, awaited — for `async def` handlers (see the note above)."""
    url, payload = _cumulative_stats_request(character_id, increments, set_max)
    try:
        async with httpx.AsyncClient(timeout=FIRE_AND_FORGET_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=_internal_token_headers())
        if resp.status_code != 200:
            logger.warning(f"Cumulative stats tracking failed for char {character_id}: {resp.text}")
    except Exception as e:
        logger.warning(f"Cumulative stats tracking error for char {character_id}: {e}")


def _reconcile_perks_url(character_id: int) -> str:
    return f"{settings.ATTRIBUTES_SERVICE_URL}internal/{character_id}/reconcile-perks"


def _reconcile_perks(character_id: int):
    """Re-evaluate perks after a stat-affecting change. **Sync handlers only.**

    Equip/unequip change attributes, so attribute-condition perks may need to
    activate or deactivate (FEAT-143). Non-fatal.
    """
    try:
        resp = httpx.post(
            _reconcile_perks_url(character_id),
            timeout=FIRE_AND_FORGET_TIMEOUT,
            headers=_internal_token_headers(),
        )
        if resp.status_code != 200:
            logger.warning(f"Perk reconcile failed for char {character_id}: {resp.text}")
    except Exception as e:
        logger.warning(f"Perk reconcile error for char {character_id}: {e}")


async def _reconcile_perks_async(character_id: int):
    """Same call, awaited — for `async def` handlers (see the note above)."""
    try:
        async with httpx.AsyncClient(timeout=FIRE_AND_FORGET_TIMEOUT) as client:
            resp = await client.post(
                _reconcile_perks_url(character_id),
                headers=_internal_token_headers(),
            )
        if resp.status_code != 200:
            logger.warning(f"Perk reconcile failed for char {character_id}: {resp.text}")
    except Exception as e:
        logger.warning(f"Perk reconcile error for char {character_id}: {e}")


async def _evaluate_titles_async(character_id: int, action: str):
    """Ask character-service to re-evaluate titles. **Awaited, never blocking.**

    `action` is only used in the log line ("equip" / "unequip"). Non-fatal: a
    failure here must never fail the equip itself.

    This is the call review #5 pinned down. It must stay awaited: character-service
    reads this service's XP-multiplier endpoint while handling it, so blocking the
    loop here deadlocks the pair until character-service's 5 s timeout fires.
    """
    try:
        async with httpx.AsyncClient(timeout=FIRE_AND_FORGET_TIMEOUT) as client:
            await client.post(
                f"{settings.CHARACTER_SERVICE_URL}/characters/internal/evaluate-titles",
                json={"character_id": character_id},
                headers=_internal_token_headers(),
            )
    except Exception as e:
        logger.warning(
            f"Title evaluation error after {action} for character {character_id}: {e}"
        )


async def recover_in_attributes_service(character_id: int, recovery: dict):
    """
    Для восстановления ресурсов (health_recovery, mana_recovery и т.д.).
    """
    url = f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/recover"
    async with httpx.AsyncClient() as client:
        # FEAT-167: /recover is internal-only now — send the shared token.
        resp = await client.post(url, json=recovery, headers=_internal_token_headers())
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
    check_not_gathering(db, character_id, "Вы не можете менять экипировку во время добычи")

    try:
        # 1) Проверяем предмет
        db_item = db.query(models.Items).filter(models.Items.id == req.item_id).first()
        if not db_item:
            db.rollback()
            raise HTTPException(status_code=404, detail="Предмет не найден")
        if db_item.is_food:
            # FEAT-164: food cannot be eaten in battle, so no fast slot for it
            db.rollback()
            raise HTTPException(status_code=400, detail="Еду нельзя положить в быстрый слот")

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

        # 2.6) Правила класса/подкласса
        rules = equipment_rules.rules_for_character(db, character_id)
        if not equipment_rules.armor_allowed(rules, db_item):
            raise HTTPException(
                status_code=400,
                detail=f"Ваш {_scope_word(rules)} не может носить броню этого класса",
            )

        # 3) Ищем слот
        if db_item.item_type == "weapon":
            slot = _pick_weapon_slot(db, character_id, db_item, rules, req.slot_type)
        else:
            slot = crud.find_equipment_slot_for_item(db, character_id, db_item)
        if not slot:
            db.rollback()
            raise HTTPException(status_code=404, detail="Нет подходящего слота для этого предмета")

        # Двуручное оружие занимает обе руки: доп. рука освобождается
        if slot.slot_type == equipment_rules.MAIN_HAND and equipment_rules.is_two_handed(db_item):
            off_slot = db.query(models.EquipmentSlot).filter(
                models.EquipmentSlot.character_id == character_id,
                models.EquipmentSlot.slot_type == equipment_rules.OFF_HAND,
            ).with_for_update().first()
            if off_slot and off_slot.item_id:
                await _move_slot_item_to_inventory(db, character_id, off_slot)

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
                minus_mods = crud.build_modifiers_dict(old_item, negative=True, enhancement_bonuses=old_enh_bonuses, gem_items=old_gem_items, current_durability=old_current_durability, max_durability=old_item.max_durability, slot_type=slot.slot_type)
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
        plus_mods = crud.build_modifiers_dict(db_item, negative=False, enhancement_bonuses=inv_enh_bonuses, gem_items=inv_gem_items, current_durability=inv_current_durability, max_durability=db_item.max_durability, slot_type=slot.slot_type)
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

    # Track cumulative stats for equip (non-fatal). Only real equipment slots
    # count toward "items equipped" — quick/fast slots (potions/consumables) must
    # NOT (FEAT-143 bug 4). Re-equip abuse of the same item is a known limitation
    # of a cumulative counter (needs a distinct/current-count redesign).
    if not str(getattr(slot, "slot_type", "")).startswith("fast_slot_"):
        await _track_cumulative_stats_async(character_id, {"items_equipped": 1})

    # Re-evaluate perks — equipping changed attributes (FEAT-143 dynamic perks).
    await _reconcile_perks_async(character_id)

    # Trigger title evaluation after equip (non-fatal). Awaited, not blocking:
    # character-service calls this service back while handling it.
    await _evaluate_titles_async(character_id, "equip")

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
    check_not_gathering(db, character_id, "Вы не можете менять экипировку во время добычи")
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
        minus_mods = crud.build_modifiers_dict(old_item, negative=True, enhancement_bonuses=slot_enh_bonuses, gem_items=slot_gem_items, current_durability=slot_current_durability, max_durability=old_item.max_durability, slot_type=slot.slot_type)
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

    # Re-evaluate perks — unequipping changed attributes; attribute-condition
    # perks may need to deactivate (FEAT-143 dynamic perks).
    await _reconcile_perks_async(character_id)

    # Trigger title evaluation after unequip (non-fatal). Awaited, not blocking.
    await _evaluate_titles_async(character_id, "unequip")

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
    # FEAT-168: в бою расходники применяются только из быстрых слотов
    # (battle-service), иначе предмет списывается впустую.
    check_not_in_battle(db, character_id, "Нельзя использовать предметы во время боя")
    check_not_gathering(db, character_id, "Нельзя использовать предметы во время добычи")
    db_item = db.query(models.Items).filter(models.Items.id == req.item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    if db_item.item_type not in ("consumable", "scroll", "misc", "resource"):
        raise HTTPException(status_code=400, detail="Нельзя использовать этот предмет")
    if db_item.is_food:
        # FEAT-164: food must go through /eat-food (satiety rules)
        raise HTTPException(status_code=400, detail=FOOD_REJECT_MESSAGE)

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

def _get_fast_slots_core(db: Session, character_id: int) -> List[schemas.FastSlot]:
    """
    Возвращает список включённых fast_slot_* для этого персонажа.
    Для каждого слота отдаёт:
      - slot_type: fast_slot_1…fast_slot_10
      - item_id   : id надетого consumable
      - quantity  : сколько штук этого item_id осталось в инвентаре

    Общее тело для игрового и внутреннего маршрутов (FEAT-169 §3.2).
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

        # 3) Добавляем в ответ.
        # FEAT-168: восстановление и боевые эффекты едут вместе со слотом —
        # battle-service снимает с этого ответа снапшот в состояние боя.
        result.append(schemas.FastSlot(
            slot_type=slot.slot_type,
            item_id=slot.item_id,
            quantity=qty,
            name=item.name,
            image=item.image or "",
            health_recovery=item.health_recovery or 0,
            mana_recovery=item.mana_recovery or 0,
            energy_recovery=item.energy_recovery or 0,
            stamina_recovery=item.stamina_recovery or 0,
            consumable_action=item.consumable_action,
            coating_turns=item.coating_turns,
            coating_bonus_damage=item.coating_bonus_damage,
            effects=[schemas.ItemEffectOut.from_orm(e) for e in item.effects],
            damage_entries=[schemas.ItemDamageOut.from_orm(d) for d in item.damage_entries],
        ))

    return result


@router.get(
    "/internal/characters/{character_id}/fast_slots",
    response_model=List[schemas.FastSlot]
)
def get_fast_slots_internal(
    character_id: int,
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """Пояс персонажа для межсервисных вызовов (FEAT-169 §3.2).

    Только service-to-service: требует заголовок `X-Internal-Token`.
    Проверки владения тут нет намеренно — battle-service читает пояс мобов и
    НПС, у которых нет владельца (`user_id IS NULL`).
    """
    return _get_fast_slots_core(db, character_id)


@router.get(
    "/characters/{character_id}/fast_slots",
    response_model=List[schemas.FastSlot]
)
def get_fast_slots(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Пояс своего персонажа для игрока (FEAT-169 §3.2).

    Требует JWT и владение персонажем: состав пояса — это разведданные перед
    боем, читать чужой пояс нельзя.
    """
    verify_character_ownership(db, character_id, current_user.id)
    return _get_fast_slots_core(db, character_id)


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

        # Track cumulative stats for both participants
        trade_items = db.query(models.TradeOfferItem).filter(
            models.TradeOfferItem.trade_offer_id == trade.id
        ).all()
        init_items_given = sum(ti.quantity for ti in trade_items if ti.character_id == trade.initiator_character_id)
        target_items_given = sum(ti.quantity for ti in trade_items if ti.character_id == trade.target_character_id)

        # Initiator: sold init_items_given, bought target_items_given
        init_increments = {}
        if init_items_given > 0:
            init_increments["items_sold"] = init_items_given
        if target_items_given > 0:
            init_increments["items_bought"] = target_items_given
        if trade.initiator_gold > 0:
            init_increments["total_gold_spent"] = trade.initiator_gold
        if trade.target_gold > 0:
            init_increments["total_gold_earned"] = trade.target_gold
        if init_increments:
            _track_cumulative_stats(trade.initiator_character_id, init_increments)

        # Target: sold target_items_given, bought init_items_given
        target_increments = {}
        if target_items_given > 0:
            target_increments["items_sold"] = target_items_given
        if init_items_given > 0:
            target_increments["items_bought"] = init_items_given
        if trade.target_gold > 0:
            target_increments["total_gold_spent"] = trade.target_gold
        if trade.initiator_gold > 0:
            target_increments["total_gold_earned"] = trade.initiator_gold
        if target_increments:
            _track_cumulative_stats(trade.target_character_id, target_increments)

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
    _internal=Depends(verify_internal_token),
):
    """
    Списывает 1 единицу предмета из инвентаря персонажа и очищает
    быстрый слот, если предмет закончился.
    Используется battle-service при применении расходника в бою.
    Только для межсервисных вызовов: требует `X-Internal-Token` (FEAT-169).
    """
    # FEAT-164: food is never usable in battle (defence in depth)
    food_item = db.query(models.Items.is_food).filter(models.Items.id == req.item_id).first()
    if food_item is not None and food_item[0]:
        raise HTTPException(status_code=400, detail="Еду нельзя использовать в бою")

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
# Internal: free-slots check (FEAT-128)
# ---------------------------------------------------------------------------
# Used by locations-service at gather-start to confirm the inventory can
# accept new items. Service-to-service only: `X-Internal-Token` (FEAT-169),
# with the api-gateway as the second layer.

@router.post(
    "/internal/characters/{character_id}/free_slots_check",
    response_model=schemas.FreeSlotsCheckResponse,
)
def free_slots_check_internal(
    character_id: int,
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """
    Возвращает количество свободных слотов и флаг is_full для указанного
    персонажа. Используется locations-service перед стартом добычи.
    Только для межсервисных вызовов: требует `X-Internal-Token`.
    """
    free, is_full = crud.get_inventory_free_slots(db, character_id)
    return {"free_slot_count": free, "is_full": is_full}


# ---------------------------------------------------------------------------
# Internal: gathering award (FEAT-128 task #7)
# ---------------------------------------------------------------------------
# Atomically applies all post-gather inventory side effects:
#   - adds the result item (capacity-aware, partial-add scaling)
#   - decrements the tool durability (if any)
#   - awards XP and runs the rank-up loop on character_gathering_skills
# All under one DB transaction with row locks. Locations-service calls this
# from its lazy-finalize path (3.5.2). Service-to-service only: requires
# `X-Internal-Token` (FEAT-169); Nginx is the second layer.

@router.post(
    "/internal/characters/{character_id}/gathering/award",
    response_model=schemas.GatheringAwardResponse,
)
def gathering_award_internal(
    character_id: int,
    req: schemas.GatheringAwardRequest,
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """
    Внутренний эндпоинт: одна транзакция на все эффекты завершённой добычи —
    инвентарь, прочность инструмента, опыт и rank-up.
    Требует заголовок `X-Internal-Token`.
    """
    return crud.award_gathering(db, character_id, req)


# ---------------------------------------------------------------------------
# Internal: XP buff multiplier (FEAT-168 §3.3.4)
# ---------------------------------------------------------------------------
# character-service reads this before writing character XP, so a «книга опыта
# персонажа» works from another service without duplicating `active_buffs`.
# Guarded by X-Internal-Token like the other write-capable /internal/ routes.

@router.get(
    "/internal/characters/{character_id}/xp-multiplier",
    response_model=schemas.XpMultiplierResponse,
)
def get_xp_multiplier_internal(
    character_id: int,
    buff_type: str = Query("xp_bonus", description="Тип баффа опыта"),
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """Множитель опыта персонажа по активному баффу (1.0, если баффа нет)."""
    if buff_type not in schemas.ALLOWED_BUFF_TYPES:
        raise HTTPException(status_code=400, detail="Недопустимый тип баффа")

    exists = db.execute(
        text("SELECT id FROM characters WHERE id = :cid"),
        {"cid": character_id},
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    multiplier = crud.get_xp_multiplier(db, character_id, buff_type)
    # get_active_buff deletes an expired row and flushes; persist that cleanup.
    db.commit()
    return {
        "character_id": character_id,
        "buff_type": buff_type,
        "multiplier": multiplier,
    }


MAX_XP_MULTIPLIER_BATCH = len(schemas.ALLOWED_BUFF_TYPES)


@router.get(
    "/internal/characters/{character_id}/xp-multipliers",
    response_model=schemas.XpMultipliersResponse,
)
def get_xp_multipliers_internal(
    character_id: int,
    buff_types: str = Query(..., description="Типы баффов опыта через запятую"),
    db: Session = Depends(get_db),
    _internal=Depends(verify_internal_token),
):
    """FEAT-168 #6: множители сразу по нескольким источникам опыта, одним запросом."""
    requested = [p.strip() for p in (buff_types or "").split(",")]
    requested = [p for p in requested if p]
    if not requested:
        raise HTTPException(status_code=400, detail="Параметр buff_types не должен быть пустым")
    if len(requested) > MAX_XP_MULTIPLIER_BATCH:
        raise HTTPException(status_code=400, detail="Слишком много типов баффов в запросе")
    unknown = [p for p in requested if p not in schemas.ALLOWED_BUFF_TYPES]
    if unknown:
        raise HTTPException(status_code=400, detail="Недопустимый тип баффа")

    exists = db.execute(
        text("SELECT id FROM characters WHERE id = :cid"),
        {"cid": character_id},
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    multipliers = crud.get_xp_multipliers(db, character_id, requested)
    # get_active_buff deletes expired rows and flushes; persist that cleanup.
    db.commit()
    return {"character_id": character_id, "multipliers": multipliers}


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

    # FEAT-165: base recipes created after the character reached the rank
    crud.sync_auto_learned_recipes_and_commit(db, cp)
    cp = crud.get_character_profession(db, character_id)

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
        "auto_learned_recipes": auto_recipes,
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
        "auto_learned_recipes": auto_recipes,
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
# Gathering skills endpoints — PUBLIC (FEAT-128)
# ---------------------------------------------------------------------------

@router.get(
    "/characters/{character_id}/gathering-skills",
    response_model=schemas.CharacterGatheringSkillsResponse,
)
def get_character_gathering_skills(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Возвращает прогресс трёх навыков добычи (Горное дело / Травничество /
    Лесорубство) для персонажа. Лениво создаёт строки прогресса с
    rank=1, xp=0 при первом обращении.

    Доступно любому аутентифицированному пользователю — вкладка «Сбор»
    видна в read-only режиме на чужих профилях (см. 2.7 #4).
    """
    return crud.build_gathering_skills_response(db, character_id)


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
    """Список изученных рецептов персонажа (базовые рецепты по рангу досинхронизируются)."""
    verify_character_ownership(db, character_id, current_user.id)
    cp = crud.get_character_profession(db, character_id)
    if cp is not None:
        crud.sync_auto_learned_recipes_and_commit(db, cp)
    return crud.get_available_recipes_for_character(db, character_id, profession_id)


@router.get("/crafting/refining-rules", response_model=List[schemas.RefiningRuleOut])
def get_refining_rules(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Какая профессия какое сырьё во что перерабатывает (FEAT-165)."""
    return crud.get_refining_rules(db)


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
    check_not_gathering(db, character_id, "Нельзя крафтить во время добычи")

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

    # 5. Verify the recipe is learned
    learned = db.query(models.CharacterRecipe).filter(
        models.CharacterRecipe.character_id == character_id,
        models.CharacterRecipe.recipe_id == req.recipe_id,
    ).first()
    if not learned:
        raise HTTPException(status_code=400, detail="Рецепт не изучен")

    # 6. Execute craft in transaction
    try:
        result = crud.execute_craft(db, character_id, recipe, cp=cp)
        db.commit()
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Crafting error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании предмета")


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
            "is_active": recipe.is_active,
            "auto_learn_rank": recipe.auto_learn_rank,
            "ingredients": ingredients,
            "recipe_item_id": recipe_item.id if recipe_item else None,
            "recipe_item_name": recipe_item.name if recipe_item else None,
        })

    return {"items": items, "total": total, "page": page, "per_page": per_page}


RECIPE_RARITY_CAP_ERROR = (
    "Крафт не может создавать предметы мифической, божественной или демонической редкости"
)


def _ensure_recipe_rarity_allowed(result_item) -> None:
    """FEAT-164 rarity cap for crafting.

    Recipes have no quality of their own — only the result item does (the
    recipe's stored rarity is derived from it). Equipment-only rarities
    (mythical/divine/demonic) are fine for equipment results; a non-equipment
    result above legendary (legacy rows only — the item validator forbids it)
    cannot be crafted.
    """
    if not schemas.is_rarity_allowed_for_type(result_item.item_type, result_item.item_rarity):
        raise HTTPException(status_code=400, detail=RECIPE_RARITY_CAP_ERROR)


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

    _ensure_recipe_rarity_allowed(result_item)

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
    else:
        result_item = db.query(models.Items).filter(models.Items.id == recipe.result_item_id).first()

    if result_item is None:
        raise HTTPException(status_code=400, detail="Результирующий предмет не найден")
    # FEAT-164: cap checked on the (new or stored) result item
    _ensure_recipe_rarity_allowed(result_item)

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
    """Получить информацию о заточке предмета: текущие бонусы, доступные статы, подходящие камни.
    source=inventory для предмета в инвентаре, source=equipment для экипированного.
    Профессия не нужна (FEAT-165)."""
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

    sharpen_group = crud.sharpen_group_for_type(item_obj.item_type)
    if sharpen_group is None:
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

    # Only stones of the matching group
    whetstones = []
    whetstone_inv_rows = (
        db.query(models.CharacterInventory)
        .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
        .filter(
            models.CharacterInventory.character_id == character_id,
            models.Items.whetstone_level.isnot(None),
            models.Items.whetstone_group == sharpen_group,
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
            "whetstone_group": sharpen_group,
        })

    return {
        "item_name": item_obj.name,
        "item_type": item_obj.item_type,
        "points_spent": points_spent,
        "points_remaining": points_remaining,
        "sharpen_group": sharpen_group,
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
    """Заточить конкретный стат предмета подходящим камнем заточки.
    Точить может любой персонаж; опыт профессии за заточку не начисляется (FEAT-165)."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя затачивать предметы во время боя")
    check_not_gathering(db, character_id, "Нельзя затачивать предметы во время добычи")

    # 1. Get item row (inventory or equipment)
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

    # 2. Check identification (only for inventory items — equipped items are always identified)
    if not is_equipped:
        if not inv_row.is_identified:
            raise HTTPException(status_code=400, detail="Предмет не опознан")

    # 3. Validate item type
    sharpen_group = crud.sharpen_group_for_type(item_obj.item_type)
    if sharpen_group is None:
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

    # 7. Point cost
    point_cost = 1

    # 8. Check points budget
    if item_row.enhancement_points_spent + point_cost > crud.MAX_ENHANCEMENT_POINTS:
        raise HTTPException(status_code=400, detail="Недостаточно поинтов заточки")

    # 9. Find and validate the stone (nothing is consumed before these checks pass)
    whetstone_inv = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.whetstone_item_id,
        models.CharacterInventory.character_id == character_id,
    ).with_for_update().first()
    if not whetstone_inv or whetstone_inv.quantity < 1:
        raise HTTPException(status_code=400, detail="Точильный камень не найден в инвентаре")

    whetstone_item = db.query(models.Items).filter(models.Items.id == whetstone_inv.item_id).first()
    if not whetstone_item or whetstone_item.whetstone_level is None:
        raise HTTPException(status_code=400, detail="Этот предмет не является точильным камнем")
    if getattr(whetstone_item.whetstone_group, "value", whetstone_item.whetstone_group) != sharpen_group:
        raise HTTPException(status_code=400, detail="Этот камень не подходит для этого предмета")

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
                # FEAT-167: sharpening a weapon's damage belongs to that hand,
                # not to the shared `damage` attribute.
                if eq_slot is not None and eq_slot.slot_type in crud.WEAPON_SLOTS:
                    delta.pop("damage", None)
                if delta:
                    await apply_modifiers_in_attributes_service(character_id, delta)
        else:
            new_value = old_value

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
# Refining endpoints — PUBLIC (FEAT-165)
# ---------------------------------------------------------------------------

@router.get("/crafting/{character_id}/refine-info", response_model=schemas.RefineInfoResponse)
def get_refine_info(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Что персонаж может переработать своей профессией (сырьё из инвентаря с настроенным результатом)."""
    verify_character_ownership(db, character_id, current_user.id)
    return crud.get_refine_info(db, character_id)


@router.post("/crafting/{character_id}/refine", response_model=schemas.RefineResult)
def refine_item(
    character_id: int,
    req: schemas.RefineRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Переработать сырьё одного вида. Всегда успешно; остаток, не кратный пропорции, не тратится."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя перерабатывать во время боя")
    check_not_gathering(db, character_id, "Нельзя перерабатывать во время добычи")

    try:
        result = crud.refine_items(db, character_id, req.source_item_id, req.quantity)
        db.commit()
        return result
    except crud.RefineNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        db.rollback()
        logger.exception("Refining error for character %s", character_id)
        raise HTTPException(status_code=500, detail="Ошибка при переработке")


# ---------------------------------------------------------------------------
# Gem / rune socket endpoints — PUBLIC
# FEAT-165: anyone may INSERT a gem (jewelry) or a rune (weapon/body/head/cloak);
# only a jeweler extracts gems and only an enchanter extracts runes (incl. legacy belt runes).
# ---------------------------------------------------------------------------

INSERT_WRONG_KIND_ERRORS = {
    'gem': "В украшение можно вставить только огранку",
    'rune': "В этот предмет можно вставить только руну",
}


def _load_socket_row(db: Session, character_id: int, row_id: int, source: str, lock: bool):
    """Inventory or equipment row of the character + its item, or 404."""
    if source == "equipment":
        query = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == row_id,
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.item_id.isnot(None),
        )
        not_found = "Экипированный предмет не найден"
    else:
        query = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == row_id,
            models.CharacterInventory.character_id == character_id,
        )
        not_found = "Предмет не найден в инвентаре"
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail=not_found)
    item_obj = db.query(models.Items).filter(models.Items.id == row.item_id).first()
    if not item_obj:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    return row, item_obj


def _socket_slots(row, item_obj) -> list:
    """socketed_gems padded to the item's socket count (legacy rows may hold more)."""
    socketed = crud.get_socketed_gems(row)
    socket_count = item_obj.socket_count or 0
    while len(socketed) < socket_count:
        socketed.append(None)
    return socketed


def _can_extract(cp, insertable_type: str) -> bool:
    return (
        cp is not None
        and cp.profession is not None
        and cp.profession.slug == crud.SOCKET_EXTRACTOR_BY_INSERTABLE[insertable_type]
    )


@router.get("/crafting/{character_id}/socket-info/{item_row_id}")
def get_socket_info(
    character_id: int,
    item_row_id: int,
    source: str = Query("inventory", regex="^(inventory|equipment)$"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Получить информацию о слотах камней/рун предмета. Профессия не нужна;
    can_extract показывает, может ли персонаж извлекать из этого предмета."""
    verify_character_ownership(db, character_id, current_user.id)

    row, item_obj = _load_socket_row(db, character_id, item_row_id, source, lock=False)

    insertable_type = crud.insertable_type_for_item(item_obj.item_type)
    if insertable_type is None:
        raise HTTPException(status_code=400, detail="Этот тип предмета не поддерживает камни и руны")

    socketed = _socket_slots(row, item_obj)
    can_insert = item_obj.item_type in crud.SOCKETABLE_TYPES
    if not can_insert and not any(g is not None for g in socketed):
        # Legacy belts are shown only while they still hold runes
        raise HTTPException(status_code=400, detail="Этот тип предмета не поддерживает руны")

    cp = crud.get_character_profession(db, character_id)
    can_extract = _can_extract(cp, insertable_type)
    preservation_pct = (
        crud.GEM_PRESERVATION_CHANCES.get(cp.current_rank, 10) if can_extract else None
    )

    # Load gem items for filled slots
    gem_ids = [gid for gid in socketed if gid is not None]
    gem_items_map = {}
    if gem_ids:
        gem_items_map = {
            g.id: g for g in db.query(models.Items).filter(models.Items.id.in_(gem_ids)).all()
        }

    slots = []
    for i, gem_id in enumerate(socketed):
        gem_item = gem_items_map.get(gem_id) if gem_id else None
        slots.append({
            "slot_index": i,
            "gem_item_id": gem_id,
            "gem_name": gem_item.name if gem_item else None,
            "gem_image": gem_item.image if gem_item else None,
            "gem_modifiers": crud.get_gem_modifiers_dict(gem_item) if gem_item else {},
        })

    available_gems = []
    if can_insert:
        gem_inv_rows = (
            db.query(models.CharacterInventory)
            .join(models.Items, models.CharacterInventory.item_id == models.Items.id)
            .filter(
                models.CharacterInventory.character_id == character_id,
                models.Items.item_type == insertable_type,
            )
            .all()
        )
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
        "socket_count": len(socketed),
        "insertable_type": insertable_type,
        "can_insert": can_insert,
        "can_extract": can_extract,
        "extract_preservation_chance": preservation_pct,
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
    """Вставить огранку (в украшение) или руну (в оружие, броню, шлем, плащ). Доступно любому персонажу."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя вставлять камни/руны во время боя")
    check_not_gathering(db, character_id, "Нельзя вставлять камни/руны во время добычи")

    is_equipped = req.source == "equipment"
    row, item_obj = _load_socket_row(
        db, character_id, req.item_row_id, "equipment" if is_equipped else "inventory", lock=True
    )

    # Equipped items are always identified
    if not is_equipped and not row.is_identified:
        raise HTTPException(status_code=400, detail="Предмет не опознан")

    if item_obj.item_type in crud.JEWELRY_TYPES:
        insertable_type = 'gem'
    elif item_obj.item_type in crud.RUNE_INSERT_TYPES:
        insertable_type = 'rune'
    elif item_obj.item_type in crud.RUNE_EXTRACT_TYPES:
        raise HTTPException(status_code=400, detail="Этот тип предмета не поддерживает руны")
    else:
        raise HTTPException(status_code=400, detail="Этот тип предмета не поддерживает камни и руны")

    socket_count = item_obj.socket_count or 0
    if req.slot_index < 0 or req.slot_index >= socket_count:
        raise HTTPException(status_code=400, detail="Недопустимый индекс слота")

    socketed = _socket_slots(row, item_obj)
    if socketed[req.slot_index] is not None:
        raise HTTPException(status_code=400, detail="Этот слот уже занят")

    gem_inv = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.gem_inventory_id,
        models.CharacterInventory.character_id == character_id,
    ).with_for_update().first()
    if not gem_inv or gem_inv.quantity < 1:
        raise HTTPException(status_code=404, detail="Предмет для вставки не найден в инвентаре")

    gem_item = db.query(models.Items).filter(models.Items.id == gem_inv.item_id).first()
    if not gem_item or gem_item.item_type != insertable_type:
        raise HTTPException(status_code=400, detail=INSERT_WRONG_KIND_ERRORS[insertable_type])

    try:
        # Consume gem
        gem_inv.quantity -= 1
        if gem_inv.quantity <= 0:
            db.delete(gem_inv)
        db.flush()

        socketed[req.slot_index] = gem_item.id
        crud.set_socketed_gems(row, socketed)
        db.flush()

        # If equipped, apply the gem's own modifiers
        if is_equipped:
            gem_only_mods = {}
            for field in crud.ALL_MODIFIER_FIELDS:
                val = getattr(gem_item, field, 0) or 0
                if val:
                    gem_only_mods[field.replace('_modifier', '')] = val
            # FEAT-167: a rune's damage in a weapon belongs to that hand.
            if row.slot_type in crud.WEAPON_SLOTS:
                gem_only_mods.pop("damage", None)
            if gem_only_mods:
                await apply_modifiers_in_attributes_service(character_id, gem_only_mods)

        db.commit()

        return {
            "success": True,
            "item_name": item_obj.name,
            "gem_name": gem_item.name,
            "slot_index": req.slot_index,
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
    """Извлечь огранку (ювелир) или руну (зачарователь) из слота предмета."""
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя извлекать камни/руны во время боя")
    check_not_gathering(db, character_id, "Нельзя извлекать камни/руны во время добычи")

    # 1. Profession + rank
    cp = crud.get_character_profession(db, character_id)
    if not cp:
        raise HTTPException(status_code=400, detail="У персонажа нет профессии")

    if cp.profession.slug == "jeweler":
        allowed_types = crud.JEWELRY_TYPES
    elif cp.profession.slug == "enchanter":
        allowed_types = crud.RUNE_EXTRACT_TYPES
    else:
        raise HTTPException(status_code=400, detail="Только ювелир или зачарователь могут извлекать предметы из слотов")

    # 2. Load item row
    is_equipped = req.source == "equipment"
    row, item_obj = _load_socket_row(
        db, character_id, req.item_row_id, "equipment" if is_equipped else "inventory", lock=True
    )

    if item_obj.item_type not in allowed_types:
        if cp.profession.slug == "jeweler":
            raise HTTPException(status_code=400, detail="Ювелир может извлекать только из украшений")
        raise HTTPException(status_code=400, detail="Зачарователь может извлекать только из оружия и брони")

    # 3. Validate slot_index has a gem
    socketed = _socket_slots(row, item_obj)
    if req.slot_index < 0 or req.slot_index >= len(socketed):
        raise HTTPException(status_code=400, detail="Недопустимый индекс слота")

    gem_item_id = socketed[req.slot_index]
    if gem_item_id is None:
        raise HTTPException(status_code=400, detail="В этом слоте нет камня")

    gem_item = db.query(models.Items).filter(models.Items.id == gem_item_id).first()
    if not gem_item:
        raise HTTPException(status_code=400, detail="Камень не найден в базе данных")

    # 4. Preservation chance by rank
    preservation_pct = crud.GEM_PRESERVATION_CHANCES.get(cp.current_rank, 10)

    try:
        gem_preserved = random.random() < (preservation_pct / 100.0)

        if gem_preserved:
            crud.return_item_to_inventory(db, character_id, gem_item)
            db.flush()

        socketed[req.slot_index] = None
        crud.set_socketed_gems(row, socketed)
        db.flush()

        # If equipped, remove gem modifiers
        if is_equipped:
            gem_neg_mods = {}
            for field in crud.ALL_MODIFIER_FIELDS:
                val = getattr(gem_item, field, 0) or 0
                if val:
                    gem_neg_mods[field.replace('_modifier', '')] = -val
            # FEAT-167: a rune's damage in a weapon belongs to that hand.
            if row.slot_type in crud.WEAPON_SLOTS:
                gem_neg_mods.pop("damage", None)
            if gem_neg_mods:
                await apply_modifiers_in_attributes_service(character_id, gem_neg_mods)

        db.commit()

        return {
            "success": True,
            "item_name": item_obj.name,
            "gem_name": gem_item.name,
            "gem_preserved": gem_preserved,
            "preservation_chance": preservation_pct,
            "slot_index": req.slot_index,
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
    check_not_gathering(db, character_id, "Нельзя опознавать предметы во время добычи")

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

# FEAT-168: человекочитаемые названия типов баффов для сообщений игроку.
# Ключи — ровно schemas.ALLOWED_BUFF_TYPES.
BUFF_TYPE_LABELS = {
    schemas.XP_BUFF_PROFESSION: "к опыту профессии",
    schemas.XP_BUFF_GATHERING: "к опыту сбора",
    schemas.XP_BUFF_CHARACTER_ALL: "ко всему опыту персонажа",
    schemas.XP_BUFF_CHARACTER_BATTLE: "к опыту персонажа за бои",
    schemas.XP_BUFF_CHARACTER_POST: "к опыту персонажа за отыгрыш",
    schemas.XP_BUFF_CHARACTER_QUEST: "к опыту персонажа за задания",
    schemas.XP_BUFF_CHARACTER_TITLE: "к опыту персонажа за титулы",
    schemas.XP_BUFF_CHARACTER_PASS: "к опыту персонажа за боевой пропуск",
}
DEFAULT_BUFF_TYPE_LABEL = "к опыту"


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
    check_not_gathering(db, character_id, "Нельзя использовать предметы во время добычи")

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

        if item_obj.is_food:
            raise HTTPException(status_code=400, detail=FOOD_REJECT_MESSAGE)

        # 3. Validate it's a buff item.
        # FEAT-168 #6: один предмет может ускорять несколько видов опыта сразу;
        # у предметов, созданных до этого, список собирается из старых колонок.
        buff_rows = crud.get_item_xp_buffs(db, item_obj)
        if not buff_rows:
            raise HTTPException(status_code=400, detail="Этот предмет не является баффовым")

        # 4. Consume 1 item
        inv_row.quantity -= 1
        if inv_row.quantity <= 0:
            db.delete(inv_row)
        db.flush()

        # 5. Apply every buff (upsert per type)
        for row in buff_rows:
            crud.apply_buff(
                db,
                character_id=character_id,
                buff_type=row["buff_type"],
                value=row["value"],
                duration_minutes=row["duration_minutes"],
                source_name=item_obj.name,
            )

        db.commit()

        # FEAT-168: текст зависит от типа баффа (раньше всегда писалось «XP»)
        parts = [
            f"+{int(row['value'] * 100)}% "
            f"{BUFF_TYPE_LABELS.get(row['buff_type'], DEFAULT_BUFF_TYPE_LABEL)} "
            f"на {row['duration_minutes']} мин"
            for row in buff_rows
        ]
        primary = buff_rows[0]
        return {
            "success": True,
            "buff_type": primary["buff_type"],
            "value": primary["value"],
            "duration_minutes": primary["duration_minutes"],
            "source_item_name": item_obj.name,
            "message": "Бафф активирован: " + ", ".join(parts),
            "buffs": buff_rows,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Use buff item error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при использовании баффового предмета")


# ---------------------------------------------------------------------------
# FEAT-164: eating food → "Сытость"
# ---------------------------------------------------------------------------
FOOD_REJECT_MESSAGE = "Еду нужно съесть"
SATIETY_HTTP_TIMEOUT = 5.0
SATIETY_UNAVAILABLE_MESSAGE = "Не удалось применить сытость, попробуйте позже"
SATIETY_DURATION_LABEL = "24 ч"


def _extract_detail(resp: httpx.Response, fallback: str) -> str:
    try:
        detail = resp.json().get("detail")
    except Exception:
        return fallback
    return detail if isinstance(detail, str) and detail else fallback


@router.post("/{character_id}/eat-food", response_model=schemas.EatFoodResponse)
def eat_food(
    character_id: int,
    req: schemas.EatFoodRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Съесть еду: сытость на 24 ч (+ мгновенное восстановление, если есть).

    Предмет списывается только после того, как сервис атрибутов применил
    сытость (201). Во время боя есть нельзя; в подземелье и на сборе — можно.
    """
    verify_character_ownership(db, character_id, current_user.id)
    check_not_in_battle(db, character_id, "Нельзя есть во время боя")

    try:
        inv_row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.inventory_item_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if not inv_row or inv_row.quantity < 1:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")

        item_obj = db.query(models.Items).filter(models.Items.id == inv_row.item_id).first()
        if not item_obj:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        if not item_obj.is_food:
            raise HTTPException(status_code=400, detail="Этот предмет нельзя съесть")

        payload = {
            "item_id": item_obj.id,
            "source_item_name": item_obj.name,
            "rarity": schemas._enum_value(item_obj.item_rarity),
            "modifiers": crud.build_modifiers_dict(item_obj),
            "recovery": {
                "health_recovery": max(0, item_obj.health_recovery or 0),
                "mana_recovery": max(0, item_obj.mana_recovery or 0),
                "energy_recovery": max(0, item_obj.energy_recovery or 0),
                "stamina_recovery": max(0, item_obj.stamina_recovery or 0),
            },
        }

        url = f"{settings.ATTRIBUTES_SERVICE_URL}internal/{character_id}/satiety"
        try:
            resp = httpx.post(
                url,
                json=payload,
                timeout=SATIETY_HTTP_TIMEOUT,
                headers=_internal_token_headers(),
            )
        except httpx.HTTPError as e:
            logger.error(f"eat-food: сервис атрибутов недоступен (персонаж {character_id}): {e}")
            raise HTTPException(status_code=502, detail=SATIETY_UNAVAILABLE_MESSAGE)

        if resp.status_code == 409:
            raise HTTPException(status_code=409, detail=_extract_detail(resp, "Вы уже наелись"))
        if resp.status_code == 400:
            raise HTTPException(status_code=400, detail=_extract_detail(resp, "Этот предмет нельзя съесть"))
        if resp.status_code != 201:
            logger.error(
                f"eat-food: сервис атрибутов вернул {resp.status_code} для персонажа {character_id}: {resp.text[:300]}"
            )
            raise HTTPException(status_code=502, detail=SATIETY_UNAVAILABLE_MESSAGE)

        satiety = resp.json().get("satiety")

        # Satiety applied — now consume exactly one item.
        inv_row.quantity -= 1
        if inv_row.quantity <= 0:
            db.delete(inv_row)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(
                f"eat-food: сытость выдана, но предмет не списан (персонаж {character_id}, "
                f"inventory_item_id={req.inventory_item_id}): {e}"
            )
            raise HTTPException(status_code=500, detail="Ошибка при списании предмета")

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"eat-food error for character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при употреблении еды")

    return {
        "success": True,
        "message": f"Вы поели: {payload['source_item_name']}. Сытость на {SATIETY_DURATION_LABEL}",
        "satiety": satiety,
    }


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
                slot_type=row.slot_type,
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
    _internal=Depends(verify_internal_token),
):
    """
    Обновить прочность экипировки после боя (internal, service-to-service).
    Если прочность падает до 0 — снять модификаторы через apply_modifiers.
    Требует заголовок `X-Internal-Token` (FEAT-169).
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
                    slot_type=slot.slot_type,
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
    result = crud.execute_buyout(db, listing_id=listing_id, data=req, user_id=current_user.id)

    # Track cumulative stats for buyer
    amount = result.get("amount", 0) if isinstance(result, dict) else 0
    if amount > 0:
        _track_cumulative_stats(req.character_id, {
            "total_gold_spent": amount,
            "items_bought": 1,
        })

    return result


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
    result = crud.claim_from_storage(db, data=req, user_id=current_user.id)

    # Track cumulative stats for seller (gold earned from auction sale)
    claimed_gold = result.get("claimed_gold", 0) if isinstance(result, dict) else 0
    if claimed_gold > 0:
        _track_cumulative_stats(req.character_id, {"total_gold_earned": claimed_gold})

    return result


# -----------------------------------------------------------------------------
# NPC Equipment (admin-only)
# -----------------------------------------------------------------------------
@router.post("/admin/npc/{character_id}/equip", response_model=schemas.EquipmentSlot)
async def admin_npc_equip(
    character_id: int,
    req: schemas.AdminNpcEquipRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("npcs:update")),
):
    """
    Экипировка предмета из каталога на NPC (admin).
    Создаёт слоты экипировки при первом вызове.
    """
    try:
        slot, old_mods, new_mods = crud.admin_equip_npc_item(
            db, character_id, req.slot_type, req.item_id,
        )

        # Применяем модификаторы через character-attributes-service
        if old_mods:
            await apply_modifiers_in_attributes_service(character_id, old_mods)
        if new_mods:
            await apply_modifiers_in_attributes_service(character_id, new_mods)

        db.commit()
        db.refresh(slot)
        return slot

    except HTTPException:
        db.rollback()
        raise
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка обращения к сервису атрибутов: {e}",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {e}")


@router.delete("/admin/npc/{character_id}/unequip/{slot_type}", response_model=schemas.EquipmentSlot)
async def admin_npc_unequip(
    character_id: int,
    slot_type: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("npcs:update")),
):
    """
    Снятие предмета со слота NPC (admin).
    """
    try:
        slot, minus_mods = crud.admin_unequip_npc_item(
            db, character_id, slot_type,
        )

        if minus_mods:
            await apply_modifiers_in_attributes_service(character_id, minus_mods)

        db.commit()
        db.refresh(slot)
        return slot

    except HTTPException:
        db.rollback()
        raise
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка обращения к сервису атрибутов: {e}",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {e}")


app.include_router(router)
