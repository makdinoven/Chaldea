from sqlalchemy.orm import Session
from models import *
from schemas import UserCreate
from passlib.context import CryptContext
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_AVATAR_URL = "assets/avatars/avatar.png"

# Получение пользователя по email
def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()
# Получение пользователя по емаилу или никнейму
def get_user_by_email_or_username(db: Session, identifier: str):
    # Простая проверка, является ли идентификатор email-адресом
    if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
        return db.query(User).filter(User.email == identifier).first()
    else:
        return db.query(User).filter(User.username == identifier).first()

# Получение пользователя по никнейму
def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

# Создание нового пользователя
def create_user(db: Session, user: UserCreate):
    hashed_password = pwd_context.hash(user.password)
    db_user = User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        avatar = DEFAULT_AVATAR_URL
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Добавление записи в таблицу UserAvatarCharacterPreview
    db_user_avatar_character_preview = UserAvatarCharacterPreview(
        user_id=db_user.id,
        avatar=DEFAULT_AVATAR_URL  # можно использовать аватар по умолчанию
    )
    db.add(db_user_avatar_character_preview)

    # Добавление записи в таблицу UserAvatarPreview
    db_user_avatar_preview = UserAvatarPreview(
        user_id=db_user.id,
        avatar=DEFAULT_AVATAR_URL  # также можно использовать аватар по умолчанию
    )
    db.add(db_user_avatar_preview)

    # Сохранение изменений в базе данных
    db.commit()

    # Обновление данных пользователя в сессии
    db.refresh(db_user)

    return db_user

# Аутентификация пользователя
def authenticate_user(db: Session, identifier: str, password: str):
    user = get_user_by_email_or_username(db, identifier)
    if not user or not pwd_context.verify(password, user.hashed_password):
        return False
    return user
