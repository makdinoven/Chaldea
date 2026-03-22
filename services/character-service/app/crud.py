import httpx
import models, schemas
from config import settings
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session
from models import (
    CharacterRequest, Race, Subrace, Class, Character, LevelThreshold,
    MobTemplate, MobTemplateSkill, MobLootTable, LocationMobSpawn, ActiveMob,
)
import logging

logger = logging.getLogger("character-service.crud")

# Функция для создания заявки на персонажа
def create_character_request(db: Session, request: schemas.CharacterRequestCreate, user_id: int):
    """
    Создание заявки на создание персонажа.
    """
    # Создаем экземпляр CharacterRequest, явно передавая user_id
    db_request = models.CharacterRequest(
        user_id=user_id,
        name=request.name,
        id_subrace=request.id_subrace,
        id_race=request.id_race,
        background=request.background,
        age=request.age,
        weight=request.weight,
        height=request.height,
        avatar=request.avatar,
        biography=request.biography,
        personality=request.personality,
        id_class=request.id_class,
        sex=request.sex,
        appearance=request.appearance
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request


## Функция для создания предварительного персонажа (с указанием user_id)
def create_preliminary_character(db: Session, character_request: models.CharacterRequest, currency_balance: int = 0, auto_commit: bool = True):
    """
    Создает предварительную запись персонажа с указанием user_id из заявки.
    currency_balance задаётся из стартового набора класса.
    При auto_commit=False вызывает flush вместо commit (для использования в транзакции).
    """
    new_character = models.Character(
        id_attributes=None,
        request_id=character_request.id,
        user_id=character_request.user_id,
        name=character_request.name,
        id_subrace=character_request.id_subrace,
        id_race=character_request.id_race,
        background=character_request.background,
        age=character_request.age,
        weight=character_request.weight,
        height=character_request.height,
        avatar=character_request.avatar,
        biography=character_request.biography,
        personality=character_request.personality,
        id_class=character_request.id_class,
        sex=character_request.sex,
        appearance=character_request.appearance,
        currency_balance=currency_balance
    )
    db.add(new_character)
    if auto_commit:
        db.commit()
    else:
        db.flush()
    db.refresh(new_character)
    return new_character


# Обновление статуса заявки
def update_character_request_status(db: Session, request_id: int, status: str, auto_commit: bool = True):
    """
    Обновляет статус заявки на персонажа.
    При auto_commit=False вызывает flush вместо commit (для использования в транзакции).
    """
    db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
    if db_request:
        db_request.status = status
        if auto_commit:
            db.commit()
        else:
            db.flush()
        db.refresh(db_request)
        return db_request
    return None


# Функция для обновления персонажа после получения зависимостей
def update_character_with_dependencies(db: Session, character_id: int,
                                       skills_id: int, attributes_id: int, auto_commit: bool = True):
    """
    Обновляет поля персонажа с полученными навыками и атрибутами.
    При auto_commit=False вызывает flush вместо commit (для использования в транзакции).
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if db_character:
        db_character.id_attributes = attributes_id
        if auto_commit:
            db.commit()
        else:
            db.flush()
        db.refresh(db_character)
        return db_character
    return None


# Функция для изменения статуса заявки на "approved"
def approve_character_request(db: Session, request_id: int):
    """
    Обновляет статус заявки на 'approved'.
    """
    db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
    if db_request:
        db_request.status = 'approved'
        db.commit()
        db.refresh(db_request)
        return db_request
    return None


# Функция для изменения статуса заявки на "rejected"
def reject_character_request(db: Session, request_id: int):
    """
    Обновляет статус заявки на 'rejected'.
    """
    db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
    if db_request:
        db_request.status = 'rejected'
        db.commit()
        db.refresh(db_request)
        return db_request
    return None


# Функция для удаления заявки после одобрения
def delete_character_request(db: Session, request_id: int):
    """
    Удаляет заявку на персонажа после её одобрения.
    """
    db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
    if db_request:
        db.delete(db_request)
        db.commit()
        return True
    return False


# Функция для удаления персонажа
def delete_character(db: Session, character_id: int):
    """
    Удаление персонажа из базы данных по его ID.
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if db_character:
        db.delete(db_character)
        db.commit()
        return True
    return False


# Получение всех рас и подрас
def get_all_races_and_subraces(db: Session):
    races = db.query(models.Race).all()
    subraces = db.query(models.Subrace).all()

    # Создаем словарь, где ключ - это ID расы, а значение - это подрасы, относящиеся к этой расе
    races_data = {}

    for race in races:
        races_data[race.id_race] = {
            "id_race": race.id_race,
            "name": race.name,
            "description": race.description,
            "image": race.image,
            "subraces": []
        }

    for subrace in subraces:
        races_data[subrace.id_race]["subraces"].append({
            "id_subrace": subrace.id_subrace,
            "name": subrace.name,
            "description": subrace.description,
            "stat_preset": subrace.stat_preset,
            "image": subrace.image,
        })

    return races_data


async def send_equipment_slots_request(character_id: int):
    """
    Отправляет запрос на создание слотов экипировки для персонажа.

    :param character_id: ID персонажа
    :return: Ответ от микросервиса экипировки
    """
    equipment_slots_data = [
        {"character_id": character_id, "slot_type": "head", "item_id": None},
        {"character_id": character_id, "slot_type": "chest", "item_id": None},
        {"character_id": character_id, "slot_type": "legs", "item_id": None},
        {"character_id": character_id, "slot_type": "feet", "item_id": None},
        {"character_id": character_id, "slot_type": "weapon", "item_id": None},
        {"character_id": character_id, "slot_type": "accessory", "item_id": None},
    ]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.EQUIPMENT_SERVICE_URL}/slots",
                json={"character_id": character_id, "equipment_slots": equipment_slots_data}
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ошибка при запросе слотов экипировки: {response.status_code} - {response.text}")
                return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса на слоты экипировки: {e}")
        return None


'''
# Получение заявок, которые находятся на модерации
def get_moderation_requests(db: Session):
    """
    Получает все заявки, которые находятся на модерации.
    """
    try:
        moderation_requests = db.query(models.CharacterRequest).filter(models.CharacterRequest.status.in_  (['pending','rejected','approved'])).all()
        return moderation_requests
    except Exception as e:
        print(f"Ошибка: {e}")
        return []
'''

def get_moderation_requests(db: Session):
    """
    Получает все заявки, которые находятся на модерации, с названиями класса, расы и подрасы.
    Результат: словарь, где ключом является id заявки, а значением словарь с остальными данными заявки.
    """
    try:
        # Выполняем запрос с соединениями таблиц для получения всех данных за один запрос
        moderation_requests = (
            db.query(
                CharacterRequest.id,
                CharacterRequest.user_id,
                CharacterRequest.name,
                CharacterRequest.biography,
                CharacterRequest.appearance,
                CharacterRequest.personality,
                CharacterRequest.background,
                CharacterRequest.age,
                CharacterRequest.weight,
                CharacterRequest.height,
                CharacterRequest.sex,
                CharacterRequest.status,
                CharacterRequest.created_at,
                CharacterRequest.id_class,
                Class.name.label('class_name'),
                CharacterRequest.id_race,
                Race.name.label('race_name'),
                CharacterRequest.id_subrace,
                Subrace.name.label('subrace_name'),
                CharacterRequest.avatar,  # добавляем поле avatar
                CharacterRequest.request_type,
                CharacterRequest.character_id,
            )
            .join(Race, CharacterRequest.id_race == Race.id_race, isouter=True)
            .join(Subrace, CharacterRequest.id_subrace == Subrace.id_subrace, isouter=True)
            .join(Class, CharacterRequest.id_class == Class.id_class, isouter=True)
            .filter(CharacterRequest.status.in_(['pending', 'rejected', 'approved']))
            .all()
        )

        # Собираем результаты
        results = {}
        for (
            request_id,
            user_id,
            name,
            biography,
            appearance,
            personality,
            background,
            age,
            weight,
            height,
            sex,
            status,
            created_at,
            id_class,
            class_name,
            id_race,
            race_name,
            id_subrace,
            subrace_name,
            avatar,  # поле avatar
            request_type,
            character_id,
        ) in moderation_requests:
            created_at_str = created_at.strftime('%Y-%m-%dT%H:%M:%S') if created_at else None

            # Добавляем в словарь с ключом request_id
            results[request_id] = {
                "request_id": request_id,
                "user_id": user_id,
                "name": name,
                "biography": biography,
                "appearance": appearance,
                "personality": personality,
                "background": background,
                "age": age,
                "weight": weight,
                "height": height,
                "sex": sex,
                "id_class": id_class,
                "class_name": class_name if class_name else "Unknown",
                "id_race": id_race,
                "race_name": race_name if race_name else "Unknown",
                "id_subrace": id_subrace,
                "subrace_name": subrace_name if subrace_name else "Unknown",
                "status": status,
                "created_at": created_at_str,
                "avatar": avatar if avatar else "",  # возвращаем пустую строку, если avatar нет
                "request_type": request_type if request_type else "creation",
                "character_id": character_id,
            }

        # Возвращаем результат как словарь с ключом id заявки
        return results

    except SQLAlchemyError as e:
        logger.error(f"Ошибка при получении заявок на модерацию: {e}")
        raise


# Функция для создания титула
def create_title(db: Session, name: str, description: str = None):
    """
    Создание нового титула.
    """
    new_title = models.Title(name=name, description=description)
    db.add(new_title)
    db.commit()
    db.refresh(new_title)
    return new_title

# Функция для присвоения титула персонажу
def assign_title_to_character(db: Session, character_id: int, title_id: int):
    """
    Присваивает титул персонажу.
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    db_title = db.query(models.Title).filter(models.Title.id_title == title_id).first()

    if db_character and db_title:
        # Создаем запись в промежуточной таблице CharacterTitle
        new_assignment = models.CharacterTitle(character_id=character_id, title_id=title_id)
        db.add(new_assignment)
        db.commit()
        db.refresh(new_assignment)
        return new_assignment
    return None


# Функция для выбора текущего титула персонажем
def set_current_title(db: Session, character_id: int, title_id: int):
    """
    Выбирает титул как текущий для персонажа.
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if db_character:
        db_character.current_title_id = title_id
        db.commit()
        db.refresh(db_character)
        return db_character
    return None


# Функция для получения всех титулов
def get_all_titles(db: Session):
    """
    Возвращает список всех титулов.
    """
    return db.query(models.Title).all()

# Функция для получения всех титулов персонажа
def get_titles_for_character(db: Session, character_id: int):
    """
    Получает все титулы для конкретного персонажа.
    """
    titles = (
        db.query(models.Title)
        .join(models.CharacterTitle, models.Title.id_title == models.CharacterTitle.title_id)
        .filter(models.CharacterTitle.character_id == character_id)
        .all()
    )
    return titles

def generate_attributes_for_subrace(db: Session, subrace_id: int) -> dict:
    """
    Генерирует атрибуты для персонажа на основе его подрасы.
    Читает stat_preset из таблицы subraces в БД.

    :param db: SQLAlchemy Session
    :param subrace_id: ID подрасы
    :return: Словарь с атрибутами
    """
    subrace = db.query(models.Subrace).filter(models.Subrace.id_subrace == subrace_id).first()
    if subrace and subrace.stat_preset:
        return dict(subrace.stat_preset)

    # Дефолтные значения, если пресет не найден
    logger.warning(f"Пресет статов для подрасы {subrace_id} не найден, используются значения по умолчанию")
    return {
        "strength": 10,
        "agility": 10,
        "intelligence": 10,
        "endurance": 10,
        "health": 10,
        "energy": 10,
        "mana": 10,
        "stamina": 10,
        "charisma": 10,
        "luck": 10,
    }


async def send_inventory_request(character_id: int, items: list):
    """
    Отправляет запрос на создание инвентаря в микросервис инвентаря.

    :param character_id: ID персонажа
    :param items: Список предметов для добавления в инвентарь
    :return: Ответ от микросервиса инвентаря
    """
    inventory_data = {
        "character_id": character_id,
        "items": items  # Формат: [{'item_id': int, 'quantity': int}, ...]
    }

    logger.info(f"Отправка запроса на создание инвентаря для персонажа {character_id} с данными: {inventory_data}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{settings.INVENTORY_SERVICE_URL}", json=inventory_data)
            logger.info(f"Ответ от inventory-service: статус {response.status_code}, тело {response.text}")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ошибка при создании инвентаря: {response.status_code} - {response.text}")
                return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса на инвентарь: {e}")
        return None


async def send_skills_request(character_id: int):
    """
    Отправляет запрос на создание навыков в микросервис навыков.

    :param character_id: ID персонажа
    :return: Ответ от микросервиса навыков
    """
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Отправка запроса на создание навыков для персонажа {character_id}")
            response = await client.post(f"{settings.SKILLS_SERVICE_URL}", json={"character_id": character_id})

            logger.info(f"Статус-код ответа от сервиса навыков: {response.status_code}")
            logger.info(f"Тело ответа от сервиса навыков: {response.text}")

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ошибка при создании навыков: {response.status_code} - {response.text}")
                return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса на навыки: {e}")
        return None


async def send_attributes_request(character_id: int, attributes: dict):
    """
    Отправляет запрос на создание атрибутов в микросервис атрибутов.

    :param character_id: ID персонажа
    :param attributes: Словарь с атрибутами персонажа
    :return: Ответ от микросервиса атрибутов
    """
    try:
        # Добавляем character_id в данные запроса
        attributes["character_id"] = character_id
        async with httpx.AsyncClient() as client:
            logger.info(f"Отправка запроса на создание атрибутов для персонажа {character_id} с данными: {attributes}")

            response = await client.post(f"{settings.ATTRIBUTES_SERVICE_URL}", json=attributes)

            logger.info(f"Статус-код ответа от сервиса атрибутов: {response.status_code}")
            logger.info(f"Тело ответа: {response.text}")

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ошибка при создании атрибутов: {response.status_code} - {response.text}")
                return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса на атрибуты: {e}")
        return None


async def assign_character_to_user(user_id: int, character_id: int, token: str = None):
    """
    Отправляет запрос в микросервис пользователей для присвоения персонажа пользователю.
    """
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient() as client:
            # Шаг 1: Создание записи в user_characters
            logger.info(f"Отправляем запрос на создание связи между пользователем {user_id} и персонажем {character_id}")
            create_relation_response = await client.post(
                f"{settings.USER_SERVICE_URL}/users/user_characters/",
                json={"user_id": user_id, "character_id": character_id}
            )

            if create_relation_response.status_code not in [200, 201]:
                logger.error(f"Ошибка при создании записи в user_characters: {create_relation_response.status_code}")
                logger.error(f"Ответ от сервера: {create_relation_response.text}")
                return False

            logger.info(f"Запись в user_characters успешно создана для пользователя {user_id} и персонажа {character_id}")

            # Шаг 2: Обновление поля current_character у пользователя
            logger.info(f"Отправляем запрос на обновление current_character для пользователя {user_id} с персонажем {character_id}")
            update_user_response = await client.put(
                f"{settings.USER_SERVICE_URL}/users/{user_id}/update_character",
                json={"current_character": character_id},
                headers=headers
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


def check_and_update_level(db: Session, character_id: int, passive_experience: int):
    """
    Проверяет и обновляет уровень персонажа на основе пассивного опыта.
    Повышает уровень и начисляет stat_points до тех пор, пока опыт позволяет.
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        logger.error(f"Персонаж ID {character_id} не найден при проверке уровня.")
        return None

    leveled_up = False

    while True:
        next_level = character.level + 1
        threshold = db.query(LevelThreshold).filter(LevelThreshold.level_number == next_level).first()
        if not threshold:
            logger.info(f"Нет порога для уровня {next_level}. Уровень персонажа останется {character.level}.")
            break

        required_exp = threshold.required_experience
        if passive_experience >= required_exp:
            # Повышаем уровень
            character.level += 1
            character.stat_points += 10
            passive_experience -= required_exp
            leveled_up = True
            logger.info(f"Персонаж ID {character_id} повысился до уровня {character.level}. stat_points += 10. Остаток опыта: {passive_experience}")
        else:
            break

    if leveled_up:
        # Обновляем только локальные поля, не пытаясь изменить passive_experience
        # Если passive_experience должен быть обновлён в attributes-service, реализуйте это отдельно
        db.commit()
        db.refresh(character)
        logger.info(f"Персонаж ID {character_id} обновлен после повышения уровня. Новый уровень: {character.level}, stat_points: {character.stat_points}")

    return character

async def get_character_experience(character_id: int):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ATTRIBUTES_SERVICE_URL}/{character_id}/experience")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ошибка при получении опыта персонажа {character_id}: {response.status_code} - {response.text}")
                return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса на получение опыта персонажа {character_id}: {e}")
        return None

def get_all_starter_kits(db: Session):
    """
    Возвращает все стартовые наборы (по одному на каждый класс).
    """
    return db.query(models.StarterKit).all()


def upsert_starter_kit(db: Session, class_id: int, data: schemas.StarterKitUpdate):
    """
    Создаёт или обновляет стартовый набор для указанного класса.
    Если запись для class_id уже существует — обновляет, иначе создаёт новую.
    """
    db_kit = db.query(models.StarterKit).filter(models.StarterKit.class_id == class_id).first()
    if db_kit:
        db_kit.items = [item.dict() for item in data.items]
        db_kit.skills = [skill.dict() for skill in data.skills]
        db_kit.currency_amount = data.currency_amount
    else:
        db_kit = models.StarterKit(
            class_id=class_id,
            items=[item.dict() for item in data.items],
            skills=[skill.dict() for skill in data.skills],
            currency_amount=data.currency_amount,
        )
        db.add(db_kit)
    db.commit()
    db.refresh(db_kit)
    return db_kit


async def send_skills_presets_request(character_id: int, skill_ids: list[int]):
    """
    Массовое назначение нескольких навыков персонажу.
    Каждый навык - rank_number=1 (первый ранг).
    """
    # Сформируем структуру данных под эндпоинт сервисе навыков
    request_body = {
        "character_id": character_id,
        "skills": []
    }
    for skill_id in skill_ids:
        request_body["skills"].append({
            "skill_id": skill_id,
            "rank_number": 1
        })

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.SKILLS_SERVICE_URL}assign_multiple",
                json=request_body
            )
            if response.status_code == 200:
                return response.json()  # Возвращаем ответ от сервиса
            else:
                logger.error(f"Ошибка при массовом назначении навыков: {response.status_code} - {response.text}")
                return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса в сервис навыков: {e}")
        return None


# ============================================================
# Mob Template CRUD
# ============================================================

def get_mob_templates(
    db: Session,
    q: str = "",
    tier: str = None,
    page: int = 1,
    page_size: int = 20,
):
    """Paginated list of mob templates with optional search and tier filter."""
    query = db.query(MobTemplate)
    if q:
        query = query.filter(MobTemplate.name.ilike(f"%{q}%"))
    if tier:
        query = query.filter(MobTemplate.tier == tier)
    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(MobTemplate.id).offset(offset).limit(page_size).all()
    return items, total


def get_mob_template_by_id(db: Session, template_id: int):
    """Get a single mob template by ID with relationships loaded."""
    return db.query(MobTemplate).options(
        joinedload(MobTemplate.skills),
        joinedload(MobTemplate.loot_entries),
        joinedload(MobTemplate.spawn_locations),
    ).filter(MobTemplate.id == template_id).first()


def create_mob_template(db: Session, data: schemas.MobTemplateCreate):
    """Create a new mob template."""
    template = MobTemplate(
        name=data.name,
        description=data.description,
        tier=data.tier,
        level=data.level,
        avatar=data.avatar,
        id_race=data.id_race,
        id_subrace=data.id_subrace,
        id_class=data.id_class,
        sex=data.sex,
        base_attributes=data.base_attributes,
        xp_reward=data.xp_reward,
        gold_reward=data.gold_reward,
        respawn_enabled=data.respawn_enabled,
        respawn_seconds=data.respawn_seconds,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_mob_template(db: Session, template: MobTemplate, data: schemas.MobTemplateUpdate):
    """Update an existing mob template."""
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


def delete_mob_template(db: Session, template: MobTemplate):
    """Delete a mob template (cascades to skills, loot, spawns, active mobs)."""
    db.delete(template)
    db.commit()


def replace_mob_skills(db: Session, template_id: int, skill_rank_ids: list):
    """Replace all skills for a mob template."""
    db.query(MobTemplateSkill).filter(MobTemplateSkill.mob_template_id == template_id).delete()
    for rank_id in skill_rank_ids:
        db.add(MobTemplateSkill(mob_template_id=template_id, skill_rank_id=rank_id))
    db.commit()


def replace_mob_loot(db: Session, template_id: int, entries: list):
    """Replace all loot entries for a mob template."""
    db.query(MobLootTable).filter(MobLootTable.mob_template_id == template_id).delete()
    for entry in entries:
        db.add(MobLootTable(
            mob_template_id=template_id,
            item_id=entry.item_id,
            drop_chance=entry.drop_chance,
            min_quantity=entry.min_quantity,
            max_quantity=entry.max_quantity,
        ))
    db.commit()


def replace_mob_spawns(db: Session, template_id: int, spawns: list):
    """Replace all spawn rules for a mob template."""
    db.query(LocationMobSpawn).filter(LocationMobSpawn.mob_template_id == template_id).delete()
    for spawn in spawns:
        db.add(LocationMobSpawn(
            mob_template_id=template_id,
            location_id=spawn.location_id,
            spawn_chance=spawn.spawn_chance,
            max_active=spawn.max_active,
            is_enabled=spawn.is_enabled,
        ))
    db.commit()


# ============================================================
# Mob Spawning & Lifecycle (Phase 3)
# ============================================================

def spawn_mob_from_template(db: Session, template_id: int, location_id: int, spawn_type: str = "random"):
    """
    Create a mob instance from a template:
    1. Load MobTemplate
    2. Create a Character record (is_npc=True, npc_role='mob')
    3. Call character-attributes-service to create attributes
    4. Call skills-service to assign skills (via shared DB)
    5. Create an ActiveMob record
    Returns (active_mob, character) tuple.
    """
    import asyncio
    from sqlalchemy import text as sa_text

    template = db.query(MobTemplate).filter(MobTemplate.id == template_id).first()
    if not template:
        raise ValueError(f"MobTemplate {template_id} не найден")

    # 1. Create Character record
    new_character = Character(
        name=template.name,
        id_race=template.id_race,
        id_subrace=template.id_subrace,
        id_class=template.id_class,
        sex=template.sex or "genderless",
        level=template.level,
        avatar=template.avatar or "",
        appearance="",
        is_npc=True,
        npc_role="mob",
        user_id=None,
        request_id=None,
        currency_balance=0,
        stat_points=0,
        current_location_id=location_id,
    )
    db.add(new_character)
    db.flush()
    db.refresh(new_character)
    logger.info(f"Создан персонаж моба ID {new_character.id} из шаблона {template.name}")

    # 2. Create attributes via character-attributes-service
    attributes = template.base_attributes or {}
    if not attributes:
        # Fallback: generate from subrace
        attributes = generate_attributes_for_subrace(db, template.id_subrace)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                attributes_response = pool.submit(
                    _sync_send_attributes_request, new_character.id, dict(attributes)
                ).result(timeout=15)
        else:
            attributes_response = loop.run_until_complete(
                send_attributes_request(new_character.id, dict(attributes))
            )
    except Exception:
        attributes_response = _sync_send_attributes_request(new_character.id, dict(attributes))

    if attributes_response:
        new_character.id_attributes = attributes_response.get("id")
        db.flush()
        logger.info(f"Атрибуты созданы для моба {new_character.id}")
    else:
        logger.warning(f"Не удалось создать атрибуты для моба {new_character.id}")

    # 3. Assign skills from template via shared DB (direct INSERT into character_skills)
    template_skills = db.query(MobTemplateSkill).filter(
        MobTemplateSkill.mob_template_id == template_id
    ).all()
    for ts in template_skills:
        try:
            db.execute(
                sa_text(
                    "INSERT INTO character_skills (character_id, skill_rank_id) VALUES (:cid, :srid)"
                ),
                {"cid": new_character.id, "srid": ts.skill_rank_id},
            )
        except Exception as e:
            logger.warning(f"Не удалось назначить навык skill_rank_id={ts.skill_rank_id} мобу {new_character.id}: {e}")
    if template_skills:
        logger.info(f"Назначено {len(template_skills)} навыков мобу {new_character.id}")

    # 4. Create ActiveMob record
    active_mob = ActiveMob(
        mob_template_id=template_id,
        character_id=new_character.id,
        location_id=location_id,
        status="alive",
        spawn_type=spawn_type,
    )
    db.add(active_mob)
    db.commit()
    db.refresh(active_mob)
    logger.info(f"ActiveMob ID {active_mob.id} создан на локации {location_id}")

    return active_mob, new_character


def _sync_send_attributes_request(character_id: int, attributes: dict):
    """Synchronous version of send_attributes_request for use in sync context."""
    attributes["character_id"] = character_id
    try:
        response = httpx.post(
            f"{settings.ATTRIBUTES_SERVICE_URL}",
            json=attributes,
            timeout=10.0,
        )
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Ошибка при создании атрибутов моба: {response.status_code} - {response.text}")
            return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса на атрибуты моба: {e}")
        return None


def try_spawn_at_location(db: Session, location_id: int):
    """
    Check spawn rules for a location and try to spawn a mob.
    Returns (active_mob, character) if spawned, or None.
    """
    import random

    spawn_rules = db.query(LocationMobSpawn).filter(
        LocationMobSpawn.location_id == location_id,
        LocationMobSpawn.is_enabled == True,
    ).all()

    if not spawn_rules:
        return None

    for rule in spawn_rules:
        # Count current active mobs of this template at this location
        active_count = db.query(ActiveMob).filter(
            ActiveMob.mob_template_id == rule.mob_template_id,
            ActiveMob.location_id == location_id,
            ActiveMob.status != "dead",
        ).count()

        if active_count >= rule.max_active:
            continue

        # Roll the dice
        roll = random.random() * 100
        if roll < rule.spawn_chance:
            try:
                active_mob, character = spawn_mob_from_template(
                    db, rule.mob_template_id, location_id, "random"
                )
                template = db.query(MobTemplate).filter(MobTemplate.id == rule.mob_template_id).first()
                return active_mob, character, template
            except Exception as e:
                logger.error(f"Ошибка при спавне моба template={rule.mob_template_id} на локации {location_id}: {e}")
                db.rollback()
                continue

    return None


def get_active_mobs(
    db: Session,
    location_id: int = None,
    status: str = None,
    template_id: int = None,
    page: int = 1,
    page_size: int = 20,
):
    """Paginated list of active mobs with optional filters."""
    query = db.query(ActiveMob)
    if location_id is not None:
        query = query.filter(ActiveMob.location_id == location_id)
    if status is not None:
        query = query.filter(ActiveMob.status == status)
    if template_id is not None:
        query = query.filter(ActiveMob.mob_template_id == template_id)

    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(ActiveMob.id.desc()).offset(offset).limit(page_size).all()
    return items, total


def get_active_mob_by_id(db: Session, active_mob_id: int):
    """Get a single active mob by ID."""
    return db.query(ActiveMob).filter(ActiveMob.id == active_mob_id).first()


def delete_active_mob(db: Session, active_mob: ActiveMob):
    """Delete an active mob and its associated Character record."""
    character_id = active_mob.character_id

    # Delete the active mob record
    db.delete(active_mob)
    db.flush()

    # Delete the associated Character record
    character = db.query(Character).filter(Character.id == character_id).first()
    if character:
        db.delete(character)

    db.commit()
    logger.info(f"ActiveMob ID {active_mob.id} и персонаж ID {character_id} удалены")


def get_mobs_at_location(db: Session, location_id: int):
    """Get alive/in_battle mobs at a location for public display."""
    active_mobs = db.query(ActiveMob).filter(
        ActiveMob.location_id == location_id,
        ActiveMob.status.in_(["alive", "in_battle"]),
    ).all()

    result = []
    for am in active_mobs:
        template = db.query(MobTemplate).filter(MobTemplate.id == am.mob_template_id).first()
        character = db.query(Character).filter(Character.id == am.character_id).first()
        if template and character:
            result.append({
                "active_mob_id": am.id,
                "character_id": am.character_id,
                "name": character.name,
                "level": character.level,
                "tier": template.tier,
                "avatar": character.avatar,
                "status": am.status,
            })
    return result


# ============================================================
# Rewards (Phase 4)
# ============================================================

def add_rewards_to_character(db: Session, character_id: int, xp: int, gold: int):
    """
    Adds gold to character's currency_balance and XP via shared DB (character_attributes table).
    Returns (new_balance, new_xp) or None if character not found.
    """
    from sqlalchemy import text as sa_text

    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        return None

    # Add gold directly
    character.currency_balance = (character.currency_balance or 0) + gold
    db.flush()

    # Add XP via shared DB — directly update character_attributes table
    new_xp = None
    try:
        # Get current passive_experience from shared DB
        row = db.execute(
            sa_text("SELECT passive_experience FROM character_attributes WHERE character_id = :cid"),
            {"cid": character_id},
        ).fetchone()
        if row:
            current_xp = row[0] or 0
            new_xp = current_xp + xp
            db.execute(
                sa_text("UPDATE character_attributes SET passive_experience = :xp WHERE character_id = :cid"),
                {"xp": new_xp, "cid": character_id},
            )
            logger.info(f"XP обновлён для персонажа {character_id}: {current_xp} -> {new_xp}")
        else:
            logger.error(f"Атрибуты не найдены для персонажа {character_id}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении XP для персонажа {character_id}: {e}")

    db.commit()
    db.refresh(character)
    new_balance = character.currency_balance

    # Check and update level based on new XP
    if new_xp is not None:
        check_and_update_level(db, character_id, new_xp)

    return new_balance, new_xp


def get_mob_reward_data(db: Session, character_id: int):
    """
    Given a mob's character_id, find the active_mob record, then load the mob_template.
    Returns reward data dict or None if not a mob.
    """
    # Verify this is a mob character
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.is_npc == True,
        Character.npc_role == 'mob',
    ).first()
    if not character:
        return None

    # Find active_mob record for this character
    active_mob = db.query(ActiveMob).filter(
        ActiveMob.character_id == character_id,
    ).first()
    if not active_mob:
        return None

    # Load template with loot entries
    template = db.query(MobTemplate).options(
        joinedload(MobTemplate.loot_entries),
    ).filter(MobTemplate.id == active_mob.mob_template_id).first()
    if not template:
        return None

    loot_table = []
    for entry in template.loot_entries:
        loot_table.append({
            "item_id": entry.item_id,
            "drop_chance": entry.drop_chance,
            "min_quantity": entry.min_quantity,
            "max_quantity": entry.max_quantity,
        })

    return {
        "xp_reward": template.xp_reward,
        "gold_reward": template.gold_reward,
        "loot_table": loot_table,
        "template_name": template.name,
        "tier": template.tier,
    }


def update_active_mob_status(db: Session, character_id: int, new_status: str):
    """Update the status of an active mob by its character_id."""
    from datetime import datetime, timedelta

    active_mob = db.query(ActiveMob).filter(
        ActiveMob.character_id == character_id,
    ).first()
    if not active_mob:
        return None

    active_mob.status = new_status
    if new_status == 'dead':
        active_mob.killed_at = datetime.utcnow()
        # If respawn enabled, set respawn_at
        template = db.query(MobTemplate).filter(MobTemplate.id == active_mob.mob_template_id).first()
        if template and template.respawn_enabled and template.respawn_seconds:
            active_mob.respawn_at = datetime.utcnow() + timedelta(seconds=template.respawn_seconds)
    db.commit()
    db.refresh(active_mob)
    return active_mob