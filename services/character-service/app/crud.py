import httpx
import models, schemas
from config import settings
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session
from models import CharacterRequest, Race, Subrace, Class
from sqlalchemy.orm import Session



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
        id_item_inventory=None,
        id_skill_inventory=None,
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
                                       inventory_id: int, skills_id: int, attributes_id: int):
    """
    Обновляет поля персонажа с полученными инвентарем, навыками и атрибутами.
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if db_character:
        db_character.id_item_inventory = inventory_id
        db_character.id_skill_inventory = skills_id
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

