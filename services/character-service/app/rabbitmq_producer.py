import aio_pika
import json
from .config import settings


async def send_to_rabbitmq(queue_name: str, message: dict):
    """
    Отправляет сообщение в указанную очередь RabbitMQ.

    :param queue_name: Название очереди.
    :param message: Сообщение для отправки.
    """
    try:
        # Устанавливаем соединение с RabbitMQ
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)

        async with connection:
            # Открываем канал
            channel = await connection.channel()

            # Декларируем очередь (если её ещё нет)
            queue = await channel.declare_queue(queue_name, durable=True)

            # Публикуем сообщение в очередь
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(message).encode()),
                routing_key=queue_name
            )
        print(f"Сообщение отправлено в {queue_name}: {message}")
    except Exception as e:
        print(f"Ошибка при отправке сообщения в RabbitMQ: {e}")
