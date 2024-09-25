from sqlalchemy.orm import Session
import models, schemas
from sqlalchemy.orm import joinedload


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
        biography=request.biography,
        personality=request.personality,
        id_class=request.id_class,
        #sex=request.sex,
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
        name=character_request.name,
        id_subrace=character_request.id_subrace,
        biography=character_request.biography,
        personality=character_request.personality,
        id_item_inventory=None,
        id_skill_inventory=None,
        id_attributes=None,
        id_class=character_request.id_class,
        currency_balance=0,
        user_id=character_request.user_id,  # Присваиваем user_id из заявки
        request_id=character_request.id  # Связь с заявкой
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

#Получение всех рас и подрас
def get_all_races_and_subraces(db: Session):
    races = db.query(models.Race).all()
    subraces = db.query(models.Subrace).all()

    # Создаем словарь, где ключ - это ID расы, а значение - это подрасы, относящиеся к этой расе
    races_data = {}

    for race in races:
        races_data[race.id_race] = {
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
    """
    try:
        # Выполняем запрос для получения заявок на модерацию
        moderation_requests = (
            db.query(models.CharacterRequest)
            .filter(models.CharacterRequest.status.in_(['pending', 'rejected', 'approved']))
            .all()
        )

        results = []
        for request in moderation_requests:
            # Получаем данные подрасы и расы
            subrace = db.query(models.Subrace).filter(models.Subrace.id_subrace == request.id_subrace).first()
            race = db.query(models.Race).filter(models.Race.id_race == subrace.id_race).first() if subrace else None

            # Получаем данные о классе
            char_class = db.query(models.Class).filter(models.Class.id_class == request.id_class).first()
            created_at_str = request.created_at.strftime('%Y-%m-%dT%H:%M:%S')if request.created_at else None
            # Собираем результат
            results.append(
                {
                "id": request.id,
                "id_subrace": request.id_subrace,
                "biography": request.biography,
                "personality": request.personality,
                "id_class": request.id_class,
                "appearance": request.appearance,
                "background": request.background,
                "age": request.age,
                "weight": request.weight,
                "height": request.height,
                "name": request.name,
                "status": request.status,
                "created_at": created_at_str,
                "user_id": request.user_id,
                "race_name": race.name if race else "Unknown",
                "subrace_name": subrace.name if subrace else "Unknown",
                "class_name": char_class.name if char_class else "Unknown",
            })

        return results
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

