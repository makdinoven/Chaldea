# import aio_pika
# import asyncio
# import json
# from crud import create_character_inventory
# from database import SessionLocal
# from config import settings
# import time
#
# async def process_message(message: aio_pika.IncomingMessage):
#     """
#     Обрабатывает сообщения из RabbitMQ для создания инвентаря персонажа.
#     """
#     async with message.process():
#         db = SessionLocal()
#         try:
#             data = json.loads(message.body.decode())
#             character_id = data.get("character_id")
#             print(f"Получено сообщение для создания инвентаря персонажа с ID: {character_id}")
#             if character_id:
#                 # Создаем инвентарь для персонажа
#                 create_character_inventory(db, character_id)
#                 print(f"Инвентарь для персонажа с ID {character_id} создан.")
#
#                 # Отправляем ответ обратно в очередь для ответа
#                 response = {
#                     "inventory_id": character_id  # Верните ID инвентаря или другой нужный параметр
#                 }
#                 connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
#                 async with connection:
#                     channel = await connection.channel()
#                     await channel.default_exchange.publish(
#                         aio_pika.Message(body=json.dumps(response).encode()),
#                         routing_key="inventory_response_queue"  # Очередь ответа
#                     )
#                 print(f"Ответ с ID инвентаря отправлен в очередь inventory_response_queue: {response}")
#         except Exception as e:
#             print(f"Ошибка при обработке сообщения: {e}")
#         finally:
#             db.close()
#
# async def consume():
#     """
#     Потребляет сообщения из очереди RabbitMQ.
#     """
#     while True:
#         try:
#             connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
#             print("Успешное подключение к RabbitMQ")
#             break  # Выход из цикла, если подключение удалось
#         except Exception as e:
#             print(f"Ошибка подключения к RabbitMQ: {e}. Повтор через 5 секунд...")
#             time.sleep(5)  # Ожидание перед повторной попыткой
#     async with connection:
#         channel = await connection.channel()
#         queue = await channel.declare_queue("character_inventory_queue", durable=True)  # Уникальная очередь для инвентаря
#         print(f"Ожидание сообщений в очереди character_inventory_queue...")
#         async for message in queue:
#             await process_message(message)
#
# if __name__ == "__main__":
#     asyncio.run(consume())
