# import aio_pika
# import asyncio
# import json
# from sqlalchemy.orm import Session
# from database import SessionLocal
# from crud import create_preliminary_character, update_character_with_dependencies, create_character_request
# from config import settings
# import time
# from models import CharacterRequest, Character  # Добавили импорт моделей
#
# # Функция для отправки сообщения в очередь RabbitMQ
# async def send_to_rabbitmq(queue_name: str, message: dict, response_queue_name: str = None):
#     """
#     Отправляет сообщение в очередь RabbitMQ.
#     Если указана response_queue_name, ожидает ответа из этой очереди.
#     """
#     try:
#         print(f"Отправка сообщения в очередь {queue_name}: {message}")
#         connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
#
#         async with connection:
#             channel = await connection.channel()
#
#             # Декларируем очередь
#             await channel.declare_queue(queue_name, durable=True)
#
#             # Отправляем сообщение
#             await channel.default_exchange.publish(
#                 aio_pika.Message(body=json.dumps(message).encode()),
#                 routing_key=queue_name
#             )
#
#             # Ожидаем ответ, если указан response_queue_name
#             if response_queue_name:
#                 print(f"Ожидание ответа из очереди {response_queue_name}")
#                 return await receive_response_from_queue(response_queue_name)
#
#         print(f"Сообщение отправлено в очередь {queue_name}")
#     except Exception as e:
#         print(f"Ошибка при отправке сообщения в RabbitMQ: {e}")
#         return None
#
# # Функция для получения ответа из очереди RabbitMQ
# async def receive_response_from_queue(response_queue_name: str):
#     """
#     Ожидает сообщения из очереди RabbitMQ.
#     """
#     try:
#         connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
#         async with connection:
#             channel = await connection.channel()
#             response_queue = await channel.declare_queue(response_queue_name, durable=True)
#
#             # Ожидаем сообщение в течение 60 секунд
#             incoming_message = await response_queue.get(timeout=60)
#             async with incoming_message.process():
#                 response = json.loads(incoming_message.body)
#                 return response
#     except Exception as e:
#         print(f"Ошибка получения ответа из {response_queue_name}: {e}")
#         return None
#
# # Функция для обработки сообщений из очередей RabbitMQ
# async def process_message(message: aio_pika.IncomingMessage, queue_name: str):
#     """
#     Обрабатывает сообщения из очереди.
#     """
#     async with message.process():
#         db: Session = SessionLocal()
#         try:
#             print(f"Сообщение получено из очереди {queue_name}: {message.body.decode()}")
#             data = json.loads(message.body.decode())
#
#             # Обработка заявок на персонажа
#             if queue_name == "character_request_queue":
#                 action = data.get("action")
#                 character_data = data.get("character_data")
#
#                 if action == "create_request":
#                     if character_data is None:
#                         print("Ошибка: отсутствуют данные для создания заявки.")
#                         return
#                     # Создаем заявку на персонажа
#                     character_request = create_character_request(db, character_data)
#                     print(f"Заявка на персонажа создана: {character_request}")
#
#                 elif action == "approve_request":
#                     # Обрабатываем одобрение заявки и создание персонажа
#                     request_id = data.get("request_id")
#                     await approve_character_request_with_dependencies(db, request_id)
#
#             db.commit()
#             print(f"Сообщение из {queue_name} успешно обработано.")
#
#         except Exception as e:
#             print(f"Ошибка при обработке сообщения из {queue_name}: {e}")
#         finally:
#             db.close()
#
# # Функция для одобрения заявки и создания предварительной записи персонажа
# # Функция для одобрения заявки и создания предварительной записи персонажа
# # Функция для одобрения заявки и создания предварительной записи персонажа
# async def approve_character_request_with_dependencies(db: Session, request_id: int):
#     """
#     Обрабатывает одобрение заявки на персонажа, создает предварительную запись персонажа,
#     отправляет запросы на создание инвентаря, навыков и атрибутов.
#     """
#     # Получаем заявку
#     character_request = db.query(CharacterRequest).filter(CharacterRequest.id == request_id).first()
#     if not character_request:
#         raise Exception("Заявка не найдена")
#
#     # Создаем предварительную запись персонажа
#     new_character = create_preliminary_character(db, character_request)
#     print(f"Создана предварительная запись для персонажа с ID {new_character.id}")
#
#     # Отправляем запросы на создание инвентаря, навыков и атрибутов
#     message = {"character_id": new_character.id}
#
#     print(f"Отправка сообщения в очередь character_inventory_queue для персонажа с ID {new_character.id}")
#     await send_to_rabbitmq("character_inventory_queue", message)
#
#     print(f"Отправка сообщения в очередь character_skills_queue для персонажа с ID {new_character.id}")
#     await send_to_rabbitmq("character_skills_queue", message)
#
#     print(f"Отправка сообщения в очередь character_attributes_queue для персонажа с ID {new_character.id}")
#     await send_to_rabbitmq("character_attributes_queue", message)
#
#     # Ожидаем ответы от всех микросервисов
#     inventory_response = await receive_response_from_queue("inventory_response_queue")
#     skills_response = await receive_response_from_queue("skills_response_queue")
#     attributes_response = await receive_response_from_queue("attributes_response_queue")
#
#     # Проверяем, что все ответы получены
#     if inventory_response and skills_response and attributes_response:
#         # Обновляем запись персонажа с новыми данными
#         print(f"Все ответы получены, обновление персонажа с ID {new_character.id}")
#         update_character_with_dependencies(db, new_character.id,
#                                            inventory_response["inventory_id"],
#                                            skills_response["skills_id"],
#                                            attributes_response["attributes_id"])
#         print(f"Персонаж с ID {new_character.id} успешно создан и обновлен.")
#     else:
#         print("Ошибка: Один из микросервисов не вернул ответ.")
#
#
# # Консюмирование очередей в character-service
# async def consume_character_request_queue():
#     """
#     Подключение к очереди заявок на персонажа и обработка сообщений.
#     """
#     while True:
#         try:
#             connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
#             print(f"Успешное подключение к RabbitMQ для character_request_queue")
#             break
#         except Exception as e:
#             print(f"Ошибка подключения к RabbitMQ для character_request_queue: {e}. Повтор через 5 секунд...")
#             time.sleep(5)
#
#     async with connection:
#         channel = await connection.channel()
#         queue = await channel.declare_queue("character_request_queue", durable=True)
#         print(f"Консюмер подключен к character_request_queue, ожидание сообщений...")
#
#         async for message in queue:
#             await process_message(message, "character_request_queue")
#
# # Главная функция запуска
# async def consume_all_queues():
#     """
#     Запуск всех консюмеров очередей в character-service.
#     """
#     await asyncio.gather(
#         consume_character_request_queue(),
#     )
#
# if __name__ == "__main__":
#     print("Запуск консюмеров для всех очередей в character-service...")
#     asyncio.run(consume_all_queues())
