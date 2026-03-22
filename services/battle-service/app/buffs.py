# buffs.py
from typing import Dict, List

# ──────────────────────────────────────────────────────────
def _normalize_effect(row: Dict) -> Dict:
    """
    Разворачивает JSON-строку из БД в единый формат:
        {name, attribute, magnitude, duration}
    """
    ALIASES = {"crit_chance": "critical_hit_chance"}
    name      = row["effect_name"]
    magnitude = row["magnitude"]
    duration  = row["duration"]

    if row.get("attribute_key"):  # StatModifier
        attribute = ALIASES.get(row["attribute_key"], row["attribute_key"])
    else:
        parts = [s.strip().lower() for s in name.split(":", 1)]
        if len(parts) == 2:
            kind, tail = parts
            if kind == "buff":
                attribute = "percent_damage" if tail == "all" else f"percent_damage_{tail}"
            elif kind == "resist":
                attribute = f"percent_resist_{tail}"
            else:
                attribute = name.replace(" ", "_").lower()
        else:
            attribute = name.replace(" ", "_").lower()

    return {
        "name"      : name,
        "attribute" : attribute,
        "magnitude" : magnitude,
        "duration"  : duration,
    }


def apply_new_effects(state: Dict, pid: int, raw_effect_rows: List[Dict], is_enemy: bool = False) -> None:
    """
    • Для hp/mana/energy/stamina — применяем сразу (clamp 0..max_*)
    • Для остальных — нормализуем и добавляем в active_effects[pid]
    • is_enemy=True — эффекты применяются к врагу (положительные мгновенные
      значения инвертируются в урон, чтобы не лечить противника)
    """
    inst_attrs = {"hp", "mana", "energy", "stamina"}
    aid = str(pid)

    for row in raw_effect_rows:
        eff = _normalize_effect(row)
        if eff["attribute"] in inst_attrs:
            magnitude = eff["magnitude"]
            # Вражеские эффекты с положительной magnitude на HP/mana/etc
            # должны наносить урон, а не лечить
            if is_enemy and magnitude > 0:
                magnitude = -magnitude
            part = state["participants"][aid]
            mx = part[f"max_{eff['attribute']}"]
            new = part[eff["attribute"]] + magnitude
            part[eff["attribute"]] = max(0, min(mx, new))
        else:
            state.setdefault("active_effects", {}).setdefault(aid, []).append(eff)


def decrement_durations(state: Dict) -> None:
    """
    Каждый ход уменьшаем duration всех активных эффектов,
    удаляем, когда duration == 0.
    """
    for pid, lst in list(state.get("active_effects", {}).items()):
        new_lst = []
        for eff in lst:
            eff["duration"] -= 1
            if eff["duration"] > 0:
                new_lst.append(eff)
        state["active_effects"][pid] = new_lst


def aggregate_modifiers(effects_for_participant: List[Dict]) -> Dict[str, float]:
    """
    Складывает magnitude по ключам attribute.
    """
    summary: Dict[str, float] = {}
    for eff in effects_for_participant:
        summary[eff["attribute"]] = summary.get(eff["attribute"], 0.0) + eff["magnitude"]
    return summary


def build_percent_damage_buffs(mods: Dict[str, float]) -> Dict[str, float]:
    """
    Из aggregated modifiers достаёт только percent_damage*.
    """
    out: Dict[str, float] = {}
    for k, v in mods.items():
        if k == "percent_damage":
            out["all"] = v
        elif k.startswith("percent_damage_"):
            out[k[len("percent_damage_"):]] = v
    return out


def build_percent_resist_buffs(mods: Dict[str, float]) -> Dict[str, float]:
    """
    Из aggregated modifiers достаёт только percent_resist*.
    """
    out: Dict[str, float] = {}
    for k, v in mods.items():
        if k == "percent_resist":
            out["all"] = v
        elif k.startswith("percent_resist_"):
            out[k[len("percent_resist_"):]] = v
    return out
