"""Subclass passives — battle-side numbers, math, per-battle state and rolls.

FEAT-188 laid the foundation (Berserk «Ярость»); FEAT-189 added wave 1 — the
13 passives that ride on existing combat mechanics; FEAT-190 adds wave 2 —
the last 7 (Paladin, Guardian, Bard, Necromancer, Etheriad, Auromancer,
Priest) plus Berserk lifesteal and the Trickster redirect, on new mechanics:
shields, lifesteal, reflect, HP payment, passive-applied ally/enemy effects
and the one friendly-fire exception. All 21 registry passives are live.

Pure module, no I/O. Passive *identity* (key, player-facing name and
description, `implemented` flag) lives in the skills-service registry
`services/skills-service/app/subclasses.py`; this module holds the numbers and
the logic. The registry descriptions quote these numbers — **change a
constant here → update that description too.** `IMPLEMENTED_PASSIVES` below is
the battle-side mirror of the registry `implemented` flag (a contract test
compares the two).

A participant's passive is fixed at battle start (`build_participant_info` →
`passive_key` in the Redis participant state) and never changes during the
battle. States created before FEAT-188 have no `passive_key` → no passive;
states created before FEAT-189 have no `is_npc` / `passive_state` /
`dungeon_session_id` → every hook below is neutral for them.

Design rules (FEAT-189 §3, D1/D2):
  * `main.py` calls only the hooks H0–H25 below at fixed pipeline points; all
    passive logic lives here. `buffs.py` only gets two optional callbacks
    (`absorb_fn` / `overheal_fn`, FEAT-190 E2) that main wires to `absorb` /
    `on_heal` here.
  * This module imports NOTHING from `buffs` / `battle_engine` — ~30 test
    suites replace those modules with `MagicMock` at collection time, and a
    helper imported from them would silently turn into a mock. The few
    constant sets needed are local copies (see `PHYSICAL_TYPES`,
    `RESOURCE_ATTRS`).
  * Every passive random roll goes through `roll_pct` / `pick` (module RNG
    `_rng`). Tests patch `passives.roll_pct` / `passives.pick` or seed
    `passives._rng`. A hook rolls ONLY for a participant owning the passive in
    question, so randomness of every other battle is untouched.
  * Per-battle passive state lives in `participant["passive_state"]` (dict,
    created lazily by `pstate`). Keys (all optional):
      used_magic (bool, any participant), heresy_stacks (int, target),
      saber_kills (int), saber_pvp (int), own_turns (int), lancer_stacks (int),
      lancer_gain ({stat: amount}), stolen ({stat: amount}, target),
      first_blood_done ([pid, ...]), shadow_ready (bool),
      control_immunity_used (bool), kindling_target (pid|None),
      kindling_stacks (int);
    FEAT-190: shields ([{key, owner, amount, cap, turns_left, fresh}], on
      the shielded participant — see the wave-2 section), vow_used (bool),
      bard_stacks (int), bard_mode ("group"|"solo").
  * Readers never create `passive_state` (`_ps_read`); only writers do.
  * FEAT-190 random sources stay `pick` only (Trickster redirect target,
    Etheriad curse / might target) — no new chance rolls.

"Contribution" = `{"key": str, "kind": str, "value": number?, "owner": pid?}`
— goes into the damage event's `passives` list (log contract §3.5).
"""
import math
import random
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

# =============================================================================
# Passive keys (mirror of the skills-service registry)
# =============================================================================
PASSIVE_BERSERKER_RAGE = "berserker_rage"
PASSIVE_INQUISITOR = "inquisitor_heresy_seal"
PASSIVE_SABER = "saber_monster_hunter"
PASSIVE_GLADIATOR = "gladiator_arena"
PASSIVE_AGENT = "agent_weak_spot"
PASSIVE_LANCER = "lancer_pin"
PASSIVE_MECHANIC = "mechanic_shrapnel"
PASSIVE_ARCHER = "archer_first_blood"
PASSIVE_ASSASSIN = "assassin_from_shadow"
PASSIVE_TRICKSTER = "trickster_deceit"
PASSIVE_MONK = "monk_harmony"
PASSIVE_SALAMANDER = "salamander_kindling"
PASSIVE_CASTER = "caster_pure_energy"
PASSIVE_SPARKMAGE = "sparkmage_chain_lightning"
# FEAT-190 — wave 2
PASSIVE_PALADIN = "paladin_sacred_vow"
PASSIVE_GUARDIAN = "guardian_retribution"
PASSIVE_BARD = "bard_rhythm"
PASSIVE_NECROMANCER = "necromancer_blood_price"
PASSIVE_ETHERIAD = "etheriad_spirit_whisper"
PASSIVE_AUROMANCER = "auromancer_tide"
PASSIVE_PRIEST = "priest_faith"

# Battle-side mirror of the registry `implemented=True` set (all 21).
IMPLEMENTED_PASSIVES: FrozenSet[str] = frozenset({
    PASSIVE_BERSERKER_RAGE,
    PASSIVE_INQUISITOR,
    PASSIVE_SABER,
    PASSIVE_GLADIATOR,
    PASSIVE_AGENT,
    PASSIVE_LANCER,
    PASSIVE_MECHANIC,
    PASSIVE_ARCHER,
    PASSIVE_ASSASSIN,
    PASSIVE_TRICKSTER,
    PASSIVE_MONK,
    PASSIVE_SALAMANDER,
    PASSIVE_CASTER,
    PASSIVE_SPARKMAGE,
    PASSIVE_PALADIN,
    PASSIVE_GUARDIAN,
    PASSIVE_BARD,
    PASSIVE_NECROMANCER,
    PASSIVE_ETHERIAD,
    PASSIVE_AUROMANCER,
    PASSIVE_PRIEST,
})

# =============================================================================
# Numbers (quoted by the registry descriptions — keep them in sync)
# =============================================================================
# --- Berserk «Ярость» --------------------------------------------------------
RAGE_HP_STEP_PCT = 10    # one step per full 10% of max HP lost
RAGE_PCT_PER_STEP = 4    # +4% outgoing damage per step
RAGE_MAX_STEPS = 9       # cap -> +36%

# --- Инквизитор «Печать ереси» -----------------------------------------------
HERESY_RESIST_PER_STACK = 3   # −3% to every non-physical resist per stack
HERESY_MAX_STACKS = 5         # −15%

# --- Сейбер «Охотник на чудовищ + Несгибаемость» -----------------------------
SABER_NPC_DAMAGE_PCT = 15     # vs any NPC (`is_npc is True`)
SABER_KILL_PCT = 2            # per kill in a dungeon run
SABER_KILL_MAX_PCT = 10
SABER_KILL_MAX_STACKS = SABER_KILL_MAX_PCT // SABER_KILL_PCT  # 5 kills
SABER_PVP_RESIST_PCT = 2      # +2% all resists per hit taken from a player
SABER_PVP_MAX_STACKS = 3      # +6%
SABER_RUN_STACKS_TTL_S = 14 * 24 * 3600   # Redis run-key TTL (refreshed on write)

# --- Гладиатор «Арена» -------------------------------------------------------
ARENA_DAMAGE_PCT = 8          # per enemy above own side's count
ARENA_RESIST_PCT = 4
ARENA_MAX_SURPLUS = 3
RAMP_PCT_PER_TURN = 3         # not outnumbered: +3% per own (non-skipped) turn
RAMP_MAX_PCT = 15
_RAMP_MAX_TURNS = -(-RAMP_MAX_PCT // RAMP_PCT_PER_TURN)   # ceil → 5

# --- Агент «Слабое место» ----------------------------------------------------
WEAK_SPOT_BONUS_PP = 20
WEAK_SPOT_HARD_CONTROL_BONUS_PP = 10

# --- Лансер «Пригвоздить» ----------------------------------------------------
PIN_STEAL = 2                 # per stat per hit
PIN_MAX_STACKS = 5            # ±10
# Target loses AND the Lancer gains each of these (PM-accepted default, Q1).
LANCER_STOLEN_STATS = ("dodge", "critical_hit_chance")

# --- Механик «Шрапнель» ------------------------------------------------------
SHRAPNEL_CHANCE = 30
SHRAPNEL_MULT = 0.4
SHRAPNEL_DUEL_PCT = 35

# --- Арчер «Первая кровь» ----------------------------------------------------
FIRST_BLOOD_CRIT_BONUS = 50   # added to critical_damage (125 → 175 ⇒ ×1.75)

# --- Ассасин «Из тени + Добивание» -------------------------------------------
SHADOW_CRIT_BONUS = 25
EXECUTE_HP_PCT = 30           # target HP strictly below 30% of max
EXECUTE_DAMAGE_PCT = 20

# --- Фокусник «Обман» (часть 1) ---------------------------------------------
DECEIT_CHANCE = 10
DEBUFF_EXTRA_TURNS = 1

# --- Монах «Гармония» --------------------------------------------------------
HARMONY_CONTROL_BONUS_PP = 10
HARMONY_HARD_CONTROL_BONUS_PP = 5

# --- Саламандр «Разгорание» --------------------------------------------------
KINDLING_PCT = 6
KINDLING_MAX_STACKS = 5       # +30%
BURN_EXTRA_TURNS = 1

# --- Кастер «Чистая энергия» -------------------------------------------------
PURE_ENERGY_RESIST_IGNORE = 0.25   # fraction of a positive `magic` resist
CASTER_MANA_DISCOUNT_PCT = 10      # mirrored in frontend utils/passiveCosts.ts

# --- Искромаг «Цепная молния» ------------------------------------------------
CHAIN_CHANCE = 25
CHAIN_MULT = 0.5
ECHO_CHANCE = 25
ECHO_MULT = 0.4

# --- FEAT-190: Берсерк «Ярость» — вампиризм ----------------------------------
RAGE_LIFESTEAL_HP_PCT = 25    # attacker HP strictly below 25% of max
RAGE_LIFESTEAL_PCT = 15       # of the HP actually removed from the target

# --- Паладин «Священный обет» ------------------------------------------------
VOW_HP_PCT = 30               # triggers when 0 < HP < 30% max, once per battle
VOW_SHIELD_PCT = 20           # shield = 20% max HP (until broken / battle end)

# --- Хранитель «Возмездие» ---------------------------------------------------
RETRIBUTION_PCT = 15          # of the damage taken (after resists, incl. shield part)

# --- Жрец «Вера» -------------------------------------------------------------
FAITH_LIFESTEAL_PCT = 10
FAITH_HOLY_LIFESTEAL_PCT = 15
HOLY_TYPE = "sainting"

# --- Бард «Ритм» -------------------------------------------------------------
INSPIRATION_PCT = 3           # group: +3% damage per stack
INSPIRATION_MAX_STACKS = 4    # +12%
INSPIRATION_SOLO_PCT = 5      # solo: +5% per stack
INSPIRATION_SOLO_MAX_STACKS = 3   # +15%
INSPIRATION_DURATION = 2      # refreshed every Bard turn → permanent while he acts
INSPIRATION_EFFECT_NAME = "Вдохновение"

# --- Некромант «Плата кровью» ------------------------------------------------
BLOOD_HP_PER_MANA = 1.5       # mirrored in frontend utils/passiveCosts.ts
BLOOD_MIN_HP_LEFT = 1         # can't kill yourself: HP after payment ≥ 1
NECRO_KILL_HEAL_PCT = 10      # kill → heal 10% max HP (max HP unchanged)

# --- Эфириад «Шёпот духов» ---------------------------------------------------
SPIRIT_ALLY_HP_PCT = 50
SPIRIT_RESIST_PCT = 8
SPIRIT_DAMAGE_PCT = 8
SPIRIT_DURATION = 2
SPIRIT_WARD_NAME = "Шёпот духов: стойкость"
SPIRIT_CURSE_NAME = "Шёпот духов: уязвимость"
SPIRIT_MIGHT_NAME = "Шёпот духов: сила"

# --- Ауромант «Прилив» -------------------------------------------------------
TIDE_CAP_PCT = 20             # shield cap = 20% of the TARGET's max HP
TIDE_TURNS = 3                # ticks on the Auromancer's own turns

# --- Фокусник «Обман» (часть 2) ---------------------------------------------
REDIRECT_MULT = 0.5

# Effect-row sources of passive-applied rows. Equal to
# `buffs.normalize_source(("passive", key))` — local strings, no import (D1).
SOURCE_BARD = "passive:" + PASSIVE_BARD
SOURCE_ETHERIAD = "passive:" + PASSIVE_ETHERIAD

# =============================================================================
# Type sets — local copies (see module docstring, D1)
# =============================================================================
# Copy of buffs._PHYSICAL_TYPES.
PHYSICAL_TYPES: FrozenSet[str] = frozenset({"physical", "catting", "crushing", "piercing"})
NON_PHYSICAL_TYPES: Tuple[str, ...] = (
    "magic", "fire", "ice", "watering", "electricity", "wind", "sainting", "damning",
)
# Copy of buffs.RESOURCE_ATTRS.
RESOURCE_ATTRS: FrozenSet[str] = frozenset({"hp", "mana", "energy", "stamina"})
FIRE_TYPE = "fire"
MAGIC_TYPE = "magic"
CHAIN_TYPES: FrozenSet[str] = frozenset({"electricity", "wind"})
BURN_EFFECT_NAME = "burn"

# Log kinds (contributions / passive_proc events), §3.5.
KIND_DAMAGE_PCT = "damage_pct"
KIND_RESIST_PCT = "resist_pct"
KIND_FORCED_CRIT = "forced_crit"
KIND_RESIST_IGNORE = "resist_ignore"
KIND_EXTRA_HIT = "extra_hit"
KIND_DECEIT = "deceit"
KIND_DURATION_PLUS = "duration_plus"
KIND_MANA_DISCOUNT = "mana_discount"
PROC_HERESY_STACK = "heresy_stack"
PROC_PIN = "pin"
PROC_SABER_KILL = "saber_kill"
PROC_SABER_RESOLVE = "saber_resolve"
PROC_SHADOW_READY = "shadow_ready"
PROC_CONTROL_IMMUNE = "control_immune"
PROC_WEAK_SPOT = "weak_spot"
# FEAT-190
KIND_LIFESTEAL = "lifesteal"
KIND_REFLECT = "reflect"
KIND_REDIRECT = "redirect"
KIND_BLOOD_PRICE = "blood_price"
PROC_VOW = "vow"
PROC_TIDE = "tide"
PROC_SHIELD_ABSORB = "shield_absorb"
PROC_KILL_HEAL = "kill_heal"
PROC_INSPIRATION = "inspiration"
PROC_INSPIRATION_END = "inspiration_end"
PROC_SPIRIT_WHISPER = "spirit_whisper"

EXTRA_SPLASH = "splash"   # Mechanic
EXTRA_CHAIN = "chain"     # Sparkmage, another enemy
EXTRA_ECHO = "echo"       # Sparkmage, same target (no other enemy)

# Float HP is reduced by float damage; the epsilon makes "exactly 10% lost"
# count as a full step despite rounding noise.
_STEP_EPSILON = 1e-9


# =============================================================================
# H0 — gates and helpers
# =============================================================================
_rng = random.Random()


def roll_pct(pct) -> bool:
    """The ONLY passive chance gate: True with probability `pct`% (0..100).

    Non-numeric / NaN / ≤0 → False, ≥100 → True (no random number consumed in
    either case). Tests patch `passives.roll_pct` or seed `passives._rng`.
    """
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(p) or p <= 0:
        return False
    if p >= 100:
        return True
    return _rng.random() * 100.0 < p


def pick(seq: Sequence):
    """The ONLY passive random choice: one element of `seq`, None if empty."""
    items = list(seq or [])
    if not items:
        return None
    return _rng.choice(items)


def _num(value, default: float = 0.0) -> float:
    """Tolerant float: garbage (None, strings, NaN, inf) → default."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return f


def _int(value, default: int = 0) -> int:
    f = _num(value, default)
    return int(f)


def _key_of(participant) -> Optional[str]:
    if not isinstance(participant, dict):
        return None
    key = participant.get("passive_key")
    return key if isinstance(key, str) and key else None


def _ps_read(participant) -> dict:
    """Read-only view of `passive_state` — never creates the key."""
    if not isinstance(participant, dict):
        return {}
    ps = participant.get("passive_state")
    return ps if isinstance(ps, dict) else {}


def pstate(participant) -> dict:
    """H0. The participant's mutable `passive_state` dict, created lazily.

    Old states (no key) or a garbage value get a fresh `{}` stored in place.
    A non-dict participant yields a throwaway `{}` (writes are lost — no crash).
    """
    if not isinstance(participant, dict):
        return {}
    ps = participant.get("passive_state")
    if not isinstance(ps, dict):
        ps = {}
        participant["passive_state"] = ps
    return ps


def _participants(state) -> dict:
    if not isinstance(state, dict):
        return {}
    parts = state.get("participants")
    return parts if isinstance(parts, dict) else {}


def _part(state, pid) -> Optional[dict]:
    if pid is None:
        return None
    p = _participants(state).get(str(pid))
    return p if isinstance(p, dict) else None


def _owns(state, pid, key: str) -> bool:
    return _key_of(_part(state, pid)) == key


def _is_alive(p: dict) -> bool:
    return _num(p.get("hp"), 0) > 0 and not p.get("dropped_out")


def _alive_sides(state, pid) -> Tuple[List[int], List[int]]:
    """(alive enemies, alive allies incl. self) of `pid`, by team, right now."""
    me = _part(state, pid)
    if me is None:
        return [], []
    team = me.get("team")
    enemies, allies = [], []
    for spid, p in _participants(state).items():
        if not isinstance(p, dict) or not _is_alive(p):
            continue
        try:
            ipid = int(spid)
        except (TypeError, ValueError):
            continue
        (allies if p.get("team") == team else enemies).append(ipid)
    return enemies, allies


def _row_name(row) -> str:
    if not isinstance(row, dict):
        return ""
    name = row.get("effect_name")
    if name is None:
        name = row.get("name")
    return str(name or "").strip().lower()


def _row_attr(row) -> str:
    """Attribute of a raw (`attribute_key`) or normalized (`attribute`) row;
    falls back to the name-derived attribute like buffs._normalize_effect."""
    if not isinstance(row, dict):
        return ""
    attr = row.get("attribute_key")
    if not attr:
        attr = row.get("attribute")
    if attr:
        return str(attr).strip().lower()
    name = _row_name(row)
    if ":" in name:
        return ""
    return name.replace(" ", "_")


def control_kind(row) -> Optional[str]:
    """H0. Control classification by NAME (D6), raw or normalized rows.

    "hard" = Stun, Poison with `paralysis`; "soft" = Knockdown / Windburn with
    any attribute (incl. unresolved "random"); otherwise None.
    """
    name = _row_name(row)
    if name == "stun":
        return "hard"
    if name == "poison" and _row_attr(row) == "paralysis":
        return "hard"
    if name in ("knockdown", "windburn"):
        return "soft"
    return None


def resolve_entry_type(dmg, weapons, default_slot: str = "main_weapon") -> str:
    """H0. Damage type of a damage entry exactly as the engine resolves it.

    `"all"` → the weapon's `primary_damage_type` for the entry's
    `weapon_slot` (default `default_slot`: "main_weapon" for skills,
    "no_weapon" for items), or "physical" when unarmed / slot unknown.
    `weapons` = {slot: weapon dict} (may be None).
    """
    if not isinstance(dmg, dict):
        return "physical"
    dtype = dmg.get("damage_type") or "physical"
    if dtype != "all":
        return str(dtype)
    slot = dmg.get("weapon_slot", default_slot) or default_slot
    weapon = None
    if slot != "no_weapon" and isinstance(weapons, dict):
        weapon = weapons.get(slot)
    if isinstance(weapon, dict) and weapon.get("primary_damage_type"):
        return str(weapon["primary_damage_type"])
    return "physical"


def _is_physical(dtype) -> bool:
    return str(dtype or "").strip().lower() in PHYSICAL_TYPES


def contribution(key: str, kind: str, value=None, owner=None) -> dict:
    """Builds one `passives` list entry (§3.5)."""
    c = {"key": key, "kind": kind}
    if value is not None:
        c["value"] = value
    if owner is not None:
        c["owner"] = owner
    return c


def passive_proc_event(who, key: str, kind: str, **extra) -> dict:
    """Builds a `passive_proc` log event (§3.5). `extra` keys with value None
    are dropped (target / value / stacks / effects / stolen)."""
    ev = {"event": "passive_proc", "who": who, "key": key, "kind": kind}
    for k, v in extra.items():
        if v is not None:
            ev[k] = v
    return ev


def _clean_num(x):
    """int if integral, else rounded float — for log values."""
    f = _num(x, 0.0)
    return int(f) if f == int(f) else round(f, 2)


# =============================================================================
# FEAT-188 — Berserk «Ярость» (unchanged behaviour)
# =============================================================================
def rage_bonus_pct(hp, max_hp) -> int:
    """Percent damage bonus of «Ярость» for the given current/max HP.

    +RAGE_PCT_PER_STEP for every full RAGE_HP_STEP_PCT of max HP lost, capped
    at RAGE_MAX_STEPS steps. Missing / non-numeric / non-positive `max_hp`
    (old states) → 0. `hp` is clamped to [0, max_hp].
    """
    try:
        max_hp_f = float(max_hp)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(max_hp_f) or max_hp_f <= 0:
        return 0
    try:
        hp_f = float(hp)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(hp_f):
        return 0
    hp_f = min(max(hp_f, 0.0), max_hp_f)

    lost_pct = (max_hp_f - hp_f) * 100.0 / max_hp_f
    steps = min(RAGE_MAX_STEPS, int(math.floor(lost_pct / RAGE_HP_STEP_PCT + _STEP_EPSILON)))
    return max(steps, 0) * RAGE_PCT_PER_STEP


def _berserker_rage(participant_state: dict) -> float:
    return rage_bonus_pct(participant_state.get("hp", 0), participant_state.get("max_hp", 0))


# Passive key -> function(participant_state) -> outgoing % damage bonus.
# FEAT-188 dispatch; stays rage-only — wave-1 damage bonuses go through
# `begin_attack` / `target_damage_mods` instead.
_DAMAGE_PASSIVES: Dict[str, Callable[[dict], float]] = {
    PASSIVE_BERSERKER_RAGE: _berserker_rage,
}


def passive_damage_bonus(participant_state: Optional[dict]) -> Tuple[float, Optional[str]]:
    """Outgoing percent-damage bonus from the attacker's passive (FEAT-188).

    Returns `(pct, passive_key)`; `(0, None)` when there is no passive, the
    passive has no damage effect, or the bonus is currently 0. Rage only —
    main.py keeps applying it to `percent_damage_buffs["all"]` and emitting
    `passive_key` / `passive_pct` exactly as in FEAT-188.
    """
    if not isinstance(participant_state, dict):
        return 0, None
    key = participant_state.get("passive_key")
    fn = _DAMAGE_PASSIVES.get(key) if key else None
    if fn is None:
        return 0, None
    pct = fn(participant_state)
    if not pct or pct <= 0:
        return 0, None
    return pct, key


# =============================================================================
# H1 — turn start
# =============================================================================
def on_turn_start(state, actor_pid, skipped: bool) -> None:
    """H1. Called right after `evaluate_control` for the acting participant.

    `skipped` = the whole turn is lost to Stun / Poison-paralysis
    (`control_skip`). Gladiator: a non-skipped own turn increments
    `own_turns` (ramp +3%/turn, so the first own attack already has +3%).
    Everyone else: no-op.
    """
    actor = _part(state, actor_pid)
    if _key_of(actor) != PASSIVE_GLADIATOR or skipped:
        return
    ps = pstate(actor)
    ps["own_turns"] = min(_RAMP_MAX_TURNS, max(0, _int(ps.get("own_turns"))) + 1)


# =============================================================================
# H2 — attack begin
# =============================================================================
def _gladiator_surplus(state, pid) -> int:
    enemies, allies = _alive_sides(state, pid)
    return max(0, min(ARENA_MAX_SURPLUS, len(enemies) - len(allies)))


def begin_attack(state, attacker_pid, primary_pid, entry_types: Iterable[str],
                 source_kind: str = "skill") -> dict:
    """H2. Opens an attack and returns its `AttackCtx` (plain dict, local to
    one attack, NEVER saved to Redis).

    Called once per attack — the attack-skill step and the damaging-item
    (scroll) step — before the damage loop, after enemy effects (9.0b/9.0e).
    Items without damage rows are not attacks (don't call).

    Inputs:
      entry_types — RESOLVED damage types of the attack's damage entries
                    (`resolve_entry_type` per entry).
      source_kind — "skill" / "item" (informational).

    Side effects on state:
      * any attacker: `used_magic = True` if any entry type is non-physical
        (Inquisitor's mark — works for every participant);
      * Assassin: a ready shadow is CONSUMED here (whatever the outcome, Q2);
      * Salamander: kindling reset when the attack has no fire entry or the
        primary target is not the kindling target;
      * Mechanic: duel roll (30%) when no other living enemy than the primary.

    AttackCtx keys main.py reads:
      pct           — attack-level outgoing % damage, add to
                      `percent_damage_buffs["all"]` ONCE for this attack
                      (extra hits get it too). Rage is NOT included — rage
                      stays on the FEAT-188 path (`passive_damage_bonus`).
      contributions — attack-level contributions for every damage event of
                      this attack (Gladiator / Saber kill stacks).
    Everything else is internal to H3/H8/H9/H10.
    """
    attacker = _part(state, attacker_pid)
    key = _key_of(attacker)
    types = [str(t) for t in (entry_types or []) if t is not None]
    actx: Dict[str, Any] = {
        "attacker": attacker_pid,
        "primary": primary_pid,
        "key": key,
        "source_kind": source_kind,
        "entry_types": types,
        "pct": 0,
        "contributions": [],
        "shadow": False,
        "duel_bonus": 0,
        "fb_granted": set(),
        "hits": {},          # target_pid -> per-target record (H8)
        "extra_planned": False,
    }
    if attacker is None:
        return actx

    # Inquisitor's mark: "применял магию" = any non-physical entry.
    if any(not _is_physical(t) for t in types):
        pstate(attacker)["used_magic"] = True

    if key is None:
        return actx
    ps_read = _ps_read(attacker)

    if key == PASSIVE_GLADIATOR:
        surplus = _gladiator_surplus(state, attacker_pid)
        if surplus > 0:
            pct = ARENA_DAMAGE_PCT * surplus
        else:
            turns = max(0, _int(ps_read.get("own_turns")))
            pct = min(RAMP_MAX_PCT, RAMP_PCT_PER_TURN * turns)
        if pct > 0:
            actx["pct"] += pct
            actx["contributions"].append(
                contribution(key, KIND_DAMAGE_PCT, pct, attacker_pid))

    elif key == PASSIVE_SABER:
        kills = max(0, min(SABER_KILL_MAX_STACKS, _int(ps_read.get("saber_kills"))))
        pct = SABER_KILL_PCT * kills
        if pct > 0:
            actx["pct"] += pct
            actx["contributions"].append(
                contribution(key, KIND_DAMAGE_PCT, pct, attacker_pid))

    elif key == PASSIVE_ASSASSIN:
        if ps_read.get("shadow_ready"):
            pstate(attacker)["shadow_ready"] = False
            actx["shadow"] = True

    elif key == PASSIVE_MECHANIC:
        enemies, _ = _alive_sides(state, attacker_pid)
        others = [e for e in enemies if str(e) != str(primary_pid)]
        if not others and roll_pct(SHRAPNEL_CHANCE):
            actx["duel_bonus"] = SHRAPNEL_DUEL_PCT

    elif key == PASSIVE_SALAMANDER:
        has_fire = any(str(t).lower() == FIRE_TYPE for t in types)
        target = ps_read.get("kindling_target")
        if not has_fire or target is None or str(target) != str(primary_pid):
            if ps_read.get("kindling_stacks") or target is not None:
                ps = pstate(attacker)
                ps["kindling_target"] = None
                ps["kindling_stacks"] = 0

    return actx


# =============================================================================
# H3 — per damage roll, attacker/target side
# =============================================================================
def target_damage_mods(actx, state, target_pid, dmg_type, is_primary: bool) -> dict:
    """H3. Per-target modifiers for ONE damage roll (inside `_strike`).

    NOT called for extra hits (they use the attack-level `pct` only).
    `dmg_type` = resolved entry type; `is_primary` = target is the attack's
    primary target.

    Returns:
      pct_by_type       — {"all": pct, <type>: pct}; ADD to a per-target copy
                          of `percent_damage_buffs` (already holding actx pct).
      force_crit        — bool → `compute_damage_with_rolls(force_crit=)`.
      crit_damage_bonus — number → `compute_damage_with_rolls(crit_damage_bonus=)`.
      resist_ignore     — dict|None → `compute_damage_with_rolls(resist_ignore=)`.
      contributions     — target-level contributions for the event.

    Covers: Saber vs NPC (+15), Assassin execute (<30% HP now, +20) and
    shadow (forced crit +25), Salamander kindling (+6/stack on fire vs the
    kindling target), Mechanic duel (+35 on the primary), Archer first blood
    (forced crit +50 until the target took its first landed hit), Caster
    resist ignore (magic).
    """
    out = {
        "pct_by_type": {},
        "force_crit": False,
        "crit_damage_bonus": 0,
        "resist_ignore": None,
        "contributions": [],
    }
    if not isinstance(actx, dict):
        return out
    key = actx.get("key")
    if key is None:
        return out
    attacker_pid = actx.get("attacker")
    attacker = _part(state, attacker_pid)
    target = _part(state, target_pid)
    pct_by_type: Dict[str, float] = out["pct_by_type"]
    contribs: list = out["contributions"]

    def _add(type_key, pct):
        pct_by_type[type_key] = pct_by_type.get(type_key, 0) + pct
        contribs.append(contribution(key, KIND_DAMAGE_PCT, pct, attacker_pid))

    if key == PASSIVE_SABER:
        if target is not None and target.get("is_npc") is True:
            _add("all", SABER_NPC_DAMAGE_PCT)

    elif key == PASSIVE_ASSASSIN:
        if target is not None:
            max_hp = _num(target.get("max_hp"), 0)
            hp = _num(target.get("hp"), 0)
            if max_hp > 0 and hp * 100.0 < EXECUTE_HP_PCT * max_hp:
                _add("all", EXECUTE_DAMAGE_PCT)
        if actx.get("shadow"):
            out["force_crit"] = True
            out["crit_damage_bonus"] += SHADOW_CRIT_BONUS
            contribs.append(contribution(key, KIND_FORCED_CRIT, SHADOW_CRIT_BONUS, attacker_pid))

    elif key == PASSIVE_SALAMANDER:
        ps = _ps_read(attacker)
        stacks = max(0, min(KINDLING_MAX_STACKS, _int(ps.get("kindling_stacks"))))
        kt = ps.get("kindling_target")
        if (stacks > 0 and kt is not None and str(kt) == str(target_pid)
                and str(dmg_type).lower() == FIRE_TYPE):
            _add(str(dmg_type), KINDLING_PCT * stacks)

    elif key == PASSIVE_MECHANIC:
        if is_primary and actx.get("duel_bonus"):
            _add("all", actx["duel_bonus"])

    elif key == PASSIVE_ARCHER:
        done = _ps_read(attacker).get("first_blood_done") or []
        done_s = {str(x) for x in done} if isinstance(done, list) else set()
        granted = actx.setdefault("fb_granted", set())
        if str(target_pid) in granted or str(target_pid) not in done_s:
            granted.add(str(target_pid))
            out["force_crit"] = True
            out["crit_damage_bonus"] += FIRST_BLOOD_CRIT_BONUS
            contribs.append(contribution(key, KIND_FORCED_CRIT, FIRST_BLOOD_CRIT_BONUS, attacker_pid))

    elif key == PASSIVE_CASTER:
        out["resist_ignore"] = {MAGIC_TYPE: PURE_ENERGY_RESIST_IGNORE}
        if str(dmg_type).lower() == MAGIC_TYPE:
            contribs.append(contribution(
                key, KIND_RESIST_IGNORE, _clean_num(PURE_ENERGY_RESIST_IGNORE * 100), attacker_pid))

    return out


# =============================================================================
# H4 — defender resist deltas
# =============================================================================
def defender_resist_mods(state, defender_pid, attacker_pid) -> Tuple[Dict[str, float], List[dict]]:
    """H4. Resist deltas for `defender_pid` when hit by `attacker_pid`.

    Called in the target-ctx builder; ADD the deltas to a COPY of the
    defender's `build_percent_resist_buffs` dict (signed points). Returns
    `(delta_by_type, contributions)`.

      * Inquisitor heresy stacks ON THE DEFENDER: −3×n on every
        NON_PHYSICAL type (physical untouched) — for any attacker, so the
        Inquisitor's allies benefit too.
      * Gladiator defender: +4×surplus on "all" (surplus from the
        defender's own perspective, alive counts now).
      * Saber defender: +2×n on "all" from PvP «Несгибаемость» stacks.
    """
    deltas: Dict[str, float] = {}
    contribs: List[dict] = []
    defender = _part(state, defender_pid)
    if defender is None:
        return deltas, contribs
    ps = _ps_read(defender)

    stacks = max(0, min(HERESY_MAX_STACKS, _int(ps.get("heresy_stacks"))))
    if stacks > 0:
        d = -HERESY_RESIST_PER_STACK * stacks
        for t in NON_PHYSICAL_TYPES:
            deltas[t] = deltas.get(t, 0) + d
        contribs.append(contribution(PASSIVE_INQUISITOR, KIND_RESIST_PCT, d))

    key = _key_of(defender)
    if key == PASSIVE_GLADIATOR:
        surplus = _gladiator_surplus(state, defender_pid)
        if surplus > 0:
            d = ARENA_RESIST_PCT * surplus
            deltas["all"] = deltas.get("all", 0) + d
            contribs.append(contribution(key, KIND_RESIST_PCT, d, defender_pid))
    elif key == PASSIVE_SABER:
        n = max(0, min(SABER_PVP_MAX_STACKS, _int(ps.get("saber_pvp"))))
        if n > 0:
            d = SABER_PVP_RESIST_PCT * n
            deltas["all"] = deltas.get("all", 0) + d
            contribs.append(contribution(key, KIND_RESIST_PCT, d, defender_pid))

    return deltas, contribs


def defender_contribs_for_type(contribs, dmg_type) -> List[dict]:
    """Filter H4 contributions for ONE resolved damage type.

    The target ctx (and its contributions) is built before the entry type
    is known; heresy only cuts NON_PHYSICAL resists, so its contribution is
    dropped from the event of a hit whose resolved type it did not touch.
    Every other contribution ("all"-scoped) passes through unchanged."""
    if not contribs:
        return []
    t = str(dmg_type).lower()
    return [
        c for c in contribs
        if not (c.get("key") == PASSIVE_INQUISITOR
                and c.get("kind") == KIND_RESIST_PCT
                and t not in NON_PHYSICAL_TYPES)
    ]


def attacker_contribs_for_log(contribs, log) -> List[dict]:
    """Filter H3 contributions against the engine log of ONE roll.

    The Caster's «Чистая энергия» `resist_ignore` contribution is added for
    every magic roll, but the engine only ignores part of a POSITIVE resist
    (vulnerability / zero resist are untouched, no `resist_ignored_pct` in
    the log). Keep it only when the log shows points actually ignored.
    Every other contribution passes through unchanged."""
    if not contribs:
        return []
    ignored = _num((log or {}).get("resist_ignored_pct"), 0)
    return [
        c for c in contribs
        if not (c.get("key") == PASSIVE_CASTER
                and c.get("kind") == KIND_RESIST_IGNORE
                and ignored <= 0)
    ]


# =============================================================================
# H5 — flat stat deltas (Lancer)
# =============================================================================
def stat_deltas(state, pid) -> Dict[str, float]:
    """H5. Flat stat deltas of `pid` from Lancer steals: + what a Lancer
    gained, − what was stolen from this participant. `{}` when none."""
    p = _part(state, pid)
    if p is None:
        return {}
    ps = _ps_read(p)
    out: Dict[str, float] = {}
    gain = ps.get("lancer_gain")
    if isinstance(gain, dict) and _key_of(p) == PASSIVE_LANCER:
        for stat, amt in gain.items():
            a = _num(amt, 0)
            if a > 0:
                out[stat] = out.get(stat, 0) + a
    stolen = ps.get("stolen")
    if isinstance(stolen, dict):
        for stat, amt in stolen.items():
            a = _num(amt, 0)
            if a > 0:
                out[stat] = out.get(stat, 0) - a
    return out


def apply_stat_deltas(attrs, deltas) -> dict:
    """H5. Copy of `attrs` with `deltas` added. A lowered stat never goes
    below 0 (or below its own value if it already was negative). Apply to
    every attacker attrs copy and in the target-ctx builder, after the flat
    effect modifiers and BEFORE `roll_dodge`."""
    new = dict(attrs or {})
    if not isinstance(deltas, dict):
        return new
    for stat, delta in deltas.items():
        d = _num(delta, 0)
        if d == 0:
            continue
        orig = _num(new.get(stat), 0)
        val = orig + d
        if d < 0:
            val = max(val, min(orig, 0.0))
        new[stat] = val
    return new


# =============================================================================
# H6 — Trickster deceit
# =============================================================================
def roll_deceit(state, target_pid) -> bool:
    """H6. Target-ctx builder, only when the target did NOT dodge: True =
    the attack on the Trickster «не проходит» (10%). Rolls only for a
    Trickster target. Emit it as `{"event":"damage", ..., "dodged": True,
    "final": 0, "deceived": True, "passives": [deceit_contribution(t)]}` and
    do NOT call `on_dodged` for it."""
    if not _owns(state, target_pid, PASSIVE_TRICKSTER):
        return False
    return roll_pct(DECEIT_CHANCE)


def deceit_contribution(trickster_pid) -> dict:
    """Contribution for a deceit event (§3.5)."""
    return contribution(PASSIVE_TRICKSTER, KIND_DECEIT, owner=trickster_pid)


def deceit_redirect_target(state, attacker_pid, trickster_pid) -> Optional[int]:
    """H6 (FEAT-190 E19). Where a deceived attack goes instead.

    Called in `_finish_target_ctx` right after `roll_deceit` returned True
    (main stores the result as `ctx["redirect_pid"]`); NOT called for extra
    hits (`allow_redirect=False` — a deceived extra hit is a plain miss).

    Returns `pick()` of the attacker's teammates alive NOW, excluding the
    attacker himself (and the Trickster, defensively); None when there is no
    candidate (duel / lone attacker → the attack just fails, FEAT-189
    behaviour) or `trickster_pid` is not a Trickster. Rolls only when there
    are candidates and the target owns «Обман».

    main.py then strikes the returned ally with every entry aimed at the
    Trickster at `× REDIRECT_MULT` (0.5), plain ctx, no dodge, no passives of
    either side; only the ally's shields absorb (`land_hit(direct=False)`).
    """
    if not _owns(state, trickster_pid, PASSIVE_TRICKSTER):
        return None
    _, allies = _alive_sides(state, attacker_pid)
    candidates = [a for a in allies
                  if str(a) != str(attacker_pid) and str(a) != str(trickster_pid)]
    if not candidates:
        return None
    return pick(candidates)


def redirect_contribution(trickster_pid) -> dict:
    """Contribution for a redirected blow's damage event (§3.5):
    `{"key": "trickster_deceit", "kind": "redirect", "value": 50, "owner": trickster}`."""
    return contribution(PASSIVE_TRICKSTER, KIND_REDIRECT,
                        _clean_num(REDIRECT_MULT * 100), trickster_pid)


# =============================================================================
# H7 — real dodge
# =============================================================================
def on_dodged(state, dodger_pid) -> List[dict]:
    """H7. Call wherever a ctx `dodged` (a REAL dodge, not deceit) is consumed
    — skill, item and extra-hit paths; once per target per attack. Assassin:
    sets `shadow_ready` (next own attack = forced crit +25). Returns
    `passive_proc` events (only when the flag was newly set)."""
    p = _part(state, dodger_pid)
    if _key_of(p) != PASSIVE_ASSASSIN:
        return []
    ps = pstate(p)
    if ps.get("shadow_ready"):
        return []
    ps["shadow_ready"] = True
    return [passive_proc_event(dodger_pid, PASSIVE_ASSASSIN, PROC_SHADOW_READY)]


# =============================================================================
# H8 — record each damage roll
# =============================================================================
def _landed(log) -> bool:
    if not isinstance(log, dict):
        return False
    return not log.get("dodged") and not log.get("hit_chance_failed") and "final" in log


def record_strike(actx, target_pid, dmg, log, is_extra: bool = False,
                  target_attrs: Optional[dict] = None) -> None:
    """H8. Call after EACH `compute_damage_with_rolls` of the attack (skill
    loop, item loop) with the entry `dmg` and the engine `log`.

    `target_attrs` = the target ctx `attrs` used for this roll (after H5) —
    the Lancer steal reads the target's CURRENT dodge / crit from it, so pass
    it. `is_extra=True` for the extra hit → nothing is recorded (extra hits
    never trigger on-hit passives, first blood, Agent re-rolls or another
    extra hit).

    A roll "lands" when it is not dodged and not `hit_chance_failed` (final
    may be 0 after resists). Records per target: landed, crit, the first
    landed entry (Mechanic trigger), the first landed electricity/wind entry
    (Sparkmage trigger), whether fire landed (Salamander).
    """
    if not isinstance(actx, dict) or is_extra:
        return
    hits = actx.setdefault("hits", {})
    rec = hits.get(target_pid)
    if rec is None:
        rec = {"landed": False, "crit": False, "trigger": None,
               "chain_trigger": None, "fire": False, "attrs": None}
        hits[target_pid] = rec
    if rec["attrs"] is None and isinstance(target_attrs, dict):
        rec["attrs"] = target_attrs
    if not _landed(log):
        return
    rec["landed"] = True
    if log.get("critical"):
        rec["crit"] = True
    dtype = str(log.get("damage_type") or (dmg or {}).get("damage_type") or "").lower()
    if rec["trigger"] is None:
        rec["trigger"] = dmg
    if rec["chain_trigger"] is None and dtype in CHAIN_TYPES:
        rec["chain_trigger"] = dmg
    if dtype == FIRE_TYPE:
        rec["fire"] = True


def critted_targets(actx) -> List[Any]:
    """Targets that took a (landed) crit in this attack — Agent re-roll and
    coating bonus apply to them."""
    if not isinstance(actx, dict):
        return []
    return [t for t, rec in (actx.get("hits") or {}).items() if rec.get("crit")]


def landed_targets(actx) -> List[Any]:
    if not isinstance(actx, dict):
        return []
    return [t for t, rec in (actx.get("hits") or {}).items() if rec.get("landed")]


# =============================================================================
# H9 — attack finish (on-hit stacks)
# =============================================================================
def finish_attack(actx, state) -> List[dict]:
    """H9. After the attack's damage loop, BEFORE the Agent re-roll and the
    extra hit. Once per attack. Returns `passive_proc` events.

      * Archer: targets that took a landed hit are first-blooded for the rest
        of the battle (`first_blood_done`).
      * Inquisitor: +1 heresy stack (cap 5) on each landed target that has
        `used_magic`.
      * Lancer: per landed target, steals min(2, target's current value) of
        each LANCER_STOLEN_STATS (never below 0); a steal of >0 is one stack,
        up to 5 per Lancer. Affects NEXT attacks only.
      * Saber «Несгибаемость»: each Saber hit by a player attacker
        (`is_npc is False`) gets +1 PvP stack (cap 3) — once per attack.
      * Salamander: a landed fire hit on the primary → stack +1 (cap 5) on
        that target (a new target starts at 1).
    """
    events: List[dict] = []
    if not isinstance(actx, dict):
        return events
    attacker_pid = actx.get("attacker")
    attacker = _part(state, attacker_pid)
    if attacker is None:
        return events
    key = actx.get("key")
    hits = actx.get("hits") or {}
    landed = [t for t, rec in hits.items() if rec.get("landed")]

    # Saber PvP stacks — defender side, any attacker with is_npc False.
    if attacker.get("is_npc") is False:
        for t in landed:
            tp = _part(state, t)
            if _key_of(tp) != PASSIVE_SABER:
                continue
            ps = pstate(tp)
            cur = max(0, _int(ps.get("saber_pvp")))
            if cur < SABER_PVP_MAX_STACKS:
                ps["saber_pvp"] = cur + 1
                events.append(passive_proc_event(
                    t, PASSIVE_SABER, PROC_SABER_RESOLVE, stacks=cur + 1,
                    value=SABER_PVP_RESIST_PCT * (cur + 1)))

    if key == PASSIVE_ARCHER and landed:
        ps = pstate(attacker)
        done = ps.get("first_blood_done")
        if not isinstance(done, list):
            done = []
        done_s = {str(x) for x in done}
        for t in landed:
            if str(t) not in done_s:
                done.append(t)
                done_s.add(str(t))
        ps["first_blood_done"] = done

    elif key == PASSIVE_INQUISITOR:
        for t in landed:
            tp = _part(state, t)
            if tp is None or not _ps_read(tp).get("used_magic"):
                continue
            ps = pstate(tp)
            cur = max(0, _int(ps.get("heresy_stacks")))
            if cur < HERESY_MAX_STACKS:
                ps["heresy_stacks"] = cur + 1
                events.append(passive_proc_event(
                    attacker_pid, key, PROC_HERESY_STACK, target=t, stacks=cur + 1,
                    value=-HERESY_RESIST_PER_STACK * (cur + 1)))

    elif key == PASSIVE_LANCER:
        for t in landed:
            aps = _ps_read(attacker)
            stacks = max(0, _int(aps.get("lancer_stacks")))
            if stacks >= PIN_MAX_STACKS:
                break
            tp = _part(state, t)
            if tp is None:
                continue
            tattrs = hits[t].get("attrs")
            stolen_now: Dict[str, float] = {}
            for stat in LANCER_STOLEN_STATS:
                if isinstance(tattrs, dict):
                    avail = max(0.0, _num(tattrs.get(stat), 0))
                else:
                    avail = float(PIN_STEAL)   # unknown → assume enough
                amt = min(float(PIN_STEAL), avail)
                if amt > 0:
                    stolen_now[stat] = _clean_num(amt)
            if not stolen_now:
                continue
            aps_w = pstate(attacker)
            tps_w = pstate(tp)
            gain = aps_w.get("lancer_gain") if isinstance(aps_w.get("lancer_gain"), dict) else {}
            lost = tps_w.get("stolen") if isinstance(tps_w.get("stolen"), dict) else {}
            for stat, amt in stolen_now.items():
                gain[stat] = _clean_num(_num(gain.get(stat), 0) + amt)
                lost[stat] = _clean_num(_num(lost.get(stat), 0) + amt)
            aps_w["lancer_gain"] = gain
            tps_w["stolen"] = lost
            aps_w["lancer_stacks"] = stacks + 1
            events.append(passive_proc_event(
                attacker_pid, key, PROC_PIN, target=t, stacks=stacks + 1, stolen=stolen_now))

    elif key == PASSIVE_SALAMANDER:
        primary = actx.get("primary")
        rec = None
        for t, r in hits.items():
            if str(t) == str(primary):
                rec = r
                break
        if rec is not None and rec.get("fire"):
            ps = pstate(attacker)
            kt = ps.get("kindling_target")
            if kt is not None and str(kt) == str(primary):
                stacks = min(KINDLING_MAX_STACKS, max(0, _int(ps.get("kindling_stacks"))) + 1)
            else:
                stacks = 1
            ps["kindling_target"] = primary
            ps["kindling_stacks"] = stacks

    return events


# =============================================================================
# H10 — extra hit (Mechanic / Sparkmage)
# =============================================================================
def plan_extra_hit(actx, state) -> Optional[dict]:
    """H10. After H9 (and the Agent re-roll). At most ONE extra hit per
    attack — a second call returns None. Rolls only for Mechanic/Sparkmage.

    Candidates = attacker's enemies alive NOW, excluding the primary.
      * Mechanic: ≥1 landed hit; candidates → 30% → `splash` ×0.4 on a
        random candidate (no candidates → nothing here; the duel +35% was
        decided in H2).
      * Sparkmage: ≥1 landed electricity/wind roll; candidates → 25% →
        `chain` ×0.5 on a random candidate; none and the primary alive →
        25% → `echo` ×0.4 on the primary.

    Returns None or `{"target_pid", "entry", "mult", "kind", "contribution"}`:
    re-run `entry` through `_strike` with a FRESH target ctx (dodge, deceit,
    H7), the attack-level buffs only (no H3), normal crit roll, `× mult`,
    `record_strike(is_extra=True)`, event `extra_hit=kind`,
    `extra_mult=mult` and `contribution` in `passives`. Check the target is
    still alive right before striking.
    """
    if not isinstance(actx, dict) or actx.get("extra_planned"):
        return None
    actx["extra_planned"] = True
    key = actx.get("key")
    if key not in (PASSIVE_MECHANIC, PASSIVE_SPARKMAGE):
        return None
    attacker_pid = actx.get("attacker")
    primary = actx.get("primary")
    hits = actx.get("hits") or {}
    enemies, _ = _alive_sides(state, attacker_pid)
    candidates = [e for e in enemies if str(e) != str(primary)]

    def _plan(target, entry, mult, kind):
        return {
            "target_pid": target,
            "entry": entry,
            "mult": mult,
            "kind": kind,
            "contribution": contribution(key, KIND_EXTRA_HIT, _clean_num(mult * 100), attacker_pid),
        }

    if key == PASSIVE_MECHANIC:
        trigger = next((r["trigger"] for r in hits.values()
                        if r.get("landed") and r.get("trigger") is not None), None)
        if trigger is None or not candidates:
            return None
        if not roll_pct(SHRAPNEL_CHANCE):
            return None
        return _plan(pick(candidates), trigger, SHRAPNEL_MULT, EXTRA_SPLASH)

    # Sparkmage
    trigger = next((r["chain_trigger"] for r in hits.values()
                    if r.get("chain_trigger") is not None), None)
    if trigger is None:
        return None
    if candidates:
        if not roll_pct(CHAIN_CHANCE):
            return None
        return _plan(pick(candidates), trigger, CHAIN_MULT, EXTRA_CHAIN)
    prim = _part(state, primary)
    if prim is None or not _is_alive(prim):
        return None
    if not roll_pct(ECHO_CHANCE):
        return None
    return _plan(primary, trigger, ECHO_MULT, EXTRA_ECHO)


# =============================================================================
# H11 — effects (Monk / Agent / Trickster / Salamander)
# =============================================================================
def effect_chance_bonus_pp(caster, row) -> float:
    """H11a. Extra pp for an ENEMY-side effect row of `caster` (participant
    dict) — `_filter_effects_by_chance(bonus_pp_fn=…)`. Monk: +10 for soft
    control, +5 for hard control (stun / paralysis); else 0. No roll."""
    if _key_of(caster) != PASSIVE_MONK:
        return 0
    kind = control_kind(row)
    if kind == "hard":
        return HARMONY_HARD_CONTROL_BONUS_PP
    if kind == "soft":
        return HARMONY_CONTROL_BONUS_PP
    return 0


def weak_spot_bonus_pp(caster, row) -> float:
    """H11b. Agent's direct bonus pp for a row rolled AFTER the crit is known
    (weapon coating on a critted target): +20, +10 for hard control. 0 for
    non-Agents. No roll."""
    if _key_of(caster) != PASSIVE_AGENT:
        return 0
    return WEAK_SPOT_HARD_CONTROL_BONUS_PP if control_kind(row) == "hard" else WEAK_SPOT_BONUS_PP


def weak_spot_reroll(caster, row, failed_chance) -> bool:
    """H11b. Conditional re-roll (D5) for an enemy-side row that FAILED its
    pre-damage roll with effective chance `failed_chance` (from
    `failed_out`), on a target the Agent critted this attack. Chance
    q = bonus / (100 − p) × 100 (clamped), so the overall chance becomes
    exactly min(100, p + bonus). True → land the row (through the landing
    wrapper). Non-Agents → False with no roll."""
    bonus = weak_spot_bonus_pp(caster, row)
    if bonus <= 0:
        return False
    p = max(0.0, min(100.0, _num(failed_chance, 0)))
    if p >= 100:
        return False
    q = min(100.0, bonus / (100.0 - p) * 100.0)
    return roll_pct(q)


def weak_spot_event(agent_pid, target_pid, effects) -> dict:
    """`passive_proc` for effects that landed by the Agent re-roll."""
    return passive_proc_event(agent_pid, PASSIVE_AGENT, PROC_WEAK_SPOT,
                              target=target_pid, effects=effects)


def _is_instant_resource(row) -> bool:
    return _row_attr(row) in RESOURCE_ATTRS and _num((row or {}).get("duration"), 0) <= 1


def adjust_outgoing_enemy_rows(caster, rows, caster_pid=None) -> Tuple[List[dict], List[dict]]:
    """H11c. In `_land_enemy_effects`, BEFORE H11d / `apply_new_effects`.
    Returns `(row copies, contributions)` — input rows are never mutated.

      * Trickster: every row with duration ≥ 1 gets +1 turn, except hard
        control (stun / poison-paralysis) and instant resource rows
        (hp/mana/energy/stamina with duration ≤ 1).
      * Salamander: only `Burn` rows get +1 turn.
    Contribution: `{"key", "kind": "duration_plus", "value": 1, "owner"}`
    once per batch when anything was bumped.
    """
    copies = [dict(r) if isinstance(r, dict) else r for r in (rows or [])]
    key = _key_of(caster)
    if key not in (PASSIVE_TRICKSTER, PASSIVE_SALAMANDER):
        return copies, []
    bumped = False
    for r in copies:
        if not isinstance(r, dict):
            continue
        dur = _num(r.get("duration"), 0)
        if dur < 1 or control_kind(r) == "hard":
            continue
        if key == PASSIVE_TRICKSTER:
            if _is_instant_resource(r):
                continue
            r["duration"] = _int(r.get("duration")) + DEBUFF_EXTRA_TURNS
            bumped = True
        elif _row_name(r) == BURN_EFFECT_NAME:
            r["duration"] = _int(r.get("duration")) + BURN_EXTRA_TURNS
            bumped = True
    contribs = [contribution(key, KIND_DURATION_PLUS, 1, caster_pid)] if bumped else []
    return copies, contribs


def filter_incoming_control(target, rows, target_pid) -> Tuple[List[dict], List[dict]]:
    """H11d. In `_land_enemy_effects`, after H11c, on rows that PASSED their
    roll. Monk: the FIRST control row (hard or soft, by name) landing on the
    Monk in this battle is dropped (`control_immunity_used`) and a
    `control_immune` `passive_proc` is returned; the rest of the batch lands.
    Returns `(kept_rows, events)`."""
    rows = list(rows or [])
    if _key_of(target) != PASSIVE_MONK or _ps_read(target).get("control_immunity_used"):
        return rows, []
    for i, r in enumerate(rows):
        if control_kind(r) is not None:
            pstate(target)["control_immunity_used"] = True
            name = (r.get("effect_name") or r.get("name")) if isinstance(r, dict) else None
            ev = passive_proc_event(target_pid, PASSIVE_MONK, PROC_CONTROL_IMMUNE,
                                    effects=[name] if name else None)
            return rows[:i] + rows[i + 1:], [ev]
    return rows, []


# =============================================================================
# H12 — mana cost (Caster)
# =============================================================================
def mana_cost(participant, raw_cost):
    """H12. Effective mana cost of one rank in `_pay_skill_costs`, applied
    BEFORE the affordability check. Caster: −10%, integer round-half-up
    `(raw × 90 + 50) // 100` (0→0, 1→1, 5→5, 10→9, 15→14, 25→23); the
    frontend `utils/passiveCosts.ts` mirrors the same formula. Others (and
    non-positive / garbage costs): `raw_cost` unchanged."""
    if _key_of(participant) != PASSIVE_CASTER:
        return raw_cost
    cost = _int(raw_cost, 0)
    if cost <= 0:
        return raw_cost
    return (cost * (100 - CASTER_MANA_DISCOUNT_PCT) + 50) // 100


def mana_discount_contribution(value, owner=None) -> dict:
    """Contribution for the `resource_spend` event (value = mana saved)."""
    return contribution(PASSIVE_CASTER, KIND_MANA_DISCOUNT, value, owner)


# =============================================================================
# H23 — Necromancer «Плата кровью» (mana shortfall paid with HP)
# =============================================================================
def blood_hp_cost(shortfall) -> int:
    """HP needed to cover `shortfall` mana: `ceil(shortfall × 1.5)`, 0 for
    non-positive / garbage. Same integer rule as the frontend
    `utils/passiveCosts.ts::bloodPriceHp` (1→2, 3→5, 10→15)."""
    s = _num(shortfall, 0.0)
    if s <= 0:
        return 0
    # The epsilon keeps exact products (10 × 1.5 = 15.0) from ceiling up.
    return int(math.ceil(s * BLOOD_HP_PER_MANA - 1e-9))


def blood_price(participant, mana_cost) -> Optional[dict]:
    """H23 (FEAT-190 E13). Called in `_pay_skill_costs` AFTER the H12 loop
    summed the (possibly discounted) mana cost of all ranks, BEFORE the
    generic affordability check and before any deduction.

    Inputs: `participant` — the actor's Redis participant dict (read only,
    never mutated here); `mana_cost` — total mana of the action.

    Returns None (→ the old code path, generic mana check) unless the actor
    is a Necromancer with `mana < mana_cost`. Otherwise a dict:
      hp_cost    — int HP to deduct (`blood_hp_cost(cost − mana)`); 0 when
                   waived;
      mana_paid  — the mana actually spent (= current mana; mana → 0);
      affordable — `hp − hp_cost ≥ BLOOD_MIN_HP_LEFT` (strict "can't kill
                   yourself"); False → main raises the Russian 400 and the
                   turn is void (state unsaved);
      waived     — True when the Necromancer is already dead (hp ≤ 0 —
                   killed by a reflect earlier in this action, Q7): no HP
                   is taken, mana → 0, `affordable` True, no `hp_paid`.
    main.py then: energy/stamina checked as before, `mana = 0`,
    `hp −= hp_cost` (bypasses shields, triggers nothing), `spend["mana"] =
    mana_paid`, `spend["hp_paid"] = hp_cost` only when > 0.
    """
    if _key_of(participant) != PASSIVE_NECROMANCER:
        return None
    cost = _num(mana_cost, 0.0)
    mana = max(0.0, _num(participant.get("mana"), 0.0))
    if cost <= 0 or cost <= mana:
        return None
    hp = _num(participant.get("hp"), 0.0)
    mana_paid = _clean_num(mana)
    if hp <= 0:
        return {"hp_cost": 0, "mana_paid": mana_paid, "affordable": True, "waived": True}
    hp_cost = blood_hp_cost(cost - mana)
    return {
        "hp_cost": hp_cost,
        "mana_paid": mana_paid,
        "affordable": hp - hp_cost >= BLOOD_MIN_HP_LEFT,
        "waived": False,
    }


def blood_price_contribution(value, owner=None) -> dict:
    """Contribution for the `resource_spend` event (value = HP paid, §3.5)."""
    return contribution(PASSIVE_NECROMANCER, KIND_BLOOD_PRICE, value, owner)


# =============================================================================
# H13 — kills (Saber run stacks)
# =============================================================================
def on_kills(state, killer_pid, victim_pids) -> Tuple[List[dict], Optional[int]]:
    """H13. Step 9.5: `victim_pids` = enemies of the actor newly defeated
    during this action (D11 — every HP loss in an action is the actor's,
    DoT ticks included). Returns `(events, stacks_to_persist)`.

      * Saber in a dungeon battle (`state["dungeon_session_id"]` set): +1
        kill stack per victim (cap 5 = +10%), effective immediately.
        `stacks_to_persist` is the new `saber_kills` (→
        `redis_state.set_saber_run_stacks`) or None when nothing changed.
      * Necromancer (FEAT-190 E13, any battle): per victim of another team,
        if the Necromancer is alive, heal `NECRO_KILL_HEAL_PCT`% of his
        `max_hp` (clamped to max; `max_hp` itself never changes). One
        `kill_heal` proc (`who` = Necro, `target` = victim, `value` = HP
        healed, int) per victim that actually healed (> 0) — at full HP no
        event. `stacks_to_persist` is always None.
    Everyone else: `([], None)`."""
    if not isinstance(state, dict):
        return [], None
    killer = _part(state, killer_pid)
    key = _key_of(killer)
    if key == PASSIVE_NECROMANCER:
        return _necro_kill_heals(state, killer_pid, killer, victim_pids), None
    if key != PASSIVE_SABER or not state.get("dungeon_session_id"):
        return [], None
    team = killer.get("team")
    seen = set()
    events: List[dict] = []
    ps = None
    changed = False
    for v in victim_pids or []:
        if str(v) in seen:
            continue
        seen.add(str(v))
        vp = _part(state, v)
        if vp is not None and vp.get("team") == team:
            continue
        if ps is None:
            ps = pstate(killer)
        cur = max(0, _int(ps.get("saber_kills")))
        if cur >= SABER_KILL_MAX_STACKS:
            break
        ps["saber_kills"] = cur + 1
        changed = True
        events.append(passive_proc_event(
            killer_pid, PASSIVE_SABER, PROC_SABER_KILL, target=v, stacks=cur + 1,
            value=SABER_KILL_PCT * (cur + 1)))
    return events, (ps["saber_kills"] if changed else None)


def _necro_kill_heals(state, killer_pid, killer, victim_pids) -> List[dict]:
    """Necromancer branch of H13 (see `on_kills`)."""
    if killer is None or not _is_alive(killer):
        return []
    team = killer.get("team")
    max_hp = _num(killer.get("max_hp"), 0)
    if max_hp <= 0:
        return []
    events: List[dict] = []
    seen = set()
    for v in victim_pids or []:
        if str(v) in seen:
            continue
        seen.add(str(v))
        vp = _part(state, v)
        if vp is not None and vp.get("team") == team:
            continue
        healed = heal(killer, max_hp * NECRO_KILL_HEAL_PCT / 100.0)
        if healed > 0:
            events.append(passive_proc_event(
                killer_pid, PASSIVE_NECROMANCER, PROC_KILL_HEAL,
                target=v, value=int(round(healed))))
    return events


# =============================================================================
# FEAT-190 — wave 2: shields, heals, vow, lifesteal, reflect
# =============================================================================
# Shield entries live on the SHIELDED participant (E3):
#   passive_state["shields"] = [{"key", "owner", "amount", "cap",
#                                "turns_left", "fresh"}, ...]
#   key        — source passive (PASSIVE_PALADIN / PASSIVE_AUROMANCER)
#   owner      — pid whose passive created it (its turns tick `turns_left`)
#   amount     — float > 0 (an entry at ~0 is removed)
#   cap        — its ceiling (top-ups never exceed it)
#   turns_left — int (timed: Auromancer) or None (Paladin: until broken / end)
#   fresh      — skip the first owner-turn tick (creation turn)
# Not an `active_effects` row on purpose: cleanse `all` would strip it,
# `aggregate_modifiers` would sum it, absorb mutates it.
_SHIELD_EPS = 1e-6
SHIELD_PROC_KEY = "shield"   # `key` of `shield_absorb` procs (may mix sources)


def _shield_list(participant) -> list:
    """Read-only list of the participant's valid shield entries (no create)."""
    shields = _ps_read(participant).get("shields")
    if not isinstance(shields, list):
        return []
    return [e for e in shields if isinstance(e, dict)]


def shield_total(participant) -> int:
    """H14. `round(Σ amount)` of the participant's shields; 0 for old states,
    no shields or garbage. Goes into every runtime participant payload as
    `shield` (E20) and into event fields (`shield_left`, proc `shield`).
    Never creates `passive_state`."""
    total = 0.0
    for e in _shield_list(participant):
        a = _num(e.get("amount"), 0)
        if a > 0:
            total += a
    return int(round(total))


def _passthrough(amount, amt: float):
    """The caller's own number back when nothing changed, so a battle without
    shields keeps the exact same int/float values (byte-identical results)."""
    if (isinstance(amount, (int, float)) and not isinstance(amount, bool)
            and math.isfinite(amount)):
        return amount
    return amt


def absorb(state, pid, amount) -> Tuple[float, float]:
    """H15. Lets `pid`'s shields absorb `amount` of incoming damage.

    Called from `land_hit` (direct strikes), `retaliate` (reflect) and
    main's `absorb_fn` closure handed to buffs (enemy instant HP rows, DoT,
    negative HP doses). NOT for Necromancer HP payment or timeout drop-out.

    Returns `(remaining, absorbed)`: `remaining` = damage that still hits
    the HP bar. No shields / `amount ≤ 0` / garbage / dead holder →
    `(amount, 0.0)` with `amount` returned as-is (same object/type).

    Order (E4): timed entries first, shortest `turns_left` first, then
    permanent ones (`turns_left` None); ties → list order. Mutates amounts
    in place and removes emptied (and garbage) entries from
    `passive_state["shields"]`.
    """
    amt = _num(amount, 0.0)
    p = _part(state, pid)
    if p is None or amt <= 0 or not _is_alive(p):
        return _passthrough(amount, amt), 0.0
    ps = _ps_read(p)
    raw = ps.get("shields")
    if not isinstance(raw, list) or not raw:
        return _passthrough(amount, amt), 0.0
    entries = [e for e in raw
               if isinstance(e, dict) and _num(e.get("amount"), 0) > _SHIELD_EPS]

    def _order(i):
        tl = entries[i].get("turns_left")
        if tl is None:
            return (1, 0.0, i)
        return (0, _num(tl, 0), i)

    left = amt
    absorbed = 0.0
    for i in sorted(range(len(entries)), key=_order):
        if left <= 0:
            break
        e = entries[i]
        cur = _num(e.get("amount"), 0)
        take = min(cur, left)
        e["amount"] = cur - take
        left -= take
        absorbed += take
    ps["shields"] = [e for e in entries if _num(e.get("amount"), 0) > _SHIELD_EPS]
    if absorbed <= 0:
        return _passthrough(amount, amt), 0.0
    return max(0.0, left), absorbed


def add_shield(state, pid, key: str, owner, amount, cap, turns_left) -> float:
    """H16. Gives `pid` a shield from passive `key` owned by `owner`.

    Internal (vow, tide); exposed for tests. Returns the amount actually
    added (cap-limited, float ≥ 0). An existing entry with the same
    (`key`, `owner`) is TOPPED UP to at most `cap` (cap updated), its
    `turns_left` reset to `turns_left` and — for timed entries — `fresh`
    set again, so a top-up made on the owner's turn isn't eaten by that
    same turn's tick (E4 "turns reset to 3"); the reset also happens when
    the entry already sits at its cap (gained 0). Otherwise a new entry
    `{key, owner, amount=min(amount, cap), cap, turns_left, fresh}` is
    appended (`fresh` True only for timed entries). Dead / unknown target,
    `amount ≤ 0` or `cap ≤ 0` → 0.0 and nothing changes.
    """
    p = _part(state, pid)
    amt = _num(amount, 0.0)
    cap_f = _num(cap, 0.0)
    if p is None or not _is_alive(p) or amt <= 0 or cap_f <= 0:
        return 0.0
    timed = turns_left is not None
    ps = pstate(p)
    shields = ps.get("shields")
    if not isinstance(shields, list):
        shields = []
    shields = [e for e in shields if isinstance(e, dict)]
    ps["shields"] = shields
    for e in shields:
        if e.get("key") == key and str(e.get("owner")) == str(owner):
            cur = max(0.0, _num(e.get("amount"), 0))
            new = max(cur, min(cap_f, cur + amt))
            e["amount"] = new
            e["cap"] = cap_f
            e["turns_left"] = turns_left
            e["fresh"] = timed
            return new - cur
    gained = min(amt, cap_f)
    shields.append({
        "key": key,
        "owner": owner,
        "amount": gained,
        "cap": cap_f,
        "turns_left": turns_left,
        "fresh": timed,
    })
    return gained


def tick_shields(state, actor_pid) -> None:
    """H17. Step 9.4, right after `decrement_durations(state, actor)`.

    For every participant, timed shields (`turns_left` not None) OWNED by
    `actor_pid`: `fresh` → clear the flag (creation turn skipped); else
    `turns_left −= 1`, the entry is dropped at 0. Permanent (Paladin) and
    other owners' shields are untouched. Same clock as the effects the
    owner casts (E6). Never creates `passive_state`; no events.
    """
    for p in _participants(state).values():
        if not isinstance(p, dict):
            continue
        ps = _ps_read(p)
        shields = ps.get("shields")
        if not isinstance(shields, list) or not shields:
            continue
        kept = []
        for e in shields:
            if not isinstance(e, dict):
                continue
            if e.get("turns_left") is None or str(e.get("owner")) != str(actor_pid):
                kept.append(e)
                continue
            if e.get("fresh"):
                e["fresh"] = False
                kept.append(e)
                continue
            e["turns_left"] = _int(e.get("turns_left")) - 1
            if e["turns_left"] > 0:
                kept.append(e)
        ps["shields"] = kept


def shield_absorb_event(state, holder_pid, absorbed) -> Optional[dict]:
    """`passive_proc shield_absorb` (§3.5) for EFFECT / DoT damage eaten by
    shields — main's `_flush_absorbs` builds one per holder from the
    amounts its `absorb_fn` closure collected (strikes and reflects report
    `absorbed` on their damage event instead). `who` = holder, `key` =
    SHIELD_PROC_KEY (a hit may drain shields of several sources), `value` =
    absorbed (int), `shield` = holder's total left. None when the rounded
    value is 0 (main appends nothing)."""
    v = int(round(_num(absorbed, 0)))
    if v <= 0:
        return None
    return passive_proc_event(holder_pid, SHIELD_PROC_KEY, PROC_SHIELD_ABSORB,
                              value=v, shield=shield_total(_part(state, holder_pid)))


def heal(participant, amount) -> float:
    """H21. Heals `participant` by `amount`, clamped to `max_hp`.

    Internal (lifesteal, «Вера», Necromancer kill heal). Never heals a
    participant with `hp ≤ 0` (dead) or dropped out, never lowers HP (a
    participant already at/above max is left as is), never creates a
    shield (overflow is lost — tide is only for heals CAST by an
    Auromancer). Returns the HP actually restored (float ≥ 0)."""
    if not isinstance(participant, dict) or not _is_alive(participant):
        return 0.0
    amt = _num(amount, 0.0)
    max_hp = _num(participant.get("max_hp"), 0)
    hp = _num(participant.get("hp"), 0)
    if amt <= 0 or max_hp <= 0 or hp >= max_hp:
        return 0.0
    new = min(max_hp, hp + amt)
    participant["hp"] = new
    return new - hp


def on_heal(state, healer_pid, target_pid, intended, applied) -> List[dict]:
    """H22 (FEAT-190 E18) — Auromancer «Прилив».

    Called by main's `overheal_fn(pid, intended, applied, owner_id)` closure
    as `on_heal(state, owner_id, pid, intended, applied)` — buffs calls the
    closure for every POSITIVE HP dose: skill / item HP rows (self, ally,
    all_allies, item non-enemy, incl. the first dose of a HoT) and every
    HoT dose at 9.4a, also when the target is at full HP and nothing was
    applied — and by main's potion path (`health_recovery`:
    `on_heal(state, actor, actor, delta, new − old)`).

    `healer_pid` must own «Прилив» and the target must be alive; overflow
    `intended − applied > 0` → `add_shield(target, PASSIVE_AUROMANCER,
    owner=healer, overflow, cap = TIDE_CAP_PCT% of the TARGET's max_hp,
    TIDE_TURNS)` (tops up his existing tide on that target). Returns
    `[passive_proc tide]` (`who` = Auromancer, `target`, `value` = shield
    gained int, `shield` = target total after) when something was gained,
    else `[]`. Rolls nothing.
    """
    if not _owns(state, healer_pid, PASSIVE_AUROMANCER):
        return []
    target = _part(state, target_pid)
    if target is None or not _is_alive(target):
        return []
    overflow = _num(intended, 0.0) - _num(applied, 0.0)
    if overflow <= _SHIELD_EPS:
        return []
    cap = _num(target.get("max_hp"), 0) * TIDE_CAP_PCT / 100.0
    gained = add_shield(state, target_pid, PASSIVE_AUROMANCER, healer_pid,
                        overflow, cap, TIDE_TURNS)
    if gained <= _SHIELD_EPS:
        return []
    return [passive_proc_event(healer_pid, PASSIVE_AUROMANCER, PROC_TIDE,
                               target=target_pid, value=int(round(gained)),
                               shield=shield_total(target))]


# --- H18 — Paladin «Священный обет» -----------------------------------------
def _vow_cleanse(state, paladin_pid, paladin) -> Optional[str]:
    """Pops the LAST (most recent) negative removable row from the
    Paladin's `active_effects` and returns its name ("" if unnamed), None
    if nothing was removed. Negative = `owner_id` belongs to a participant
    of ANOTHER team (rows without `owner_id` / unknown owner → treated as
    own → not negative). Hard control (Stun / Poison-paralysis) is never
    removed."""
    active = state.get("active_effects") if isinstance(state, dict) else None
    if not isinstance(active, dict):
        return None
    lst = active.get(str(paladin_pid))
    if not isinstance(lst, list) or not lst:
        return None
    team = paladin.get("team")
    for i in range(len(lst) - 1, -1, -1):
        row = lst[i]
        if not isinstance(row, dict):
            continue
        owner = row.get("owner_id")
        if owner is None:
            continue
        op = _part(state, owner)
        if op is None or op.get("team") == team:
            continue
        if control_kind(row) == "hard":
            continue
        lst.pop(i)
        name = row.get("name") or row.get("effect_name")
        return str(name) if name else ""
    return None


def check_vow(state, pid) -> List[dict]:
    """H18. Vow check on ONE participant after it lost HP.

    Called inside `land_hit` (step ④, target of a direct non-redirected
    strike), inside `retaliate` (attacker side) and via `check_vows` after
    the effect wrappers and the DoT tick. Condition: `pid` owns «Священный
    обет», alive, `0 < hp < VOW_HP_PCT% max_hp` (so 40% → 0 in one hit
    never triggers), `vow_used` not set. Then: `vow_used = True`, a
    permanent shield of `VOW_SHIELD_PCT`% max HP (`add_shield`, turns None)
    and ONE cleanse (`_vow_cleanse`). Returns `[passive_proc vow]` (`who` =
    Paladin, `value` = shield gained int, `shield` = total after, `effects`
    = [removed name], absent when nothing was removed) or `[]`.
    """
    p = _part(state, pid)
    if _key_of(p) != PASSIVE_PALADIN or not _is_alive(p):
        return []
    if _ps_read(p).get("vow_used"):
        return []
    max_hp = _num(p.get("max_hp"), 0)
    hp = _num(p.get("hp"), 0)
    if max_hp <= 0 or hp * 100.0 >= VOW_HP_PCT * max_hp:
        return []
    pstate(p)["vow_used"] = True
    shield = max_hp * VOW_SHIELD_PCT / 100.0
    gained = add_shield(state, pid, PASSIVE_PALADIN, pid, shield, shield, None)
    removed = _vow_cleanse(state, pid, p)
    return [passive_proc_event(
        pid, PASSIVE_PALADIN, PROC_VOW, value=int(round(gained)),
        shield=shield_total(p), effects=[removed] if removed is not None else None)]


def snapshot_hp(state) -> Dict[int, float]:
    """H18 helper. `{pid: hp}` of every participant right now — take it
    BEFORE an effect application / the DoT tick and pass it to
    `check_vows`. Non-int pids and garbage are skipped."""
    out: Dict[int, float] = {}
    for spid, p in _participants(state).items():
        if not isinstance(p, dict):
            continue
        try:
            out[int(spid)] = _num(p.get("hp"), 0)
        except (TypeError, ValueError):
            continue
    return out


def check_vows(state, before) -> List[dict]:
    """H18 sweep. `check_vow` for every participant whose HP is now LOWER
    than in the `before` snapshot (`snapshot_hp`; keys int or str). Called
    after `_land_enemy_effects`, after the non-enemy effect wrapper and
    after the DoT tick (9.4a, after the periodic events). Returns the vow
    events in participant order."""
    if not isinstance(before, dict):
        return []
    prev = {str(k): v for k, v in before.items()}
    events: List[dict] = []
    for spid, p in _participants(state).items():
        if not isinstance(p, dict) or str(spid) not in prev:
            continue
        if _num(p.get("hp"), 0) < _num(prev[str(spid)], 0):
            try:
                pid = int(spid)
            except (TypeError, ValueError):
                continue
            events.extend(check_vow(state, pid))
    return events


# --- H19 — lifesteal (Berserk «Ярость» < 25%, Priest «Вера») -----------------
def lifesteal(state, attacker_pid, hp_removed, damage_type) -> Optional[dict]:
    """H19 (FEAT-190 E11). Inside `land_hit`, step ⑤ — only for direct
    enemy-side strikes (skill, scroll, extra hit); never redirected blows,
    DoT, effect damage or reflect.

    `hp_removed` = HP actually taken off the target's bar by this strike
    (after its shield, overkill excluded). Attacker must be alive.
      * Berserk: attacker `hp < RAGE_LIFESTEAL_HP_PCT% max_hp` right now
        (before this hit's heal) → `RAGE_LIFESTEAL_PCT`%;
      * Priest: `FAITH_LIFESTEAL_PCT`%, `FAITH_HOLY_LIFESTEAL_PCT`% when the
        resolved `damage_type == HOLY_TYPE` ("sainting").
    Heals via `heal` (max-capped). Returns the damage-event contribution
    `{"key", "kind": "lifesteal", "value": healed int, "owner": attacker}`,
    or None when nothing was healed / no such passive.
    """
    attacker = _part(state, attacker_pid)
    if attacker is None or not _is_alive(attacker):
        return None
    removed = _num(hp_removed, 0.0)
    if removed <= 0:
        return None
    key = _key_of(attacker)
    if key == PASSIVE_BERSERKER_RAGE:
        max_hp = _num(attacker.get("max_hp"), 0)
        hp = _num(attacker.get("hp"), 0)
        if max_hp <= 0 or hp * 100.0 >= RAGE_LIFESTEAL_HP_PCT * max_hp:
            return None
        pct = RAGE_LIFESTEAL_PCT
    elif key == PASSIVE_PRIEST:
        is_holy = str(damage_type or "").strip().lower() == HOLY_TYPE
        pct = FAITH_HOLY_LIFESTEAL_PCT if is_holy else FAITH_LIFESTEAL_PCT
    else:
        return None
    healed = heal(attacker, removed * pct / 100.0)
    if healed <= 0:
        return None
    return contribution(key, KIND_LIFESTEAL, int(round(healed)), attacker_pid)


# --- H20 — Guardian «Возмездие» ----------------------------------------------
def retaliate(state, guardian_pid, attacker_pid, taken, damage_type) -> List[dict]:
    """H20 (FEAT-190 E9). Inside `land_hit`, step ⑥ (after lifesteal).

    `guardian_pid` = the struck target; `taken` = damage it took from this
    strike after resists: shield-absorbed part + HP removed, overkill
    excluded. Fires when the target owns «Возмездие» (alive or just killed
    by this very hit, Q6), the attacker is an ALIVE participant of ANOTHER
    team and `R = taken × RETRIBUTION_PCT%` > 0.

    R is applied directly — no engine: no crit, dodge, resists, deceit,
    H3/H8; it is never reflected again (this function is never reached from
    the reflect path, so Guardian vs Guardian yields exactly one reflect)
    and never lifesteals. The attacker's shields absorb first, then
    `hp −= remaining` (unclamped like `_strike`; can kill), then
    `check_vow(attacker)`. Stats: `round(R)` is added to the Guardian's
    `total_damage_dealt` and the attacker's `total_damage_received`.

    Returns `[reflect damage event, *attacker vow events]` or `[]`:
    `{"event": "damage", "source": guardian, "target": attacker,
      "final": round(R, 2), "damage_type": type, "reflected": True,
      "absorbed": int, "shield_left"?: int (only when absorbed > 0),
      "passives": [{"key": "guardian_retribution", "kind": "reflect",
                    "value": round(R), "owner": guardian}]}`.
    """
    guardian = _part(state, guardian_pid)
    attacker = _part(state, attacker_pid)
    if _key_of(guardian) != PASSIVE_GUARDIAN or attacker is None:
        return []
    if str(guardian_pid) == str(attacker_pid) or guardian.get("team") == attacker.get("team"):
        return []
    if not _is_alive(attacker):
        return []
    reflect = _num(taken, 0.0) * RETRIBUTION_PCT / 100.0
    if reflect <= 0:
        return []
    remaining, absorbed = absorb(state, attacker_pid, reflect)
    attacker["hp"] = _num(attacker.get("hp"), 0) - _num(remaining, 0)
    r_int = int(round(reflect))
    guardian["total_damage_dealt"] = guardian.get("total_damage_dealt", 0) + r_int
    attacker["total_damage_received"] = attacker.get("total_damage_received", 0) + r_int
    ev: Dict[str, Any] = {
        "event": "damage",
        "source": guardian_pid,
        "target": attacker_pid,
        "final": round(reflect, 2),
        "damage_type": str(damage_type or "physical"),
        "reflected": True,
        "absorbed": int(round(absorbed)),
    }
    if absorbed > 0:
        ev["shield_left"] = shield_total(attacker)
    ev["passives"] = [contribution(PASSIVE_GUARDIAN, KIND_REFLECT, r_int, guardian_pid)]
    return [ev] + check_vow(state, attacker_pid)


# --- Strike resolution in the fixed E7 order ---------------------------------
def land_hit(state, attacker_pid, target_pid, dealt, damage_type,
             direct: bool = True) -> dict:
    """Puts ONE strike's engine damage on the target in the fixed E7 order.

    Call from `_strike` in place of `target_state["hp"] -= dealt`, once the
    engine `dealt` (× mult) is known. main keeps counting `dealt_int` into
    `total_damage_dealt/received` exactly as before (E21).

      ② target shields absorb (`absorb`) → ③ `hp −= remaining` (unclamped);
      `hp_removed = min(remaining, max(0, hp_before))` →
      ④ `check_vow(target)` → ⑤ `lifesteal(attacker, hp_removed)` →
      ⑥ `retaliate(target, attacker, absorbed + hp_removed)`.

    `direct=False` for redirected «Обман» blows (and for strikes that must
    not trigger passives, e.g. non-enemy item rows with `actx=None`): only
    ②/③ run — no vow, no lifesteal, no reflect.

    Returns a dict:
      absorbed      — float absorbed by the target's shields;
      shield_left   — int target shield after (0 when none);
      hp_removed    — float HP actually removed (overkill excluded);
      contributions — [lifesteal contribution] or [] → append to the
                      strike event's `passives`;
      post_events   — events to append AFTER the strike event, in order:
                      target vow, reflect damage event, attacker vow.
    Put `absorbed` (int) / `shield_left` on the strike event only when
    `absorbed > 0` (§3.5). With no shields and no passive owners the HP
    change is exactly the old `hp -= dealt` (same number object), and the
    result has no contributions / post events.
    """
    out: Dict[str, Any] = {
        "absorbed": 0.0, "shield_left": 0, "hp_removed": 0.0,
        "contributions": [], "post_events": [],
    }
    target = _part(state, target_pid)
    if target is None:
        return out
    remaining, absorbed = absorb(state, target_pid, dealt)
    hp_before = _passthrough(target.get("hp", 0), _num(target.get("hp"), 0.0))
    target["hp"] = hp_before - remaining
    hp_removed = max(0.0, min(_num(remaining, 0.0), max(0.0, _num(hp_before, 0))))
    out["absorbed"] = absorbed
    out["shield_left"] = shield_total(target)
    out["hp_removed"] = hp_removed
    if not direct:
        return out
    post: List[dict] = out["post_events"]
    post.extend(check_vow(state, target_pid))
    steal = lifesteal(state, attacker_pid, hp_removed, damage_type)
    if steal is not None:
        out["contributions"].append(steal)
    post.extend(retaliate(state, target_pid, attacker_pid, absorbed + hp_removed, damage_type))
    return out


# =============================================================================
# H24 — end of the actor's action (Bard «Ритм», Etheriad «Шёпот духов»)
# =============================================================================
def _stat_row(name: str, attribute_key: str, magnitude, duration: int) -> dict:
    """Raw StatModifier row for `buffs.apply_new_effects` (normalized there
    to `{name, attribute, magnitude, duration}`)."""
    return {"effect_name": name, "attribute_key": attribute_key,
            "magnitude": magnitude, "duration": duration}


def _bard_end_of_action(state, actor_pid, actor, skipped: bool):
    _, allies = _alive_sides(state, actor_pid)
    mates = [a for a in allies if str(a) != str(actor_pid)]
    if mates:
        mode, pct, cap = "group", INSPIRATION_PCT, INSPIRATION_MAX_STACKS
    else:
        mode, pct, cap = "solo", INSPIRATION_SOLO_PCT, INSPIRATION_SOLO_MAX_STACKS
    ps = pstate(actor)
    stacks = max(0, min(cap, _int(ps.get("bard_stacks"))))   # clamp on mode change
    if not skipped:
        stacks = min(cap, stacks + 1)
    ps["bard_stacks"] = stacks
    ps["bard_mode"] = mode
    if stacks <= 0:
        return [], []
    value = stacks * pct
    targets = [int(actor_pid)] + [int(m) for m in mates]
    source = ("passive", PASSIVE_BARD)
    apps = [(t, [_stat_row(INSPIRATION_EFFECT_NAME, "percent_damage", value,
                           INSPIRATION_DURATION)], source, False)
            for t in targets]
    ev = passive_proc_event(actor_pid, PASSIVE_BARD, PROC_INSPIRATION,
                            stacks=stacks, value=value, mode=mode, targets=targets)
    return apps, [ev]


def _has_spirit_curse(state, pid) -> bool:
    active = state.get("active_effects") if isinstance(state, dict) else None
    lst = active.get(str(pid)) if isinstance(active, dict) else None
    if not isinstance(lst, list):
        return False
    curse = SPIRIT_CURSE_NAME.strip().lower()
    for row in lst:
        if (isinstance(row, dict) and row.get("source") == SOURCE_ETHERIAD
                and _row_name(row) == curse):
            return True
    return False


def _etheriad_end_of_action(state, actor_pid, skipped: bool, landed_pids):
    if skipped:
        return [], []
    enemies, allies = _alive_sides(state, actor_pid)
    mates = [a for a in allies if str(a) != str(actor_pid)]
    pool = mates or [int(actor_pid)]
    source = ("passive", PASSIVE_ETHERIAD)

    def _result(target, mode, name, attr, value, is_enemy):
        row = _stat_row(name, attr, value, SPIRIT_DURATION)
        ev = passive_proc_event(actor_pid, PASSIVE_ETHERIAD, PROC_SPIRIT_WHISPER,
                                target=target, mode=mode, value=value)
        return [(target, [row], source, is_enemy)], [ev]

    # (1) the most beaten ally below 50% → resist ward.
    low = []
    for a in pool:
        ap = _part(state, a) or {}
        max_hp = _num(ap.get("max_hp"), 0)
        if max_hp <= 0:
            continue
        ratio = _num(ap.get("hp"), 0) / max_hp
        if ratio * 100.0 < SPIRIT_ALLY_HP_PCT:
            low.append((ratio, int(a)))
    if low:
        target = min(low)[1]
        return _result(target, "ward", SPIRIT_WARD_NAME, "percent_resist_all",
                       SPIRIT_RESIST_PCT, False)

    # (2) an enemy hit this action, alive, not cursed yet → vulnerability.
    landed = {str(x) for x in (landed_pids or [])}
    curse_pool = [e for e in enemies
                  if str(e) in landed and not _has_spirit_curse(state, e)]
    if curse_pool:
        target = pick(curse_pool)
        return _result(target, "curse", SPIRIT_CURSE_NAME, "percent_resist_all",
                       -SPIRIT_RESIST_PCT, True)

    # (3) an ally → might.
    target = pick(pool)
    return _result(target, "might", SPIRIT_MIGHT_NAME, "percent_damage",
                   SPIRIT_DAMAGE_PCT, False)


def end_of_action(state, actor_pid, skipped: bool, landed_pids) -> Tuple[list, List[dict]]:
    """H24 (FEAT-190 E15–E17). Called once per action AFTER the
    `resource_spend` event (so a payment 400 voids it) and BEFORE the DoT
    tick 9.4a; main calls it only when the actor is alive (a dead / unknown
    actor gets `([], [])` anyway).

    Inputs: `skipped` = the whole turn was lost to Stun / Poison-paralysis
    (`bool(_full_skip)`); `landed_pids` = enemies the actor LANDED a hit on
    this action (union of `landed_targets(actx)` of the scroll and skill
    attacks + the landed extra-hit target; redirected blows don't count).

    Returns `(applications, events)`. Each application is
    `(target_pid, rows, source_tuple, is_enemy)`; main applies it with
    `apply_new_effects(state, target_pid, rows, is_enemy=is_enemy,
    owner_pid=actor, source=source_tuple)` — the `("passive", key)` source
    makes re-application refresh in place (duration = max, magnitude = new)
    — then appends `events`. Rows are plain StatModifier rows
    (`percent_damage` / `percent_resist_all`), so they work through the
    existing damage / resist channels and show as effect circles.

      * Bard «Ритм» (E16): mode decided now — "group" if a living teammate
        other than the Bard exists (+3%/stack, cap 4) else "solo"
        (+5%/stack, cap 3); stacks clamped to the mode's cap; a non-skipped
        turn adds a stack, a skipped one only refreshes (Q1).
        `passive_state["bard_stacks"]` / `["bard_mode"]` written. Rows
        «Вдохновение» `percent_damage = stacks × pct`, duration 2, to the
        Bard + living teammates (group) or the Bard only (solo). Event
        `inspiration` (`stacks`, `value` = % per target, `mode`,
        `targets`). Zero stacks → nothing.
      * Etheriad «Шёпот духов» (E17): silent on a skipped turn (Q2). Allies
        = living teammates excluding him, or [him] when alone (Q3).
        Priority: (1) ally with hp/max < 50%, lowest ratio (tie → lowest
        pid) → «Шёпот духов: стойкость» `percent_resist_all +8`; (2) else
        `pick` of alive landed enemies without a spirit curse row →
        «Шёпот духов: уязвимость» `percent_resist_all −8`, `is_enemy=True`
        (no chance roll, not control, no Monk/Trickster adjustments);
        (3) else `pick(allies)` → «Шёпот духов: сила» `percent_damage +8`.
        Duration 2. Event `spirit_whisper` (`target`, `mode`
        ward/curse/might, `value` ±8).
    Everyone else → `([], [])`.
    """
    actor = _part(state, actor_pid)
    if actor is None or not _is_alive(actor):
        return [], []
    key = _key_of(actor)
    if key == PASSIVE_BARD:
        return _bard_end_of_action(state, actor_pid, actor, bool(skipped))
    if key == PASSIVE_ETHERIAD:
        return _etheriad_end_of_action(state, actor_pid, bool(skipped), landed_pids)
    return [], []


# =============================================================================
# H25 — deaths / drop-outs cleanup
# =============================================================================
_OWNED_SOURCES = (SOURCE_BARD, SOURCE_ETHERIAD)


def on_deaths(state, pids) -> List[dict]:
    """H25 (FEAT-190 E14). Called at 9.5 with `_newly_defeated` (after the
    `participant_defeated` events) and in `handle_expired_turn` right after
    the timed-out participant is marked defeated.

    A dead owner has no more turns, so whatever it owns would never tick:
      * removes, on EVERY participant, `active_effects` rows whose `source`
        is `passive:bard_rhythm` / `passive:etheriad_spirit_whisper` and
        whose `owner_id` is a dead pid;
      * removes shields OWNED by a dead pid (on everyone) and all shields
        ON a dead pid (Q4: tide vanishes with its Auromancer);
      * a dead Bard: `bard_stacks` reset to 0, `passive_proc
        inspiration_end` (`who` = Bard, `targets` = sorted pids whose
        «Вдохновение» was removed) when any row was removed.
    Returns the events. Garbage / old states → `[]`, never raises.
    """
    dead = {str(p) for p in (pids or []) if p is not None}
    if not dead or not isinstance(state, dict):
        return []
    removed_by_bard: Dict[str, List[int]] = {}
    active = state.get("active_effects")
    if isinstance(active, dict):
        for list_pid, lst in list(active.items()):
            if not isinstance(lst, list):
                continue
            kept = []
            for row in lst:
                if (isinstance(row, dict) and row.get("source") in _OWNED_SOURCES
                        and str(row.get("owner_id")) in dead):
                    if row.get("source") == SOURCE_BARD:
                        bucket = removed_by_bard.setdefault(str(row.get("owner_id")), [])
                        try:
                            ipid = int(list_pid)
                        except (TypeError, ValueError):
                            ipid = None
                        if ipid is not None and ipid not in bucket:
                            bucket.append(ipid)
                    continue
                kept.append(row)
            if len(kept) != len(lst):
                active[list_pid] = kept

    for spid, p in _participants(state).items():
        if not isinstance(p, dict):
            continue
        ps = _ps_read(p)
        shields = ps.get("shields")
        if not isinstance(shields, list) or not shields:
            continue
        if str(spid) in dead:
            ps["shields"] = []
            continue
        kept_sh = [e for e in shields
                   if isinstance(e, dict) and str(e.get("owner")) not in dead]
        if len(kept_sh) != len(shields):
            ps["shields"] = kept_sh

    events: List[dict] = []
    for d in sorted(dead, key=lambda s: (len(s), s)):
        p = _part(state, d)
        if _key_of(p) != PASSIVE_BARD:
            continue
        if "bard_stacks" in _ps_read(p):
            pstate(p)["bard_stacks"] = 0
        targets = removed_by_bard.get(d)
        if targets:
            try:
                who: Any = int(d)
            except (TypeError, ValueError):
                who = d
            events.append(passive_proc_event(
                who, PASSIVE_BARD, PROC_INSPIRATION_END, targets=sorted(targets)))
    return events
