from sqlalchemy.orm import Session
import models, schemas


def create_character_request(db: Session, request: schemas.CharacterRequestCreate):
    """
    Создание заявки на создание персонажа.
    """
    db_request = models.CharacterRequest(**request.dict())
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request


def approve_character_request(db: Session, request_id: int):
    """
    Подтверждение заявки на создание персонажа.
    """
    db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()

    if not db_request:
        raise Exception("Заявка не найдена")

    # Создаем персонажа на основе данных из заявки
    character = models.Character(
        name=db_request.name,
        id_subrace=db_request.id_subrace,
        biography=db_request.biography,
        personality=db_request.personality,
        id_class=db_request.id_class
    )

    db.add(character)
    db.delete(db_request)  # Удаляем заявку после создания персонажа
    db.commit()
    db.refresh(character)

    return character
