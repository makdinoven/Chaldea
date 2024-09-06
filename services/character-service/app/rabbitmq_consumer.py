import aio_pika
import asyncio
import json
from sqlalchemy.orm import Session
from .database import SessionLocal
from crud import *
from .schemas import CharacterCreate, CharacterUpdate, CharacterRequestCreate
from .config import settings


async def send_to_rabbitmq(message: dict):
    """
    Функция для отправки сообщения в очередь RabbitMQ.

    :param message: Сообщение в формате словаря, которое нужно отправить.
    """
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)  # Подключение к RabbitMQ
    async with connection:
        channel = await connection.channel()  # Открытие канала
        queue = await channel.declare_queue(settings.RABBITMQ_QUEUE, durable=True)  # Объявление очереди
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(message).encode()),  # Публикация сообщения
            routing_key=queue.name
        )
    print("Message sent to RabbitMQ:", message)


# Функция для обработки входящих сообщений из очереди RabbitMQ
async def process_message(message: aio_pika.IncomingMessage):
    """
    Функция обработки сообщений из RabbitMQ. В зависимости от типа сообщения
    выполняется одна из операций: создание заявки, одобрение заявки,
    отклонение заявки, обновление или удаление персонажа.

    :param message: Сообщение, полученное из RabbitMQ.
    """
    async with message.process():  # Подтверждаем получение сообщения для RabbitMQ
        try:
            db: Session = SessionLocal()  # Создаем сессию для работы с базой данных
            data = json.loads(message.body.decode())  # Декодируем JSON-сообщение

            action = data.get(
                "action")  # Определяем тип действия (create_request, approve_request, reject_request, update, delete)
            character_data = data.get("character_data")  # Получаем данные о персонаже

            if action == "create_request":
                # Если действие - создание новой заявки на персонажа
                character_request = CharacterRequestCreate(**character_data)
                create_character_request(db, character_request)  # Создаем заявку в базе данных
            elif action == "approve_request":
                # Если действие - одобрение заявки
                request_id = character_data["id"]  # Извлекаем ID заявки для одобрения
                approve_character_request(db, request_id)  # Переносим персонажа из заявки в основную таблицу
            elif action == "reject_request":
                # Если действие - отклонение заявки
                request_id = character_data["id"]  # Извлекаем ID заявки для отклонения
                reject_character_request(db, request_id)  # Отклоняем заявку
            elif action == "update":
                # Если действие - обновление персонажа
                character_id = character_data.pop("id")  # Извлекаем ID персонажа для обновления
                character_update = CharacterUpdate(**character_data)
                update_character(db, character_id, character_update)  # Обновляем данные персонажа
            elif action == "delete":
                # Если действие - удаление персонажа
                character_id = character_data["id"]  # Извлекаем ID персонажа для удаления
                delete_character(db, character_id)  # Удаляем персонажа из базы данных

            db.commit()  # Фиксируем изменения в базе данных

        except Exception as e:
            # Обработка ошибок
            print(f"Failed to process message: {e}")
        finally:
            db.close()  # Закрываем сессию с базой данных в любом случае


# Функция для потребления сообщений из очереди RabbitMQ
async def consume():
    """
    Функция для подключения к RabbitMQ и получения сообщений из очереди.
    """
    # Устанавливаем соединение с RabbitMQ
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    queue_name = settings.RABBITMQ_QUEUE

    async with connection:
        # Открываем канал и декларируем очередь
        channel = await connection.channel()
        queue = await channel.declare_queue(queue_name, durable=True)

        # Асинхронно обрабатываем сообщения из очереди
        async for message in queue:
            await process_message(message)  # Обрабатываем каждое сообщение


# Главная функция для запуска консюмера
if __name__ == "__main__":
    # Запускаем event loop для запуска консюмера
    asyncio.run(consume())
