import httpx
import models, schemas
from config import settings
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session
from models import CharacterRequest, Race, Subrace, Class, Character, LevelThreshold
from sqlalchemy.orm import Session
from presets import SUBRACE_ATTRIBUTES, CLASS_ITEMS
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
def create_preliminary_character(db: Session, character_request: models.CharacterRequest):
    """
    Создает предварительную запись персонажа с указанием user_id из заявки.
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
        appearance=character_request.appearance
    )
    db.add(new_character)
    db.commit()
    db.refresh(new_character)
    return new_character


# Обновление статуса заявки
def update_character_request_status(db: Session, request_id: int, status: str):
    """
    Обновляет статус заявки на персонажа.
    """
    db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
    if db_request:
        db_request.status = status
        db.commit()
        db.refresh(db_request)
        return db_request
    return None


# Функция для обновления персонажа после получения зависимостей
def update_character_with_dependencies(db: Session, character_id: int,
                                       skills_id: int, attributes_id: int):
    """
    Обновляет поля персонажа с полученными навыками и атрибутами.
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if db_character:
        db_character.id_attributes = attributes_id
        db.commit()
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
            "description": race.description,  # Добавляем описание расы
            "subraces": []
        }

    for subrace in subraces:
        races_data[subrace.id_race]["subraces"].append({
            "id_subrace": subrace.id_subrace,
            "name": subrace.name,
            "description": subrace.description  # Добавляем описание подрасы
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
                print(f"Ошибка при запросе слотов экипировки: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        print(f"Ошибка при отправке запроса на слоты экипировки: {e}")
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
                CharacterRequest.avatar  # добавляем поле avatar
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
            avatar  # поле avatar
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
                "avatar": avatar if avatar else ""  # возвращаем пустую строку, если avatar нет
            }

        # Возвращаем результат как словарь с ключом id заявки
        return results

    except Exception as e:
        print(f"Ошибка при получении заявок на модерацию: {e}")
        return {}


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

def generate_attributes_for_subrace(subrace_id: int) -> dict:
    """
    Генерирует атрибуты для персонажа на основе его подрасы.

    :param subrace_id: ID подрасы
    :return: Словарь с атрибутами
    """
    # Извлекаем атрибуты из шаблона или возвращаем дефолтные значения
    return SUBRACE_ATTRIBUTES.get(subrace_id, {
        "strength": 10,
        "agility": 10,
        "intelligence": 10,
        "endurance": 100,
        "health": 100,
        "energy": 50,
        "mana": 75,
        "stamina": 100,
        "charisma": 10,
        "luck": 10
    })


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

    print(f"[INFO] Отправка запроса на создание инвентаря для персонажа {character_id} с данными: {inventory_data}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{settings.INVENTORY_SERVICE_URL}", json=inventory_data)
            print(f"[INFO] Ответ от inventory-service: статус {response.status_code}, тело {response.text}")
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[ERROR] Ошибка при создании инвентаря: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        print(f"[ERROR] Ошибка при отправке запроса на инвентарь: {e}")
        return None


async def send_skills_request(character_id: int):
    """
    Отправляет запрос на создание навыков в микросервис навыков.

    :param character_id: ID персонажа
    :return: Ответ от микросервиса навыков
    """
    try:
        async with httpx.AsyncClient() as client:
            print(f"[INFO] Отправка запроса на создание навыков для персонажа {character_id}")
            response = await client.post(f"{settings.SKILLS_SERVICE_URL}", json={"character_id": character_id})

            print(f"[INFO] Статус-код ответа от сервиса навыков: {response.status_code}")
            print(f"[INFO] Тело ответа от сервиса навыков: {response.text}")

            if response.status_code == 200:
                return response.json()
            else:
                print(f"[ERROR] Ошибка при создании навыков: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        print(f"[ERROR] Ошибка при отправке запроса на навыки: {e}")
        return None


logger = logging.getLogger("character-service.utils")

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
    except Exception as e:
        logger.error(f"Ошибка при отправке запроса на атрибуты: {e}")
        return None


async def assign_character_to_user(user_id: int, character_id: int):
    """
    Отправляет запрос в микросервис пользователей для присвоения персонажа пользователю.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Шаг 1: Создание записи в user_characters
            print(f"Отправляем запрос на создание связи между пользователем {user_id} и персонажем {character_id}")
            create_relation_response = await client.post(
                f"{settings.USER_SERVICE_URL}/users/user_characters/",
                json={"user_id": user_id, "character_id": character_id}
            )

            if create_relation_response.status_code not in [200, 201]:
                print(f"Ошибка при создании записи в user_characters: {create_relation_response.status_code}")
                print(f"Ответ от сервера: {create_relation_response.text}")
                return False

            print(f"Запись в user_characters успешно создана для пользователя {user_id} и персонажа {character_id}")

            # Шаг 2: Обновление поля current_character у пользователя
            print(f"Отправляем запрос на обновление current_character для пользователя {user_id} с персонажем {character_id}")
            update_user_response = await client.put(
                f"{settings.USER_SERVICE_URL}/users/{user_id}/update_character",
                json={"current_character": character_id}
            )

            if update_user_response.status_code == 200:
                print(f"Пользователь с ID {user_id} успешно обновлен с персонажем ID {character_id}")
                return True
            else:
                print(f"Ошибка при обновлении пользователя: {update_user_response.status_code}")
                print(f"Ответ от сервера: {update_user_response.text}")
                return False

    except Exception as e:
        print(f"Ошибка при отправке запросов на обновление пользователя: {e}")
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
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{settings.ATTRIBUTES_SERVICE_URL}/{character_id}/experience")
        if response.status_code == 200:
            return response.json()
        else:
            return None