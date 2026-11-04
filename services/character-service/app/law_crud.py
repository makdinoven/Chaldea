"""FEAT-198 law (reputation stage 2a) — DB layer (sync SQLAlchemy). Pure maths: ``law_core``.

Everything here runs in the CALLER's transaction and never commits (``law_flows`` / the routers commit and publish
notifications after the commit). Sections:

* settings / levels / region helpers;
* wanted: lazy decay read, locked materialise, :func:`register_crime` = :func:`record_crime` (the crime row + infamy)
  + :func:`apply_crime_wanted` (THE single wanted write path of a crime; FEAT-199 ``shadow_crud`` defers it for
  unwitnessed / masked crimes and applies it on reveal), and the guard knock-out;
* :func:`evaluate_entry` — the guard encounter created in the same transaction that moves the character;
* encounter / jail state changes used by ``law_flows`` (fine, forced fine, jail, flee, fight, battle result);
* escape, bail, prisoners, staff release / clear, settings, read models.

Lock order: the ``characters`` row(s) first (ascending id), then ``law_encounters`` / ``law_jail_terms``, then
``character_wanted`` rows of one character by ascending ``region_id``. Wanted rows are locked after the ledger
posting (like reputation rows), so no cycle with the economy lock order is possible.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

import activity_lock
import econ_core
import econ_ledger
import law_core as lc
import models
import renown_crud
import reputation_core as rc
import reputation_crud
import shadow_core as sc
import stat_caps
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.law")

ECON_SOURCE_SERVICE = "character-service"
MAX_EVENT_KEY = 191
MAX_REASON = 500
ADMIN_CRIMES_LIMIT = 50
ADMIN_LOG_LIMIT = 100

MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_ENCOUNTER_NOT_FOUND = "Встреча со стражей не найдена"
MSG_ENCOUNTER_CLOSED = "Встреча со стражей уже завершена"
MSG_CHOICE_UNAVAILABLE = "Этот вариант сейчас недоступен"
MSG_NO_JAIL = "В этом крае больше нет тюрьмы"
MSG_GUARD_BUSY = "Стражник сейчас занят — попробуйте чуть позже"
MSG_NOT_JAILED = "Персонаж не в тюрьме"
MSG_ESCAPE_COOLDOWN = "Следующая попытка побега — через {time}"
MSG_BAIL_DONE = "Залог уже внесён"
MSG_NOT_OWNER = "Вы можете управлять только своими персонажами"
MSG_NOT_PLAYER = "Это действие доступно только персонажу игрока"
MSG_BANKER_NOT_FOUND = "Банкир не найден"
MSG_BANKER_DEAD = "Банкир мёртв"
MSG_WRONG_LOCATION = "Вы должны находиться в локации с банкиром"
MSG_NOTHING_TO_RELEASE = "Персонаж не в тюрьме и не задержан стражей"
MSG_BATTLE_MISMATCH = "Бой не относится к этой встрече со стражей"
MSG_REGION_NOT_FOUND = "Регион не найден"

# results of a choice (LawChoiceOut.result)
RESULT_FINED = "fined"
RESULT_JAILED = "jailed"
RESULT_FLED = "fled"
RESULT_FIGHT = "fight"
RESULT_FLEE_BLOCKED = "flee_failed_blocked"
RESULT_GUARD_GONE = "guard_gone"


class LawError(EconomyApiError):
    """Business error of the law layer (HTTP status + Russian text); a subclass of the economy error."""


_rng = secrets.SystemRandom()


def rng():
    """The server-side RNG (tests patch this function)."""
    return _rng


# =====================================================================================================================
# helpers / loaders
# =====================================================================================================================

def now_utc() -> datetime:
    return reputation_crud.now_utc()


def _is_mysql(db: Session) -> bool:
    return db.get_bind().dialect.name == "mysql"


def _for_update(db: Session) -> bool:
    return db.get_bind().dialect.name != "sqlite"


def _in(prefix: str, values: Sequence) -> Tuple[str, Dict[str, object]]:
    names = [f"{prefix}{i}" for i in range(len(values))]
    return ", ".join(f":{n}" for n in names), dict(zip(names, values))


def _dt(value) -> Optional[datetime]:
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def load_settings(db: Session) -> lc.LawSettings:
    return lc.settings_from_row(db.execute(text(lc.SQL_SELECT_SETTINGS)).first())


def load_levels(db: Session) -> List[lc.Level]:
    return lc.levels_from_rows(db.execute(text(lc.SQL_SELECT_LEVELS)).fetchall())


def region_jail_location(db: Session, region_id: Optional[int]) -> Optional[int]:
    """``Regions.jail_location_id`` (locations-service column, read by raw SQL)."""
    if not region_id:
        return None
    row = db.execute(text("SELECT jail_location_id FROM Regions WHERE id = :r"), {"r": int(region_id)}).first()
    return int(row[0]) if row is not None and row[0] is not None else None


def region_names(db: Session, region_ids: Iterable[int]) -> Dict[int, Optional[str]]:
    return {rid: info.name for rid, info in reputation_crud.region_infos(db, region_ids).items()}


def location_names(db: Session, location_ids: Iterable[int]) -> Dict[int, Optional[str]]:
    ids = sorted({int(x) for x in location_ids if x})
    if not ids:
        return {}
    ph, params = _in("l", ids)
    rows = db.execute(text(f"SELECT id, name FROM Locations WHERE id IN ({ph})"), params).fetchall()
    return {int(r[0]): r[1] for r in rows}


def character_user_ids(db: Session, character_ids: Iterable[int]) -> Dict[int, Optional[int]]:
    ids = sorted({int(x) for x in character_ids if x})
    if not ids:
        return {}
    ph, params = _in("c", ids)
    rows = db.execute(text(f"SELECT id, user_id, is_npc FROM characters WHERE id IN ({ph})"), params).fetchall()
    return {int(r[0]): (int(r[1]) if r[1] is not None and not bool(r[2]) else None) for r in rows}


def lock_character(db: Session, character_id: int) -> Optional["models.Character"]:
    query = db.query(models.Character).filter(models.Character.id == int(character_id))
    if _for_update(db):
        query = query.with_for_update()
    return query.populate_existing().first()


def attributes_of(db: Session, character_id: int) -> Tuple[int, int]:
    """(agility, luck) from ``character_attributes`` (attributes-service table, raw SQL); (0, 0) without a row."""
    row = db.execute(text("SELECT agility, luck FROM character_attributes WHERE character_id = :c"),
                     {"c": int(character_id)}).first()
    if row is None:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


def _effective(value: int) -> Decimal:
    return Decimal(str(stat_caps.effective_stat(value))).quantize(Decimal("0.01"))


def effective_attributes_of(db: Session, character_id: int) -> Tuple[Decimal, Decimal]:
    """FEAT-199 §3.3: (agility, luck) after the FEAT-195 caps (the stored values already include gear)."""
    agility, luck = attributes_of(db, character_id)
    return _effective(agility), _effective(luck)


def flee_chance(db: Session, character_id: int, settings: lc.LawSettings) -> Decimal:
    agility, luck = effective_attributes_of(db, character_id)
    return lc.chance(settings.flee_base_pct, settings.flee_per_point_pct, settings.flee_min_pct,
                     settings.flee_max_pct, agility, luck)


def escape_chance(db: Session, character_id: int, settings: lc.LawSettings) -> Decimal:
    agility, luck = effective_attributes_of(db, character_id)
    return lc.chance(settings.escape_base_pct, settings.escape_per_point_pct, settings.escape_min_pct,
                     settings.escape_max_pct, agility, luck)


def in_active_battle(db: Session, character_id: int) -> bool:
    """Active battle by the shared DB (battle-service tables, read only) — the same predicate as main._is_in_battle."""
    row = db.execute(text(
        "SELECT 1 FROM battles b JOIN battle_participants bp ON b.id = bp.battle_id "
        "WHERE bp.character_id = :cid AND b.status IN ('pending', 'in_progress') "
        "AND bp.dropped_out_at IS NULL LIMIT 1"), {"cid": int(character_id)}).first()
    return row is not None


def log_exists(db: Session, key: str) -> bool:
    return db.execute(text("SELECT 1 FROM law_log WHERE event_key = :k"), {"k": key}).first() is not None


def log_action(db: Session, key: str) -> Optional[str]:
    row = db.execute(text("SELECT action FROM law_log WHERE event_key = :k"), {"k": key}).first()
    return row[0] if row is not None else None


def _log(db: Session, *, key: str, character_id: int, action: str, region_id: Optional[int] = None,
         wanted_before: Optional[int] = None, wanted_after: Optional[int] = None, amount: Optional[int] = None,
         chance_pct=None, roll_pct=None, ref_id: Optional[int] = None, reason: Optional[str] = None,
         actor_user_id: Optional[int] = None, now: Optional[datetime] = None) -> None:
    db.add(models.LawLog(
        event_key=key[:MAX_EVENT_KEY], character_id=int(character_id), region_id=region_id, action=action,
        wanted_before=wanted_before, wanted_after=wanted_after, amount=amount,
        chance_pct=Decimal(str(chance_pct)) if chance_pct is not None else None,
        roll_pct=Decimal(str(roll_pct)) if roll_pct is not None else None,
        ref_id=ref_id, reason=(reason[:MAX_REASON] if reason else None), actor_user_id=actor_user_id,
        created_at=now or now_utc()))


def _insufficient_message(db: Session, what: str) -> str:
    import crud  # local: crud is heavy and imports this module lazily itself
    return f"{crud.insufficient_funds_message(db)} {what}"


# =====================================================================================================================
# wanted
# =====================================================================================================================

@dataclass(frozen=True)
class WantedChange:
    character_id: int
    user_id: Optional[int]
    region_id: int
    region_name: Optional[str]
    value_before: int
    value_after: int
    level_before: Optional[str]
    level_after: Optional[str]
    level_after_name: Optional[str]
    level_raised: bool


def _ensure_wanted_row(db: Session, character_id: int, region_id: int, now: datetime) -> None:
    if db.execute(text("SELECT 1 FROM character_wanted WHERE character_id = :c AND region_id = :r"),
                  {"c": int(character_id), "r": int(region_id)}).first() is not None:
        return
    if _is_mysql(db):
        sql = ("INSERT INTO character_wanted (character_id, region_id, value, decay_at, updated_at) "
               "VALUES (:c, :r, 0, NULL, :now) ON DUPLICATE KEY UPDATE id = id")
    else:
        sql = ("INSERT OR IGNORE INTO character_wanted (character_id, region_id, value, decay_at, updated_at) "
               "VALUES (:c, :r, 0, NULL, :now)")
    db.execute(text(sql), {"c": int(character_id), "r": int(region_id), "now": now})


def lock_wanted(db: Session, character_id: int, region_id: int, settings: lc.LawSettings,
                now: datetime) -> "models.CharacterWanted":
    """Ensure + lock the row and materialise its decay up to ``now``."""
    _ensure_wanted_row(db, character_id, region_id, now)
    query = db.query(models.CharacterWanted).filter(models.CharacterWanted.character_id == int(character_id),
                                                    models.CharacterWanted.region_id == int(region_id))
    if _for_update(db):
        query = query.with_for_update()
    row = query.populate_existing().one()
    value, anchor = lc.materialise(int(row.value or 0), row.decay_at, now, settings.decay_per_day)
    if value != int(row.value or 0) or anchor != row.decay_at:
        row.value, row.decay_at, row.updated_at = value, anchor, now
    return row


def _store_wanted(row: "models.CharacterWanted", new_value: int, now: datetime) -> None:
    old = int(row.value or 0)
    row.decay_at = lc.next_decay_at(old, int(new_value), row.decay_at, now)
    row.value = int(new_value)
    row.updated_at = now


def read_wanted(db: Session, character_id: int, region_id: Optional[int], settings: lc.LawSettings,
                now: datetime) -> int:
    """Effective wanted (0 without a row / region)."""
    if not region_id:
        return 0
    row = db.execute(text("SELECT value, decay_at FROM character_wanted WHERE character_id = :c AND region_id = :r"),
                     {"c": int(character_id), "r": int(region_id)}).first()
    if row is None:
        return 0
    return lc.effective_wanted(int(row[0] or 0), row[1], now, settings.decay_per_day)


def clear_wanted(db: Session, character_id: int, region_id: int, settings: lc.LawSettings, now: datetime,
                 *, key: Optional[str] = None, action: Optional[str] = None, ref_id: Optional[int] = None,
                 reason: Optional[str] = None, actor_user_id: Optional[int] = None) -> int:
    """Wanted in the region -> 0 (with a log row when ``key`` is given). Returns the value before."""
    row = lock_wanted(db, character_id, region_id, settings, now)
    before = int(row.value or 0)
    _store_wanted(row, 0, now)
    if key:
        _log(db, key=key, character_id=character_id, action=action, region_id=region_id, wanted_before=before,
             wanted_after=0, ref_id=ref_id, reason=reason, actor_user_id=actor_user_id, now=now)
    return before


def _change(levels: Sequence[lc.Level], character_id: int, user_id: Optional[int], region_id: int,
            region_name: Optional[str], before: int, after: int) -> WantedChange:
    lb, la = lc.level_for(before, levels), lc.level_for(after, levels)
    raised = la is not None and (lb is None or la.sort_order > lb.sort_order)
    return WantedChange(int(character_id), user_id, int(region_id), region_name, before, after,
                        lb.code if lb else None, la.code if la else None, la.name if la else None, raised)


@dataclass
class CrimeResult:
    duplicate: bool = False
    skipped: bool = False
    crime_id: Optional[int] = None
    change: Optional[WantedChange] = None
    crime: Optional["models.LawCrime"] = None
    user_id: Optional[int] = None


def record_crime(db: Session, *, crime_type: str, character_id: int, region_id: int, points: int, event_key: str,
                 location_id: Optional[int] = None, victim_id: Optional[int] = None,
                 battle_id: Optional[int] = None, floor: Optional[int] = None, now: Optional[datetime] = None,
                 status: str = lc.CRIME_REPORTED, reputation_delta: Optional[int] = None,
                 reputation_key: Optional[str] = None, reputation_reason: Optional[str] = None, masked: bool = False,
                 witness_chance_pct=None, witness_roll_pct=None, reveal_until: Optional[datetime] = None,
                 next_roll_at: Optional[datetime] = None) -> CrimeResult:
    """Write the crime row (+ the FEAT-199 snapshot) and its infamy, WITHOUT any wanted change.

    ``points <= 0`` without a floor -> nothing (a bandit kill is not a crime). Idempotent per ``event_key`` (pre-check +
    UNIQUE). NPC characters are skipped. Infamy (hidden) is added for every row, witnessed or not."""
    now = now or now_utc()
    points = int(points or 0)
    if points <= 0 and not floor:
        return CrimeResult(skipped=True)
    if len(event_key or "") > MAX_EVENT_KEY or not event_key:
        raise LawError(400, "Слишком длинный ключ события")
    if status not in lc.CRIME_STATUSES:
        raise ValueError(f"unknown crime status {status!r}")
    char = db.execute(text("SELECT is_npc, user_id FROM characters WHERE id = :id"), {"id": int(character_id)}).first()
    if char is None or bool(char[0]):
        return CrimeResult(skipped=True)
    if db.execute(text("SELECT 1 FROM law_crimes WHERE event_key = :k"), {"k": event_key}).first() is not None:
        return CrimeResult(duplicate=True)
    crime = models.LawCrime(
        event_key=event_key, crime_type=crime_type, character_id=int(character_id), region_id=int(region_id),
        location_id=location_id, victim_character_id=victim_id, battle_id=battle_id, wanted_points=max(0, points),
        wanted_applied=0, status=status, created_at=now, reputation_delta=reputation_delta,
        reputation_key=reputation_key, reputation_reason=(reputation_reason[:255] if reputation_reason else None),
        wanted_floor=int(floor) if floor else None, masked=bool(masked),
        witness_chance_pct=Decimal(str(witness_chance_pct)) if witness_chance_pct is not None else None,
        witness_roll_pct=Decimal(str(witness_roll_pct)) if witness_roll_pct is not None else None,
        reveal_until=reveal_until, next_roll_at=next_roll_at, reveal_attempts=0)
    db.add(crime)
    db.flush()
    shadow = renown_crud.load_shadow_settings(db)
    renown_crud.add_infamy(db, character_id=int(character_id), points=sc.infamy_gain(max(0, points), shadow),
                           event_key=f"infamy:crime:{crime.id}", ref_id=int(crime.id), now=now)
    user_id = int(char[1]) if char[1] is not None else None
    return CrimeResult(crime_id=int(crime.id), crime=crime, user_id=user_id)


def apply_crime_wanted(db: Session, crime: "models.LawCrime", *, floor: Optional[int], settings: lc.LawSettings,
                       levels: Sequence[lc.Level], now: datetime, user_id: Optional[int] = None) -> WantedChange:
    """Apply the wanted of a recorded crime (at once, or on a FEAT-199 reveal). The log key ``law:crime:{id}`` is
    unique, so a second application of the same crime fails loudly instead of doubling the wanted."""
    character_id, region_id = int(crime.character_id), int(crime.region_id)
    row = lock_wanted(db, character_id, region_id, settings, now)
    before = int(row.value or 0)
    after = lc.add_wanted(before, max(0, int(crime.wanted_points or 0)), settings, floor)
    _store_wanted(row, after, now)
    crime.wanted_applied = after - before
    crime.resolved_at = now
    _log(db, key=f"law:crime:{crime.id}", character_id=character_id, action=lc.LOG_CRIME, region_id=region_id,
         wanted_before=before, wanted_after=after, ref_id=int(crime.id), now=now)
    db.flush()
    if user_id is None:
        user_id = character_user_ids(db, [character_id]).get(character_id)
    name = region_names(db, [region_id]).get(region_id)
    return _change(levels, character_id, user_id, region_id, name, before, after)


def register_crime(db: Session, *, crime_type: str, character_id: int, region_id: int, points: int, event_key: str,
                   location_id: Optional[int] = None, victim_id: Optional[int] = None,
                   battle_id: Optional[int] = None, floor: Optional[int] = None, now: Optional[datetime] = None,
                   settings: Optional[lc.LawSettings] = None,
                   levels: Optional[Sequence[lc.Level]] = None, status: str = lc.CRIME_REPORTED,
                   **snapshot) -> CrimeResult:
    """Record one crime (:func:`record_crime`) and, when it is ``reported`` (witnessed), apply its wanted at once
    (:func:`apply_crime_wanted`), in the caller's transaction. Deferred statuses (FEAT-199 ``unwitnessed`` /
    ``masked``) only record the row with its snapshot; ``shadow_crud.reveal_crime`` applies it later.
    Jail escape and every other direct caller keep the default ``reported``."""
    now = now or now_utc()
    result = record_crime(db, crime_type=crime_type, character_id=character_id, region_id=region_id, points=points,
                          event_key=event_key, location_id=location_id, victim_id=victim_id, battle_id=battle_id,
                          floor=floor, now=now, status=status, **snapshot)
    if result.crime is None or status != lc.CRIME_REPORTED:
        return result
    settings = settings or load_settings(db)
    levels = levels or load_levels(db)
    result.change = apply_crime_wanted(db, result.crime, floor=floor, settings=settings, levels=levels, now=now,
                                       user_id=result.user_id)
    return result


def knock_out_guard(db: Session, npc_id: int, *, battle_id: Optional[int], now: Optional[datetime] = None,
                    settings: Optional[lc.LawSettings] = None) -> Optional[datetime]:
    """A defeated guard is knocked out for ``guard_ko_hours`` instead of dying (user decision 3). Conditional and
    idempotent: returns the KO end on a real transition, None when already KO'd / dead."""
    now = now or now_utc()
    settings = settings or load_settings(db)
    until = now + timedelta(hours=int(settings.guard_ko_hours))
    result = db.execute(text(
        "UPDATE characters SET unconscious_until = :until WHERE id = :id AND npc_status = 'alive' "
        "AND (unconscious_until IS NULL OR unconscious_until <= :now)"),
        {"until": until, "id": int(npc_id), "now": now})
    if (result.rowcount or 0) != 1:
        return None
    stamp = str(int(battle_id)) if battle_id else f"t{now.strftime('%Y%m%d%H%M%S')}"
    _log(db, key=f"law:guard_ko:{npc_id}:{stamp}", character_id=npc_id, action=lc.LOG_GUARD_KO, ref_id=battle_id,
         now=now)
    return until


# =====================================================================================================================
# guards / encounter creation
# =====================================================================================================================

_SQL_GUARDS = (
    "SELECT id FROM characters WHERE is_npc = 1 AND npc_role = :role AND npc_status = 'alive' "
    "AND current_location_id = :loc AND (unconscious_until IS NULL OR unconscious_until <= :now) ORDER BY id"
)


def guards_at(db: Session, location_id: int, now: datetime) -> List[int]:
    rows = db.execute(text(_SQL_GUARDS), {"role": lc.GUARD_ROLE, "loc": int(location_id), "now": now}).fetchall()
    return [int(r[0]) for r in rows]


def is_outlaw(db: Session, character_id: int, region_id: int) -> bool:
    return reputation_crud.tier_of(db, character_id, region_id).code == rc.OUTLAW_TIER


def _flee_cooldown_active(db: Session, character_id: int, location_id: int, now: datetime) -> bool:
    return db.execute(text(
        "SELECT 1 FROM law_encounters WHERE character_id = :c AND location_id = :l AND cooldown_until > :now LIMIT 1"),
        {"c": int(character_id), "l": int(location_id), "now": now}).first() is not None


def evaluate_entry(db: Session, character: "models.Character", location_id, source: str,
                   now: Optional[datetime] = None, *,
                   from_location_id: Optional[int] = None) -> Optional["models.LawEncounter"]:
    """A wanted (or outlaw) character entering a location with a live guard is stopped (§3.4). Runs inside the moving
    transaction (the character row is already locked); sets ``characters.law_encounter_id``. None = not stopped."""
    now = now or now_utc()
    if character is None or bool(character.is_npc) or not location_id:
        return None
    if character.law_encounter_id:
        return None
    jailed = _dt(character.jailed_until)
    if jailed is not None and jailed > now:
        return None
    location_id = int(location_id)
    region_id = reputation_crud.location_region(db, location_id)
    if not region_id:
        return None
    guards = guards_at(db, location_id, now)
    if not guards:
        return None
    if _flee_cooldown_active(db, character.id, location_id, now):
        return None
    settings = load_settings(db)
    wanted = read_wanted(db, character.id, region_id, settings, now)
    outlaw = is_outlaw(db, character.id, region_id)
    if wanted <= 0 and not outlaw:
        return None
    levels = load_levels(db)
    level = lc.level_for(wanted, levels)
    if outlaw:
        level = lc.level_at_least(level, settings.outlaw_min_level, levels)
    if level is None:
        return None
    has_jail = region_jail_location(db, region_id) is not None
    enc = models.LawEncounter(
        character_id=int(character.id), region_id=int(region_id), location_id=location_id,
        from_location_id=int(from_location_id) if from_location_id else None, guard_npc_id=guards[0],
        is_outlaw=bool(outlaw), has_jail=bool(has_jail), level_code=level.code, wanted_value=int(wanted),
        fine=int(level.fine), jail_hours=int(level.jail_hours), flee_used=False, status=lc.ENC_PENDING,
        source=source if source in (lc.SOURCE_MOVE, lc.SOURCE_QUICK_MOVE, lc.SOURCE_TELEPORT) else lc.SOURCE_MOVE,
        created_at=now, expires_at=now + timedelta(hours=int(settings.encounter_timeout_hours)))
    db.add(enc)
    db.flush()
    character.law_encounter_id = int(enc.id)
    _log(db, key=f"law:encounter:{enc.id}", character_id=character.id, action=lc.LOG_ENCOUNTER, region_id=region_id,
         wanted_before=int(wanted), wanted_after=int(wanted), ref_id=int(enc.id), now=now)
    db.flush()
    return enc


def encounter_notice(db: Session, enc: "models.LawEncounter"):
    """The «стража остановила вас» notification of a just-created encounter (send after the commit)."""
    import law_notify
    user_id = character_user_ids(db, [enc.character_id]).get(int(enc.character_id))
    name = region_names(db, [enc.region_id]).get(int(enc.region_id))
    return law_notify.Notice(user_id, law_notify.encounter_message(name, _dt(enc.expires_at), _dt(enc.created_at)),
                             law_notify.WS_ENCOUNTER,
                             data={"encounter_id": int(enc.id), "character_id": int(enc.character_id)})


# =====================================================================================================================
# read models
# =====================================================================================================================

def get_encounter(db: Session, encounter_id: int, *, lock: bool = False) -> Optional["models.LawEncounter"]:
    query = db.query(models.LawEncounter).filter(models.LawEncounter.id == int(encounter_id))
    if lock and _for_update(db):
        query = query.with_for_update()
    return query.populate_existing().first()


def open_encounter(db: Session, character: "models.Character") -> Optional["models.LawEncounter"]:
    if not character.law_encounter_id:
        return None
    enc = get_encounter(db, character.law_encounter_id)
    if enc is None or enc.status not in lc.ENC_OPEN:
        return None
    return enc


def encounter_options(db: Session, enc: "models.LawEncounter") -> List[str]:
    if enc.status != lc.ENC_PENDING:
        return []
    has_jail = region_jail_location(db, enc.region_id) is not None
    return lc.options(bool(enc.is_outlaw), has_jail, bool(enc.flee_used))


def encounter_out(db: Session, enc: "models.LawEncounter", *, staff: bool = False,
                  settings: Optional[lc.LawSettings] = None) -> dict:
    settings = settings or load_settings(db)
    guard = None
    if enc.guard_npc_id:
        guard = db.execute(text("SELECT name, avatar FROM characters WHERE id = :id"),
                           {"id": int(enc.guard_npc_id)}).first()
    level = lc.level_by_code(enc.level_code, load_levels(db))
    options = encounter_options(db, enc)
    has_jail = region_jail_location(db, enc.region_id) is not None if enc.status == lc.ENC_PENDING \
        else bool(enc.has_jail)
    out = {
        "id": int(enc.id),
        "region_id": int(enc.region_id),
        "region_name": region_names(db, [enc.region_id]).get(int(enc.region_id)),
        "location_id": int(enc.location_id),
        "guard_name": guard[0] if guard else None,
        "guard_avatar": guard[1] if guard else None,
        "is_outlaw": bool(enc.is_outlaw),
        "has_jail": bool(has_jail),
        "level_name": level.name if level else enc.level_code,
        "fine": int(enc.fine),
        "jail_hours": int(enc.jail_hours),
        "options": options,
        "flee_chance_pct": float(flee_chance(db, enc.character_id, settings)) if lc.CHOICE_FLEE in options else None,
        "status": enc.status,
        "battle_id": int(enc.battle_id) if enc.battle_id else None,
        "expires_at": _dt(enc.expires_at),
    }
    if staff:
        out.update({
            "character_id": int(enc.character_id),
            "guard_npc_id": int(enc.guard_npc_id) if enc.guard_npc_id else None,
            "level_code": enc.level_code,
            "wanted_value": int(enc.wanted_value),
            "source": enc.source,
            "from_location_id": int(enc.from_location_id) if enc.from_location_id else None,
            "flee_used": bool(enc.flee_used),
            "created_at": _dt(enc.created_at),
            "fight_started_at": _dt(enc.fight_started_at),
            "resolved_at": _dt(enc.resolved_at),
        })
    return out


def active_term(db: Session, character_id: int, now: datetime, *,
                lock: bool = False) -> Optional["models.LawJailTerm"]:
    """The serving term whose ``until`` is still ahead (a past ``until`` = already free, lazily)."""
    query = (db.query(models.LawJailTerm)
             .filter(models.LawJailTerm.character_id == int(character_id),
                     models.LawJailTerm.status == lc.JAIL_SERVING,
                     models.LawJailTerm.until > now)
             .order_by(models.LawJailTerm.id.desc()))
    if lock and _for_update(db):
        query = query.with_for_update()
    return query.populate_existing().first()


def jail_out(db: Session, term: "models.LawJailTerm", *, staff: bool = False,
             settings: Optional[lc.LawSettings] = None, now: Optional[datetime] = None) -> dict:
    settings = settings or load_settings(db)
    now = now or now_utc()
    next_at = _dt(term.next_escape_at)
    out = {
        "id": int(term.id),
        "region_id": int(term.region_id),
        "region_name": region_names(db, [term.region_id]).get(int(term.region_id)),
        "location_id": int(term.location_id),
        "location_name": location_names(db, [term.location_id]).get(int(term.location_id)),
        "until": _dt(term.until),
        "bail_price": int(term.bail_price),
        "can_escape_at": next_at if next_at is not None and next_at > now else None,
        "escape_chance_pct": float(escape_chance(db, term.character_id, settings)),
        "escape_attempts": int(term.escape_attempts or 0),
    }
    if staff:
        out.update({"status": term.status, "level_code": term.level_code,
                    "encounter_id": int(term.encounter_id) if term.encounter_id else None,
                    "started_at": _dt(term.started_at)})
    return out


def _require_character(db: Session, character_id: int) -> "models.Character":
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    return character


def _wanted_rows(db: Session, character_id: int, settings: lc.LawSettings, now: datetime) -> List[Tuple[int, int]]:
    rows = db.execute(text("SELECT region_id, value, decay_at FROM character_wanted WHERE character_id = :c "
                           "AND value > 0 ORDER BY region_id"), {"c": int(character_id)}).fetchall()
    out = []
    for region_id, value, decay_at in rows:
        effective = lc.effective_wanted(int(value or 0), decay_at, now, settings.decay_per_day)
        if effective > 0:
            out.append((int(region_id), effective))
    return out


def player_state(db: Session, character_id: int) -> dict:
    """``GET /characters/{id}/law`` — levels only, never the raw numbers."""
    character = _require_character(db, character_id)
    settings, levels, now = load_settings(db), load_levels(db), now_utc()
    rows = _wanted_rows(db, character_id, settings, now) if not character.is_npc else []
    names = region_names(db, [r for r, _ in rows])
    wanted = []
    for region_id, value in rows:
        level = lc.level_for(value, levels)
        if level is None:
            continue
        wanted.append({"region_id": region_id, "region_name": names.get(region_id), "level_code": level.code,
                       "level_name": level.name, "fine": int(level.fine), "jail_hours": int(level.jail_hours),
                       "decaying": settings.decay_per_day > 0})
    enc = open_encounter(db, character)
    term = active_term(db, character_id, now)
    return {
        "wanted": sorted(wanted, key=lambda w: (w["region_name"] or "", w["region_id"])),
        "encounter": encounter_out(db, enc, settings=settings) if enc else None,
        "jail": jail_out(db, term, settings=settings, now=now) if term else None,
    }


def player_encounter(db: Session, character_id: int) -> Optional[dict]:
    character = _require_character(db, character_id)
    enc = open_encounter(db, character)
    return encounter_out(db, enc) if enc else None


def player_jail(db: Session, character_id: int) -> Optional[dict]:
    _require_character(db, character_id)
    term = active_term(db, character_id, now_utc())
    return jail_out(db, term) if term else None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def prisoners(db: Session, q: Optional[str], page: int, page_size: int) -> dict:
    """``GET /characters/law/prisoners`` — players serving a term right now (public in-world)."""
    now = now_utc()
    where = ["t.status = :serving", "t.until > :now", "c.is_npc = 0"]
    params: Dict[str, object] = {"serving": lc.JAIL_SERVING, "now": now}
    if q and q.strip():
        where.append("c.name LIKE :q ESCAPE '\\\\'" if _is_mysql(db) else "c.name LIKE :q ESCAPE '\\'")
        params["q"] = f"%{_escape_like(q.strip())}%"
    clause = " AND ".join(where)
    total = int(db.execute(text(
        f"SELECT COUNT(*) FROM law_jail_terms t JOIN characters c ON c.id = t.character_id WHERE {clause}"),
        params).scalar() or 0)
    params.update({"lim": int(page_size), "off": (int(page) - 1) * int(page_size)})
    rows = db.execute(text(
        "SELECT t.character_id, c.name, c.avatar, t.region_id, t.location_id, t.until, t.bail_price "
        f"FROM law_jail_terms t JOIN characters c ON c.id = t.character_id WHERE {clause} "
        "ORDER BY t.until, t.id LIMIT :lim OFFSET :off"), params).fetchall()
    regions = region_names(db, [r[3] for r in rows])
    locations = location_names(db, [r[4] for r in rows])
    items = [{"character_id": int(r[0]), "name": r[1], "avatar": r[2], "region_name": regions.get(int(r[3])),
              "location_name": locations.get(int(r[4])), "until": _dt(r[5]), "bail_price": int(r[6])} for r in rows]
    return {"items": items, "total": total}


# =====================================================================================================================
# encounter state changes (used by law_flows; caller commits)
# =====================================================================================================================

def lock_open_encounter(db: Session, character_id: int, encounter_id: int) -> Tuple["models.Character",
                                                                                     "models.LawEncounter"]:
    """Character row, then the encounter row (both locked). 404 when it is not this character's; 409 when closed."""
    character = lock_character(db, character_id)
    if character is None:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    enc = get_encounter(db, encounter_id, lock=True)
    if enc is None or int(enc.character_id) != int(character_id):
        raise LawError(404, MSG_ENCOUNTER_NOT_FOUND)
    if enc.status != lc.ENC_PENDING:
        raise LawError(409, MSG_ENCOUNTER_CLOSED)
    return character, enc


def _close(character: "models.Character", enc: "models.LawEncounter", status: str, now: datetime) -> None:
    enc.status = status
    enc.resolved_at = now
    if character.law_encounter_id and int(character.law_encounter_id) == int(enc.id):
        character.law_encounter_id = None


def pay_fine(db: Session, character: "models.Character", enc: "models.LawEncounter", *, key: str,
             now: datetime, settings: lc.LawSettings) -> None:
    """Choice «заплатить штраф»: ledger ``law_fine`` purse -> region treasury (10 % tax), wanted -> 0, lock cleared.
    400 on insufficient gold (the encounter stays pending)."""
    amount = int(enc.fine or 0)
    try:
        econ_ledger.post_operation(
            db, op_type=econ_core.OP_LAW_FINE,
            legs=[econ_ledger.Leg(econ_ledger.AccountRef.character(character.id),
                                  econ_ledger.AccountRef.region(int(enc.region_id)), amount)],
            source_service=ECON_SOURCE_SERVICE, location_id=int(enc.location_id), region_id=int(enc.region_id),
            idempotency_key=f"law_fine:{enc.id}", metadata={"encounter_id": int(enc.id)})
    except econ_ledger.InsufficientFunds:
        raise LawError(400, _insufficient_message(db, "для уплаты штрафа"))
    except econ_ledger.DuplicateOperation:
        pass                                    # already charged by an earlier attempt of this encounter
    clear_wanted(db, character.id, int(enc.region_id), settings, now)
    _close(character, enc, lc.ENC_FINED, now)
    _log(db, key=key, character_id=character.id, action=lc.LOG_FINE, region_id=int(enc.region_id), amount=amount,
         ref_id=int(enc.id), now=now)


def forced_fine(db: Session, character: "models.Character", enc: "models.LawEncounter", *, key: str, action: str,
                now: datetime, settings: lc.LawSettings) -> Tuple[int, bool]:
    """No jail (user decision 2 / §3.14 A3): take the gold up to the fine; wanted -> 0 only when paid in full.
    Returns (charged, paid_in_full)."""
    balance = int(character.currency_balance or 0)
    fine = int(enc.fine or 0)
    amount = max(0, min(fine, balance))
    if amount > 0:
        try:
            econ_ledger.post_operation(
                db, op_type=econ_core.OP_LAW_FINE,
                legs=[econ_ledger.Leg(econ_ledger.AccountRef.character(character.id),
                                      econ_ledger.AccountRef.region(int(enc.region_id)), amount)],
                source_service=ECON_SOURCE_SERVICE, location_id=int(enc.location_id), region_id=int(enc.region_id),
                idempotency_key=f"law_fine_forced:{enc.id}", metadata={"encounter_id": int(enc.id), "forced": True})
        except econ_ledger.DuplicateOperation:
            pass
    full = amount >= fine
    if full:
        clear_wanted(db, character.id, int(enc.region_id), settings, now)
    _close(character, enc, lc.ENC_AUTO_FINED, now)
    _log(db, key=key, character_id=character.id, action=action, region_id=int(enc.region_id), amount=amount,
         ref_id=int(enc.id), now=now)
    return amount, full


def jail_writes(db: Session, character: "models.Character", enc: "models.LawEncounter", jail_location_id: int, *,
                key: str, action: str, now: datetime, settings: lc.LawSettings) -> "models.LawJailTerm":
    """The jail itself (after the move to the jail location was written in the same transaction): term, lock columns,
    wanted -> 0, encounter ``jailed``."""
    until = now + timedelta(hours=int(enc.jail_hours))
    character.jailed_until = until
    character.jail_region_id = int(enc.region_id)
    term = models.LawJailTerm(
        character_id=int(character.id), region_id=int(enc.region_id), location_id=int(jail_location_id),
        encounter_id=int(enc.id), level_code=enc.level_code, fine_base=int(enc.fine),
        bail_price=lc.bail_price(int(enc.fine), settings.bail_multiplier), started_at=now, until=until,
        status=lc.JAIL_SERVING, escape_attempts=0, next_escape_at=None, notified=False)
    db.add(term)
    db.flush()
    before = clear_wanted(db, character.id, int(enc.region_id), settings, now)
    _close(character, enc, lc.ENC_JAILED, now)
    _log(db, key=key, character_id=character.id, action=action, region_id=int(enc.region_id), wanted_before=before,
         wanted_after=0, ref_id=int(term.id), now=now)
    db.flush()
    return term


def flee_roll(db: Session, character: "models.Character", enc: "models.LawEncounter", *, key: str, now: datetime,
              settings: lc.LawSettings) -> Tuple[bool, Decimal, Decimal]:
    """Roll the flee. Success -> encounter ``fled`` + the 1 h guard cooldown of this location (§3.14 A7), lock
    cleared; failure -> ``flee_used``. Both write a log row with chance and roll."""
    chance_pct = flee_chance(db, character.id, settings)
    ok, roll = lc.roll_succeeds(chance_pct, rng())
    if ok:
        enc.cooldown_until = now + lc.FLEE_GUARD_COOLDOWN
        _close(character, enc, lc.ENC_FLED, now)
    else:
        enc.flee_used = True
    _log(db, key=key, character_id=character.id, action=lc.LOG_FLEE_OK if ok else lc.LOG_FLEE_FAIL,
         region_id=int(enc.region_id), chance_pct=chance_pct, roll_pct=roll, ref_id=int(enc.id), now=now)
    return ok, chance_pct, roll


def pick_free_guard(db: Session, enc: "models.LawEncounter", now: datetime) -> Tuple[Optional[int], bool]:
    """(a free guard at the encounter location — alive, not KO'd, not in battle; the original one first,
    any guard alive at all)."""
    guards = guards_at(db, int(enc.location_id), now)
    if enc.guard_npc_id and int(enc.guard_npc_id) in guards:
        guards.remove(int(enc.guard_npc_id))
        guards.insert(0, int(enc.guard_npc_id))
    for guard_id in guards:
        if not in_active_battle(db, guard_id):
            return guard_id, True
    return None, bool(guards)


def heal_guard(db: Session, guard_id: int) -> None:
    db.execute(text(
        "UPDATE character_attributes SET current_health = max_health, current_mana = max_mana, "
        "current_energy = max_energy, current_stamina = max_stamina WHERE character_id = :g"), {"g": int(guard_id)})


def start_fight(db: Session, character: "models.Character", enc: "models.LawEncounter", guard_id: int, *, key: str,
                now: datetime) -> None:
    heal_guard(db, guard_id)
    enc.status = lc.ENC_FIGHTING
    enc.fight_started_at = now
    enc.guard_npc_id = int(guard_id)
    enc.battle_id = None
    _log(db, key=key, character_id=character.id, action=lc.LOG_FIGHT, region_id=int(enc.region_id),
         ref_id=int(enc.id), now=now)


def guard_gone(db: Session, character: "models.Character", enc: "models.LawEncounter", *, key: str,
               now: datetime) -> None:
    _close(character, enc, lc.ENC_GUARD_GONE, now)
    _log(db, key=key, character_id=character.id, action=lc.LOG_GUARD_GONE, region_id=int(enc.region_id),
         ref_id=int(enc.id), now=now)


# =====================================================================================================================
# escape / bail
# =====================================================================================================================

def _jailed_character(db: Session, character_id: int, now: datetime) -> Tuple["models.Character",
                                                                              "models.LawJailTerm"]:
    character = lock_character(db, character_id)
    if character is None:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    term = active_term(db, character_id, now, lock=True)
    if term is None:
        raise LawError(409, MSG_NOT_JAILED)
    return character, term


def _end_term(character: "models.Character", term: "models.LawJailTerm", status: str, now: datetime) -> None:
    term.status = status
    term.resolved_at = now
    term.until = now
    term.notified = True
    character.jailed_until = now
    character.jail_region_id = None


def escape(db: Session, character_id: int, request_id: str) -> Tuple[bool, str, Optional[int]]:
    """``POST …/law/jail/escape`` (owner). Returns (success, message, term_id). A repeated ``request_id`` returns the
    stored outcome; a second attempt inside the cooldown is a 409 with the next time."""
    now = now_utc()
    settings = load_settings(db)
    character = lock_character(db, character_id)
    if character is None:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    previous = db.execute(text("SELECT action, ref_id FROM law_log WHERE event_key = :k"),
                          {"k": f"law:escape:{character_id}:{request_id}"}).first()
    if previous is not None:
        ok = previous[0] == lc.LOG_ESCAPE_OK
        return ok, _escape_message(ok, None), int(previous[1]) if previous[1] else None
    term = active_term(db, character_id, now, lock=True)
    if term is None:
        raise LawError(409, MSG_NOT_JAILED)
    next_at = _dt(term.next_escape_at)
    if next_at is not None and next_at > now:
        raise LawError(409, MSG_ESCAPE_COOLDOWN.format(time=_remaining(next_at, now)))
    chance_pct = escape_chance(db, character_id, settings)
    ok, roll = lc.roll_succeeds(chance_pct, rng())
    term.escape_attempts = int(term.escape_attempts or 0) + 1
    attempt = int(term.escape_attempts)
    if ok:
        _end_term(character, term, lc.JAIL_ESCAPED, now)
        _log(db, key=f"law:escape:{character_id}:{request_id}", character_id=character_id,
             action=lc.LOG_ESCAPE_OK, region_id=int(term.region_id), chance_pct=chance_pct, roll_pct=roll,
             ref_id=int(term.id), now=now)
        register_crime(db, crime_type=lc.CRIME_JAIL_ESCAPE, character_id=character_id,
                       region_id=int(term.region_id), points=0,
                       event_key=f"crime:escape:{term.id}:{attempt}", location_id=int(term.location_id),
                       floor=int(settings.heavy_wanted), now=now, settings=settings)
        db.flush()
        return True, _escape_message(True, None), int(term.id)
    new_until = lc.extended_until(now, _dt(term.until), settings.escape_fail_extend_pct,
                                  settings.max_remaining_jail_hours)
    term.until = new_until
    term.next_escape_at = now + timedelta(hours=int(settings.escape_cooldown_hours))
    character.jailed_until = new_until
    _log(db, key=f"law:escape:{character_id}:{request_id}", character_id=character_id, action=lc.LOG_ESCAPE_FAIL,
         region_id=int(term.region_id), chance_pct=chance_pct, roll_pct=roll, ref_id=int(term.id), now=now)
    db.flush()
    return False, _escape_message(False, new_until, now), int(term.id)


def _remaining(value: Optional[datetime], now: Optional[datetime] = None) -> str:
    import law_notify
    return law_notify.remaining(value, now)


def _escape_message(ok: bool, until: Optional[datetime], now: Optional[datetime] = None) -> str:
    if ok:
        return "Побег удался! Вы на свободе, но стража края теперь ищет вас всерьёз"
    if until is not None:
        return f"Побег не удался — срок увеличен, осталось {_remaining(until, now)}"
    return "Побег не удался — срок продлён"


def self_bail(db: Session, character_id: int, request_id: str) -> Tuple[int, Optional[int], bool]:
    """``POST …/law/jail/bail`` (owner pays own bail). Returns (paid, term_id, duplicate)."""
    now = now_utc()
    character = lock_character(db, character_id)
    if character is None:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    previous = db.execute(text("SELECT amount, ref_id FROM law_log WHERE event_key = :k"),
                          {"k": f"law:bail:{character_id}:{request_id}"}).first()
    if previous is not None:
        return int(previous[0] or 0), int(previous[1]) if previous[1] else None, True
    term = active_term(db, character_id, now, lock=True)
    if term is None:
        raise LawError(409, MSG_NOT_JAILED)
    _post_bail(db, payer_id=character_id, term=term, now=now)
    _end_term(character, term, lc.JAIL_BAILED, now)
    term.bailed_by_character_id = int(character_id)
    _log(db, key=f"law:bail:{character_id}:{request_id}", character_id=character_id, action=lc.LOG_BAIL,
         region_id=int(term.region_id), amount=int(term.bail_price), ref_id=int(term.id), now=now)
    db.flush()
    return int(term.bail_price), int(term.id), False


def _post_bail(db: Session, *, payer_id: int, term: "models.LawJailTerm", now: datetime) -> None:
    try:
        econ_ledger.post_operation(
            db, op_type=econ_core.OP_LAW_BAIL,
            legs=[econ_ledger.Leg(econ_ledger.AccountRef.character(payer_id),
                                  econ_ledger.AccountRef.region(int(term.region_id)), int(term.bail_price))],
            source_service=ECON_SOURCE_SERVICE, location_id=int(term.location_id), region_id=int(term.region_id),
            idempotency_key=f"law_bail:{term.id}",
            metadata={"term_id": int(term.id), "prisoner_id": int(term.character_id), "payer_id": int(payer_id)})
    except econ_ledger.InsufficientFunds:
        raise LawError(400, _insufficient_message(db, "для залога"))
    except econ_ledger.DuplicateOperation:
        raise LawError(409, MSG_BAIL_DONE)


@dataclass
class BailResult:
    paid: int
    duplicate: bool
    prisoner_id: int
    prisoner_user_id: Optional[int]
    payer_name: str
    prisoner_name: str


def bail_other(db: Session, *, user_id: int, payer_id: int, banker_id: int, prisoner_id: int,
               request_id: str) -> BailResult:
    """``POST /characters/law/bail`` — any player at a banker (any region) pays a prisoner's bail into the jail
    region treasury (user decision 6). Own alts may pay; the payer must not be activity-locked."""
    now = now_utc()
    ids = sorted({int(payer_id), int(prisoner_id)})
    locked = {}
    for cid in ids:                                     # ascending id lock order
        row = lock_character(db, cid)
        if row is None:
            raise LawError(404, MSG_CHARACTER_NOT_FOUND)
        locked[cid] = row
    payer, prisoner = locked[int(payer_id)], locked[int(prisoner_id)]
    if payer.user_id != int(user_id):
        raise LawError(403, MSG_NOT_OWNER)
    if payer.is_npc:
        raise LawError(403, MSG_NOT_PLAYER)
    previous = db.execute(text("SELECT amount FROM law_log WHERE event_key = :k"),
                          {"k": f"law:bail_by:{payer_id}:{request_id}"}).first()
    if previous is not None:
        return BailResult(int(previous[0] or 0), True, int(prisoner.id), None, payer.name, prisoner.name)
    message = activity_lock.lock_message(activity_lock.lock_for_character(payer))
    if message:
        raise LawError(409, message)
    banker = db.query(models.Character).filter(models.Character.id == int(banker_id)).first()
    if banker is None or not banker.is_npc or banker.npc_role != lc.BANKER_ROLE:
        raise LawError(404, MSG_BANKER_NOT_FOUND)
    if banker.npc_status == "dead":
        raise LawError(409, MSG_BANKER_DEAD)
    if banker.current_location_id is None or payer.current_location_id != banker.current_location_id:
        raise LawError(400, MSG_WRONG_LOCATION)
    banker_region = reputation_crud.location_region(db, banker.current_location_id)
    try:
        reputation_crud.require_npc_tier(db, payer.id, banker.id, banker_region)
    except reputation_crud.ReputationError as exc:
        raise LawError(exc.status_code, exc.detail)
    if prisoner.is_npc:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    term = active_term(db, prisoner.id, now, lock=True)
    if term is None:
        last = (db.query(models.LawJailTerm).filter(models.LawJailTerm.character_id == int(prisoner.id))
                .order_by(models.LawJailTerm.id.desc()).first())
        if last is not None and last.status == lc.JAIL_BAILED:
            raise LawError(409, MSG_BAIL_DONE)
        raise LawError(409, MSG_NOT_JAILED)
    _post_bail(db, payer_id=payer.id, term=term, now=now)
    _end_term(prisoner, term, lc.JAIL_BAILED, now)
    term.bailed_by_character_id = int(payer.id)
    _log(db, key=f"law:bail_by:{payer_id}:{request_id}", character_id=payer.id, action=lc.LOG_BAIL,
         region_id=int(term.region_id), amount=int(term.bail_price), ref_id=int(term.id), now=now)
    _log(db, key=f"law:bailed:{term.id}", character_id=prisoner.id, action=lc.LOG_BAIL,
         region_id=int(term.region_id), amount=int(term.bail_price), ref_id=int(term.id), now=now)
    db.flush()
    user = int(prisoner.user_id) if prisoner.user_id is not None else None
    return BailResult(int(term.bail_price), False, int(prisoner.id), user, payer.name, prisoner.name)


# =====================================================================================================================
# staff
# =====================================================================================================================

def _staff_key(actor_user_id: int, request_id: str, suffix: str) -> str:
    return f"law:staff:{int(actor_user_id)}:{request_id}:{suffix}"


def _staff_done(db: Session, actor_user_id: int, request_id: str) -> bool:
    prefix = f"law:staff:{int(actor_user_id)}:{request_id}:"
    return db.execute(text("SELECT 1 FROM law_log WHERE event_key LIKE :p LIMIT 1"),
                      {"p": _escape_like(prefix) + "%"}).first() is not None


def staff_release(db: Session, character_id: int, *, reason: str, request_id: str,
                  actor_user_id: int) -> Tuple[bool, bool, bool]:
    """End a serving term and/or cancel an open encounter. Returns (released, cancelled, duplicate)."""
    now = now_utc()
    character = lock_character(db, character_id)
    if character is None:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    if _staff_done(db, actor_user_id, request_id):
        return False, False, True
    released = cancelled = False
    term = active_term(db, character_id, now, lock=True)
    if term is not None:
        _end_term(character, term, lc.JAIL_RELEASED, now)
        _log(db, key=_staff_key(actor_user_id, request_id, "release"), character_id=character_id,
             action=lc.LOG_STAFF_RELEASE, region_id=int(term.region_id), ref_id=int(term.id), reason=reason,
             actor_user_id=actor_user_id, now=now)
        released = True
    elif character.jailed_until is not None:
        character.jailed_until = None           # a stale lazy value: tidy up
        character.jail_region_id = None
    if character.law_encounter_id:
        enc = get_encounter(db, character.law_encounter_id, lock=True)
        if enc is not None and enc.status in lc.ENC_OPEN:
            _close(character, enc, lc.ENC_CANCELLED, now)
            _log(db, key=_staff_key(actor_user_id, request_id, "cancel"), character_id=character_id,
                 action=lc.LOG_STAFF_CANCEL, region_id=int(enc.region_id), ref_id=int(enc.id), reason=reason,
                 actor_user_id=actor_user_id, now=now)
            cancelled = True
        else:
            character.law_encounter_id = None
    if not released and not cancelled:
        raise LawError(409, MSG_NOTHING_TO_RELEASE)
    db.flush()
    return released, cancelled, False


def staff_clear_wanted(db: Session, character_id: int, *, region_id: Optional[int], reason: str, request_id: str,
                       actor_user_id: int) -> Tuple[List[int], bool]:
    """Wanted -> 0 in one region (or every region with ``region_id=None``). Returns (cleared region ids, duplicate)."""
    now = now_utc()
    if lock_character(db, character_id) is None:
        raise LawError(404, MSG_CHARACTER_NOT_FOUND)
    if _staff_done(db, actor_user_id, request_id):
        return [], True
    settings = load_settings(db)
    if region_id is not None:
        if not region_names(db, [region_id]):
            raise LawError(404, MSG_REGION_NOT_FOUND)
        # FEAT-200 (fix 6): a region without wanted is nothing to clear — no journal row, «Розыска нет»
        targets = [int(region_id)] if read_wanted(db, character_id, region_id, settings, now) > 0 else []
    else:
        targets = [r for r, _ in _wanted_rows(db, character_id, settings, now)]
    cleared = []
    for rid in sorted(targets):
        clear_wanted(db, character_id, rid, settings, now, key=_staff_key(actor_user_id, request_id, f"clear:{rid}"),
                     action=lc.LOG_STAFF_CLEAR, reason=reason, actor_user_id=actor_user_id)
        cleared.append(rid)
    # nothing to clear: nothing is written (FEAT-200) — a replay of that request_id answers «Розыска нет» again
    db.flush()
    return cleared, False


def admin_character(db: Session, character_id: int) -> dict:
    character = _require_character(db, character_id)
    settings, levels, now = load_settings(db), load_levels(db), now_utc()
    rows = _wanted_rows(db, character_id, settings, now)
    crimes = (db.query(models.LawCrime).filter(models.LawCrime.character_id == int(character_id))
              .order_by(models.LawCrime.created_at.desc(), models.LawCrime.id.desc()).limit(ADMIN_CRIMES_LIMIT).all())
    logs = (db.query(models.LawLog).filter(models.LawLog.character_id == int(character_id))
            .order_by(models.LawLog.created_at.desc(), models.LawLog.id.desc()).limit(ADMIN_LOG_LIMIT).all())
    names = region_names(db, {r for r, _ in rows} | {int(c.region_id) for c in crimes}
                         | {int(x.region_id) for x in logs if x.region_id})
    users = reputation_crud._usernames(db, [x.actor_user_id for x in logs])
    wanted = []
    for region_id, value in rows:
        level = lc.level_for(value, levels)
        wanted.append({"region_id": region_id, "region_name": names.get(region_id), "value": value,
                       "level_code": level.code if level else None, "level_name": level.name if level else None})
    enc = open_encounter(db, character)
    term = active_term(db, character_id, now)
    return {
        "wanted": wanted,
        "encounter": encounter_out(db, enc, staff=True, settings=settings) if enc else None,
        "jail": jail_out(db, term, staff=True, settings=settings, now=now) if term else None,
        "crimes": [{"id": int(c.id), "crime_type": c.crime_type, "region_id": int(c.region_id),
                    "region_name": names.get(int(c.region_id)), "location_id": c.location_id,
                    "victim_character_id": c.victim_character_id, "battle_id": c.battle_id,
                    "wanted_points": int(c.wanted_points), "wanted_applied": int(c.wanted_applied),
                    "status": c.status, "created_at": c.created_at, "masked": bool(c.masked),
                    "witness_chance_pct": float(c.witness_chance_pct) if c.witness_chance_pct is not None else None,
                    "witness_roll_pct": float(c.witness_roll_pct) if c.witness_roll_pct is not None else None,
                    "reputation_delta": c.reputation_delta, "wanted_floor": c.wanted_floor,
                    "reveal_attempts": int(c.reveal_attempts or 0), "next_roll_at": c.next_roll_at,
                    "reveal_until": c.reveal_until, "revealed_at": c.revealed_at} for c in crimes],
        "renown": renown_crud.admin_renown(db, character_id),
        "renown_log": renown_crud.admin_renown_log(db, character_id),
        "log": [{"id": int(x.id), "created_at": x.created_at, "action": x.action, "region_id": x.region_id,
                 "region_name": names.get(int(x.region_id)) if x.region_id else None,
                 "wanted_before": x.wanted_before, "wanted_after": x.wanted_after, "amount": x.amount,
                 "chance_pct": float(x.chance_pct) if x.chance_pct is not None else None,
                 "roll_pct": float(x.roll_pct) if x.roll_pct is not None else None, "ref_id": x.ref_id,
                 "reason": x.reason, "actor_user_id": x.actor_user_id,
                 "actor_username": users.get(int(x.actor_user_id)) if x.actor_user_id else None} for x in logs],
    }


# =====================================================================================================================
# settings
# =====================================================================================================================

def _settings_dict(s: lc.LawSettings) -> dict:
    out = {}
    for name in lc.SETTINGS_FIELDS:
        value = getattr(s, name)
        out[name] = float(value) if isinstance(value, Decimal) else value
    return out


def settings_out(db: Session) -> dict:
    return {
        "settings": _settings_dict(load_settings(db)),
        "levels": [{"code": lv.code, "sort_order": lv.sort_order, "name": lv.name, "min_value": lv.min_value,
                    "fine": lv.fine, "jail_hours": lv.jail_hours} for lv in load_levels(db)],
    }


def update_settings(db: Session, body) -> dict:
    """Validate and store the settings + all 5 levels (``reputation:settings``). A changed decay rate first
    materialises every row with ``value > 0`` at the OLD rate (same transaction), so the change is not retroactive."""
    old = load_settings(db)
    raw = body.settings
    values = {}
    for name in lc.SETTINGS_FIELDS:
        value = getattr(raw, name)
        if name in ("decay_per_day", "flee_base_pct", "flee_per_point_pct", "flee_min_pct", "flee_max_pct",
                    "escape_base_pct", "escape_per_point_pct", "escape_min_pct", "escape_max_pct",
                    "escape_fail_extend_pct", "bail_multiplier"):
            value = Decimal(str(value))
        elif name == "outlaw_min_level":
            value = str(value).strip()
        else:
            value = int(value)
        values[name] = value
    new = lc.LawSettings(**values)
    levels = [lc.Level(code=x.code, sort_order=lc.LEVEL_CODES.index(x.code) + 1 if x.code in lc.LEVEL_CODES else 0,
                       name=(x.name or "").strip(), min_value=int(x.min_value), fine=int(x.fine),
                       jail_hours=int(x.jail_hours)) for x in body.levels]
    error = lc.validate(new, levels)
    if error:
        raise LawError(400, error)
    now = now_utc()
    if Decimal(str(new.decay_per_day)) != Decimal(str(old.decay_per_day)):
        query = (db.query(models.CharacterWanted).filter(models.CharacterWanted.value > 0)
                 .order_by(models.CharacterWanted.character_id, models.CharacterWanted.region_id))
        if _for_update(db):
            query = query.with_for_update()
        for row in query.populate_existing().all():
            value, anchor = lc.materialise(int(row.value or 0), row.decay_at, now, old.decay_per_day)
            row.value, row.decay_at, row.updated_at = value, anchor, now
            if value > 0 and (old.decay_per_day <= 0 or anchor is None):
                row.decay_at = now              # decay was off: the new rate counts from now
    row = db.get(models.LawSettings, 1)
    if row is None:
        row = models.LawSettings(id=1, updated_at=now)
        db.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    row.updated_at = now
    existing = {x.code: x for x in db.query(models.LawLevel).all()}
    for lv in levels:
        target = existing.get(lv.code)
        if target is None:
            target = models.LawLevel(code=lv.code, sort_order=lv.sort_order)
            db.add(target)
        target.sort_order = lv.sort_order
        target.name = lv.name
        target.min_value = lv.min_value
        target.fine = lv.fine
        target.jail_hours = lv.jail_hours
    db.flush()
    return settings_out(db)
