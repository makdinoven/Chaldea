# import aio_pika
# import asyncio
# import json
# from crud import create_character_attributes
# from database import SessionLocal
# from config import settings
# import time
#
#
# async def process_message(message: aio_pika.IncomingMessage):
#     async with message.process():
#         db = SessionLocal()
#         try:
#             data = json.loads(message.body.decode())
#             character_id = data.get("character_id")
#             print(f"Получено сообщение для создания атрибутов персонажа с ID: {character_id}")
#             if character_id:
#                 create_character_attributes(db, character_id)
#                 print(f"Атрибуты для персонажа с ID {character_id} созданы.")
#
#                 response = {"attributes_id": character_id}
#                 try:
#                     connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
#                     async with connection:
#                         channel = await connection.channel()
#
#                         # Явно создаем очередь для ответа
#                         await channel.declare_queue("attributes_response_queue", durable=True)
#
#                         print(f"Отправка ответа с атрибутами в очередь attributes_response_queue: {response}")
#                         await channel.default_exchange.publish(
#                             aio_pika.Message(body=json.dumps(response).encode()),
#                             routing_key="attributes_response_queue"
#                         )
#                     print(f"Ответ отправлен успешно")
#                 except Exception as e:
#                     print(f"Ошибка при отправке ответа в очередь: {e}")
#         except Exception as e:
#             print(f"Ошибка при обработке сообщения: {e}")
#         finally:
#             db.close()
#
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
#
#     async with connection:
#         try:
#             channel = await connection.channel()
#             queue = await channel.declare_queue("character_attributes_queue", durable=True)  # Уникальная очередь для атрибутов
#             print(f"Ожидание сообщений в очереди character_attributes_queue...")
#             async for message in queue:
#                 await process_message(message)
#         except Exception as e:
#             print(f"Ошибка при обработке сообщений: {e}")
#
# if __name__ == "__main__":
#     print("Запуск консюмера для character_attributes_service...")
#     asyncio.run(consume())
