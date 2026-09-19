# inventory_client.py
import os

import httpx
from config import settings

BASE = settings.INVENTORY_URL.rstrip("/")


def _internal_token_headers() -> dict:
    """Заголовок для обращений в /inventory/internal/* (FEAT-169 §3.3 M3).

    Модуль-локальный хелпер: `main.py` импортирует `inventory_client`, поэтому
    импортировать хелпер оттуда нельзя — будет циклический импорт. Токен
    читается из окружения в момент вызова, как и во всех остальных сервисах.
    """
    return {"X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", "")}

async def get_item(item_id: int) -> dict:
    """Полный шаблон предмета (FEAT-171 I3i).

    Публичный `/inventory/items/{id}` отдаёт тонкую карточку без цифр,
    поэтому бой читает внутренний двойник с X-Internal-Token.
    """
    if item_id <= 0:
        raise ValueError("item_id must be > 0")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/inventory/internal/items/{item_id}",
            headers=_internal_token_headers(),
        )
        r.raise_for_status()
        return r.json()

async def consume_item(character_id: int, item_id: int) -> dict:
    """
    Call inventory-service to consume 1 unit of item from character's inventory.
    Returns {"status": "ok", "remaining_quantity": N} on success,
    or {"status": "error", "detail": "..."} on failure.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{BASE}/inventory/internal/characters/{character_id}/consume_item",
            json={"item_id": item_id},
            headers=_internal_token_headers(),
        )
        if r.status_code != 200:
            try:
                detail = r.json().get("detail", "Unknown error")
            except Exception:
                detail = r.text
            return {"status": "error", "detail": detail}
        return r.json()


DURABILITY_SLOT_TYPES = {"head", "body", "cloak", "main_weapon", "additional_weapons"}


async def get_equipment_durability(character_id: int) -> dict:
    """
    Returns {slot_type: {item_id, current_durability, max_durability}}
    for durability-eligible equipment slots.
    Slots without items or without durability are omitted.

    FEAT-171 I2i: игровой маршрут `/inventory/{id}/equipment` уходит под гейт,
    поэтому прочность читается из внутреннего двойника с X-Internal-Token.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{BASE}/inventory/internal/characters/{character_id}/equipment",
            headers=_internal_token_headers(),
        )
        r.raise_for_status()
        slots = r.json()

    result = {}
    for slot in slots:
        slot_type = slot.get("slot_type")
        item_id = slot.get("item_id")
        if slot_type not in DURABILITY_SLOT_TYPES or not item_id:
            continue
        # Fetch item template to get max_durability
        try:
            item_data = await get_item(item_id)
        except Exception:
            continue
        max_dur = item_data.get("max_durability", 0)
        if max_dur <= 0:
            continue
        # current_durability: NULL means full (= max_durability)
        current_dur = slot.get("current_durability")
        if current_dur is None:
            current_dur = max_dur
        result[slot_type] = {
            "item_id": item_id,
            "current_durability": current_dur,
            "max_durability": max_dur,
        }
    return result


async def update_durability(character_id: int, entries: list[dict]) -> dict:
    """
    Call inventory-service to persist durability changes after battle.
    entries: [{"slot_type": str, "new_durability": int}, ...]
    Best-effort: caller should catch exceptions.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{BASE}/inventory/internal/update-durability",
            json={"character_id": character_id, "entries": entries},
            headers=_internal_token_headers(),
        )
        r.raise_for_status()
        return r.json()


async def get_fast_slots(character_id: int) -> list[dict]:
    """
    Возвращает список быстрых слотов (пояс) со всем, что нужно бою:

    [
      {
        "slot_type": "fast_slot_1",
        "item_id": 3,
        "quantity": 5,
        "name": "...", "image": "...",
        "health_recovery": 30,            # только ненулевые
        "consumable_action": None,        # None | weapon_coating | cleanse
        "coating_turns": None,
        "coating_bonus_damage": None,
        "effects": [...],                 # строки item_effects
        "damage_entries": [...],          # строки item_damage_entries
      }, …
    ]

    FEAT-168: inventory-service отдаёт восстановление и боевую настройку
    предмета прямо в ответе fast_slots, поэтому дозапрос карточки каждого
    предмета больше не нужен. Всё читается через .get(..., default): если
    inventory-service почему-то отдаст старый ответ, слот просто останется
    без боевых эффектов и сработает как раньше.

    Результат снапшотится в состояние боя (Redis, TTL 48 ч) на старте боя.

    FEAT-169: игровой маршрут `/inventory/characters/{id}/fast_slots` закрыт
    JWT и проверкой владения, поэтому бой ходит во внутренний двойник
    `/inventory/internal/characters/{id}/fast_slots` с X-Internal-Token
    (у мобов и НПС владельца нет, проверка владения для них невозможна).
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/inventory/internal/characters/{character_id}/fast_slots",
            headers=_internal_token_headers(),
        )
        r.raise_for_status()
        slots = r.json()

    out = []
    for slot in slots:
        # восстановление кладём, только если оно ненулевое — как и раньше
        rec = {k: slot.get(k, 0) for k in (
            "health_recovery",
            "mana_recovery",
            "energy_recovery",
            "stamina_recovery",
        ) if slot.get(k)}
        out.append({
            "slot_type": slot.get("slot_type"),
            "item_id": slot.get("item_id"),
            "quantity": slot.get("quantity", 0),
            "name": slot.get("name"),
            "image": slot.get("image"),
            **rec,
            "consumable_action": slot.get("consumable_action"),
            "coating_turns": slot.get("coating_turns"),
            "coating_bonus_damage": slot.get("coating_bonus_damage"),
            "effects": slot.get("effects") or [],
            "damage_entries": slot.get("damage_entries") or [],
        })
    return out
