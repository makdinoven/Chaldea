import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..main import app
from ..database import *
from ..models import *
from functools import partial

# Настраиваем тестовую базу данных на MySQL
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://myuser:mypassword@mysql_test/test_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Фикстура для базы данных
@pytest.fixture(scope="function")
def db_session():
    # Создаем все таблицы в тестовой базе данных
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Удаляем все таблицы после теста
        Base.metadata.drop_all(bind=engine)


# Подменяем зависимость для базы данных на тестовую
def override_get_db(db_session):
    try:
        yield db_session
    finally:
        db_session.close()


# Фикстура для асинхронного клиента FastAPI
@pytest.fixture(scope="function")
async def client(db_session):
    # Подменяем зависимость в пределах теста
    app.dependency_overrides[get_db] = lambda: override_get_db(db_session)

    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c


# 1. Тестирование создания заявки
@pytest.mark.asyncio
async def test_create_character_request(client):
    request_data = {
        "user_id": 1,
        "name": "Test Character",
        "id_subrace": 10,
        "biography": "A hero from the north",
        "personality": "Brave and kind",
        "id_class": 2
    }

    response = await client.post("/character/requests/", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == request_data["name"]

    # Проверка, что заявка появилась в базе данных
    db_request = db_session.query(CharacterRequest).filter_by(name="Test Character").first()
    assert db_request is not None
    assert db_request.name == "Test Character"

# 2. Тестирование одобрения заявки с реальными микросервисами
@pytest.mark.asyncio
async def test_approve_character_request_with_real_services(client, db_session):
    # Создаем заявку для последующего одобрения
    new_request = CharacterRequest(
        user_id=1,
        name="Test Character",
        id_subrace=10,
        biography="A hero from the north",
        personality="Brave",
        id_class=2,
        status="pending"
    )
    db_session.add(new_request)
    db_session.commit()

    # Отправляем запрос на одобрение
    response = await client.post(f"/character/requests/{new_request.id}/approve")
    assert response.status_code == 200
    data = response.json()

    # Проверка, что персонаж был создан
    db_character = db_session.query(Character).filter_by(name="Test Character").first()
    assert db_character is not None
    assert db_character.name == "Test Character"

    # Проверка, что статус заявки обновлен на 'approved'
    db_request = db_session.query(CharacterRequest).filter_by(id=new_request.id).first()
    assert db_request is None  # Заявка должна быть удалена после одобрения

# 3. Тестирование отклонения заявки
@pytest.mark.asyncio
async def test_reject_character_request(client, db_session):
    # Создаем заявку для последующего отклонения
    new_request = CharacterRequest(
        user_id=1,
        name="Test Character",
        id_subrace=10,
        biography="A hero from the north",
        personality="Brave",
        id_class=2,
        status="pending"
    )
    db_session.add(new_request)
    db_session.commit()

    # Отправляем запрос на отклонение
    response = await client.post(f"/character/requests/{new_request.id}/reject")
    assert response.status_code == 200

    # Проверка, что статус заявки изменен на 'rejected'
    db_request = db_session.query(CharacterRequest).filter_by(id=new_request.id).first()
    assert db_request is not None
    assert db_request.status == "rejected"

# 4. Тестирование присвоения персонажа пользователю
@pytest.mark.asyncio
async def test_assign_character_to_user(client, db_session):
    # Создаем заявку для одобрения и присвоения персонажа пользователю
    new_request = CharacterRequest(
        user_id=1,
        name="Test Character",
        id_subrace=10,
        biography="A hero from the north",
        personality="Brave",
        id_class=2,
        status="pending"
    )
    db_session.add(new_request)
    db_session.commit()

    # Одобряем заявку, что автоматически создает персонажа и присваивает его пользователю
    response = await client.post(f"/character/requests/{new_request.id}/approve")
    assert response.status_code == 200

    # Проверяем, что персонаж присвоен пользователю
    user_response = await client.get(f"/users/1")  # Предполагается, что у пользователя с ID=1 уже есть запрос
    assert user_response.status_code == 200
    user_data = user_response.json()

    # Проверяем, что у пользователя есть персонаж
    assert "character_id" in user_data
    assert user_data["character_id"] is not None

# 5. Тестирование удаления персонажа
@pytest.mark.asyncio
async def test_delete_character(client, db_session):
    # Создаем персонажа напрямую в базе данных
    new_character = Character(
        name="Test Character",
        id_subrace=10,
        biography="A hero from the north",
        personality="Brave",
        id_class=2,
        currency_balance=0
    )
    db_session.add(new_character)
    db_session.commit()

    # Отправляем запрос на удаление персонажа
    response = await client.delete(f"/character/characters/{new_character.id}")
    assert response.status_code == 200

    # Проверяем, что персонажа нет в базе данных
    db_character = db_session.query(Character).filter_by(id=new_character.id).first()
    assert db_character is None
