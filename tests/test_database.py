import time
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

@pytest.fixture(scope='module')
def db_connection():
    """Создает соединение с тестовой базой данных."""
    DATABASE_URL = 'mysql+pymysql://myuser:mypassword@mysql_test:3306/mydatabase_test'

    engine = create_engine(DATABASE_URL)

    for _ in range(10):  # Повторяем попытку 10 раз
        try:
            connection = engine.connect()
            return connection
        except OperationalError:
            time.sleep(2)  # Подождите 2 секунды перед повторной попыткой

    pytest.fail("Не удалось подключиться к базе данных после 10 попыток")

def test_database_connection(db_connection):
    """Проверяет подключение к базе данных."""
    db_connection.execute(text("SELECT 1"))
    assert db_connection is not None
