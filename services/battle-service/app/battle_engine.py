"""
Мини-движок: пока умеет только один damage_entry без уклонений и критов.
Дальнейшие функции (dodge / crit / эффекты) появятся по мере реализации.
"""

from __future__ import annotations

from random import random

import httpx
import os
from typing import Dict, Tuple

ATTR_SERVICE_URL = os.getenv(
    "ATTRIBUTES_SERVICE_URL",
    "http://character-attributes-service:8002",
)
INVENTORY_SERVICE_URL = os.getenv(
    "INVENTORY_SERVICE_URL",
    "http://inventory-service:8004",
)
import logging
logger = logging.getLogger(__name__)

# ---------- helpers service calls -----------------------------------------
async def fetch_full_attributes(character_id: int) -> Dict:
    """GET /attributes/{character_id}"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{ATTR_SERVICE_URL}/attributes/{character_id}")
        response.raise_for_status()
        return response.json()


async def fetch_main_weapon(character_id: int) -> Dict | None:
    """Возвращает JSON-описание оружия из слота main_weapon или None."""
    async with httpx.AsyncClient() as client:
        # 1) все слоты экипировки
        equip_resp = await client.get(
            f"{INVENTORY_SERVICE_URL}/inventory/{character_id}/equipment"
        )
        equip_resp.raise_for_status()
        for slot in equip_resp.json():
            if slot["slot_type"] == "main_weapon" and slot["item_id"]:
                # 2) сведения о самом предмете
                item_resp = await client.get(
                    f"{INVENTORY_SERVICE_URL}/inventory/items/{slot['item_id']}"
                )
                item_resp.raise_for_status()
                return item_resp.json()
    return None


# ---------- основной расчёт ------------------------------------------------
async def compute_single_damage_entry(
    damage_entry: Dict,                # один элемент из SkillRank.damage_entries
    attacker_attr: Dict,               # ответа attributes-service
    weapon_item: Dict | None,          # JSON main_weapon или None
    percent_buffs: Dict[str, float],   # {'all':10, 'fire':5, ...}
    defender_resist: Dict,             # attributes-service цели
) -> Tuple[float, Dict]:
    """
    Возвращает кортеж:
      (фактический итоговый урон, log-словарь для battle-log)
    """
    # -------- 1. базовый урон игрока (damage атрибут + weapon) -------------
    base_attack_value: float = attacker_attr["damage"]
    if weapon_item and weapon_item["damage_modifier"]:
        base_attack_value += weapon_item["damage_modifier"]

    # -------- 2. определяем финальный damage_type -------------------------
    damage_type: str = damage_entry["damage_type"]
    if damage_type == "all":
        damage_type = (
            weapon_item["primary_damage_type"]
            if weapon_item
            else "physical"
        )

    # -------- 3. «сырое» значение -----------------------------------------
    raw_damage: float = base_attack_value + damage_entry["amount"]

    # -------- 4. применяем баффы % на общий и конкретный тип --------------
    buff_percent = percent_buffs.get("all", 0.0) + percent_buffs.get(
        damage_type, 0.0
    )
    raw_damage *= 1 + buff_percent / 100.0

    # -------- 5. сопротивления цели ---------------------------------------
    resist_field = f"res_{damage_type}"
    resist_percent = (
        defender_resist.get(resist_field, 0.0)
        + defender_resist.get("res_effects", 0.0)
    )
    final_damage = raw_damage * (1 - resist_percent / 100.0)

    # -------- 6. строим лог-объект ----------------------------------------
    log_entry = {
        "damage_type": damage_type,
        "raw": round(raw_damage, 2),
        "resist_percent": resist_percent,
        "final": round(final_damage, 2),
    }
    return final_damage, log_entry

def roll_dodge(dodge_percent: float) -> bool:
    """True — уклонился."""
    return random() < dodge_percent / 100.0


def roll_crit(crit_chance_percent: float) -> bool:
    return random() < crit_chance_percent / 100.0


def roll_chance(chance_percent: float) -> bool:
    return random() < chance_percent / 100.0


async def compute_damage_with_rolls(
    damage_entry: Dict,
    attacker_attr: Dict,
    weapon: Dict | None,
    percent_buffs: Dict[str, float],
    defender_attr: Dict,
    percent_resists: Dict[str, float],    # ← НОВОЕ
) -> Tuple[float, Dict]:
    """
    • roll_dodge, roll_chance, roll_crit
    • применяет +%баффы, криты, −%резисты
    """
    # 1) базовый урон
    base = attacker_attr["damage"] + (weapon["damage_modifier"] if weapon else 0)
    dmg_type = damage_entry["damage_type"]
    if dmg_type == "all":
        dmg_type = weapon["primary_damage_type"] if weapon else "physical"

    raw = base + damage_entry["amount"]
    buff_pct = percent_buffs.get("all", 0) + percent_buffs.get(dmg_type, 0)
    raw *= 1 + buff_pct / 100

    log = {
        "damage_type": dmg_type,
        "base": base,
        "entry": damage_entry["amount"],
        "buff_pct": buff_pct,
        "after_buffs": round(raw, 2),
    }

    # dodge
    if roll_dodge(defender_attr["dodge"]):
        log["dodged"] = True
        return 0.0, log
    log["dodged"] = False

    # hit chance
    if not roll_chance(damage_entry["chance"]):
        log["hit_chance_failed"] = True
        return 0.0, log
    log["hit_chance_failed"] = False

    # crit
    if roll_crit(attacker_attr["critical_hit_chance"]):
        crit_mul = attacker_attr["critical_damage"] / 100.0
        raw *= crit_mul
        log["critical"] = True
        log["crit_mul"] = crit_mul
    else:
        log["critical"] = False

    # resist
    resist_pct = percent_resists.get("all", 0) + percent_resists.get(dmg_type, 0)
    final = raw * (1 - resist_pct / 100.0)
    log.update({
        "resist_pct": resist_pct,
        "final": round(final, 2),
    })

    return final, log


def apply_flat_modifiers(attributes: Dict, modifiers: Dict[str, float]) -> Dict:
    """
    Создаёт копию attributes с +modifiers (flat); проценты уже учтены заранее.
    """
    new_attr = dict(attributes)
    for key, delta in modifiers.items():
        new_attr[key] = new_attr.get(key, 0) + delta
    return new_attr

def set_cooldown(state: dict, pid: int, rank_id: int, cd: int) -> None:
    """Записываем новый кулдаун ранга."""
    p = state["participants"][str(pid)]
    p.setdefault("cooldowns", {})            # ← уже есть при init, но на всякий
    p["cooldowns"][str(rank_id)] = cd


def decrement_cooldowns(state: dict) -> None:
    """
    В конце хода пробегаемся по всем участникам и уменьшаем
    оставшиеся кулдауны. 0 → удаляем ключ.
    """
    for p in state["participants"].values():
        cd_map = p.get("cooldowns", {})
        to_delete = []
        for rank_id, remaining in cd_map.items():
            new_val = remaining - 1
            if new_val <= 0:
                to_delete.append(rank_id)
            else:
                cd_map[rank_id] = new_val
        for rid in to_delete:
            cd_map.pop(rid, None)
