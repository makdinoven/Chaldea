"""
Хранение и пересчёт баффов/дебаффов.
Каждый эффект мы кладём в Redis-state:

state["active_effects"] = {
    "<participant_id>": [
        {
            "effect_id":   17,
            "attribute":   "res_fire",   # attribute_key
            "magnitude":   10,           # величина (пока «плоская»)
            "remaining":   3             # ходов до исчезновения
        }, ...
    ]
}
"""
from __future__ import annotations
from typing import Dict, List


def aggregate_modifiers(effects_for_participant: List[Dict]) -> Dict[str, float]:
    """
    Суммирует модификаторы; percent_damage_* агрегирует отдельно,
    чтобы battle_engine смог использовать как {'all':…, 'fire':…}
    """
    summary: Dict[str, float] = {}
    for eff in effects_for_participant:
        key = eff["attribute"]
        mag = eff["magnitude"]
        summary[key] = summary.get(key, 0.0) + mag
    return summary

def build_percent_damage_buffs(mods: dict[str, float]) -> dict[str, float]:
    """
    Выдёргивает ключи вида
      • percent_damage         → {'all': value}
      • percent_damage_fire    → {'fire': value}
    и возвращает {'all': …, 'fire': …}
    """
    out: dict[str, float] = {}
    for key, val in mods.items():
        if not key.startswith("percent_damage"):
            continue
        if key == "percent_damage":
            out["all"] = val
        else:
            dmg_type = key[len("percent_damage_"):]
            out[dmg_type] = val
    return out



def decrement_durations(state: Dict) -> None:
    """
    Для каждого участника уменьшаем remaining; если 0 — удаляем.
    """
    if "active_effects" not in state:
        return
    for pid, eff_list in state["active_effects"].items():
        updated = []
        for eff in eff_list:
            eff["remaining"] -= 1
            if eff["remaining"] > 0:
                updated.append(eff)
        state["active_effects"][pid] = updated


def apply_new_effects(
    state: Dict,
    target_participant_id: int,
    new_effects: List[Dict],
) -> None:
    """
    Добавляет эффекты (из SkillRankEffect) к участнику.
    new_effects: [{effect_id, attribute_key, magnitude, duration}, ...]
    """
    if "active_effects" not in state:
        state["active_effects"] = {}
    eff_list = state["active_effects"].setdefault(str(target_participant_id), [])
    for eff in new_effects:
        eff_list.append(
            {
                "effect_id": eff["id"],
                "attribute": eff["attribute_key"],
                "magnitude": eff["magnitude"],
                "remaining": eff["duration"],
            }
        )
