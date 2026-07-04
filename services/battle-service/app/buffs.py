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


def apply_new_effects(
    state: Dict,
    pid: int,
    raw_effect_rows: List[Dict],
    is_enemy: bool = False,
    owner_pid: int | None = None,
) -> None:
    """
    • Для hp/mana/energy/stamina — применяем сразу (clamp 0..max_*)
    • Для остальных — нормализуем и добавляем в active_effects[pid]
    • is_enemy=True — эффекты применяются к врагу (положительные мгновенные
      значения инвертируются в урон, чтобы не лечить противника)
    • owner_pid — id участника, который КАСТанул эффект (caster). Если None,
      считаем, что владелец = target (legacy-поведение). Owner используется
      для тика длительности: эффект убывает только в конце хода владельца,
      даже если лежит в active_effects цели.
    """
    inst_attrs = {"hp", "mana", "energy", "stamina"}
    aid = str(pid)
    owner_id = int(owner_pid) if owner_pid is not None else int(pid)

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
            eff["owner_id"] = owner_id
            # Freshly cast: must NOT tick on the same turn it was applied, so its
            # remaining duration stays equal to the applied value until the next
            # owner turn (FEAT-143 — keeps active-effect duration == log duration).
            eff["fresh"] = True
            state.setdefault("active_effects", {}).setdefault(aid, []).append(eff)


# Complex effects that deal periodic HP damage each turn (magnitude = HP/turn).
# Detected by normalized attribute or effect name; Poison only when its subtype
# (carried in `attribute` via attribute_key) is periodic_damage.
_PERIODIC_DAMAGE = {"bleeding", "burn"}


def _is_periodic_damage(eff: Dict) -> bool:
    attr = (eff.get("attribute") or "").lower()
    name = (eff.get("name") or "").lower()
    if attr in _PERIODIC_DAMAGE or name in _PERIODIC_DAMAGE:
        return True
    return name == "poison" and attr == "periodic_damage"


def evaluate_control(actor_effects: List[Dict]) -> tuple:
    """Control effects on the acting participant (FEAT-143 group B).

    Returns (full_skip_reason, blocked_skill_types):
      * full_skip_reason — "Stun" / "Poison" if the actor loses the whole turn,
        else None;
      * blocked_skill_types — set of "attack"/"defense"/"support" that Knockdown
        or Windburn block this turn.
    """
    full_skip = None
    blocked: set = set()
    for e in actor_effects or []:
        name = (e.get("name") or "").lower()
        attr = (e.get("attribute") or "").lower()
        if name == "stun":
            full_skip = full_skip or "Stun"
        elif name == "poison" and attr == "paralysis":
            full_skip = full_skip or "Poison"
        elif name in ("knockdown", "windburn") and attr in ("attack", "defense", "support"):
            blocked.add(attr)
    return full_skip, blocked


def tick_periodic_effects(state: Dict, participant_id: int | None = None) -> List[Dict]:
    """Apply periodic HP damage (bleeding / burn / periodic poison) for effects
    OWNED by `participant_id` — same ownership model as decrement_durations, so a
    DoT ticks on its caster's turn together with its duration. Freshly-cast
    effects are skipped (no tick on the turn they were applied). Returns a list
    of `effect_tick` events for the battle log. Call BEFORE decrement_durations
    (which clears the `fresh` flag).
    """
    active = state.get("active_effects", {})
    owner_filter = int(participant_id) if participant_id is not None else None
    events: List[Dict] = []

    for pid, lst in active.items():
        for eff in lst:
            eff_owner = eff.get("owner_id", int(pid))
            if owner_filter is not None and eff_owner != owner_filter:
                continue
            if eff.get("fresh") or not _is_periodic_damage(eff):
                continue
            amount = abs(eff.get("magnitude", 0))
            if amount <= 0:
                continue
            part = state["participants"].get(str(pid))
            if not part or part["hp"] <= 0:
                continue
            new_hp = max(0, part["hp"] - amount)
            dealt = part["hp"] - new_hp
            part["hp"] = new_hp
            part["total_damage_received"] = part.get("total_damage_received", 0) + int(dealt)
            events.append({
                "event": "effect_tick",
                "target": int(pid),
                "source": eff_owner,
                "effect": eff.get("name"),
                "attribute": eff.get("attribute"),
                "amount": int(dealt),
            })
    return events


def decrement_durations(state: Dict, participant_id: int | None = None) -> None:
    """
    Уменьшаем duration активных эффектов в конце хода владельца (caster).
    Если participant_id указан — тикают ТОЛЬКО эффекты, которые КАСТанул
    этот участник, независимо от того, на ком они висят. Это гарантирует,
    что дебафф, повешенный на врага, убывает на ходу кастера, а не жертвы.
    Если None — тикает у всех (legacy).
    Эффекты без owner_id считаются принадлежащими участнику, в чьём списке
    они лежат (обратная совместимость со старым state в Redis).
    Удаляем, когда duration == 0.
    """
    active = state.get("active_effects", {})
    pids = list(active.keys())
    owner_filter = int(participant_id) if participant_id is not None else None

    for pid in pids:
        lst = active.get(pid)
        if not lst:
            continue
        new_lst = []
        for eff in lst:
            eff_owner = eff.get("owner_id", int(pid))  # legacy: own list
            if owner_filter is not None and eff_owner != owner_filter:
                new_lst.append(eff)
                continue
            # Skip the very first tick — the turn the effect was cast on.
            if eff.pop("fresh", False):
                new_lst.append(eff)
                continue
            eff["duration"] -= 1
            if eff["duration"] > 0:
                new_lst.append(eff)
        active[pid] = new_lst


# Complex effects that act as stat / resist / damage modifiers, expanded onto the
# engine's existing channels (percent_damage_*, percent_resist_*, primary attrs).
# Convention: `magnitude` is the effect's positive strength; the direction is
# baked in here (debuffs contribute negative deltas, buffs positive). This mirrors
# the COMPLEX_EFFECTS descriptions in the frontend skill editor.
_PRIMARY_ATTRS = ("strength", "agility", "intelligence", "endurance")
_PHYSICAL_TYPES = ("physical", "catting", "crushing", "piercing")


def _expand_complex_effect(name: str, magnitude: float) -> Dict[str, float] | None:
    """Map a complex-effect NAME to engine modifier contributions, or None if the
    effect isn't a modifier (periodic-damage / control effects return None)."""
    n = (name or "").lower()
    m = abs(magnitude)
    if n == "armorbreak":            # −все физические сопротивления
        return {f"percent_resist_{t}": -m for t in _PHYSICAL_TYPES}
    if n == "freeze":                # −все сопротивления
        return {"percent_resist_all": -m}
    if n == "electrify":             # +весь входящий урон (= −сопротивление)
        return {"percent_resist_all": -m}
    if n == "daze":                  # −весь исходящий урон
        return {"percent_damage_all": -m}
    if n == "wet":                   # −исходящий магический урон
        return {"percent_damage_magic": -m}
    if n == "holy":                  # +все 4 первичных атрибута
        return {a: m for a in _PRIMARY_ATTRS}
    if n == "curse":                 # −все 4 первичных атрибута
        return {a: -m for a in _PRIMARY_ATTRS}
    return None


def aggregate_modifiers(effects_for_participant: List[Dict]) -> Dict[str, float]:
    """
    Складывает magnitude по движковым ключам. Сложные эффекты-модификаторы
    (ArmorBreak, Freeze, Electrify, Daze, Wet, Holy, Curse) раскрываются в
    соответствующие каналы; остальные (StatModifier / Buff: / Resist: /
    MagicImpact через attribute_key) используют свой нормализованный attribute.
    """
    summary: Dict[str, float] = {}
    for eff in effects_for_participant:
        expanded = _expand_complex_effect(eff.get("name", ""), eff.get("magnitude", 0))
        if expanded is not None:
            for key, delta in expanded.items():
                summary[key] = summary.get(key, 0.0) + delta
        else:
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
