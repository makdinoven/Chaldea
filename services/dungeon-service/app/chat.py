"""
The run's chat and log (FEAT-176): what the party says to each other, and a
line for everything that happens — moves, traps and who took how much,
battles, who is doing what. Kept in Redis for the run only.

Most log lines come from the run's own WS events (ws_manager hands every
broadcast here); a few are written straight from gameplay where the events
lack the detail (who took how much from an ambush's first blow).
"""

import json
import logging
import re
import time
import uuid
from typing import Dict, List, Optional

import session_state
import ws_manager

logger = logging.getLogger(__name__)

CHAT_MAX_LEN = 300
# Lines kept for a run (older ones drop off).
CHAT_KEEP = 200
SAY_COOLDOWN_SECONDS = 1

TONE_INFO = "info"
TONE_GOOD = "good"
TONE_BAD = "bad"

# Who is busy with what (a challenge started), by kind.
DOING = {
    "lockpick": "взламывает замок",
    "mechanism": "ищет скрытый механизм",
    "illusion": "рассеивает иллюзию",
    "rubble": "разбирает завал",
    "shield": "поднимает щит",
    "gate": "держит проход",
    "seal": "снимает печать",
    "search": "обыскивает комнату",
    "watch": "встаёт в дозор",
    "scout": "крадётся разведать путь",
    "disarm": "обезвреживает ловушку",
    "insight": "вчитывается в знаки",
}


def _entry(kind: str, text: str, tone: str = TONE_INFO, character_id: Optional[int] = None,
           name: Optional[str] = None) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "at": int(time.time() * 1000),
        "kind": kind,
        "text": text,
        "tone": tone,
        "character_id": character_id,
        "name": name,
    }


async def _publish(session_id: int, entry: dict) -> dict:
    await session_state.push_chat(session_id, entry, CHAT_KEEP)
    await ws_manager.broadcast_to_session(session_id, {"type": "chat_message", "data": entry})
    return entry


async def log(session_id: int, text: str, tone: str = TONE_INFO) -> None:
    """A line in the run's log. Never fails the action that wrote it."""
    if not text:
        return
    try:
        await _publish(session_id, _entry("log", text, tone))
    except Exception:
        logger.warning("Сессия %d: запись в журнал не удалась", session_id, exc_info=True)


async def say(session_id: int, character_id: int, name: str, text: str) -> dict:
    """A party member's line in the chat (the caller checks membership and the rate)."""
    return await _publish(session_id, _entry("say", text, TONE_INFO, character_id, name))


async def history(session_id: int, limit: int = CHAT_KEEP) -> List[dict]:
    return await session_state.get_chat(session_id, limit)


# ---------------------------------------------------------------- from the run's events

async def _names(ids: List[int]) -> Dict[int, str]:
    import gameplay  # late: gameplay imports this module
    return {cid: await gameplay._character_name(cid) for cid in ids}


async def _damage_line(report) -> str:
    """"Урон: Аэлис −5, Ашари −5" from a damage report (only those who took any)."""
    hurt = [r for r in (report or []) if isinstance(r, dict) and r.get("damage")]
    if not hurt:
        return ""
    names = await _names([r["character_id"] for r in hurt])
    return "Урон: " + ", ".join(f"{names[r['character_id']]} −{r['damage']}" for r in hurt) + "."


def _msg(data: dict) -> str:
    return str(data.get("message") or "").strip()


async def from_event(session_id: int, event: dict) -> None:
    """Turn a run's WS event into log lines (ws_manager calls this for every broadcast)."""
    kind = event.get("type")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    try:
        if kind in (None, "chat_message", "party_vote", "party_ping"):
            return
        if kind == "room_entered":
            await _room_entered(session_id, data)
        elif kind == "trap_triggered":
            damage = await _damage_line(data.get("damage_report"))
            # Who took how much says it better than the trap's own "Урон: N.".
            text = re.sub(r"\s*Урон: \d+\.", "", _msg(data)) if damage else _msg(data)
            await log(session_id, " ".join(x for x in (text, damage) if x),
                      TONE_GOOD if data.get("passed") else TONE_BAD)
        elif kind == "battle_started":
            names = ", ".join(data.get("mob_names") or [])
            await log(session_id, f"{_msg(data) or 'Бой начинается!'}" + (f" Противники: {names}." if names else ""),
                      TONE_BAD)
        elif kind == "battle_ended":
            await log(session_id, _msg(data), TONE_GOOD if data.get("party_won") else TONE_BAD)
        elif kind == "member_status_changed":
            status = data.get("status") or data.get("new_status")
            name = data.get("name") or "Участник"
            await log(session_id, f"{name} выбывает из строя." if status == "dead" else f"{name} снова в строю.",
                      TONE_BAD if status == "dead" else TONE_GOOD)
        elif kind == "challenge_started":
            doing = DOING.get(str(data.get("kind")), "берётся за дело")
            await log(session_id, f"{data.get('name') or 'Участник'} {doing}…")
        elif kind == "challenge_finished":
            await log(session_id, _msg(data), TONE_GOOD if data.get("passed") else TONE_BAD)
        elif kind == "rest_completed":
            await log(session_id, _msg(data), TONE_BAD if data.get("raided") else TONE_GOOD)
        elif kind in ("loot_added", "key_found", "loot_distributed", "item_given"):
            await log(session_id, _msg(data), TONE_GOOD)
        elif kind in ("teleport_failed", "battle_error"):
            await log(session_id, _msg(data), TONE_BAD)
        else:
            await log(session_id, _msg(data))
    except Exception:
        logger.warning("Сессия %d: журнал не разобрал событие %s", session_id, kind, exc_info=True)


async def _room_entered(session_id: int, data: dict) -> None:
    """Into a room. A move by the leader is told as it sets off (gameplay writes it before the corridor's events);
    here only arrivals that are not such a move: a teleport, the way on after a corridor fight."""
    if data.get("from_room_name"):
        return
    room = data.get("room") if isinstance(data.get("room"), dict) else {}
    to_name = room.get("name") or "?"
    if data.get("teleported"):
        await log(session_id, _msg(data) or f"Отряд переносится в «{to_name}».")
        return
    await log(session_id, f"Отряд входит в «{to_name}».")


ws_manager.add_listener(from_event)
