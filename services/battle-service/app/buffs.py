# buffs.py
from typing import Dict, List


# ──────────────────────────────────────────────────────────
# 1.  «Разворачиваем» JSON-эффект из БД → рабочий формат
# ──────────────────────────────────────────────────────────
def _normalize_effect(row: Dict) -> Dict:
    """
    БД хранит строки вида:
        effect_name      = "Buff: all" / "Resist: physical" / "StatModifier"
        attribute_key    = dodge_chance / crit_chance / NULL
        magnitude        = ±N
        duration         = ходов
    На выходе должно быть:
        {"name":…, "attribute":…, "magnitude":…, "duration":…}

    Правила:
      • Buff: all            → attribute = "percent_damage"
      • Buff: <type>         → percent_damage_<type>
      • Resist: all|magic…   → percent_resist_<type>
      • StatModifier         → attribute_key (из колонки)
    """
    name      = row["effect_name"]
    magnitude = row["magnitude"]
    duration  = row["duration"]

    if row.get("attribute_key"):                     # StatModifier
        attribute = row["attribute_key"]
    else:
        kind, tail = [s.strip().lower() for s in name.split(":", 1)]
        if kind == "buff":
            attribute = (
                "percent_damage"
                if tail == "all"
                else f"percent_damage_{tail}"
            )
        elif kind == "resist":
            attribute = f"percent_resist_{tail}"
        else:                                        # Poison, etc.
            attribute = name.replace(" ", "_").lower()

    return {
        "name"      : name,
        "attribute" : attribute,
        "magnitude" : magnitude,
        "duration"  : duration,
    }


# ──────────────────────────────────────────────────────────
def apply_new_effects(state: Dict, pid: int, raw_effect_rows: List[Dict]) -> None:
    """
    Добавляет эффекты к `active_effects[pid]`, разворачивая их через
    _normalize_effect().  Если группа для участника отсутствует ─ создаём.
    """
    norm = [_normalize_effect(row) for row in raw_effect_rows]
    eff_list = state.setdefault("active_effects", {}).setdefault(str(pid), [])
    eff_list.extend(norm)


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
    Суммируем модификаторы (attribute → Σ magnitude)
    """
    summary: Dict[str, float] = {}
    for eff in effects_for_participant:
        key = eff["attribute"]
        summary[key] = summary.get(key, 0.0) + eff["magnitude"]
    return summary


def build_percent_damage_buffs(mods: Dict[str, float]) -> Dict[str, float]:
    """
    Из агрегированного словаря достаём только percent_damage*.
    """
    out = {}
    for k, v in mods.items():
        if k == "percent_damage":
            out["all"] = v
        elif k.startswith("percent_damage_"):
            out[k[len("percent_damage_"):]] = v
    return out
