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


def normalize_source(source) -> str | None:
    """Нормализует «источник эффекта» в строку вида "item:42".

    Принимает кортеж/список `(kind, id)`, готовую строку "item:42" или None.
    Строка выбрана специально: состояние боя сериализуется в JSON и лежит в
    Redis до 48 часов, а кортеж после round-trip превратился бы в список и
    перестал совпадать сам с собой.
    Возвращает None, если источник не задан (эффекты навыков).
    """
    if source is None:
        return None
    if isinstance(source, (tuple, list)):
        if len(source) != 2:
            raise ValueError("source должен быть парой (kind, id)")
        kind, ident = source
    elif isinstance(source, str):
        text = source.strip()
        return text or None
    else:
        raise TypeError("source должен быть парой (kind, id), строкой или None")
    kind = str(kind).strip().lower()
    ident = str(ident).strip()
    if not kind or not ident:
        return None
    return f"{kind}:{ident}"


def _effect_identity(eff: Dict, list_pid: int) -> tuple | None:
    """Ключ «то же самое применение» для обновления вместо накопления (FEAT-168).

    Ключ существует ТОЛЬКО у эффектов с известным источником (`source`), то
    есть у эффектов предметов. Эффекты навыков источника не имеют и никогда не
    объединяются: каждое применение — независимый экземпляр со своей
    длительностью и силой (кровотечение на 2 хода по 5 и кровотечение на
    3 хода по 10 тикают параллельно).

    Для эффектов предмета совпадать должны источник, имя, нормализованный
    атрибут и владелец (кастер). Записи из старого состояния Redis не имеют ни
    source, ни owner_id: source отсутствует ⇒ ключа нет ⇒ такие записи никогда
    не обновляются и не мешают (та же совместимость, что в decrement_durations).
    """
    src = eff.get("source")
    if not src:
        return None
    return (
        str(src),
        (eff.get("name") or "").strip().lower(),
        (eff.get("attribute") or "").strip().lower(),
        int(eff.get("owner_id", list_pid)),
    )


def apply_new_effects(
    state: Dict,
    pid: int,
    raw_effect_rows: List[Dict],
    is_enemy: bool = False,
    owner_pid: int | None = None,
    source=None,
) -> None:
    """
    • Для hp/mana/energy/stamina — применяем сразу (clamp 0..max_*)
    • Для остальных — нормализуем и кладём в active_effects[pid]
    • is_enemy=True — эффекты применяются к врагу (положительные мгновенные
      значения инвертируются в урон, чтобы не лечить противника)
    • owner_pid — id участника, который КАСТанул эффект (caster). Если None,
      считаем, что владелец = target (legacy-поведение). Owner используется
      для тика длительности: эффект убывает только в конце хода владельца,
      даже если лежит в active_effects цели.
    • source — источник эффекта, пара (kind, id), например ("item", 42).
      По умолчанию None — так его передают НАВЫКИ.

    FEAT-168, правило накопления:
    • НАВЫКИ (source=None) — накапливаются как раньше: каждое применение
      добавляет отдельную запись со своей длительностью и силой, записи тикают
      независимо друг от друга.
    • ПРЕДМЕТЫ (source=("item", item_id)) — не накапливаются: повторное
      применение ТОГО ЖЕ предмета обновляет его собственную запись на месте
      (duration = max(старая, новая), magnitude = новая). Эффекты другого
      предмета или навыка с тем же именем не трогаются — ключ включает источник.

    Флаг `fresh` выставляется ТОЛЬКО у по-настоящему новой записи; при
    обновлении уже активного эффекта он не трогается, иначе эффект пропустил бы
    один тик (подновлённый яд переставал бы наносить урон на ход).
    """
    inst_attrs = {"hp", "mana", "energy", "stamina"}
    aid = str(pid)
    owner_id = int(owner_pid) if owner_pid is not None else int(pid)
    source_key = normalize_source(source)

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
            if source_key:
                eff["source"] = source_key
            lst = state.setdefault("active_effects", {}).setdefault(aid, [])
            key = _effect_identity(eff, int(pid))
            existing = None
            if key is not None:  # источника нет (навык) ⇒ всегда новая запись
                existing = next(
                    (e for e in lst if _effect_identity(e, int(pid)) == key), None
                )
            if existing is None:
                lst.append(eff)
                continue
            # Refresh-in-place: длительность не суммируется, а продлевается до
            # большей из двух; сила эффекта берётся новая.
            # Флаг `fresh` НЕ выставляется заново: он существует только для
            # пропуска первого тика в ход наложения. Если сбрасывать его при
            # обновлении, уже работающий DoT (например, подновлённый яд) терял
            # бы один тик урона — игрок этого не ожидает. Уже висящий эффект
            # продолжает тикать в своём ритме.
            old_duration = existing.get("duration") or 0
            new_duration = eff.get("duration") or 0
            existing["duration"] = max(old_duration, new_duration)
            existing["magnitude"] = eff["magnitude"]
            existing["owner_id"] = owner_id


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


def first_cycle_limit_skills(attack_id, defense_id, support_id) -> tuple:
    """First cycle (FEAT-143): only ONE skill type may be used per turn. Keeps
    the first present one in priority order attack > defense > support and nulls
    the rest. Returns (attack_id, defense_id, support_id)."""
    kept = False
    out = []
    for sid in (attack_id, defense_id, support_id):
        if sid and not kept:
            kept = True
            out.append(sid)
        else:
            out.append(None)
    return tuple(out)


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


# ──────────────────────────────────────────────────────────
# FEAT-168: снятие эффектов (противоядия, свитки очищения)
#
# Селектор приходит из строки предмета (item_effects.attribute_key у строки
# с effect_name="Cleanse") — то есть настраивается админом. Что бы админ ни
# настроил, полный контроль с пропуском хода снять нельзя: это правило движка.

SELECTOR_DEBUFF = "debuff"                  # всё, что повесил кто-то другой
SELECTOR_PERIODIC_DAMAGE = "periodic_damage"  # только DoT
SELECTOR_CONTROL_PARTIAL = "control_partial"  # Knockdown / Windburn
SELECTOR_STAT_DOWN = "stat_down"            # эффекты с отрицательным вкладом
SELECTOR_ALL = "all"                        # всё снимаемое, включая свои баффы

# Набор именованных селекторов; любое другое значение трактуется как имя
# конкретного эффекта (например "Bleeding").
CLEANSE_SELECTORS = frozenset({
    SELECTOR_DEBUFF,
    SELECTOR_PERIODIC_DAMAGE,
    SELECTOR_CONTROL_PARTIAL,
    SELECTOR_STAT_DOWN,
    SELECTOR_ALL,
})

# Селектор по умолчанию, если у строки Cleanse не задан attribute_key —
# поведение обычного противоядия.
DEFAULT_CLEANSE_SELECTOR = SELECTOR_DEBUFF


def is_unremovable(eff: Dict) -> bool:
    """True для эффектов, дающих полный пропуск хода (Stun, Poison:paralysis).

    Такие эффекты не снимаются НИКАКИМ очищением, включая селектор "all".
    Правило движка, а не настройка предмета (FEAT-168 §3.2).
    Список полного контроля берётся из evaluate_control, чтобы две функции
    не разъезжались.
    """
    full_skip, _ = evaluate_control([eff])
    return full_skip is not None


def _is_partial_control(eff: Dict) -> bool:
    _, blocked = evaluate_control([eff])
    return bool(blocked)


def _is_stat_down(eff: Dict) -> bool:
    """Эффект уменьшает характеристики/сопротивления/урон цели."""
    # aggregate_modifiers ожидает нормализованный attribute; у записей из
    # старого состояния он всегда есть, но подстрахуемся без глотания ошибки.
    probe = dict(eff)
    if not probe.get("attribute"):
        probe["attribute"] = (probe.get("name") or "").replace(" ", "_").lower()
    probe.setdefault("magnitude", 0)
    mods = aggregate_modifiers([probe])
    return any((value or 0) < 0 for value in mods.values())


def _matches_selector(eff: Dict, selector: str, list_pid: int) -> bool:
    if selector == SELECTOR_ALL:
        return True
    if selector == SELECTOR_DEBUFF:
        return int(eff.get("owner_id", list_pid)) != list_pid
    if selector == SELECTOR_PERIODIC_DAMAGE:
        return _is_periodic_damage(eff)
    if selector == SELECTOR_CONTROL_PARTIAL:
        return _is_partial_control(eff)
    if selector == SELECTOR_STAT_DOWN:
        return _is_stat_down(eff)
    # Конкретный эффект по имени (или по нормализованному атрибуту —
    # админ может указать и то, и другое, например "Bleeding"/"bleeding").
    name = (eff.get("name") or "").strip().lower()
    attribute = (eff.get("attribute") or "").strip().lower()
    return selector in (name, attribute)


def remove_effects(
    state: Dict,
    pid: int,
    *,
    selector: str,
    limit: int = 0,
) -> List[Dict]:
    """Снимает с участника `pid` эффекты, подходящие под `selector`.

    selector: debuff | periodic_damage | control_partial | stat_down | all
              либо имя конкретного эффекта ("Bleeding").
              Пустое значение трактуется как "debuff" (обычное противоядие).
    limit:    сколько эффектов снять; 0 (и любое значение <= 0) — снять все
              подходящие. Снимаются самые старые записи из списка.

    Возвращает список снятых эффектов (как они лежали в состоянии) — для
    события `effects_removed` в журнале боя.

    НИКОГДА не снимает полный контроль с пропуском хода (Stun, Poison с
    атрибутом 'paralysis'), даже при selector="all" — правило движка.

    Записи из старого состояния Redis (без owner_id / fresh) обрабатываются
    так же, как в decrement_durations: владельцем считается участник, в чьём
    списке лежит эффект.
    """
    active = state.get("active_effects", {})
    aid = str(pid)
    lst = active.get(aid)
    if not lst:
        return []

    sel = (selector or "").strip().lower() or DEFAULT_CLEANSE_SELECTOR
    max_removals = int(limit or 0)
    list_pid = int(pid)

    kept: List[Dict] = []
    removed: List[Dict] = []
    for eff in lst:
        if is_unremovable(eff):
            kept.append(eff)
            continue
        if max_removals > 0 and len(removed) >= max_removals:
            kept.append(eff)
            continue
        if _matches_selector(eff, sel, list_pid):
            removed.append(eff)
        else:
            kept.append(eff)

    if removed:
        active[aid] = kept
    return removed
