"""FEAT-198 law notifications (sync pika -> ``general_notifications``; §3.8).

Best-effort: a RabbitMQ failure is logged and swallowed (the law change itself is already committed). Call ONLY after
the caller's commit. Sync on purpose; from an ``async def`` route wrap the call in ``run_in_threadpool``.

Category ``system`` (mandatory) for encounters, jail and release; ``progress`` for a wanted level raised by a crime.
``ws_type`` lets the frontend refresh ``/users/me`` and the law state. Messages carry no raw wanted numbers.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional

import pika

import activity_lock
from config import settings

logger = logging.getLogger("character-service.law_notify")

QUEUE_NAME = "general_notifications"
CATEGORY_SYSTEM = "system"
CATEGORY_PROGRESS = "progress"
CONNECT_TIMEOUT_SECONDS = 3

WS_ENCOUNTER = "law_encounter"
WS_JAILED = "law_jailed"
WS_RELEASED = "law_released"
WS_WANTED = "law_wanted"
WS_RESOLVED = "law_resolved"
# FEAT-199 (§3.8)
WS_UNSEEN = "law_unseen"
WS_MASKED = "law_masked"
WS_REVEALED = "law_revealed"
WS_FAME_TIER = "fame_tier"

MSG_UNSEEN = "Похоже, никто не видел, что произошло"
MSG_MASKED = "Свидетели видели лишь неизвестного в маске"


@dataclass
class Notice:
    """One message to the owner of a character (``user_id`` None = NPC / no owner -> skipped)."""
    user_id: Optional[int]
    message: str
    ws_type: str
    category: str = CATEGORY_SYSTEM
    data: dict = field(default_factory=dict)


def region_label(name: Optional[str]) -> str:
    return f"«{name}»" if name else "этого края"


def wanted_message(region_name: Optional[str], level_name: str) -> str:
    return f"Вас разыскивают в крае {region_label(region_name)}: {level_name}"


def revealed_message(region_name: Optional[str]) -> str:
    return f"Ваше преступление в крае {region_label(region_name)} раскрыто — стража знает, кто это был"


def remaining(value: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Relative time left («3 д 4 ч», «5 ч 10 мин») — player text never shows clock times (§3.14-ANSWERED A8)."""
    if value is None:
        return "—"
    return activity_lock.format_remaining(value, now)


def encounter_message(region_name: Optional[str], expires_at: Optional[datetime],
                      now: Optional[datetime] = None) -> str:
    return (f"Стража края {region_label(region_name)} остановила вас. Решите, как поступить, "
            f"в течение {remaining(expires_at, now)}")


def jailed_message(region_name: Optional[str], until: Optional[datetime], now: Optional[datetime] = None) -> str:
    return f"Стража края {region_label(region_name)} заключила вас под стражу — срок {remaining(until, now)}"


def _payload(notice: Notice) -> dict:
    return {
        "target_type": "user",
        "target_value": int(notice.user_id),
        "message": notice.message,
        "category": notice.category,
        "ws_type": notice.ws_type,
        "ws_data": dict(notice.data or {}),
    }


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
    """Publish the notices of players; returns how many were sent (0 on failure)."""
    payloads = [_payload(n) for n in (notices or ()) if n is not None and n.user_id]
    if not payloads:
        return 0
    try:
        _send(payloads)
        return len(payloads)
    except Exception:
        logger.warning("law notifications not sent (%d)", len(payloads), exc_info=True)
        return 0


def wanted_notices(changes: Iterable) -> List[Notice]:
    """``law_crud.WantedChange`` -> «Вас разыскивают…» when the level went up."""
    out = []
    for change in changes or ():
        if not change.user_id or not change.level_raised:
            continue
        out.append(Notice(change.user_id, wanted_message(change.region_name, change.level_after_name), WS_WANTED,
                          CATEGORY_PROGRESS, {"region_id": change.region_id, "character_id": change.character_id}))
    return out


def publish_wanted_changes(changes: Iterable) -> int:
    return publish(wanted_notices(changes))
