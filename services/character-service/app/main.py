import os
import httpx
from fastapi import FastAPI, Depends, APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session
import asyncio
import models, schemas, crud
from database import SessionLocal, engine
from config import settings
from producer import (
    send_character_approved_notification,
    publish_character_inventory,
    publish_character_skills,
    publish_character_attributes,
    send_title_unlocked_notification,
)
from typing import List, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware
from auth_http import get_admin_user, get_current_user_via_http, require_permission, OAUTH2_SCHEME
from sqlalchemy import text
import logging

# Universal subrace skill applied to all subraces (1-16)
SUBRACE_SKILL_ID = 7  # "Выживание"

MAX_CHARACTERS_PER_USER = 5

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("character-service")

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
router = APIRouter(prefix="/characters")
# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_character_ownership(db: Session, character_id: int, user_id: int):
    """Check that the character belongs to the given user."""
    result = db.execute(text("SELECT user_id FROM characters WHERE id = :cid"), {"cid": character_id}).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    if result[0] != user_id:
        raise HTTPException(status_code=403, detail="Вы можете управлять только своими персонажами")


# Создание заявки на персонажа
@router.post("/requests/", response_model=schemas.CharacterRequest)
async def create_character_request(request: schemas.CharacterRequestCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user_via_http)):
    """
    Создание заявки на персонажа.
    """
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете создавать заявки только для себя")
    try:
        user_id = request.user_id
        db_request = crud.create_character_request(db, request, user_id)
        return db_request
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при создании заявки: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании заявки на персонажа.")


# Создание заявки на присвоение существующего персонажа
@router.post("/requests/claim", response_model=schemas.ClaimRequestResponse)
def create_claim_request(
    data: schemas.ClaimRequestCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Создаёт заявку на присвоение существующего свободного персонажа.
    """
    # 1. Check character exists
    character = db.query(models.Character).filter(models.Character.id == data.character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    # 2. Not NPC
    if character.is_npc:
        raise HTTPException(status_code=400, detail="Нельзя подать заявку на NPC")

    # 3. No owner
    if character.user_id is not None:
        raise HTTPException(status_code=400, detail="Персонаж уже принадлежит другому пользователю")

    # 4. User under character limit
    try:
        char_count = db.execute(
            text("SELECT COUNT(*) FROM users_character WHERE user_id = :uid"),
            {"uid": current_user.id}
        ).scalar() or 0
        if char_count >= MAX_CHARACTERS_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"Достигнут лимит персонажей (максимум {MAX_CHARACTERS_PER_USER})"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Could not check character limit: {e}")

    # 5. No duplicate pending claim
    existing_claim = db.query(models.CharacterRequest).filter(
        models.CharacterRequest.user_id == current_user.id,
        models.CharacterRequest.character_id == data.character_id,
        models.CharacterRequest.request_type == 'claim',
        models.CharacterRequest.status == 'pending',
    ).first()
    if existing_claim:
        raise HTTPException(status_code=409, detail="Вы уже подали заявку на этого персонажа")

    # 6. Create claim request with bio fields copied from character
    db_request = models.CharacterRequest(
        user_id=current_user.id,
        character_id=data.character_id,
        request_type='claim',
        name=character.name,
        id_subrace=character.id_subrace,
        id_race=character.id_race,
        id_class=character.id_class,
        biography=character.biography,
        personality=character.personality,
        appearance=character.appearance,
        background=character.background,
        sex=character.sex,
        age=character.age,
        weight=character.weight,
        height=character.height,
        avatar=character.avatar,
    )
    try:
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при создании заявки на присвоение: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании заявки на присвоение персонажа")

    return db_request


# Получение количества персонажей текущего пользователя
@router.get("/my-character-count", response_model=schemas.CharacterCountResponse)
def get_my_character_count(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Возвращает количество персонажей текущего пользователя и лимит.
    """
    try:
        count = db.execute(
            text("SELECT COUNT(*) FROM users_character WHERE user_id = :uid"),
            {"uid": current_user.id}
        ).scalar() or 0
    except Exception as e:
        logger.warning(f"Could not get character count: {e}")
        count = 0

    return {"count": count, "limit": MAX_CHARACTERS_PER_USER}


# Эндпоинт для одобрения заявки
@router.post("/requests/{request_id}/approve")
async def approve_character_request(request_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("characters:approve")), token: str = Depends(OAUTH2_SCHEME)):
    """
    Одобряет заявку на создание персонажа:
    1) Проверяем, что заявка существует и имеет статус 'pending'.
    2) Читаем стартовый набор из БД (таблица starter_kits) по class_id.
    3) Создаем запись персонажа в БД с currency_balance из стартового набора.
    4) Генерируем атрибуты (через SUBRACE_ATTRIBUTES).
    5) Отправляем стартовые предметы в inventory-service (graceful).
    6) Формируем список навыков: класс + подрасовый (SUBRACE_SKILL_ID=7), вызываем skills-service (graceful).
    7) Создаем атрибуты через attributes-service.
    8) Обновляем персонажа (id_attributes).
    9) Меняем статус заявки на "approved".
    10) Привязываем персонажа к пользователю (через user-service).
    11) Отправляем SSE-уведомление через RabbitMQ.
    """
    try:
        logger.info(f"Начало обработки заявки с ID {request_id}")

        # 1) Проверка существования заявки + double-approve guard
        db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
        if not db_request:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        if db_request.status != "pending":
            raise HTTPException(status_code=400, detail="Заявка уже обработана")

        logger.info(f"Заявка с ID {request_id} найдена, статус: {db_request.status}")

        # 1.5) Проверка лимита персонажей (максимум 5 на аккаунт)
        try:
            char_count = db.execute(
                text("SELECT COUNT(*) FROM users_character WHERE user_id = :uid"),
                {"uid": db_request.user_id}
            ).scalar() or 0
            if char_count >= MAX_CHARACTERS_PER_USER:
                raise HTTPException(
                    status_code=400,
                    detail=f"Достигнут лимит персонажей (максимум {MAX_CHARACTERS_PER_USER})"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Could not check character limit: {e}")

        # --- CLAIM approval branch ---
        if getattr(db_request, 'request_type', 'creation') == 'claim':
            character_id = db_request.character_id
            if not character_id:
                raise HTTPException(status_code=400, detail="Заявка на присвоение не содержит ID персонажа")

            character = db.query(models.Character).filter(models.Character.id == character_id).first()
            if not character:
                raise HTTPException(status_code=404, detail="Персонаж не найден")
            if character.user_id is not None:
                raise HTTPException(status_code=400, detail="Персонаж уже принадлежит другому пользователю")

            # Set owner on the existing character
            character.user_id = db_request.user_id
            db.flush()

            # Mark request as approved
            crud.update_character_request_status(db, request_id, "approved", auto_commit=False)

            # Assign character to user in user-service
            assign_result = await crud.assign_character_to_user(db_request.user_id, character_id, token=token)
            if not assign_result:
                db.rollback()
                raise HTTPException(status_code=500, detail="Не удалось присвоить персонажа пользователю")

            db.commit()
            logger.info(f"Заявка на присвоение #{request_id} одобрена: персонаж {character_id} присвоен пользователю {db_request.user_id}")

            # Send notification (non-blocking)
            try:
                await send_character_approved_notification(db_request.user_id, character.name)
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление: {e}")

            return {"message": f"Персонаж с ID {character_id} успешно присвоен пользователю."}

        # 2) Читаем стартовый набор из БД
        class_id = db_request.id_class
        starter_kit = db.query(models.StarterKit).filter(models.StarterKit.class_id == class_id).first()

        if starter_kit:
            kit_items = starter_kit.items or []
            kit_skills = starter_kit.skills or []
            currency_amount = starter_kit.currency_amount or 0
            logger.info(f"Стартовый набор для класса {class_id}: {len(kit_items)} предметов, {len(kit_skills)} навыков, {currency_amount} валюты")
        else:
            kit_items = []
            kit_skills = []
            currency_amount = 0
            logger.warning(f"Стартовый набор для класса {class_id} не найден, персонаж создаётся без предметов/навыков")

        # 3) Создаем предварительную запись персонажа с currency_balance (flush, не commit)
        new_character = crud.create_preliminary_character(db, db_request, currency_balance=currency_amount, auto_commit=False)
        logger.info(f"Создан персонаж с ID {new_character.id}, currency_balance={currency_amount}")

        # Log starter kit gold transaction
        if currency_amount > 0:
            crud.log_gold_transaction(
                db, new_character.id,
                amount=currency_amount,
                balance_after=currency_amount,
                transaction_type="starter_kit",
                source="character_creation",
                metadata={"class_id": class_id},
            )

        # 4) Генерируем атрибуты по подрасе (из БД)
        attributes = crud.generate_attributes_for_subrace(db, db_request.id_subrace)
        logger.info(f"Сгенерированы атрибуты для подрасы {db_request.id_subrace}")

        # 5) Отправка запроса на создание инвентаря (graceful — не блокирует одобрение)
        if kit_items:
            # Transform starter kit format to inventory-service format
            items_to_add = [{"item_id": item["item_id"], "quantity": item.get("quantity", 1)} for item in kit_items]
            try:
                inventory_response = await crud.send_inventory_request(new_character.id, items_to_add)
                if inventory_response:
                    logger.info(f"Инвентарь создан для персонажа {new_character.id}")
                else:
                    logger.warning(f"Не удалось создать инвентарь для персонажа {new_character.id}, продолжаем без предметов")
            except Exception as e:
                logger.warning(f"Ошибка при создании инвентаря для персонажа {new_character.id}: {e}")
        else:
            logger.info("Нет стартовых предметов для добавления")

        # 6) Назначение навыков (graceful — не блокирует одобрение)
        # Extract skill IDs from starter kit skills JSON
        skill_ids_for_character = [skill["skill_id"] for skill in kit_skills]
        # Add universal subrace skill
        skill_ids_for_character.append(SUBRACE_SKILL_ID)

        if skill_ids_for_character:
            try:
                skills_response = await crud.send_skills_presets_request(
                    character_id=new_character.id,
                    skill_ids=skill_ids_for_character
                )
                if skills_response:
                    logger.info(f"Навыки назначены для персонажа {new_character.id}")
                else:
                    logger.warning(f"Не удалось назначить навыки для персонажа {new_character.id}, продолжаем без навыков")
            except Exception as e:
                logger.warning(f"Ошибка при назначении навыков для персонажа {new_character.id}: {e}")

        # 7) Создаем атрибуты через attributes-service
        attributes_response = await crud.send_attributes_request(new_character.id, attributes)
        if attributes_response:
            logger.info(f"Атрибуты созданы для персонажа {new_character.id}")
        else:
            logger.error("Ошибка при создании атрибутов")
            db.rollback()
            raise HTTPException(status_code=500, detail="Не удалось создать атрибуты")

        # 8) Обновляем персонажа с зависимостями (flush, не commit)
        updated_character = crud.update_character_with_dependencies(
            db, new_character.id,
            skills_id=None,
            attributes_id=attributes_response['id'],
            auto_commit=False
        )
        logger.info(f"Персонаж с ID {new_character.id} обновлен с id_attributes={attributes_response['id']}")

        # 9) Ставим заявке статус "approved" (flush, не commit)
        crud.update_character_request_status(db, request_id, "approved", auto_commit=False)
        logger.info(f"Заявка с ID {request_id} одобрена")

        # 10) Привязываем персонажа к пользователю
        assign_result = await crud.assign_character_to_user(db_request.user_id, updated_character.id, token=token)
        if assign_result:
            logger.info(f"Персонаж с ID {updated_character.id} успешно присвоен пользователю {db_request.user_id}")
        else:
            logger.error("Не удалось присвоить персонажа пользователю")
            db.rollback()
            raise HTTPException(status_code=500, detail="Не удалось присвоить персонажа пользователю")

        # Единый commit для шагов 3, 8, 9 — после успешного выполнения всех критических шагов
        db.commit()
        logger.info("Все изменения в БД зафиксированы единым коммитом")

        # 11) Отправляем уведомление через RabbitMQ (non-blocking, async)
        try:
            await send_character_approved_notification(db_request.user_id, new_character.name)
            logger.info(f"Уведомление отправлено пользователю {db_request.user_id}")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление: {e}")

        # 12) Публикуем в RabbitMQ очереди для параллельной обработки (alongside HTTP calls)
        # Inventory queue
        if kit_items:
            try:
                items_to_publish = [{"item_id": item["item_id"], "quantity": item.get("quantity", 1)} for item in kit_items]
                await publish_character_inventory(new_character.id, items_to_publish)
            except Exception as e:
                logger.warning(f"Не удалось опубликовать инвентарь в RabbitMQ: {e}")

        # Skills queue
        if skill_ids_for_character:
            try:
                await publish_character_skills(new_character.id, skill_ids_for_character)
            except Exception as e:
                logger.warning(f"Не удалось опубликовать навыки в RabbitMQ: {e}")

        # Attributes queue
        try:
            await publish_character_attributes(new_character.id, attributes)
        except Exception as e:
            logger.warning(f"Не удалось опубликовать атрибуты в RabbitMQ: {e}")

        logger.info(f"Завершение обработки заявки с ID {request_id}")
        return {"message": f"Персонаж с ID {new_character.id} успешно создан и присвоен пользователю."}

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при одобрении заявки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
    except Exception as e:
        db.rollback()
        logger.error(f"Непредвиденная ошибка при одобрении заявки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# ============================================================
# Admin endpoints — must be placed BEFORE /{character_id} routes
# ============================================================

@router.get("/admin/list", response_model=schemas.AdminCharacterListResponse)
def admin_list_characters(
    q: str = Query("", description="Search by character name"),
    user_id: Optional[int] = Query(None),
    level_min: Optional[int] = Query(None),
    level_max: Optional[int] = Query(None),
    id_race: Optional[int] = Query(None),
    id_class: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("characters:read")),
):
    """
    Paginated list of all characters with search and filters. Admin only.
    """
    try:
        query = db.query(models.Character)

        if q:
            query = query.filter(models.Character.name.ilike(f"%{q}%"))
        if user_id is not None:
            query = query.filter(models.Character.user_id == user_id)
        if level_min is not None:
            query = query.filter(models.Character.level >= level_min)
        if level_max is not None:
            query = query.filter(models.Character.level <= level_max)
        if id_race is not None:
            query = query.filter(models.Character.id_race == id_race)
        if id_class is not None:
            query = query.filter(models.Character.id_class == id_class)

        total = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(models.Character.id).offset(offset).limit(page_size).all()

        return schemas.AdminCharacterListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError as e:
        logger.error(f"Error fetching admin character list: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.put("/admin/{character_id}")
async def admin_update_character(
    character_id: int,
    data: schemas.AdminCharacterUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("characters:update")),
    token: str = Depends(OAUTH2_SCHEME),
):
    """
    Admin update of character fields (level, stat_points, currency_balance).
    When level is changed, syncs passive_experience in attributes-service
    so that XP is never below the minimum threshold for the new level.
    """
    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    # Validation
    if "level" in update_data and update_data["level"] < 1:
        raise HTTPException(status_code=400, detail="Уровень должен быть >= 1")
    if "stat_points" in update_data and update_data["stat_points"] < 0:
        raise HTTPException(status_code=400, detail="Очки характеристик должны быть >= 0")
    if "currency_balance" in update_data and update_data["currency_balance"] < 0:
        raise HTTPException(status_code=400, detail="Баланс валюты должен быть >= 0")

    old_level = character.level
    old_stat_points = character.stat_points
    old_currency_balance = character.currency_balance

    for field, value in update_data.items():
        setattr(character, field, value)

    # Auto-grant stat_points when admin increases level without explicitly changing stat_points.
    # The frontend always sends stat_points in the payload, so we compare against the old DB value
    # instead of checking key presence: if the sent stat_points equals the old value, the admin
    # didn't intentionally change it, and we should auto-grant level_diff * 10.
    if "level" in update_data:
        level_diff = update_data["level"] - old_level
        stat_points_changed_by_admin = (
            "stat_points" in update_data and update_data["stat_points"] != old_stat_points
        )
        if level_diff > 0 and not stat_points_changed_by_admin:
            character.stat_points = old_stat_points + level_diff * 10

    try:
        db.commit()
        db.refresh(character)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

    # Log admin changes to character log
    try:
        if "level" in update_data and character.level != old_level:
            crud.create_character_log(db, character_id, "admin_level_change",
                f"Уровень изменён администратором: {old_level} → {character.level}",
                {"old_level": old_level, "new_level": character.level, "admin_action": True})
        if "stat_points" in update_data and character.stat_points != old_stat_points:
            crud.create_character_log(db, character_id, "admin_stat_change",
                f"Очки характеристик изменены администратором: {old_stat_points} → {character.stat_points}",
                {"old_value": old_stat_points, "new_value": character.stat_points, "field": "stat_points", "admin_action": True})
        if "currency_balance" in update_data and character.currency_balance != old_currency_balance:
            crud.create_character_log(db, character_id, "admin_currency_change",
                f"Баланс изменён администратором: {old_currency_balance} → {character.currency_balance}",
                {"old_value": old_currency_balance, "new_value": character.currency_balance, "admin_action": True})
            crud.log_gold_transaction(
                db, character_id,
                amount=character.currency_balance - old_currency_balance,
                balance_after=character.currency_balance,
                transaction_type="admin_adjust",
                source="admin_panel",
                metadata={"old_balance": old_currency_balance, "admin_action": True},
            )
    except Exception as e:
        logger.warning(f"Failed to log admin changes for character {character_id}: {e}")

    # Sync passive_experience when level is changed
    if "level" in update_data:
        new_level = update_data["level"]
        threshold = db.query(models.LevelThreshold).filter(
            models.LevelThreshold.level_number == new_level
        ).first()
        required_experience = threshold.required_experience if threshold else 0

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch current passive_experience
                resp = await client.get(
                    f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/passive_experience",
                    headers=headers,
                )
                if resp.status_code == 200:
                    passive_experience = resp.json().get("passive_experience", 0)
                    # Only update if current XP is below the threshold for the new level
                    if passive_experience < required_experience:
                        put_resp = await client.put(
                            f"{settings.ATTRIBUTES_SERVICE_URL}admin/{character_id}",
                            json={"passive_experience": required_experience},
                            headers=headers,
                        )
                        if put_resp.status_code == 200:
                            logger.info(
                                f"Synced passive_experience for character {character_id} "
                                f"to {required_experience} (level {new_level})"
                            )
                        else:
                            logger.warning(
                                f"Failed to update passive_experience for character {character_id}: "
                                f"{put_resp.status_code} - {put_resp.text}"
                            )
                else:
                    logger.warning(
                        f"Failed to fetch passive_experience for character {character_id}: "
                        f"{resp.status_code} - {resp.text}"
                    )
        except Exception as e:
            logger.warning(f"Error syncing XP for character {character_id} after level change: {e}")

        # Trigger title evaluation after admin level change (non-fatal)
        try:
            newly_unlocked = crud.evaluate_titles(db, character_id)
            if newly_unlocked and character.user_id:
                for title_info in newly_unlocked:
                    try:
                        await send_title_unlocked_notification(
                            character.user_id, title_info["name"]
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось отправить уведомление о титуле: {e}")
        except Exception as e:
            logger.warning(f"Ошибка при оценке титулов после изменения уровня для персонажа {character_id}: {e}")

    return {"detail": "Character updated", "character_id": character.id}


@router.post("/admin/{character_id}/unlink")
async def admin_unlink_character(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("characters:update")),
    token: str = Depends(OAUTH2_SCHEME),
):
    """
    Unlink a character from its owning user.
    """
    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    if character.user_id is None:
        raise HTTPException(status_code=400, detail="Персонаж не привязан к пользователю")

    previous_user_id = character.user_id
    headers = {"Authorization": f"Bearer {token}"}

    # Call user-service to delete the user-character relation
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.USER_SERVICE_URL}/users/user_characters/{previous_user_id}/{character_id}",
                headers=headers,
            )
            if resp.status_code not in (200, 404):
                logger.error(f"Failed to delete user-character relation: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=502, detail="Ошибка при удалении связи пользователь-персонаж")
    except httpx.RequestError as e:
        logger.error(f"Error calling user-service to delete relation: {e}")
        raise HTTPException(status_code=502, detail="Сервис пользователей недоступен")

    # Call user-service to clear current_character
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.USER_SERVICE_URL}/users/{previous_user_id}/clear_current_character",
                json={"character_id": character_id},
                headers=headers,
            )
            if resp.status_code not in (200, 404):
                logger.warning(f"Failed to clear current_character: {resp.status_code} - {resp.text}")
    except httpx.RequestError as e:
        logger.warning(f"Error calling user-service to clear current_character: {e}")

    # Set user_id to None locally
    character.user_id = None
    try:
        db.commit()
        db.refresh(character)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error unlinking character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

    return {
        "detail": "Character unlinked from user",
        "character_id": character_id,
        "previous_user_id": previous_user_id,
    }


class InternalUnlinkRequest(schemas.BaseModel):
    character_id: int


@router.post("/internal/unlink")
async def internal_unlink_character(
    body: InternalUnlinkRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) to unlink a character from its user.
    Used by battle-service after a death duel to "kill" the loser's character.
    Should be blocked by Nginx for external access.
    """
    character = db.query(models.Character).filter(
        models.Character.id == body.character_id
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    if character.user_id is None:
        # Already unlinked — idempotent success
        return {"detail": "Character already unlinked", "character_id": body.character_id}

    previous_user_id = character.user_id

    # Clear user-character relation in shared DB directly (no auth needed)
    try:
        db.execute(
            text(
                "DELETE FROM user_characters WHERE user_id = :uid AND character_id = :cid"
            ),
            {"uid": previous_user_id, "cid": body.character_id},
        )
    except Exception as e:
        logger.warning(f"Failed to delete user_characters relation: {e}")

    # Clear current_character_id in users table if it matches
    try:
        db.execute(
            text(
                "UPDATE users SET current_character_id = NULL "
                "WHERE id = :uid AND current_character_id = :cid"
            ),
            {"uid": previous_user_id, "cid": body.character_id},
        )
    except Exception as e:
        logger.warning(f"Failed to clear current_character_id: {e}")

    # Set user_id to None on the character
    character.user_id = None
    try:
        db.commit()
        db.refresh(character)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error unlinking character {body.character_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

    logger.info(
        f"Internal unlink: character {body.character_id} unlinked from user {previous_user_id}"
    )
    return {
        "detail": "Character unlinked from user",
        "character_id": body.character_id,
        "previous_user_id": previous_user_id,
    }


# ============================================================
# Admin Title endpoints — BEFORE /{character_id} routes (FEAT-080)
# ============================================================

@router.get("/admin/titles", response_model=schemas.TitleAdminListResponse)
def admin_list_titles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    rarity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("titles:read")),
):
    """Paginated list of all titles. Admin only."""
    try:
        items, total = crud.get_all_titles_admin(db, page, per_page, search, rarity)
        return schemas.TitleAdminListResponse(
            items=items, total=total, page=page, per_page=per_page
        )
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении списка титулов: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/admin/titles", response_model=schemas.TitleAdminResponse, status_code=201)
def admin_create_title(
    data: schemas.TitleCreateFull,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("titles:create")),
):
    """Create a new title with full fields. Admin only."""
    try:
        title = crud.create_title_full(db, data)
        return schemas.TitleAdminResponse(
            id_title=title.id_title,
            name=title.name,
            description=title.description,
            rarity=title.rarity,
            conditions=title.conditions,
            icon=title.icon,
            sort_order=title.sort_order,
            is_active=title.is_active,
            reward_passive_exp=title.reward_passive_exp,
            reward_active_exp=title.reward_active_exp,
            created_at=title.created_at,
            updated_at=title.updated_at,
            holders_count=0,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Титул с таким именем уже существует")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при создании титула: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.put("/admin/titles/{title_id}", response_model=schemas.TitleAdminResponse)
def admin_update_title(
    title_id: int,
    data: schemas.TitleUpdateFull,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("titles:update")),
):
    """Update an existing title. Admin only."""
    try:
        title = crud.update_title_full(db, title_id, data)
        if not title:
            raise HTTPException(status_code=404, detail="Титул не найден")
        holders_count = db.query(models.CharacterTitle).filter(
            models.CharacterTitle.title_id == title_id
        ).count()
        return schemas.TitleAdminResponse(
            id_title=title.id_title,
            name=title.name,
            description=title.description,
            rarity=title.rarity,
            conditions=title.conditions,
            icon=title.icon,
            sort_order=title.sort_order,
            is_active=title.is_active,
            reward_passive_exp=title.reward_passive_exp,
            reward_active_exp=title.reward_active_exp,
            created_at=title.created_at,
            updated_at=title.updated_at,
            holders_count=holders_count,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Титул с таким именем уже существует")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении титула: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.delete("/admin/titles/{title_id}")
def admin_delete_title(
    title_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("titles:delete")),
):
    """Delete a title. Admin only."""
    try:
        result = crud.delete_title_full(db, title_id)
        if not result:
            raise HTTPException(status_code=404, detail="Титул не найден")
        return {"detail": "Титул удалён"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при удалении титула: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/admin/titles/grant")
def admin_grant_title(
    data: schemas.TitleGrantRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("titles:grant")),
):
    """Grant a title to a character. Admin only."""
    try:
        result, status = crud.grant_title(db, data.character_id, data.title_id)
        if status == "title_not_found":
            raise HTTPException(status_code=404, detail="Титул не найден")
        if status == "character_not_found":
            raise HTTPException(status_code=404, detail="Персонаж не найден")
        if status == "already_has":
            return {"detail": "Персонаж уже имеет этот титул"}
        return {"detail": "Титул выдан персонажу"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при выдаче титула: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.delete("/admin/titles/grant/{character_id}/{title_id}")
def admin_revoke_title(
    character_id: int,
    title_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("titles:grant")),
):
    """Revoke a title from a character. Admin only."""
    try:
        result = crud.revoke_title(db, character_id, title_id)
        if not result:
            raise HTTPException(status_code=404, detail="Титул не найден у персонажа")
        return {"detail": "Титул отозван у персонажа"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при отзыве титула: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# Internal endpoint for title evaluation (FEAT-080)

class InternalEvaluateTitlesRequest(schemas.BaseModel):
    character_id: int


@router.post("/internal/evaluate-titles")
async def internal_evaluate_titles(
    body: InternalEvaluateTitlesRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth). Evaluate and auto-grant titles for a character.
    Called by character-attributes-service after cumulative stats increment.
    """
    try:
        newly_unlocked = crud.evaluate_titles(db, body.character_id)

        # Send notification for each newly unlocked title
        for title_info in newly_unlocked:
            # Get user_id for the character
            character = db.query(models.Character).filter(
                models.Character.id == body.character_id
            ).first()
            if character and character.user_id:
                try:
                    await send_title_unlocked_notification(
                        character.user_id, title_info["name"]
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление о титуле: {e}")

        return {"newly_unlocked_titles": newly_unlocked}
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при оценке титулов для персонажа {body.character_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# Эндпоинт для удаления персонажа (enhanced with cascade cleanup)
@router.delete("/{character_id}")
async def delete_character(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("characters:delete")),
    token: str = Depends(OAUTH2_SCHEME),
):
    """
    Удаление персонажа по его ID с каскадной очисткой зависимых сервисов.
    """
    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    headers = {"Authorization": f"Bearer {token}"}
    user_id = character.user_id

    # 1. Delete all inventory (graceful)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.INVENTORY_SERVICE_URL}{character_id}/all",
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info(f"Inventory cleared for character {character_id}")
            else:
                logger.warning(f"Failed to clear inventory for character {character_id}: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"Error clearing inventory for character {character_id}: {e}")

    # 2. Delete all character skills (graceful)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.SKILLS_SERVICE_URL}admin/character_skills/by_character/{character_id}",
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info(f"Skills cleared for character {character_id}")
            else:
                logger.warning(f"Failed to clear skills for character {character_id}: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"Error clearing skills for character {character_id}: {e}")

    # 3. Delete character attributes (graceful)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}",
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info(f"Attributes cleared for character {character_id}")
            else:
                logger.warning(f"Failed to clear attributes for character {character_id}: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"Error clearing attributes for character {character_id}: {e}")

    # 4. If user_id exists, clean up user-character relation (graceful)
    if user_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"{settings.USER_SERVICE_URL}/users/user_characters/{user_id}/{character_id}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    logger.info(f"User-character relation deleted for user {user_id}, character {character_id}")
                else:
                    logger.warning(f"Failed to delete user-character relation: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.warning(f"Error deleting user-character relation: {e}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.USER_SERVICE_URL}/users/{user_id}/clear_current_character",
                    json={"character_id": character_id},
                    headers=headers,
                )
                if resp.status_code == 200:
                    logger.info(f"Current character cleared for user {user_id}")
                else:
                    logger.warning(f"Failed to clear current_character for user {user_id}: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.warning(f"Error clearing current_character for user {user_id}: {e}")

    # 5. Delete the character row
    try:
        db.delete(character)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting character {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

    return {"message": f"Персонаж с ID {character_id} успешно удален."}

# Отправка запроса на обновление пользователя в user-service
async def update_user_with_character(user_id: int, character_id: int):
    try:
        # Отправляем запрос в микросервис пользователей для добавления записи в таблицу user_characters
        async with httpx.AsyncClient() as client:
            logger.info(f"Отправляем запрос на создание связи между пользователем {user_id} и персонажем {character_id}")
            create_relation_response = await client.post(
                f"{settings.USER_SERVICE_URL}/users/user_characters/",
                json={"user_id": user_id, "character_id": character_id}
            )

            if create_relation_response.status_code not in [200, 201]:
                logger.error(f"Ошибка при создании записи в user_characters: {create_relation_response.status_code}")
                return False

            logger.info(f"Запись в user_characters успешно создана для пользователя {user_id} и персонажа {character_id}")

            # Второй запрос: обновляем поле current_character у пользователя
            logger.info(f"Отправляем запрос на обновление current_character для пользователя {user_id} с персонажем {character_id}")
            update_user_response = await client.put(
                f"{settings.USER_SERVICE_URL}/users/{user_id}/update_character",
                json={"current_character": character_id}
            )

            if update_user_response.status_code == 200:
                logger.info(f"Пользователь с ID {user_id} успешно обновлен с персонажем ID {character_id}")
                return True
            else:
                logger.error(f"Ошибка при обновлении пользователя: {update_user_response.status_code}")
                logger.error(f"Ответ от сервера: {update_user_response.text}")
                return False

    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запросов на обновление пользователя: {e}")
        return False


@router.post("/requests/{request_id}/reject")
async def reject_character_request(request_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("characters:approve"))):
    """
    Отклоняет заявку на создание персонажа и обновляет статус на 'rejected'.
    """
    try:
        db_request = crud.update_character_request_status(db, request_id, "rejected")
        if not db_request:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        return {"message": f"Заявка с ID {request_id} была отклонена."}

    except SQLAlchemyError as e:
        logger.error(f"Ошибка при отклонении заявки: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при отклонении заявки")

#Возвращает список всех рас, их подрас и атрибуты для каждой подрасы.
@router.get("/metadata", response_model=List[dict])
async def get_races_and_subraces(db: Session = Depends(get_db)):
    try:
        races_data = crud.get_all_races_and_subraces(db)
        # stat_preset и image уже включены из БД через crud.get_all_races_and_subraces
        # Добавляем обратную совместимость: "attributes" = stat_preset
        for race_id, race_info in races_data.items():
            for subrace in race_info["subraces"]:
                subrace["attributes"] = subrace.get("stat_preset") or {}
        # Преобразуем словарь в список
        return list(races_data.values())
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении рас и подрас: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении рас и подрас.")



@router.get("/moderation-requests", response_model=Dict)
async def get_moderation_requests(db: Session = Depends(get_db), current_user = Depends(require_permission("characters:approve"))):
    """
    Эндпоинт для получения всех заявок на модерации
    """
    try:
        requests = crud.get_moderation_requests(db)  # Вызов функции из CRUD для получения заявок

        if not requests:
            return {}

        return requests
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении заявок на модерацию: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении заявок на модерацию.")


@router.get("/starter-kits", response_model=List[schemas.StarterKitResponse])
async def get_starter_kits(db: Session = Depends(get_db)):
    """
    Возвращает все стартовые наборы (по одному на каждый класс).
    """
    try:
        kits = crud.get_all_starter_kits(db)
        return kits
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении стартовых наборов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении стартовых наборов.")


@router.put("/starter-kits/{class_id}", response_model=schemas.StarterKitResponse)
async def upsert_starter_kit(class_id: int, data: schemas.StarterKitUpdate, db: Session = Depends(get_db), current_user = Depends(require_permission("characters:update"))):
    """
    Создаёт или обновляет стартовый набор для указанного класса.
    """
    try:
        # Validate that the class exists
        db_class = db.query(models.Class).filter(models.Class.id_class == class_id).first()
        if not db_class:
            raise HTTPException(status_code=404, detail=f"Класс с ID {class_id} не найден")

        kit = crud.upsert_starter_kit(db, class_id, data)
        return kit
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при обновлении стартового набора для класса {class_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении стартового набора.")


@router.post("/titles/", response_model=schemas.Title)
async def create_title(request: schemas.TitleCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("characters:create"))):
    """
    Создание нового титула.
    """
    try:
        title = crud.create_title(db, request.name, request.description)
        return title
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при создании титула: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании титула.")

@router.post("/{character_id}/titles/{title_id}")
async def assign_title(character_id: int, title_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("characters:update"))):
    """
    Присваивает титул персонажу.
    """
    try:
        assignment = crud.assign_title_to_character(db, character_id, title_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Персонаж или титул не найден")
        return {"message": f"Титул с ID {title_id} успешно присвоен персонажу с ID {character_id}."}
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при присвоении титула: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при присвоении титула персонажу.")


@router.post("/{character_id}/current-title/{title_id}")
async def set_current_title(character_id: int, title_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user_via_http)):
    """
    Устанавливает текущий титул для персонажа (косметический выбор).
    """
    verify_character_ownership(db, character_id, current_user.id)
    try:
        character, status = crud.set_current_title_cosmetic(db, character_id, title_id)
        if status == "character_not_found":
            raise HTTPException(status_code=404, detail="Персонаж не найден")
        if status == "title_not_owned":
            raise HTTPException(status_code=400, detail="У персонажа нет этого титула")
        if status == "title_not_found":
            raise HTTPException(status_code=404, detail="Титул не найден")
        return {"message": "Титул установлен как текущий"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при установке текущего титула: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при установке титула.")


@router.delete("/{character_id}/current-title")
async def unset_current_title_endpoint(character_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user_via_http)):
    """
    Снимает активный титул с персонажа.
    """
    verify_character_ownership(db, character_id, current_user.id)
    try:
        character = crud.unset_current_title(db, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="Персонаж не найден")
        return {"message": "Активный титул снят"}
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при снятии титула: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при снятии титула.")


@router.get("/titles/", response_model=List[schemas.Title])
async def get_titles(db: Session = Depends(get_db)):
    """
    Получить список всех титулов.
    """
    try:
        titles = crud.get_all_titles(db)
        return titles
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении титулов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении титулов.")

@router.get("/{character_id}/titles", response_model=List[schemas.CharacterTitleResponse])
async def get_titles_for_character(character_id: int, db: Session = Depends(get_db)):
    """
    Получить все титулы для конкретного персонажа с информацией о прогрессе.
    Перед возвратом данных выполняет evaluate_titles для автоматической выдачи заслуженных титулов.
    """
    try:
        # Evaluate titles first (safety net) to auto-grant any newly earned titles
        try:
            newly_unlocked = crud.evaluate_titles(db, character_id)
            # Send notifications for newly unlocked titles
            if newly_unlocked:
                character = db.query(models.Character).filter(
                    models.Character.id == character_id
                ).first()
                if character and character.user_id:
                    for title_info in newly_unlocked:
                        try:
                            await send_title_unlocked_notification(
                                character.user_id, title_info["name"]
                            )
                        except Exception as e:
                            logger.warning(f"Не удалось отправить уведомление о титуле: {e}")
        except Exception as e:
            logger.warning(f"Ошибка при оценке титулов для персонажа {character_id}: {e}")

        titles = crud.get_character_titles_with_progress(db, character_id)
        return titles
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении титулов для персонажа {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении титулов для персонажа.")

@router.put("/{character_id}/deduct_points")
def deduct_points(character_id: int, data: dict, db: Session = Depends(get_db)):
    """
    Списание stat_points у персонажа.
    """
    points_to_deduct = data.get("points_to_deduct", 0)
    logger.info(f"Получен запрос на списание {points_to_deduct} stat_points для персонажа ID {character_id}")

    if not isinstance(points_to_deduct, int) or points_to_deduct <= 0:
        logger.warning(f"Неверное количество stat_points для списания: {points_to_deduct}")
        raise HTTPException(status_code=400, detail="Invalid points to deduct")

    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        logger.error(f"Персонаж ID {character_id} не найден.")
        raise HTTPException(status_code=404, detail="Character not found")

    if character.stat_points < points_to_deduct:
        logger.warning(f"Недостаточно stat_points для списания: требуется {points_to_deduct}, доступно {character.stat_points}")
        raise HTTPException(status_code=400, detail="Not enough stat points")

    character.stat_points -= points_to_deduct
    db.commit()
    db.refresh(character)
    logger.info(f"stat_points успешно списаны. Остаток stat_points: {character.stat_points}")

    return {"message": "Stat points deducted", "remaining_points": character.stat_points}

# character-service/main.py

@router.get("/{character_id}/full_profile", response_model=schemas.FullProfileResponse)
async def get_full_profile(character_id: int, db: Session = Depends(get_db)):
    # Получаем персонажа
    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        logger.error(f"Персонаж ID {character_id} не найден.")
        raise HTTPException(status_code=404, detail="Character not found")

    # Получаем passive_experience из attributes-service
    try:
        async with httpx.AsyncClient() as client:
            # Исправлен URL с добавлением '/attributes/'
            attributes_url = f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/passive_experience"
            logger.info(f"Отправка запроса на получение passive_experience персонажа по URL: {attributes_url}")
            response = await client.get(attributes_url)
            if response.status_code != 200:
                logger.error(f"Не удалось получить passive_experience персонажа ID {character_id}: {response.status_code} - {response.text}")
                raise HTTPException(status_code=404, detail="Passive experience not found in attributes-service")
            passive_experience = response.json().get("passive_experience", 0)
            logger.info(f"passive_experience персонажа ID {character_id}: {passive_experience}")
    except httpx.RequestError as e:
        logger.exception(f"Ошибка при запросе к attributes-service: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with attributes-service")

    # Проверка и обновление уровня на основе текущего пассивного опыта
    old_level = character.level
    character = crud.check_and_update_level(db, character_id, passive_experience)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    # Trigger title evaluation if character leveled up
    if character.level > old_level:
        try:
            newly_unlocked = crud.evaluate_titles(db, character_id)
            if newly_unlocked and character.user_id:
                for title_info in newly_unlocked:
                    try:
                        await send_title_unlocked_notification(
                            character.user_id, title_info["name"]
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось отправить уведомление о титуле: {e}")
        except Exception as e:
            logger.warning(f"Ошибка при оценке титулов после повышения уровня для персонажа {character_id}: {e}")

    # Получаем атрибуты персонажа из attributes-service
    try:
        async with httpx.AsyncClient() as client:
            attributes_url = f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}"
            logger.info(f"Отправка запроса на получение атрибутов персонажа по URL: {attributes_url}")
            response = await client.get(attributes_url)
            if response.status_code != 200:
                logger.error(f"Не удалось получить атрибуты персонажа ID {character_id}: {response.status_code} - {response.text}")
                raise HTTPException(status_code=404, detail="Attributes not found")
            attr_data = response.json()
    except httpx.RequestError as e:
        logger.exception(f"Ошибка при запросе к attributes-service: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with attributes-service")

    # Получаем порог для текущего уровня и следующего уровня
    current_level = character.level
    current_threshold = db.query(models.LevelThreshold).filter(models.LevelThreshold.level_number == current_level).first()
    next_level = current_level + 1
    next_threshold = db.query(models.LevelThreshold).filter(models.LevelThreshold.level_number == next_level).first()

    if current_threshold:
        prev_required_exp = current_threshold.required_experience
    else:
        # Если это первый уровень, порог предыдущего уровня можно считать 0
        prev_required_exp = 0

    if next_threshold:
        required_exp_for_next = next_threshold.required_experience
    else:
        # Если уровень макс. или не задан, считаем очень большое число, чтобы шкала была почти пустой
        required_exp_for_next = passive_experience + 999999

    # Текущий прогресс для шкалы уровня
    # Опыт, набранный после предыдущего уровня:
    current_level_exp = passive_experience - prev_required_exp
    # Сколько осталось до следующего уровня
    experience_to_next = required_exp_for_next - passive_experience
    if experience_to_next < 0:
        experience_to_next = 0

    # Рассчитываем заполненность шкалы уровня (0.0 до 1.0)
    if (required_exp_for_next - prev_required_exp) > 0:
        level_progress_fraction = current_level_exp / (required_exp_for_next - prev_required_exp)
    else:
        level_progress_fraction = 1.0

    # Получаем текущий активный титул (если есть)
    active_title_name = character.current_title.name if character.current_title else None
    active_title_rarity = character.current_title.rarity if character.current_title else None

    # Формируем ответ с нужными данными
    return schemas.FullProfileResponse(
        name=character.name,
        currency_balance=character.currency_balance,
        level=current_level,
        stat_points=character.stat_points,
        level_progress=schemas.LevelProgress(
            current_exp_in_level=current_level_exp,
            exp_to_next_level=experience_to_next,
            progress_fraction=min(level_progress_fraction, 1.0)  # ограничиваем до 1.0
        ),
        attributes={
            "health": {
                "current": attr_data["current_health"],
                "max": attr_data["max_health"]
            },
            "mana": {
                "current": attr_data["current_mana"],
                "max": attr_data["max_mana"]
            },
            "energy": {
                "current": attr_data["current_energy"],
                "max": attr_data["max_energy"]
            },
            "stamina": {
                "current": attr_data["current_stamina"],
                "max": attr_data["max_stamina"]
            }
        },
        active_title=active_title_name,
        active_title_rarity=active_title_rarity,
        avatar=character.avatar
    )

@router.get("/{character_id}/race_info", response_model=schemas.CharacterBaseInfoResponse)
def get_basic_info(character_id: int, db: Session = Depends(get_db)):
    """
    Возвращает основные данные о персонаже:
    - ID персонажа
    - id_class
    - id_race
    - id_subrace
    - level
    """
    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        logger.error(f"Персонаж ID {character_id} не найден.")
        raise HTTPException(status_code=404, detail="Character not found")

    return schemas.CharacterBaseInfoResponse(
        id=character.id,
        id_class=character.id_class,
        id_race=character.id_race,
        id_subrace=character.id_subrace,
        level=character.level
    )


@router.get("/by_location", response_model=List[schemas.PlayerInLocation])
def get_characters_by_location(location_id: int, db: Session = Depends(get_db)):
    """
    Возвращает список всех персонажей, находящихся в заданной локации.
    Используется поле current_location_id у модели Character.

    Ответ содержит для каждого персонажа:
      - character_name: имя персонажа,
      - character_title: имя текущего титула (если установлен; иначе пустая строка),
      - character_photo: фотография персонажа (например, avatar).
    """
    characters = db.query(models.Character).filter(
        models.Character.current_location_id == location_id,
        models.Character.is_npc == False,
    ).all()
    result = []
    for ch in characters:
        race = db.query(models.Race).filter(models.Race.id_race == ch.id_race).first()
        cls = db.query(models.Class).filter(models.Class.id_class == ch.id_class).first()
        result.append({
            "id": ch.id,
            "name": ch.name,
            "avatar": ch.avatar,
            "level": ch.level,
            "class_name": cls.name if cls else None,
            "race_name": race.name if race else None,
            "character_title": ch.current_title.name if ch.current_title else "",
            "character_title_rarity": ch.current_title.rarity if ch.current_title else None,
            "user_id": ch.user_id,
        })
    return result


@router.put("/{character_id}/update_location")
def update_location(character_id: int, payload: dict, db: Session = Depends(get_db)):
    """
    Обновляет текущую локацию персонажа.

    Запрос:
      {
          "new_location_id": <идентификатор новой локации>
      }

    Если персонаж не найден или не передан new_location_id, возвращает ошибку.
    В случае успеха – обновляет поле current_location_id и возвращает подтверждение.
    """
    new_location_id = payload.get("new_location_id")
    if new_location_id is None:
        raise HTTPException(status_code=400, detail="Поле 'new_location_id' обязательно для передачи")

    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    character.current_location_id = new_location_id
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении локации персонажа {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении локации")
    db.refresh(character)

    return {
        "detail": "Текущая локация персонажа обновлена",
        "character_id": character.id,
        "current_location_id": character.current_location_id
    }


@router.get("/{character_id}/profile", response_model=schemas.CharacterProfileResponse)
async def get_character_profile(character_id: int, db: Session = Depends(get_db)):
    """
    Возвращает профиль персонажа, включая:
      - character_photo: фото персонажа (например, поле avatar),
      - character_title: имя текущего титула (если установлен, иначе пустая строка),
      - user_id: идентификатор пользователя, которому принадлежит персонаж,
      - user_nickname: имя пользователя, полученное через вызов user‑service по эндпоинту GET /users/{user_id}.

    Если персонаж не найден, возвращает 404.
    """
    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    user_id = character.user_id
    user_nickname = ""
    if user_id:
        user_profile_url = f"{settings.USER_SERVICE_URL}/users/{user_id}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(user_profile_url)
                if resp.status_code == 200:
                    user_data = resp.json()
                    # Предполагаем, что в ответе есть ключ "username"
                    user_nickname = user_data.get("username", "")
                else:
                    logger.error(f"Не удалось получить профиль пользователя user_id {user_id}: {resp.status_code} - {resp.text}")
                    user_nickname = ""
            except httpx.RequestError as e:
                logger.error(f"Ошибка при получении профиля пользователя с user_id {user_id}: {e}")
                # Можно вернуть пустое значение или сообщить об ошибке – здесь выбираем оставить пустое имя.
                user_nickname = ""

    return {
        "character_photo": character.avatar,
        "character_title": character.current_title.name if character.current_title else "",
        "character_title_rarity": character.current_title.rarity if character.current_title else None,
        "character_level": character.level,
        "user_id": user_id,
        "user_nickname": user_nickname,
        "character_name": character.name,
    }

@router.get("/{character_id}/short_info")
def get_short_info(character_id: int, db: Session = Depends(get_db)):
    ch = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Character not found")

    # Fetch race, subrace, class names via joins
    race = db.query(models.Race).filter(models.Race.id_race == ch.id_race).first()
    subrace = db.query(models.Subrace).filter(models.Subrace.id_subrace == ch.id_subrace).first()
    char_class = db.query(models.Class).filter(models.Class.id_class == ch.id_class).first()

    return {
        "id": ch.id,
        "name": ch.name,
        "avatar": ch.avatar,
        "level": ch.level,
        "current_location_id": ch.current_location_id,
        "id_race": ch.id_race,
        "id_class": ch.id_class,
        "id_subrace": ch.id_subrace,
        "race_name": race.name if race else None,
        "class_name": char_class.name if char_class else None,
        "subrace_name": subrace.name if subrace else None,
        "is_npc": ch.is_npc,
        "npc_role": ch.npc_role,
        "biography": ch.biography,
        "personality": ch.personality,
        "sex": ch.sex,
        "age": ch.age,
    }

@router.get("/list")
def list_characters(
    q: Optional[str] = Query(None),
    id_class: Optional[int] = Query(None),
    id_race: Optional[int] = Query(None),
    include_npcs: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public list of all characters with search/filters."""
    query = db.query(models.Character)
    if not include_npcs:
        query = query.filter(models.Character.is_npc == False)
    if q:
        query = query.filter(models.Character.name.ilike(f"%{q}%"))
    if id_class is not None:
        query = query.filter(models.Character.id_class == id_class)
    if id_race is not None:
        query = query.filter(models.Character.id_race == id_race)

    total = query.count()
    characters = query.order_by(models.Character.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # Batch-fetch usernames for all unique user_ids
    unique_user_ids = set()
    for ch in characters:
        if ch.user_id is not None:
            unique_user_ids.add(ch.user_id)

    username_map = {}
    for uid in unique_user_ids:
        try:
            resp = httpx.get(f"{settings.USER_SERVICE_URL}/users/{uid}", timeout=5.0)
            if resp.status_code == 200:
                username_map[uid] = resp.json().get("username")
        except Exception as e:
            logger.warning(f"Не удалось получить username для user_id {uid}: {e}")

    result = []
    for ch in characters:
        race = db.query(models.Race).filter(models.Race.id_race == ch.id_race).first()
        cls = db.query(models.Class).filter(models.Class.id_class == ch.id_class).first()
        subrace = db.query(models.Subrace).filter(models.Subrace.id_subrace == ch.id_subrace).first()
        result.append({
            "id": ch.id,
            "name": ch.name,
            "avatar": ch.avatar,
            "level": ch.level,
            "id_class": ch.id_class,
            "id_race": ch.id_race,
            "id_subrace": ch.id_subrace,
            "biography": ch.biography,
            "personality": ch.personality,
            "appearance": ch.appearance,
            "background": ch.background,
            "sex": ch.sex,
            "age": ch.age,
            "is_npc": ch.is_npc,
            "user_id": ch.user_id,
            "username": username_map.get(ch.user_id) if ch.user_id else None,
            "class_name": cls.name if cls else None,
            "race_name": race.name if race else None,
            "subrace_name": subrace.name if subrace else None,
        })
    return {"items": result, "total": total, "page": page, "page_size": page_size}


# ============================================================
# Public races endpoint
# ============================================================

@router.get("/races", response_model=List[schemas.RaceWithSubraces])
def get_all_races(db: Session = Depends(get_db)):
    """
    Возвращает все расы с подрасами и пресетами статов.
    Публичный эндпоинт для страницы создания персонажа.
    """
    try:
        races = db.query(models.Race).all()
        result = []
        for race in races:
            subraces_data = []
            for sr in race.subraces:
                subraces_data.append(schemas.SubraceWithPreset(
                    id_subrace=sr.id_subrace,
                    name=sr.name,
                    description=sr.description,
                    stat_preset=sr.stat_preset,
                    image=sr.image,
                ))
            result.append(schemas.RaceWithSubraces(
                id_race=race.id_race,
                name=race.name,
                description=race.description,
                image=race.image,
                subraces=subraces_data,
            ))
        return result
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении рас: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении рас.")


# ============================================================
# Admin Race/Subrace CRUD endpoints
# ============================================================

@router.post("/admin/races", response_model=schemas.RaceResponse, status_code=201)
def admin_create_race(
    data: schemas.RaceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("races:create")),
):
    """Создание новой расы."""
    # Check for duplicate name
    existing = db.query(models.Race).filter(models.Race.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Раса с таким именем уже существует")

    race = models.Race(name=data.name, description=data.description)
    db.add(race)
    try:
        db.commit()
        db.refresh(race)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при создании расы: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании расы")
    return race


@router.put("/admin/races/{race_id}", response_model=schemas.RaceResponse)
def admin_update_race(
    race_id: int,
    data: schemas.RaceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("races:update")),
):
    """Обновление расы."""
    race = db.query(models.Race).filter(models.Race.id_race == race_id).first()
    if not race:
        raise HTTPException(status_code=404, detail="Раса не найдена")

    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    # Check for duplicate name if name is being changed
    if "name" in update_data and update_data["name"] != race.name:
        existing = db.query(models.Race).filter(models.Race.name == update_data["name"]).first()
        if existing:
            raise HTTPException(status_code=409, detail="Раса с таким именем уже существует")

    for field, value in update_data.items():
        setattr(race, field, value)

    try:
        db.commit()
        db.refresh(race)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении расы: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении расы")
    return race


@router.delete("/admin/races/{race_id}")
def admin_delete_race(
    race_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("races:delete")),
):
    """Удаление расы. Запрещено при наличии связанных подрас или персонажей."""
    race = db.query(models.Race).filter(models.Race.id_race == race_id).first()
    if not race:
        raise HTTPException(status_code=404, detail="Раса не найдена")

    # Check for subraces
    subrace_count = db.query(models.Subrace).filter(models.Subrace.id_race == race_id).count()
    if subrace_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Невозможно удалить расу: существуют связанные подрасы или персонажи",
        )

    # Check for characters
    character_count = db.query(models.Character).filter(models.Character.id_race == race_id).count()
    if character_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Невозможно удалить расу: существуют связанные подрасы или персонажи",
        )

    try:
        db.delete(race)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при удалении расы: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при удалении расы")

    return {"detail": "Race deleted"}


@router.post("/admin/subraces", response_model=schemas.SubraceResponse, status_code=201)
def admin_create_subrace(
    data: schemas.SubraceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("races:create")),
):
    """Создание новой подрасы с пресетом статов."""
    # Verify race exists
    race = db.query(models.Race).filter(models.Race.id_race == data.id_race).first()
    if not race:
        raise HTTPException(status_code=404, detail="Раса не найдена")

    subrace = models.Subrace(
        id_race=data.id_race,
        name=data.name,
        description=data.description,
        stat_preset=data.stat_preset.dict(),
    )
    db.add(subrace)
    try:
        db.commit()
        db.refresh(subrace)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при создании подрасы: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании подрасы")
    return subrace


@router.put("/admin/subraces/{subrace_id}", response_model=schemas.SubraceResponse)
def admin_update_subrace(
    subrace_id: int,
    data: schemas.SubraceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("races:update")),
):
    """Обновление подрасы."""
    subrace = db.query(models.Subrace).filter(models.Subrace.id_subrace == subrace_id).first()
    if not subrace:
        raise HTTPException(status_code=404, detail="Подраса не найдена")

    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    # If race is being changed, verify the new race exists
    if "id_race" in update_data:
        race = db.query(models.Race).filter(models.Race.id_race == update_data["id_race"]).first()
        if not race:
            raise HTTPException(status_code=404, detail="Раса не найдена")

    # Convert stat_preset from Pydantic model to dict if present
    if "stat_preset" in update_data and update_data["stat_preset"] is not None:
        update_data["stat_preset"] = data.stat_preset.dict()

    for field, value in update_data.items():
        setattr(subrace, field, value)

    try:
        db.commit()
        db.refresh(subrace)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении подрасы: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении подрасы")
    return subrace


@router.delete("/admin/subraces/{subrace_id}")
def admin_delete_subrace(
    subrace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("races:delete")),
):
    """Удаление подрасы. Запрещено при наличии связанных персонажей."""
    subrace = db.query(models.Subrace).filter(models.Subrace.id_subrace == subrace_id).first()
    if not subrace:
        raise HTTPException(status_code=404, detail="Подраса не найдена")

    # Check for characters referencing this subrace
    character_count = db.query(models.Character).filter(
        models.Character.id_subrace == subrace_id
    ).count()
    if character_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Невозможно удалить подрасу: существуют связанные персонажи",
        )

    try:
        db.delete(subrace)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при удалении подрасы: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при удалении подрасы")

    return {"detail": "Subrace deleted"}


# ============================================================
# NPC Admin endpoints
# ============================================================

@router.get("/admin/npcs", response_model=schemas.NpcListResponse)
def admin_list_npcs(
    q: str = Query("", description="Search by NPC name"),
    npc_role: Optional[str] = Query(None, description="Filter by NPC role"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    npc_status: Optional[str] = Query(None, description="Filter by NPC status (alive/dead)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("npcs:read")),
):
    """Paginated list of all NPCs with search and filters. Admin only."""
    try:
        query = db.query(models.Character).filter(models.Character.is_npc == True)

        if q:
            query = query.filter(models.Character.name.ilike(f"%{q}%"))
        if npc_role is not None:
            query = query.filter(models.Character.npc_role == npc_role)
        if location_id is not None:
            query = query.filter(models.Character.current_location_id == location_id)
        if npc_status is not None:
            query = query.filter(models.Character.npc_status == npc_status)

        total = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(models.Character.id).offset(offset).limit(page_size).all()

        return schemas.NpcListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError as e:
        logger.error(f"Error fetching NPC list: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/admin/npcs")
async def admin_create_npc(
    data: schemas.NpcCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("npcs:create")),
):
    """Create a new NPC character (is_npc=True, user_id=None, request_id=None)."""
    try:
        new_npc = models.Character(
            name=data.name,
            id_class=data.id_class,
            id_race=data.id_race,
            id_subrace=data.id_subrace,
            npc_role=data.npc_role,
            biography=data.biography,
            personality=data.personality,
            appearance=data.appearance,
            background=data.background,
            sex=data.sex,
            age=data.age,
            weight=data.weight,
            height=data.height,
            avatar=data.avatar,
            level=data.level,
            stat_points=data.stat_points,
            currency_balance=data.currency_balance,
            current_location_id=data.current_location_id,
            is_npc=True,
            user_id=None,
            request_id=None,
        )
        db.add(new_npc)
        db.flush()
        db.refresh(new_npc)

        # Create attributes via character-attributes-service
        attributes = crud.generate_attributes_for_subrace(db, data.id_subrace)
        attributes_response = await crud.send_attributes_request(new_npc.id, attributes)
        if attributes_response:
            new_npc.id_attributes = attributes_response.get("id")
            logger.info(f"Attributes created for NPC {new_npc.id}")
        else:
            logger.warning(f"Failed to create attributes for NPC {new_npc.id}, continuing without attributes")

        db.commit()
        db.refresh(new_npc)

        return {
            "id": new_npc.id,
            "name": new_npc.name,
            "level": new_npc.level,
            "npc_role": new_npc.npc_role,
            "current_location_id": new_npc.current_location_id,
            "detail": "NPC создан",
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating NPC: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании NPC")


@router.get("/admin/npcs/{npc_id}")
def admin_get_npc(
    npc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("npcs:read")),
):
    """Get NPC detail by ID. Verifies the character is actually an NPC."""
    npc = db.query(models.Character).filter(
        models.Character.id == npc_id,
        models.Character.is_npc == True,
    ).first()
    if not npc:
        raise HTTPException(status_code=404, detail="NPC не найден")

    race = db.query(models.Race).filter(models.Race.id_race == npc.id_race).first()
    cls = db.query(models.Class).filter(models.Class.id_class == npc.id_class).first()
    subrace = db.query(models.Subrace).filter(models.Subrace.id_subrace == npc.id_subrace).first()

    return {
        "id": npc.id,
        "name": npc.name,
        "level": npc.level,
        "stat_points": npc.stat_points,
        "currency_balance": npc.currency_balance,
        "id_race": npc.id_race,
        "race_name": race.name if race else None,
        "id_class": npc.id_class,
        "class_name": cls.name if cls else None,
        "id_subrace": npc.id_subrace,
        "subrace_name": subrace.name if subrace else None,
        "npc_role": npc.npc_role,
        "biography": npc.biography,
        "personality": npc.personality,
        "appearance": npc.appearance,
        "background": npc.background,
        "sex": npc.sex,
        "age": npc.age,
        "weight": npc.weight,
        "height": npc.height,
        "avatar": npc.avatar,
        "current_location_id": npc.current_location_id,
        "npc_status": npc.npc_status,
    }


@router.put("/admin/npcs/{npc_id}")
def admin_update_npc(
    npc_id: int,
    data: schemas.NpcUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("npcs:update")),
):
    """Update NPC fields."""
    npc = db.query(models.Character).filter(
        models.Character.id == npc_id,
        models.Character.is_npc == True,
    ).first()
    if not npc:
        raise HTTPException(status_code=404, detail="NPC не найден")

    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    for field, value in update_data.items():
        setattr(npc, field, value)

    try:
        db.commit()
        db.refresh(npc)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении NPC")

    return {"detail": "NPC обновлен", "id": npc.id}


@router.delete("/admin/npcs/{npc_id}")
async def admin_delete_npc(
    npc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("npcs:delete")),
    token: str = Depends(OAUTH2_SCHEME),
):
    """Delete NPC with cascade cleanup (attributes, inventory, skills)."""
    npc = db.query(models.Character).filter(
        models.Character.id == npc_id,
        models.Character.is_npc == True,
    ).first()
    if not npc:
        raise HTTPException(status_code=404, detail="NPC не найден")

    headers = {"Authorization": f"Bearer {token}"}

    # Cascade cleanup: inventory
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.INVENTORY_SERVICE_URL}{npc_id}/all",
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info(f"Inventory cleared for NPC {npc_id}")
            else:
                logger.warning(f"Failed to clear inventory for NPC {npc_id}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error clearing inventory for NPC {npc_id}: {e}")

    # Cascade cleanup: skills
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.SKILLS_SERVICE_URL}admin/character_skills/by_character/{npc_id}",
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info(f"Skills cleared for NPC {npc_id}")
            else:
                logger.warning(f"Failed to clear skills for NPC {npc_id}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error clearing skills for NPC {npc_id}: {e}")

    # Cascade cleanup: attributes
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.ATTRIBUTES_SERVICE_URL}{npc_id}",
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info(f"Attributes cleared for NPC {npc_id}")
            else:
                logger.warning(f"Failed to clear attributes for NPC {npc_id}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error clearing attributes for NPC {npc_id}: {e}")

    # Delete the NPC row
    try:
        db.delete(npc)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting NPC {npc_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при удалении NPC")

    return {"detail": f"NPC с ID {npc_id} удален"}


# ============================================================
# NPC Public endpoint
# ============================================================

@router.get("/npcs/by_location", response_model=List[schemas.NpcInLocation])
def get_npcs_by_location(location_id: int, db: Session = Depends(get_db)):
    """Returns list of NPCs at a given location (excludes mobs)."""
    npcs = db.query(models.Character).filter(
        models.Character.current_location_id == location_id,
        models.Character.is_npc == True,
        models.Character.npc_role != 'mob',
        models.Character.npc_status != 'dead',
    ).all()

    result = []
    for npc in npcs:
        race = db.query(models.Race).filter(models.Race.id_race == npc.id_race).first()
        cls = db.query(models.Class).filter(models.Class.id_class == npc.id_class).first()
        result.append({
            "id": npc.id,
            "name": npc.name,
            "avatar": npc.avatar,
            "level": npc.level,
            "class_name": cls.name if cls else None,
            "race_name": race.name if race else None,
            "npc_role": npc.npc_role,
        })
    return result


# ============================================================
# Mob Template Admin endpoints
# ============================================================

@router.get("/admin/mob-templates", response_model=schemas.MobTemplateListResponse)
def admin_list_mob_templates(
    q: str = Query("", description="Поиск по имени моба"),
    tier: Optional[str] = Query(None, description="Фильтр по типу: normal, elite, boss"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Paginated list of mob templates with search and tier filter. Admin only."""
    try:
        items, total = crud.get_mob_templates(db, q=q, tier=tier, page=page, page_size=page_size)
        return schemas.MobTemplateListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении шаблонов мобов: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/admin/mob-templates", status_code=201)
def admin_create_mob_template(
    data: schemas.MobTemplateCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Create a new mob template. Admin only."""
    try:
        template = crud.create_mob_template(db, data)
        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "tier": template.tier,
            "level": template.level,
            "avatar": template.avatar,
            "id_race": template.id_race,
            "id_subrace": template.id_subrace,
            "id_class": template.id_class,
            "sex": template.sex,
            "base_attributes": template.base_attributes,
            "xp_reward": template.xp_reward,
            "gold_reward": template.gold_reward,
            "respawn_enabled": template.respawn_enabled,
            "respawn_seconds": template.respawn_seconds,
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при создании шаблона моба: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании шаблона моба")


@router.get("/admin/mob-templates/{template_id}", response_model=schemas.MobTemplateDetailResponse)
def admin_get_mob_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Get mob template detail with skills, loot, and spawn config. Admin only."""
    template = crud.get_mob_template_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон моба не найден")
    return template


@router.put("/admin/mob-templates/{template_id}")
def admin_update_mob_template(
    template_id: int,
    data: schemas.MobTemplateUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Update mob template. Admin only."""
    template = db.query(models.MobTemplate).filter(models.MobTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон моба не найден")

    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    try:
        updated = crud.update_mob_template(db, template, data)
        return {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "tier": updated.tier,
            "level": updated.level,
            "avatar": updated.avatar,
            "id_race": updated.id_race,
            "id_subrace": updated.id_subrace,
            "id_class": updated.id_class,
            "sex": updated.sex,
            "base_attributes": updated.base_attributes,
            "xp_reward": updated.xp_reward,
            "gold_reward": updated.gold_reward,
            "respawn_enabled": updated.respawn_enabled,
            "respawn_seconds": updated.respawn_seconds,
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении шаблона моба {template_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении шаблона моба")


@router.delete("/admin/mob-templates/{template_id}")
def admin_delete_mob_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Delete mob template. Admin only."""
    template = db.query(models.MobTemplate).filter(models.MobTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон моба не найден")

    try:
        crud.delete_mob_template(db, template)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при удалении шаблона моба {template_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при удалении шаблона моба")

    return {"detail": "Шаблон моба удалён"}


# ============================================================
# Mob Template Skills, Loot, Spawn Config endpoints
# ============================================================

@router.put("/admin/mob-templates/{template_id}/skills")
def admin_update_mob_skills(
    template_id: int,
    data: schemas.MobSkillsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Replace all skills for a mob template. Admin only."""
    template = db.query(models.MobTemplate).filter(models.MobTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон моба не найден")

    try:
        crud.replace_mob_skills(db, template_id, data.skill_rank_ids)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении навыков моба {template_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении навыков моба")

    return {"detail": "Навыки обновлены", "skill_rank_ids": data.skill_rank_ids}


@router.put("/admin/mob-templates/{template_id}/loot")
def admin_update_mob_loot(
    template_id: int,
    data: schemas.MobLootUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Replace all loot entries for a mob template. Admin only."""
    template = db.query(models.MobTemplate).filter(models.MobTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон моба не найден")

    try:
        crud.replace_mob_loot(db, template_id, data.entries)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении лут-таблицы моба {template_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении лут-таблицы моба")

    return {
        "detail": "Лут-таблица обновлена",
        "entries": [e.dict() for e in data.entries],
    }


@router.put("/admin/mob-templates/{template_id}/spawns")
def admin_update_mob_spawns(
    template_id: int,
    data: schemas.MobSpawnUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Replace all spawn rules for a mob template. Admin only."""
    template = db.query(models.MobTemplate).filter(models.MobTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон моба не найден")

    try:
        crud.replace_mob_spawns(db, template_id, data.spawns)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении спавн-конфигурации моба {template_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении спавн-конфигурации моба")

    return {
        "detail": "Спавн-конфигурация обновлена",
        "spawns": [s.dict() for s in data.spawns],
    }


# ============================================================
# Mob Spawning & Lifecycle endpoints (Phase 3)
# ============================================================

@router.post("/internal/try-spawn")
def internal_try_spawn(
    data: schemas.TrySpawnRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) — called by locations-service after post creation.
    Queries spawn rules for the given location, rolls chance, spawns mob if successful.
    """
    try:
        result = crud.try_spawn_at_location(db, data.location_id)
        if result is None:
            return {"spawned": False}

        active_mob, character, template = result
        return {
            "spawned": True,
            "mob": {
                "active_mob_id": active_mob.id,
                "character_id": character.id,
                "name": character.name,
                "tier": template.tier,
            },
        }
    except Exception as e:
        logger.error(f"Ошибка при попытке спавна моба на локации {data.location_id}: {e}")
        return {"spawned": False}


@router.post("/admin/active-mobs/spawn", status_code=201)
def admin_manual_spawn(
    data: schemas.ManualSpawnRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Admin manually spawns a mob at a location."""
    template = db.query(models.MobTemplate).filter(models.MobTemplate.id == data.mob_template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон моба не найден")

    try:
        active_mob, character = crud.spawn_mob_from_template(
            db, data.mob_template_id, data.location_id, "manual"
        )
        return {
            "id": active_mob.id,
            "character_id": character.id,
            "location_id": active_mob.location_id,
            "status": active_mob.status,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при ручном спавне моба: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании моба")


@router.get("/admin/active-mobs", response_model=schemas.ActiveMobListResponse)
def admin_list_active_mobs(
    location_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    template_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """List active mobs with filters. Admin only."""
    try:
        items, total = crud.get_active_mobs(
            db, location_id=location_id, status=status,
            template_id=template_id, page=page, page_size=page_size,
        )
        result_items = []
        for am in items:
            template = db.query(models.MobTemplate).filter(models.MobTemplate.id == am.mob_template_id).first()
            result_items.append(schemas.ActiveMobResponse(
                id=am.id,
                mob_template_id=am.mob_template_id,
                character_id=am.character_id,
                location_id=am.location_id,
                status=am.status,
                battle_id=am.battle_id,
                spawn_type=am.spawn_type,
                spawned_at=am.spawned_at,
                killed_at=am.killed_at,
                respawn_at=am.respawn_at,
                template_name=template.name if template else None,
                template_tier=template.tier if template else None,
                template_level=template.level if template else None,
            ))
        return schemas.ActiveMobListResponse(
            items=result_items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении активных мобов: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.delete("/admin/active-mobs/{active_mob_id}")
def admin_delete_active_mob(
    active_mob_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("mobs:manage")),
):
    """Remove an active mob and its Character record. Admin only."""
    active_mob = crud.get_active_mob_by_id(db, active_mob_id)
    if not active_mob:
        raise HTTPException(status_code=404, detail="Активный моб не найден")

    try:
        crud.delete_active_mob(db, active_mob)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при удалении активного моба {active_mob_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при удалении моба")

    return {"detail": "Моб удалён"}


@router.get("/mobs/by_location", response_model=List[schemas.MobInLocation])
def get_mobs_by_location(
    location_id: int = Query(..., description="ID локации"),
    db: Session = Depends(get_db),
):
    """Public endpoint: returns alive/in_battle mobs at a given location."""
    try:
        return crud.get_mobs_at_location(db, location_id)
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении мобов на локации {location_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# ============================================================
# Rewards & Internal Mob Endpoints (Phase 4)
# ============================================================

@router.post("/{character_id}/add_rewards", response_model=schemas.AddRewardsResponse)
def add_rewards(
    character_id: int,
    data: schemas.AddRewardsRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) — adds XP and gold to a character.
    Called by battle-service after PvE victory.
    """
    result = crud.add_rewards_to_character(db, character_id, data.xp, data.gold)
    if result is None:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    new_balance, new_xp = result
    return schemas.AddRewardsResponse(
        ok=True,
        new_balance=new_balance,
        new_xp=new_xp,
    )


@router.get("/internal/mob-reward-data/{character_id}", response_model=schemas.MobRewardDataResponse)
def get_mob_reward_data_endpoint(
    character_id: int,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) — returns mob template reward data for a given mob character_id.
    Used by battle-service to determine PvE rewards.
    """
    reward_data = crud.get_mob_reward_data(db, character_id)
    if reward_data is None:
        raise HTTPException(status_code=404, detail="Персонаж не является мобом или не найден")
    return reward_data


@router.put("/internal/active-mob-status/{character_id}")
def update_mob_status(
    character_id: int,
    data: schemas.UpdateActiveMobStatusRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) — updates active mob status.
    Called by battle-service after PvE battle ends.
    """
    result = crud.update_active_mob_status(db, character_id, data.status)
    if result is None:
        raise HTTPException(status_code=404, detail="Активный моб не найден")
    return {"ok": True, "status": result.status}


# ============================================================
# Internal: NPC status update (used by battle-service)
# ============================================================

@router.put("/internal/npc-status/{character_id}")
def update_npc_status(
    character_id: int,
    data: schemas.UpdateNpcStatusRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) — updates NPC status (alive/dead).
    Called by battle-service after a battle where an NPC is defeated.
    Only works for NPCs (is_npc=True, npc_role != 'mob').
    Should be blocked by Nginx for external access.
    """
    npc = db.query(models.Character).filter(
        models.Character.id == character_id,
        models.Character.is_npc == True,
        models.Character.npc_role != 'mob',
    ).first()
    if not npc:
        raise HTTPException(status_code=404, detail="NPC не найден")

    npc.npc_status = data.status
    try:
        db.commit()
        db.refresh(npc)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении статуса NPC {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении статуса NPC")

    return {"ok": True, "status": npc.npc_status}


# ============================================================
# Internal: Record mob kill (used by battle-service for bestiary)
# ============================================================

@router.post("/internal/record-mob-kill", response_model=schemas.RecordMobKillResponse)
def record_mob_kill_endpoint(
    req: schemas.RecordMobKillRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) — records a mob kill for the bestiary.
    Called by battle-service after PvE battle ends.
    Idempotent — duplicate calls return already_recorded=true.
    """
    result = crud.record_mob_kill(db, req.character_id, req.mob_character_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Моб не найден по указанному character_id")
    return result


# ============================================================
# Public: Bestiary endpoint
# ============================================================

@router.get("/bestiary", response_model=schemas.BestiaryResponse)
def get_bestiary_endpoint(
    character_id: Optional[int] = Query(None, description="ID персонажа для проверки убийств"),
    db: Session = Depends(get_db),
):
    """
    Public endpoint (no auth) — returns bestiary data with visibility rules.
    If character_id is given, shows which mobs the character has killed.
    """
    try:
        return crud.get_bestiary(db, character_id=character_id)
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении бестиария: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# ============================================================
# Character Logs (FEAT-095)
# ============================================================

@router.post("/{character_id}/logs", response_model=schemas.CharacterLogResponse, status_code=201)
def create_character_log_endpoint(
    character_id: int,
    data: schemas.CreateCharacterLogRequest,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint (no auth) — creates a log entry for the character.
    Called by other services to record events (battles, rewards, travel, etc.).
    """
    character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    log_entry = crud.create_character_log(
        db,
        character_id=character_id,
        event_type=data.event_type,
        description=data.description,
        metadata=data.metadata,
    )
    return schemas.CharacterLogResponse(
        id=log_entry.id,
        character_id=log_entry.character_id,
        event_type=log_entry.event_type,
        description=log_entry.description,
        metadata=log_entry.metadata_,
        created_at=log_entry.created_at,
    )


@router.get("/{character_id}/logs", response_model=schemas.CharacterLogsListResponse)
def get_character_logs_endpoint(
    character_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Public endpoint (no auth) — returns paginated character logs.
    """
    logs, total = crud.get_character_logs(db, character_id, limit=limit, offset=offset, event_type=event_type)
    return schemas.CharacterLogsListResponse(
        logs=[
            schemas.CharacterLogResponse(
                id=log.id,
                character_id=log.character_id,
                event_type=log.event_type,
                description=log.description,
                metadata=log.metadata_,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
    )


@router.get("/{character_id}/post-history", response_model=schemas.PostHistoryResponse)
def get_character_post_history_endpoint(
    character_id: int,
    db: Session = Depends(get_db),
):
    """
    Public endpoint (no auth) — returns post history for the character.
    Queries the shared 'posts' table with location names.
    """
    posts = crud.get_character_post_history(db, character_id)
    return schemas.PostHistoryResponse(
        posts=[schemas.PostHistoryItem(**p) for p in posts],
    )


app.include_router(router)
