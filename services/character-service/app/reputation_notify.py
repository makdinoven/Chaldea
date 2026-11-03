"""FEAT-197: tier-change notifications (sync pika -> ``general_notifications``, category ``progress``).

Best-effort: a RabbitMQ failure is logged and swallowed (the reputation change itself is already committed).
Call ONLY after the caller's commit. Sync on purpose (the callers are sync DB code / threadpool workers); from an
``async def`` route wrap it in ``run_in_threadpool``. Messages carry no numbers (§3.3).
"""

import json
import logging
from typing import Iterable, List

import pika

from config import settings

logger = logging.getLogger("character-service.reputation_notify")

QUEUE_NAME = "general_notifications"
CATEGORY_PROGRESS = "progress"
CONNECT_TIMEOUT_SECONDS = 3

MSG_UP = "Жители края «{region}» теперь считают вас: {tier}"
MSG_DOWN = "Жители края «{region}» стали относиться к вам хуже: теперь вы — {tier}"
MSG_DECAY = "Жители края «{region}» понемногу забывают ваши проступки: теперь вы — {tier}"


def message_for(change) -> str:
    region = change.region_name or "этого края"
    template = {"up": MSG_UP, "down": MSG_DOWN, "decay": MSG_DECAY}.get(change.direction, MSG_UP)
    return template.format(region=region, tier=change.tier_after_name)


def build_payloads(changes: Iterable) -> List[dict]:
    payloads = []
    for change in changes:
        if not change.user_id:
            continue
        payloads.append({
            "target_type": "user",
            "target_value": int(change.user_id),
            "message": message_for(change),
            "category": CATEGORY_PROGRESS,
        })
    return payloads


def _send(payloads: List[dict]) -> None:
    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.socket_timeout = CONNECT_TIMEOUT_SECONDS
    params.connection_attempts = 1
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        for payload in payloads:
            channel.basic_publish(exchange="", routing_key=QUEUE_NAME, body=json.dumps(payload),
                                  properties=pika.BasicProperties(delivery_mode=2))
    finally:
        connection.close()


def publish_tier_changes(changes: Iterable) -> int:
    """Publish one notification per tier change of a player; returns how many were sent (0 on failure)."""
    payloads = build_payloads(changes or ())
    if not payloads:
        return 0
    try:
        _send(payloads)
        return len(payloads)
    except Exception:
        logger.warning("reputation tier notifications not sent (%d)", len(payloads), exc_info=True)
        return 0
