"""
Мини-движок: пока умеет только один damage_entry без уклонений и критов.
Дальнейшие функции (dodge / crit / эффекты) появятся по мере реализации.
"""

from __future__ import annotations

from random import random

import httpx
import os
from typing import Dict, Optional, Tuple

ATTR_SERVICE_URL = os.getenv(
    "ATTRIBUTES_SERVICE_URL",
    "http://character-attributes-service:8002",
)
INVENTORY_SERVICE_URL = os.getenv(
    "INVENTORY_SERVICE_URL",
    "http://inventory-service:8004",
)
import logging
from stat_caps import effective_stat
logger = logging.getLogger(__name__)


def _internal_token_headers() -> dict:
    """Заголовок для обращений во внутренние двойники соседних сервисов.

    FEAT-171 §3.5: боевой движок ходит в `/attributes/internal/*` и
    `/inventory/internal/*` — у боя нет пользователя в контексте (мобы и НПС
    вообще не имеют владельца). Токен читается из окружения в момент вызова,
    как и в `inventory_client._internal_token_headers`.
    """
    return {"X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", "")}


# ---------- helpers service calls -----------------------------------------
async def fetch_full_attributes(character_id: int) -> Dict:
    """GET /attributes/internal/{character_id} (FEAT-171 A1i)."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ATTR_SERVICE_URL}/attributes/internal/{character_id}",
            headers=_internal_token_headers(),
        )
        response.raise_for_status()
        return response.json()


async def fetch_weapons(character_id: int) -> Dict[str, Dict | None]:
    """
    Возвращает оружие из обоих слотов: main_weapon и additional_weapons.
    Один HTTP-вызов к equipment + до 2 вызовов item details.
    Результат: {"main_weapon": <item_dict or None>, "additional_weapons": <item_dict or None>}
    """
    result: Dict[str, Dict | None] = {"main_weapon": None, "additional_weapons": None}
    weapon_slots = ("main_weapon", "additional_weapons")

    async with httpx.AsyncClient() as client:
        # FEAT-171 I2i: игровой маршрут /inventory/{id}/equipment уходит под
        # гейт, бой читает внутренний двойник с X-Internal-Token.
        equip_resp = await client.get(
            f"{INVENTORY_SERVICE_URL}/inventory/internal/characters/{character_id}/equipment",
            headers=_internal_token_headers(),
        )
        equip_resp.raise_for_status()

        for slot in equip_resp.json():
            slot_type = slot["slot_type"]
            if slot_type in weapon_slots and slot["item_id"]:
                # FEAT-171 I3i: публичная карточка предмета стала тонкой,
                # бою нужен полный шаблон — идём во внутренний двойник.
                item_resp = await client.get(
                    f"{INVENTORY_SERVICE_URL}/inventory/internal/items/{slot['item_id']}",
                    headers=_internal_token_headers(),
                )
                item_resp.raise_for_status()
                # effective_damage — единственный источник урона оружия (FEAT-167):
                # шаблонный damage_modifier + заточка + камни этого оружия,
                # 0.0 у сломанного предмета. Считает inventory-service.
                result[slot_type] = {
                    **item_resp.json(),
                    "effective_damage": float(slot.get("effective_damage") or 0.0),
                }

    return result


async def fetch_main_weapon(character_id: int) -> Dict | None:
    """Возвращает JSON-описание оружия из слота main_weapon или None.
    Обёртка над fetch_weapons() для обратной совместимости."""
    weapons = await fetch_weapons(character_id)
    return weapons.get("main_weapon")


# ---------- class → main attribute mapping ----------------------------------
CLASS_MAIN_ATTRIBUTE = {1: "strength", 2: "agility", 3: "intelligence"}

# ---------- luck → offensive procs (FEAT-195) --------------------------------
LUCK_PROC_PER_POINT = 0.1  # +0.1 pp per EFFECTIVE point of luck


def luck_proc_bonus(attrs: Dict) -> float:
    """Percentage points luck adds to the attacker's hit roll and effect procs:
    0.1 * eff(luck) (soft cap 100, hard cap 200 — stat_caps.effective_stat).
    Not added to the crit roll: the stored critical_hit_chance already
    contains luck (FEAT-195 fix — luck used to be counted twice in crit)."""
    return LUCK_PROC_PER_POINT * effective_stat((attrs or {}).get("luck", 0))

# ---------- основной расчёт ------------------------------------------------
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
    percent_resists: Dict[str, float],
    class_id: int = 1,
    apply_dodge: bool = True,
    force_crit: bool = False,
    crit_damage_bonus: float = 0,
    resist_ignore: Optional[Dict[str, float]] = None,
) -> Tuple[float, Dict]:
    """
    • roll_dodge, roll_chance, roll_crit
    • применяет +%баффы, криты, −%резисты
    • class_id определяет основной атрибут урона (1=strength, 2=agility, 3=intelligence);
      FEAT-195: в урон идёт eff(атрибут) — убывающая отдача выше 100 и 200
    • luck атакующего добавляет 0.1% за эффективную единицу к шансу попадания;
      в крит удача уже входит через сохранённый critical_hit_chance

    FEAT-189 (subclass passives, all optional — defaults keep the old
    behaviour and the old log shape):
    • force_crit — the hit is a crit without rolling (the hit roll must still
      land; the crit roll is NOT consumed); log["forced_crit"] = True.
    • crit_damage_bonus — added to critical_damage before /100 on any crit
      (+50 at the default 125 ⇒ ×1.75).
    • resist_ignore — {resolved damage type: fraction 0..1}; ignores that
      share of a POSITIVE resist only (vulnerability is never reduced);
      log["resist_ignored_pct"] = points ignored.
    """
    # 1) базовый урон = основной атрибут класса + база damage + урон оружия слота.
    #    FEAT-167: урон оружия учитывается РОВНО ОДИН РАЗ и берётся только из
    #    effective_damage (его считает inventory-service: шаблон + заточка + камни,
    #    0.0 у сломанного). В attacker_attr["damage"] урона оружия больше нет,
    #    поэтому weapon=None (навык no_weapon) даёт честный безоружный урон.
    #    FEAT-195: основной атрибут идёт через eff() (attacker_attr уже содержит
    #    баффы и пассивки, т.е. кап считается от суммы).
    main_attr_key = CLASS_MAIN_ATTRIBUTE.get(class_id, "strength")
    base_stat = effective_stat(attacker_attr.get(main_attr_key, 0))
    damage_bonus = attacker_attr.get("damage", 0)
    weapon_dmg = float(weapon.get("effective_damage") or 0.0) if weapon else 0.0
    base = max(0, base_stat + damage_bonus + weapon_dmg)
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

    # luck bonus: +0.1% per effective point of luck to the hit roll (FEAT-195)
    luck_bonus = luck_proc_bonus(attacker_attr)

    # dodge — optional here so the caller can roll it ONCE per attack instead of
    # per damage_entry (avoids "dodged" + a landed hit in the same attack).
    if apply_dodge:
        if roll_dodge(defender_attr["dodge"]):
            log["dodged"] = True
            return 0.0, log
        log["dodged"] = False

    # hit chance (luck improves hit chance for attacker)
    if not roll_chance(damage_entry["chance"] + luck_bonus):
        log["hit_chance_failed"] = True
        return 0.0, log
    log["hit_chance_failed"] = False

    # crit: the stored critical_hit_chance (+ buff deltas) already contains
    # 0.1 * eff(luck) — luck is NOT added a second time (FEAT-195).
    if force_crit or roll_crit(attacker_attr["critical_hit_chance"]):
        crit_mul = (attacker_attr["critical_damage"] + crit_damage_bonus) / 100.0
        raw *= crit_mul
        log["critical"] = True
        log["crit_mul"] = crit_mul
        if force_crit:
            log["forced_crit"] = True
    else:
        log["critical"] = False

    # resist
    resist_pct = percent_resists.get("all", 0) + percent_resists.get(dmg_type, 0)
    if resist_ignore and resist_pct > 0:
        ignore_frac = min(1.0, max(0.0, float(resist_ignore.get(dmg_type, 0) or 0)))
        if ignore_frac > 0:
            ignored = resist_pct * ignore_frac
            resist_pct -= ignored
            log["resist_ignored_pct"] = round(ignored, 2)
    final = raw * (1 - resist_pct / 100.0)
    # Урон не может быть отрицательным (отрицательный урон = лечение врага)
    final = max(0.0, final)
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

def set_cooldown(state: dict, pid: int, skill_id: int, cd: int) -> None:
    """Записываем новый кулдаун навыка (FEAT-125: ключ — skill_id)."""
    p = state["participants"][str(pid)]
    p.setdefault("cooldowns", {})
    p["cooldowns"][str(skill_id)] = cd


def decrement_cooldowns(state: dict) -> None:
    """
    В конце хода пробегаемся по всем участникам и уменьшаем
    оставшиеся кулдауны. 0 → удаляем ключ.
    """
    for p in state["participants"].values():
        cd_map = p.get("cooldowns", {})
        to_delete = []
        for skill_id, remaining in cd_map.items():
            new_val = remaining - 1
            if new_val <= 0:
                to_delete.append(skill_id)
            else:
                cd_map[skill_id] = new_val
        for sid in to_delete:
            cd_map.pop(sid, None)
