import aio_pika
import asyncio
import json
from .crud import create_character_inventory
from .database import SessionLocal
from .config import settings

async def process_message(message: aio_pika.IncomingMessage):
    """
    Обрабатывает сообщения из RabbitMQ для создания инвентаря персонажа.
    """
    async with message.process():
        db = SessionLocal()
        try:
            data = json.loads(message.body.decode())
            character_id = data.get("character_id")
            if character_id:
                # Создаем инвентарь для персонажа
                create_character_inventory(db, character_id)
        except Exception as e:
            print(f"Error processing message: {e}")
        finally:
            db.close()

async def consume():
    """
    Потребляет сообщения из очереди RabbitMQ.
    """
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("character_creation_queue", durable=True)
        async for message in queue:
            await process_message(message)

if __name__ == "__main__":
    asyncio.run(consume())
