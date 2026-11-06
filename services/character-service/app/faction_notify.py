"""FEAT-205 faction notifications (sync pika -> ``general_notifications``), cloned from ``reputation_notify``.

Best-effort: a RabbitMQ failure is logged and swallowed (the faction change itself is already committed). Call ONLY
after the caller's commit. Sync on purpose; from an ``async def`` route wrap it in ``run_in_threadpool``.
Category ``progress`` for joins / rank-ups / points, ``system`` for warnings and expulsions. Notices go only to the
character's owner (secret membership never leaves the owner).
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import pika

from config import settings

logger = logging.getLogger("character-service.faction_notify")

QUEUE_NAME = "general_notifications"
CATEGORY_PROGRESS = "progress"
CATEGORY_SYSTEM = "system"
CONNECT_TIMEOUT_SECONDS = 3

WS_TYPE = "faction"


@dataclass
class Notice:
    user_id: Optional[int]
    message: str
    category: str = CATEGORY_PROGRESS
    data: dict = field(default_factory=dict)


def _payload(notice: Notice) -> dict:
    return {
        "target_type": "user",
        "target_value": int(notice.user_id),
        "message": notice.message,
        "category": notice.category,
        "ws_type": WS_TYPE,
        "ws_data": dict(notice.data or {}),
    }


def build_payloads(notices: Iterable[Notice]) -> List[dict]:
    return [_payload(n) for n in (notices or ()) if n is not None and n.user_id]


def _send(payloads: List[dict]) -> None:
    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.socket_timeout = CONNECT_TIMEOUT_SECONDS
    params.connection_attempts = 1
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        for payload in payloads:
            channel.basic_publish(exchange="", routing_key=QUEUE_NAME, body=json.dumps(payload, default=str),
                                  properties=pika.BasicProperties(delivery_mode=2))
    finally:
        connection.close()


def publish(notices: Iterable[Notice]) -> int:
    """Publish the notices; returns how many were sent (0 on failure / nothing to send)."""
    payloads = build_payloads(notices)
    if not payloads:
        return 0
    try:
        _send(payloads)
        return len(payloads)
    except Exception:
        logger.warning("faction notifications not sent (%d)", len(payloads), exc_info=True)
        return 0
