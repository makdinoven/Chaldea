from __future__ import annotations
import math, random, statistics
from typing import Dict, Any, List, Tuple

_MODE_BONUS = {
    "attack":  {"attack": +0.5, "support": +0.1, "defense": -0.2},
    "defense": {"attack": -0.2, "support": +0.1, "defense": +0.5},
    "balance": {"attack": +0.2, "support": +0.2, "defense": +0.2},
}
_MODE_CHOICES = set(_MODE_BONUS)

# ────────────────────────────────────────────────────────────────
# FEAT-168: ценность предмета из быстрого слота.
# Раньше слот оценивался ТОЛЬКО по восстановлению ресурсов, поэтому боевое
# зелье, яд или свиток урона получали ровно 0 и автобой не брал их никогда.
# Веса подобраны так, чтобы лечение в критической ситуации оставалось
# приоритетнее, чем бафф «про запас».
DAMAGE_WEIGHT   = 0.6    # за единицу урона строки item_damage_entries
BUFF_WEIGHT     = 0.15   # за единицу силы эффекта на себя/союзника за ход
DEBUFF_WEIGHT   = 0.12   # то же для эффекта на врага
COATING_WEIGHT  = 0.2    # за единицу прибавки к урону от яда на оружии за ход
CLEANSE_WEIGHT  = 2.0    # фиксированная ценность очищения, если есть что снять
QUANTITY_WEIGHT = 0.01   # прежний небольшой бонус «есть запас»

# Пороги нужды в ресурсах: ниже этой доли запаса восстановление начинает
# что-то стоить (нужда = порог − доля, максимум при полностью пустом ресурсе)
HP_NEED_THRESHOLD      = 0.7
MANA_NEED_THRESHOLD    = 0.6
ENERGY_NEED_THRESHOLD  = 0.6

MIN_EFFECT_TURNS  = 1       # мгновенный эффект считаем как один ход

ACTION_WEAPON_COATING = "weapon_coating"
CLEANSE_EFFECT_NAME   = "cleanse"

# Стороны эффекта (см. item_effects.target_side)
ALLY_SIDES  = {"self", "ally", "all_allies"}
ENEMY_SIDES = {"enemy"}

# Селекторы очищения — зеркало battle-service/app/buffs.py (FEAT-168 §3.2).
# Здесь нужна только проверка «есть ли что снимать», поэтому логика
# упрощённая: точное снятие остаётся за боевым сервисом.
SELECTOR_DEBUFF          = "debuff"
SELECTOR_PERIODIC_DAMAGE = "periodic_damage"
SELECTOR_CONTROL_PARTIAL = "control_partial"
SELECTOR_STAT_DOWN       = "stat_down"
SELECTOR_ALL             = "all"
DEFAULT_CLEANSE_SELECTOR = SELECTOR_DEBUFF

_PERIODIC_DAMAGE_NAMES = {"bleeding", "burn"}
# Сложные эффекты из buffs._expand_complex_effect: раскрываются по модулю силы,
# поэтому их знак не зависит от magnitude
_COMPLEX_NEGATIVE_NAMES = {"armorbreak", "freeze", "electrify", "daze", "wet", "curse"}
_COMPLEX_POSITIVE_NAMES = {"holy"}
_PARTIAL_CONTROL_NAMES = {"knockdown", "windburn"}
_SKILL_TYPES           = {"attack", "defense", "support"}


def _as_float(value, default: float = 0.0) -> float:
    """Числовое поле из состояния боя: None / мусор не должны ронять автобой."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _lower(value) -> str:
    return (value or "").strip().lower() if isinstance(value, str) else ""


def _is_full_skip(eff: dict) -> bool:
    """Полный контроль (Stun, Poison:paralysis) — не снимается ничем.
    Зеркало buffs.evaluate_control / buffs.is_unremovable."""
    name = _lower(eff.get("name"))
    attr = _lower(eff.get("attribute"))
    return name == "stun" or (name == "poison" and attr == "paralysis")


def _is_stat_down(eff: dict) -> bool:
    """Эффект ухудшает характеристики / сопротивления / урон цели.

    Зеркало `buffs._is_stat_down`, который прогоняет эффект через
    `aggregate_modifiers` и смотрит, есть ли отрицательный вклад:
    • сложные эффекты (ArmorBreak, Freeze, Electrify, Daze, Wet, Curse)
      раскрываются движком по МОДУЛЮ силы и всегда дают минус — значит они
      «stat_down» независимо от знака magnitude; Holy всегда даёт плюс;
    • у остальных вклад равен magnitude, то есть минус только при
      отрицательной силе.
    Источник истины — battle-service; здесь нужен лишь ответ «есть ли смысл
    брать очищение», поэтому раскрытие по каналам не повторяется.
    """
    name = _lower(eff.get("name"))
    if name in _COMPLEX_NEGATIVE_NAMES:
        return True
    if name in _COMPLEX_POSITIVE_NAMES:
        return False
    return _as_float(eff.get("magnitude")) < 0


def _matches_cleanse_selector(eff: dict, selector: str, list_pid: int) -> bool:
    name = _lower(eff.get("name"))
    attr = _lower(eff.get("attribute"))
    if selector == SELECTOR_ALL:
        return True
    if selector == SELECTOR_DEBUFF:
        try:
            owner = int(eff.get("owner_id", list_pid))
        except (TypeError, ValueError):
            owner = list_pid
        return owner != list_pid
    if selector == SELECTOR_PERIODIC_DAMAGE:
        return (
            attr in _PERIODIC_DAMAGE_NAMES
            or name in _PERIODIC_DAMAGE_NAMES
            or (name == "poison" and attr == SELECTOR_PERIODIC_DAMAGE)
        )
    if selector == SELECTOR_CONTROL_PARTIAL:
        return name in _PARTIAL_CONTROL_NAMES and attr in _SKILL_TYPES
    if selector == SELECTOR_STAT_DOWN:
        return _is_stat_down(eff)
    return selector in (name, attr)


def _has_removable_effect(effects: List[dict], selector: str, pid: int) -> bool:
    """Есть ли на участнике эффект, который это очищение реально снимет."""
    sel = _lower(selector) or DEFAULT_CLEANSE_SELECTOR
    for eff in effects or []:
        if not isinstance(eff, dict) or _is_full_skip(eff):
            continue
        if _matches_cleanse_selector(eff, sel, pid):
            return True
    return False


# ────────────────────────────────────────────────────────────────
def _flatten(tree) -> List[dict]:
    out, st = [], [tree]
    while st:
        cur = st.pop()
        if isinstance(cur, dict):
            out.append(cur)
        elif isinstance(cur, list):
            st.extend(cur)
    return out

# ────────────────────────────────────────────────────────────────
class Strategy:
    def __init__(self) -> None:
        self.mode    : str = "balance"
        # FEAT-125: keyed by skill_id (was rank_id). Prior history is dropped
        # on the cutover — acceptable per the brief (R5).
        self.rating  : Dict[int, Tuple[int, int]] = {}

    # ───────────── публичное API ─────────────
    def set_mode(self, mode: str) -> None:
        if mode not in _MODE_CHOICES:
            raise ValueError(f"unknown mode {mode}")
        self.mode = mode

    def feedback(self, skill_ids: List[int], liked: bool) -> None:
        for sid in skill_ids:
            good, bad = self.rating.get(sid, (0, 0))
            self.rating[sid] = (good + (1 if liked else 0),
                                bad  + (0 if liked else 1))

    def select_actions(
        self, ctx: Dict[str, Any]
    ) -> Tuple[Dict[str, int | None], int | None]:

        avail   = self._filter_available(ctx)
        feats   = ctx.get("features", {})
        weights = self._calc_weights(avail, feats)
        choice  = self._pick_best(weights, avail, feats, self._actor_state(ctx))
        return choice["skills"], choice["item_id"]

    def select_target(self, ctx: Dict[str, Any]) -> int | None:
        """Pick the attack target: the lowest-HP alive enemy on an opposing
        team (finish off wounded foes first). Returns None when no enemy is
        alive — the battle is effectively over and the backend will handle it."""
        rt = ctx["runtime"]
        pid = int(rt["current_actor"])
        participants = rt["participants"]
        my_team = (participants.get(str(pid)) or {}).get("team")
        enemies = [
            (int(p_id), p)
            for p_id, p in participants.items()
            if p.get("team") != my_team and p.get("hp", 0) > 0
        ]
        if not enemies:
            return None
        target_pid, _ = min(enemies, key=lambda kv: kv[1].get("hp", 0))
        return target_pid

    # ───────────── helpers ─────────────
    # ------------------------------------------------------------------
    @staticmethod
    def _actor_state(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Данные о текущем участнике, нужные для оценки предметов (FEAT-168).

        Всё читается с дефолтами: состояние боя, начатого до деплоя, просто не
        содержит weapon_coating, и предмет оценивается как раньше.
        """
        rt = ctx.get("runtime") or {}
        try:
            pid = int(rt.get("current_actor"))
        except (TypeError, ValueError):
            return {"pid": 0, "weapon_coating": None, "active_effects": []}
        part     = (rt.get("participants") or {}).get(str(pid)) or {}
        effects  = (rt.get("active_effects") or {}).get(str(pid)) or []
        return {
            "pid": pid,
            "weapon_coating": part.get("weapon_coating"),
            "active_effects": effects,
        }

    # ------------------------------------------------------------------
    def _filter_available(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        pid   = int(ctx["runtime"]["current_actor"])
        me_rt = ctx["runtime"]["participants"][str(pid)]

        snap  = next(s for s in ctx["snapshot"] if s["participant_id"] == pid)
        # FEAT-125: snapshot rows come from skills_client.character_skills(),
        # which exposes both `skill_id` and (as an alias) `id`. Key the local
        # available-skills dict by skill_id.
        skills = {
            (r.get("skill_id") or r.get("id")): r
            for r in _flatten(snap["skills"])
            if (r.get("skill_id") or r.get("id")) is not None
        }

        slots  = _flatten(me_rt.get("fast_slots", []))
        cdict  = me_rt["cooldowns"]

        def enough(r: dict) -> bool:
            return (
                me_rt["energy"]  >= r.get("cost_energy", 0) and
                me_rt["mana"]    >= r.get("cost_mana", 0) and
                me_rt["stamina"] >= r.get("cost_stamina", 0)
            )

        available = {rid: r for rid, r in skills.items()
                     if cdict.get(str(rid), 0) == 0 and enough(r)}

        return {"skills": available, "fast_slots": slots}

    # ------------------------------------------------------------------
    def _wilson(self, likes: int, dislikes: int) -> float:
        n = likes + dislikes
        if n == 0:
            return 0.5
        z = 1.96
        p = likes / n
        return (
            p + z*z/(2*n)
            - z * math.sqrt(p*(1-p)/n + z*z/(4*n))
        ) / (1 + z*z/n)       # 0…1

    def _calc_weights(
        self, avail: Dict[str, Any], f: Dict[str, float]
    ) -> Dict[int, float]:

        out: Dict[int, float] = {}
        for rid, row in avail["skills"].items():
            base  = 1.0
            stype = row.get("skill_type", "attack").lower()
            bonus = _MODE_BONUS[self.mode].get(stype, 0.0)

            # влияние HP: чем меньше, тем важнее support/defense
            if stype == "support":
                bonus += (1.0 - f.get("hp_ratio", 1.0)) * 0.5
            if stype == "defense":
                bonus += (1.0 - f.get("hp_ratio", 1.0)) * 0.3

            # пользовательские лайки
            likes, dislikes = self.rating.get(rid, (0, 0))
            rating = self._wilson(likes, dislikes)    # 0..1

            noise = random.uniform(-0.05, 0.05)
            out[rid] = base + bonus + rating + noise
        return out

    # ------------------------------------------------------------------
    def _pick_best(
        self, w: Dict[int, float],
        avail: Dict[str, Any],
        f: Dict[str, float],
        actor: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:

        # ------------- выбор навыков -----------------
        buckets = {"attack": [], "defense": [], "support": []}
        for rid, weight in w.items():
            t = avail["skills"][rid].get("skill_type", "attack").lower()
            buckets.setdefault(t, []).append((rid, weight))

        skills = {"attack_skill_id": None, "defense_skill_id": None, "support_skill_id": None}
        for t, lst in buckets.items():
            if lst:
                sid, _ = max(lst, key=lambda x: x[1])
                skills[f"{t}_skill_id"] = sid

        # ------------- выбор предмета ----------------
        # Нужда растёт по мере того, как ресурс ЗАКАНЧИВАЕТСЯ: >0 при запасе
        # ниже порога, 0 при полном. Раньше здесь была обратная разность
        # (ratio - threshold), из-за чего автобой пил лечение на полном HP и
        # не пил на 20 % (баг найден QA в FEAT-168).
        need_hp   = max(0.0, HP_NEED_THRESHOLD      - f.get("hp_ratio",1.0))
        need_mana = max(0.0, MANA_NEED_THRESHOLD    - f.get("mana_ratio",1.0))
        need_energy = max(0.0, ENERGY_NEED_THRESHOLD- f.get("energy_ratio",1.0))

        actor          = actor or {}
        actor_pid      = int(actor.get("pid") or 0)
        actor_effects  = actor.get("active_effects") or []
        coating_active = bool(actor.get("weapon_coating"))

        def value(slot):
            # Яд на оружие при уже нанесённом яде боевой сервис отклоняет
            # (item_rejected), а предмет на ход всего один — такой слот
            # обесценивается полностью, чтобы не потратить ход впустую.
            if (_lower(slot.get("consumable_action")) == ACTION_WEAPON_COATING
                    and coating_active):
                return 0.0

            v  = need_hp   * _as_float(slot.get("health_recovery", 0))
            v += need_mana * _as_float(slot.get("mana_recovery",   0))
            v += need_energy * _as_float(slot.get("energy_recovery", 0))
            v += QUANTITY_WEIGHT * _as_float(slot.get("quantity", 0))

            # Строки урона (свитки). Поле `chance` у строки урона предмета
            # боевым сервисом НЕ разыгрывается — урон предмета применяется
            # всегда, отыгрываются только уклонение и сопротивления
            # (см. docs/services/battle-service.md), поэтому шанс здесь не
            # учитывается: оценка должна совпадать с тем, что реально будет.
            for row in slot.get("damage_entries") or []:
                if not isinstance(row, dict):
                    continue
                v += _as_float(row.get("amount")) * DAMAGE_WEIGHT

            # Эффекты предмета: баффы на себя/союзника, дебаффы на врага,
            # очищение — только если реально есть что снимать
            for row in slot.get("effects") or []:
                if not isinstance(row, dict):
                    continue
                if _lower(row.get("effect_name")) == CLEANSE_EFFECT_NAME:
                    if _has_removable_effect(actor_effects,
                                             row.get("attribute_key"),
                                             actor_pid):
                        v += CLEANSE_WEIGHT
                    continue
                side = _lower(row.get("target_side")) or "self"
                if side in ENEMY_SIDES:
                    weight = DEBUFF_WEIGHT
                elif side in ALLY_SIDES:
                    weight = BUFF_WEIGHT
                else:
                    continue
                turns = max(MIN_EFFECT_TURNS,
                            int(_as_float(row.get("duration"), MIN_EFFECT_TURNS)))
                v += abs(_as_float(row.get("magnitude"))) * turns * weight

            # Яд на оружие: прибавка к урону за всё время действия
            if _lower(slot.get("consumable_action")) == ACTION_WEAPON_COATING:
                turns = max(0, int(_as_float(slot.get("coating_turns"))))
                v += (_as_float(slot.get("coating_bonus_damage")) * turns
                      * COATING_WEIGHT)

            return v

        item_id = None
        if avail["fast_slots"]:
            best = max(avail["fast_slots"], key=value)
            if value(best) > 0:
                item_id = best["item_id"]

        return {"skills": skills, "item_id": item_id}
