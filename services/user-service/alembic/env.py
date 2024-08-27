import os
import sys


from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Импортируем Base из модуля models и URL базы данных из модуля database
from models import Base
from database import SQLALCHEMY_DATABASE_URL


# Настройка файла конфигурации для логирования
config = context.config

# Прочитайте файл конфигурации, если он существует
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Укажите метаданные объектов модели, которые будут использованы для 'autogenerate'
target_metadata = Base.metadata

def run_migrations_offline():
    """Запуск миграций в 'offline' режиме."""
    url = SQLALCHEMY_DATABASE_URL  # Используем URL базы данных из вашего модуля database.py
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Запуск миграций в 'online' режиме."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        url=SQLALCHEMY_DATABASE_URL,  # Используем URL базы данных из вашего модуля database.py
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
