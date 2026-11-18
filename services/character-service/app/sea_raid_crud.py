"""FEAT-214 §3.8: sea monster raids on ship decks (sync SQLAlchemy; the caravan raid lifecycle as the template).

* **roll** (inside the ship transaction, ``sea_pass``): :func:`roll_monster` picks a template from the zone's
  ``location_mob_spawns`` (the ordinary mob editor: ``spawn_chance`` = attack chance on entry × ``raid_chance_mult``,
  ``max_active`` = monsters per battle group); :func:`eligible_players` filters the deck (not in a battle, no activity
  lock, HP > 0, not gathering); :func:`plan_raid` inserts one ``starting`` row per group of ≤ 5 (evened out). No HTTP;
* **start** (after the ship commit): :func:`start_pending` → :func:`start_raid` per row: claim the row
  (``mob_ids`` NULL → ``[]``), spawn the hidden ``spawn_type='dungeon'`` monsters on the deck (``mob_ids`` stored after
  each one), ask battle-service for the fight, then :func:`mark_fighting`; a refusal / failure → :func:`abandon`
  (monsters despawned, status ``aborted``);
* **settle** — :func:`battle_result` (the battle-service callback ``/characters/internal/sea/raid-result``) and the
  poll: :func:`settle` (conditional, idempotent) + notices + :func:`despawn_mobs`. The ship hold is released by the
  next sea pass — nothing here locks the ship;
* **cargo loss** (FEAT-215 §3.8) — :func:`apply_cargo_loss` once every group row of an attack is final (after the
  callback / poll settlement, and as a pass fallback): each caravan named in ``caravan_ids`` (in the hold when the
  attack was planned) loses ``econ_caravan.cargo_loss_units(left, caravan_sea_loss_pct, lost, decided)`` units
  (``sunk_units``; one ``econ_caravan_sea_losses`` row per caravan and attack — UNIQUE = applied once). No money
  moves: the seller is paid in full, the buyer receives fewer units. An empty deck plans no attack → no loss;
* **pass fallbacks** — :func:`raid_followups` (called at the end of ``sea_pass.run_pass``): unstarted rows, stale
  ``starting`` rows (> 10 min: attach a tagged battle or expire), ``fighting`` rows polled after 2 min (lost callbacks),
  final rows with monsters still spawned, final attacks whose cargo is not settled yet.

Lock order of the cargo loss (§3.6): ``econ_caravans (asc) → econ_caravan_sea_losses (insert) → sea_raids (UPDATE)``;
the ship row is never locked here, escorts are a plain read.

Player team = 0, monster team = 1. Rewards / loss are the ordinary PvE end of battle-service.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

import activity_lock
import caravan_escort_crud as escort_crud
import econ_caravan
import econ_core as core
import economy_caravan_crud as caravan_crud
import law_notify
import models
import sea_core
import sea_crud

logger = logging.getLogger("character-service.sea_raids")

SessionFactory = Callable[[], Session]

PLAYER_TEAM = 0
SPAWN_TYPE = "dungeon"                    # hidden from the location lists; despawned by crud.despawn_dungeon_mobs
STALE_STARTING_AFTER = timedelta(minutes=10)
POLL_AFTER = timedelta(minutes=2)
FINISHED_BATTLE_STATUSES = ("finished", "forfeit")
BATCH_SIZE = 200
PCT_SCALE = 100

RESULT_ALREADY = "already"
RESULT_UNKNOWN = "unknown"
START_FIGHTING = "fighting"
START_ABORTED = "aborted"
START_SKIPPED = "skipped"

# WS ``sea`` events of the raid lifecycle (FE tones by ``data.event``)
EV_RAID = "raid"
EV_RAID_REPELLED = "raid_repelled"
EV_RAID_WON = "raid_won"
EV_RAID_LOST = "raid_lost"

MSG_RAID = "На палубу корабля «{ship}» взбирается «{monster}»!"
MSG_RAID_BATTLE = "Бой на палубе с «{monster}» — защищайте корабль!"
MSG_REPELLED = "Команда корабля «{ship}» отбилась от «{monster}»"
MSG_WON = "Монстры отбиты! «{monster}» больше не угрожает кораблю"
MSG_LOST = "Монстры одолели вас — «{monster}» хозяйничает на палубе"
MSG_CARGO_SUNK = "Часть груза утащили в пучину: «{monster}» унёс {units} ед. с корабля «{ship}»"
EV_CARGO_SUNK = "cargo_sunk"               # escort WS event (``caravan_escort`` channel)


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _i(value) -> int:
    return int(value or 0)


def _ids(value) -> List[int]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    out: List[int] = []
    for x in value if isinstance(value, (list, tuple)) else ():
        try:
            cid = int(x)
        except (TypeError, ValueError):
            continue
        if cid not in out:
            out.append(cid)
    return out


def _json(ids: Sequence[int]) -> str:
    return json.dumps([int(i) for i in ids])


def _lock_raid(db: Session, raid_id: int) -> Optional["models.SeaRaid"]:
    return sea_crud._locked(db.query(models.SeaRaid).filter(models.SeaRaid.id == int(raid_id)), db).first()


# =====================================================================================================================
# the roll (inside the ship transaction — no HTTP, no commit)
# =====================================================================================================================

@dataclass(frozen=True)
class MonsterPick:
    template_id: int
    name: str
    max_active: int


def roll_monster(db: Session, zone_id: int, params: "sea_crud.SeaParams", rng) -> Optional[MonsterPick]:
    """The monster that attacks on entry into ``zone_id`` (None = no attack): the enabled spawn rules of the zone with
    an existing template, shuffled; the first with ``roll < spawn_chance × raid_chance_mult`` wins."""
    mult = float(params.raid_chance_mult or 0)
    if mult <= 0 or not zone_id:
        return None
    rows = (db.query(models.LocationMobSpawn.mob_template_id, models.LocationMobSpawn.spawn_chance,
                     models.LocationMobSpawn.max_active, models.MobTemplate.name)
            .join(models.MobTemplate, models.MobTemplate.id == models.LocationMobSpawn.mob_template_id)
            .filter(models.LocationMobSpawn.location_id == int(zone_id),
                    models.LocationMobSpawn.is_enabled.is_(True))
            .order_by(models.LocationMobSpawn.id).all())
    candidates = list(rows)
    rng.shuffle(candidates)
    for template_id, chance, max_active, name in candidates:
        if rng.random() * PCT_SCALE < float(chance or 0) * mult:
            return MonsterPick(int(template_id), (name or "").strip() or "морской монстр", _i(max_active))
    return None


def _health(db: Session, character_id: int) -> Optional[int]:
    """``character_attributes.current_health`` (None = unknown: no table / row — battle-service re-checks)."""
    rows = sea_crud._rows(db, "SELECT current_health FROM character_attributes WHERE character_id = :c",
                          {"c": int(character_id)})
    if not rows or rows[0][0] is None:
        return None
    return int(rows[0][0])


def eligible_players(db: Session, players: Sequence["models.Character"]) -> List[int]:
    """Deck players that are pulled into the fight: not in an active battle, not activity-locked (unconscious, jail,
    reading, asleep …), HP > 0, not gathering. Ascending ids. FEAT-215 (user decision): a caravan escort sailing with
    its cargo fights the monsters like everyone on deck — the ``caravan_escort`` lock is the only exemption (the
    battle-service ``/internal/sea-raid`` check mirrors it). NPC caravan guards never fight monsters (NPCs)."""
    import sea_pass                                     # late: sea_pass imports this module
    out: List[int] = []
    for ch in players:
        cid = int(ch.id)
        if ch.is_npc or sea_pass.in_battle(db, cid):
            continue
        if activity_lock.lock_for_character(ch).get("reason") not in (None, activity_lock.REASON_CARAVAN_ESCORT):
            continue
        hp = _health(db, cid)
        if hp is not None and hp <= 0:
            continue
        if sea_pass.gathering(db, cid):
            continue
        out.append(cid)
    return sorted(set(out))


def has_active_raid(db: Session, ship_id: int) -> bool:
    return db.query(models.SeaRaid.id).filter(models.SeaRaid.ship_id == int(ship_id),
                                              models.SeaRaid.status.in_(sea_core.RAID_ACTIVE_STATUSES)).first() \
        is not None


def attack_key(ship: "models.SeaShip") -> str:
    """One attack per zone entry: ship, trip, position, zone and the entry's timer (a drift resets ``leg_pos``)."""
    stamp = int(ship.next_zone_at.timestamp() // 60) if ship.next_zone_at is not None else 0
    return f"{int(ship.id)}:{_i(ship.trip_no)}:{_i(ship.leg_pos)}:{_i(ship.current_zone_id)}:{stamp}"


def plan_raid(db: Session, ship: "models.SeaShip", pick: MonsterPick, player_ids: Sequence[int],
              now: datetime, caravan_ids: Optional[Sequence[int]] = None) -> List["models.SeaRaid"]:
    """Insert one ``starting`` row per battle group (no commit). A duplicate entry (UNIQUE attack_key + group) →
    ``[]`` — the attack has already been planned. FEAT-215 §3.5: ``caravan_ids`` = the caravans in the hold at this
    moment, written on every group row (None / empty → NULL: no cargo to lose)."""
    key = attack_key(ship)
    cargo = sorted({int(c) for c in caravan_ids}) if caravan_ids else None
    rows: List["models.SeaRaid"] = []
    try:
        with db.begin_nested():
            for n, group in enumerate(sea_core.split_groups(player_ids, sea_core.SEA_RAID_TEAM_MAX)):
                row = models.SeaRaid(ship_id=int(ship.id), attack_key=key, group_no=n,
                                     deck_location_id=int(ship.deck_location_id), zone_id=_i(ship.current_zone_id),
                                     mob_template_id=int(pick.template_id), monster_name=pick.name,
                                     player_ids=[int(c) for c in group], status=sea_core.RAID_STARTING,
                                     mobs_despawned=False, created_at=now,
                                     caravan_ids=list(cargo) if cargo else None)
                db.add(row)
                rows.append(row)
            db.flush()
    except IntegrityError:
        logger.info("sea ship %s: attack %s already planned", ship.id, key)
        return []
    return rows


# =====================================================================================================================
# start (after the ship commit; own commits; HTTP)
# =====================================================================================================================

def _user_ids(db: Session, ids: Sequence[int]) -> Dict[int, Optional[int]]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    ph, params = core.in_params("c", ids)
    return {int(r[0]): (int(r[1]) if r[1] is not None else None) for r in db.execute(text(
        f"SELECT id, user_id FROM characters WHERE id IN ({ph})"), params).fetchall()}


def _notices(db: Session, ids: Sequence[int], message: str, ship_id: int, event: str,
             **data) -> List[law_notify.Notice]:
    users = _user_ids(db, ids)
    return [sea_crud.notice(users.get(int(c)), message, int(c), int(ship_id), event, **data)
            for c in sorted({int(i) for i in ids})]


def _claim_start(db: Session, raid_id: int) -> bool:
    """``mob_ids`` NULL → ``[]`` on a ``starting`` row: only one starter per row (commits)."""
    result = db.execute(text("UPDATE sea_raids SET mob_ids = :e WHERE id = :id AND status = :s AND mob_ids IS NULL"),
                        {"e": "[]", "id": int(raid_id), "s": sea_core.RAID_STARTING})
    db.commit()
    return (result.rowcount or 0) == 1


def _spawn(db: Session, raid: "models.SeaRaid") -> List[int]:
    """Spawn the pack (``crud.spawn_mob_from_template`` commits per mob); ``mob_ids`` is stored after each one so a
    crash never leaks an untracked monster."""
    import crud                                         # late: crud imports half of the service
    raid_id, template_id = int(raid.id), int(raid.mob_template_id)
    deck = int(raid.deck_location_id)
    max_active = db.execute(text("SELECT max_active FROM location_mob_spawns WHERE mob_template_id = :t "
                                 "AND location_id = :l"), {"t": template_id, "l": _i(raid.zone_id)}).scalar()
    count = sea_core.pack_size(_i(max_active) or 1, len(_ids(raid.player_ids)))
    db.rollback()
    spawned: List[int] = []
    for _ in range(count):
        _mob, character = crud.spawn_mob_from_template(db, template_id, deck, SPAWN_TYPE)
        spawned.append(int(character.id))
        db.execute(text("UPDATE sea_raids SET mob_ids = :m WHERE id = :id"), {"m": _json(spawned), "id": raid_id})
        db.commit()
    return spawned


def mark_fighting(db: Session, raid_id: int, battle_id: int, placed_ids: Sequence[int],
                  now: Optional[datetime] = None) -> bool:
    """``starting`` → ``fighting`` with the battle and the placed players (commits). False when the row already moved
    on (a very fast callback settled it)."""
    now = now or now_utc()
    result = db.execute(text(
        "UPDATE sea_raids SET status = :f, battle_id = :b, placed_ids = :p, started_at = :now "
        "WHERE id = :id AND status = :s"),
        {"f": sea_core.RAID_FIGHTING, "b": int(battle_id), "p": _json(placed_ids), "now": now, "id": int(raid_id),
         "s": sea_core.RAID_STARTING})
    if (result.rowcount or 0) != 1:
        db.execute(text("UPDATE sea_raids SET placed_ids = :p, battle_id = COALESCE(battle_id, :b) "
                        "WHERE id = :id AND placed_ids IS NULL"),
                   {"p": _json(placed_ids), "b": int(battle_id), "id": int(raid_id)})
        db.commit()
        return False
    db.commit()
    return True


def despawn_mobs(db: Session, raid_id: int) -> bool:
    """Remove the monsters of a finished raid (idempotent; commits). True when the raid is now marked despawned."""
    import crud
    raid = db.get(models.SeaRaid, int(raid_id))
    if raid is None or raid.status not in sea_core.RAID_FINAL_STATUSES or raid.mobs_despawned:
        db.rollback()
        return False
    mob_ids = _ids(raid.mob_ids)
    db.rollback()
    if mob_ids:
        crud.despawn_dungeon_mobs(db, mob_ids)
    db.execute(text("UPDATE sea_raids SET mobs_despawned = 1 WHERE id = :id"), {"id": int(raid_id)})
    db.commit()
    return True


def abandon(db: Session, raid_id: int, now: Optional[datetime] = None, *, status: str = sea_core.RAID_ABORTED) -> bool:
    """The fight could not be created: the row → ``aborted`` (or ``expired``), monsters despawned (commits)."""
    now = now or now_utc()
    db.rollback()
    result = db.execute(text("UPDATE sea_raids SET status = :st, ended_at = :now WHERE id = :id AND status = :s"),
                        {"st": status, "now": now, "id": int(raid_id), "s": sea_core.RAID_STARTING})
    db.commit()
    try:
        despawn_mobs(db, raid_id)
    except Exception:
        db.rollback()
        logger.exception("sea raid %s: monsters not despawned (the pass retries)", raid_id)
    return (result.rowcount or 0) == 1


@dataclass
class StartResult:
    raid_id: int
    status: str                                       # fighting | aborted | skipped
    battle_id: Optional[int] = None
    notices: List[law_notify.Notice] = field(default_factory=list)


def start_raid(db: Session, raid_id: int, now: Optional[datetime] = None) -> StartResult:
    """Spawn → battle-service → ``fighting`` for one ``starting`` row. Never raises."""
    import battle_client
    now = now or now_utc()
    out = StartResult(raid_id=int(raid_id), status=START_SKIPPED)
    try:
        if not _claim_start(db, raid_id):
            return out
        raid = db.get(models.SeaRaid, int(raid_id))
        if raid is None:
            db.rollback()
            return out
        players = _ids(raid.player_ids)
        ship_id, deck, monster = int(raid.ship_id), int(raid.deck_location_id), raid.monster_name or "монстр"
        mob_ids = _spawn(db, raid)
    except Exception:
        db.rollback()
        logger.exception("sea raid %s: monster spawn failed", raid_id)
        abandon(db, raid_id, now)
        out.status = START_ABORTED
        return out
    try:
        created = asyncio.run(battle_client.create_sea_raid_battle(int(raid_id), deck, players, mob_ids))
    except battle_client.BattleServiceError as exc:
        logger.warning("sea raid %s: battle refused (%s %s)", raid_id, exc.status_code, exc.detail)
        abandon(db, raid_id, now)
        out.status = START_ABORTED
        return out
    except Exception:
        logger.exception("sea raid %s: battle create crashed", raid_id)
        abandon(db, raid_id, now)
        out.status = START_ABORTED
        return out
    battle_id = int(created["battle_id"])
    placed = [p for p in created.get("player_character_ids") or [] if p in set(players)] or list(players)
    for attempt in range(2):
        try:
            mark_fighting(db, raid_id, battle_id, placed, now)
            break
        except DBAPIError:
            db.rollback()
            # the battle exists: the pass re-attaches a lost update through battles.sea_raid_id
            logger.exception("sea raid %s: mark fighting failed (attempt %s)", raid_id, attempt + 1)
    out.status, out.battle_id = START_FIGHTING, battle_id
    try:
        out.notices = _notices(db, placed, MSG_RAID_BATTLE.format(monster=monster), ship_id, EV_RAID,
                               battle_id=battle_id, location_id=deck, sea_raid_id=int(raid_id))
    except Exception:
        db.rollback()
        logger.exception("sea raid %s: battle notices failed", raid_id)
    db.rollback()
    logger.info("sea raid %s: ship=%s deck=%s battle=%s players=%s mobs=%s", raid_id, ship_id, deck, battle_id,
                placed, mob_ids)
    return out


def _select_ids(db: Session, sql: str, params: dict) -> List[int]:
    try:
        return [int(r[0]) for r in db.execute(text(sql), {**params, "n": BATCH_SIZE}).fetchall()]
    finally:
        db.rollback()


def start_pending(db: Session, ship_id: Optional[int] = None, now: Optional[datetime] = None) -> List[StartResult]:
    """Start every unstarted ``starting`` row (of one ship, or all). Publishes the battle notices. Never raises."""
    now = now or now_utc()
    sql = "SELECT id FROM sea_raids WHERE status = :s AND mob_ids IS NULL"
    params: dict = {"s": sea_core.RAID_STARTING}
    if ship_id is not None:
        sql += " AND ship_id = :ship"
        params["ship"] = int(ship_id)
    try:
        ids = _select_ids(db, sql + " ORDER BY id LIMIT :n", params)
    except DBAPIError:
        logger.warning("sea raids: pending rows unreadable", exc_info=True)
        return []
    results = []
    for raid_id in ids:
        result = start_raid(db, raid_id, now)
        if result.notices:
            law_notify.publish(result.notices)
        results.append(result)
    return results


# =====================================================================================================================
# settlement (callback / poll)
# =====================================================================================================================

@dataclass
class SettleResult:
    status: str                                       # won | lost | aborted | expired | already | unknown
    raid_id: Optional[int] = None
    notices: List[law_notify.Notice] = field(default_factory=list)


def settle(db: Session, raid_id: int, *, battle_id: Optional[int], winner_team: Optional[int], aborted: bool,
           now: Optional[datetime] = None, expire: bool = False) -> SettleResult:
    """Close an active raid row (commits): ``aborted`` | ``won`` (team 0 won) | ``lost``; a final row → ``already``,
    an unknown row (or a battle mismatch) → ``unknown``. Notices go to the placed players."""
    now = now or now_utc()
    raid = _lock_raid(db, raid_id)
    if raid is None:
        db.rollback()
        return SettleResult(RESULT_UNKNOWN)
    if raid.status in sea_core.RAID_FINAL_STATUSES:
        db.rollback()
        return SettleResult(RESULT_ALREADY, int(raid_id))
    if battle_id and raid.battle_id and int(raid.battle_id) != int(battle_id):
        db.rollback()
        logger.warning("sea raid %s: result of battle %s, but the raid fights battle %s", raid_id, battle_id,
                       raid.battle_id)
        return SettleResult(RESULT_UNKNOWN, int(raid_id))
    if expire:
        status = sea_core.RAID_EXPIRED
    elif aborted:
        status = sea_core.RAID_ABORTED
    elif winner_team is not None and int(winner_team) == PLAYER_TEAM:
        status = sea_core.RAID_WON
    else:
        status = sea_core.RAID_LOST
    raid.status = status
    raid.ended_at = now
    if battle_id and not raid.battle_id:
        raid.battle_id = int(battle_id)
    players = _ids(raid.placed_ids) or _ids(raid.player_ids)
    monster, ship_id = raid.monster_name or "монстр", int(raid.ship_id)
    db.flush()
    result = SettleResult(status, int(raid_id))
    if status == sea_core.RAID_WON:
        result.notices = _notices(db, players, MSG_WON.format(monster=monster), ship_id, EV_RAID_WON,
                                  sea_raid_id=int(raid_id))
    elif status == sea_core.RAID_LOST:
        result.notices = _notices(db, players, MSG_LOST.format(monster=monster), ship_id, EV_RAID_LOST,
                                  sea_raid_id=int(raid_id))
    db.commit()
    logger.info("sea raid %s settled: %s (battle %s, winner %s)", raid_id, status, battle_id, winner_team)
    return result


def battle_result(db: Session, *, battle_id: int, raid_id: int, winner_team: Optional[int], aborted: bool,
                  now: Optional[datetime] = None) -> str:
    """The battle-service callback: settle, publish, despawn. Returns the status."""
    now = now or now_utc()
    result = settle(db, raid_id, battle_id=battle_id, winner_team=winner_team, aborted=aborted, now=now)
    if result.notices:
        law_notify.publish(result.notices)
    if result.status in sea_core.RAID_FINAL_STATUSES or result.status == RESULT_ALREADY:
        try:
            despawn_mobs(db, raid_id)
        except Exception:
            db.rollback()
            logger.exception("sea raid %s: monsters not despawned, retried by the sea pass", raid_id)
        settle_cargo_of_raid(db, raid_id, now)
    return result.status


# =====================================================================================================================
# sea pass fallbacks
# =====================================================================================================================

def _tagged_battle(db: Session, raid_id: int) -> Optional[int]:
    """The battle-service battle tagged with this raid (shared DB), None when there is none / no column yet."""
    try:
        with db.begin_nested():
            value = db.execute(text("SELECT id FROM battles WHERE sea_raid_id = :r ORDER BY id LIMIT 1"),
                               {"r": int(raid_id)}).scalar()
    except DBAPIError:
        return None
    return int(value) if value is not None else None


def _each(factory: SessionFactory, sql: str, params: dict, action, what: str) -> int:
    db = factory()
    try:
        ids = _select_ids(db, sql, params)
    finally:
        db.close()
    done = 0
    for raid_id in ids:
        db = factory()
        try:
            if action(db, raid_id):
                done += 1
        except Exception:
            db.rollback()
            logger.exception("sea pass: %s of raid %s failed", what, raid_id)
        finally:
            db.close()
    return done


def _expire_one(db: Session, raid_id: int, now: datetime) -> bool:
    raid = _lock_raid(db, raid_id)
    if raid is None or raid.status != sea_core.RAID_STARTING:
        db.rollback()
        return False
    battle_id = _tagged_battle(db, raid_id)
    if battle_id is not None:                         # the fight exists, only the update was lost: keep the raid
        raid.status, raid.battle_id = sea_core.RAID_FIGHTING, battle_id
        raid.started_at = raid.started_at or raid.created_at
        if raid.placed_ids is None:
            raid.placed_ids = _ids(raid.player_ids)
        db.commit()
        logger.warning("sea raid %s: start update was lost — attached to battle %s", raid_id, battle_id)
        return True
    db.rollback()
    abandon(db, raid_id, now, status=sea_core.RAID_EXPIRED)
    logger.warning("sea raid %s: stuck in starting — expired", raid_id)
    return True


def _poll_one(db: Session, raid_id: int, now: datetime) -> bool:
    import battle_client
    raid = db.get(models.SeaRaid, int(raid_id))
    if raid is None or raid.status != sea_core.RAID_FIGHTING:
        db.rollback()
        return False
    battle_id = raid.battle_id
    db.rollback()
    if not battle_id:
        kwargs = dict(battle_id=None, winner_team=None, aborted=True)
    else:
        try:
            result = battle_client.get_battle_result(int(battle_id))
        except battle_client.BattleServiceError as exc:
            logger.warning("sea pass: battle %s of raid %s not polled: %s", battle_id, raid_id, exc)
            return False
        if result == battle_client.BATTLE_NOT_FOUND:
            kwargs = dict(battle_id=int(battle_id), winner_team=None, aborted=True)
        elif isinstance(result, dict) and result.get("status") in FINISHED_BATTLE_STATUSES:
            kwargs = dict(battle_id=int(battle_id), winner_team=result.get("winner_team"),
                          aborted=bool(result.get("aborted")))
        else:
            return False
    outcome = settle(db, raid_id, now=now, **kwargs)
    if outcome.notices:
        law_notify.publish(outcome.notices)
    if outcome.status in sea_core.RAID_FINAL_STATUSES:
        despawn_mobs(db, raid_id)
        settle_cargo_of_raid(db, raid_id, now)
        return True
    return False


def raid_followups(factory: SessionFactory, now: Optional[datetime] = None) -> Dict[str, int]:
    """End of the sea pass (each step best effort): unstarted rows, stale ``starting`` rows, lost callbacks of
    ``fighting`` rows, final rows with monsters still spawned."""
    now = now or now_utc()
    stats = {"raid_started": 0, "raid_expired": 0, "raid_polled": 0, "raid_despawned": 0, "cargo_settled": 0}
    db = factory()
    try:
        stats["raid_started"] = sum(1 for r in start_pending(db, None, now) if r.status == START_FIGHTING)
    finally:
        db.close()
    stats["raid_expired"] = _each(
        factory, "SELECT id FROM sea_raids WHERE status = :s AND created_at <= :cut ORDER BY id LIMIT :n",
        {"s": sea_core.RAID_STARTING, "cut": now - STALE_STARTING_AFTER},
        lambda db, rid: _expire_one(db, rid, now), "stale start")
    stats["raid_polled"] = _each(
        factory, "SELECT id FROM sea_raids WHERE status = :s AND started_at <= :cut ORDER BY id LIMIT :n",
        {"s": sea_core.RAID_FIGHTING, "cut": now - POLL_AFTER},
        lambda db, rid: _poll_one(db, rid, now), "poll")
    final = ", ".join(f":f{i}" for i in range(len(sea_core.RAID_FINAL_STATUSES)))
    stats["raid_despawned"] = _each(
        factory, f"SELECT id FROM sea_raids WHERE mobs_despawned = 0 AND status IN ({final}) ORDER BY id LIMIT :n",
        {f"f{i}": s for i, s in enumerate(sea_core.RAID_FINAL_STATUSES)}, despawn_mobs, "despawn")
    stats["cargo_settled"] = cargo_followups(factory, now)
    return stats


# =====================================================================================================================
# FEAT-215 §3.8: cargo lost to the monsters (own transaction; after the settlement)
# =====================================================================================================================

CARGO_APPLIED = "applied"
CARGO_PENDING = "pending"                             # a group of the attack still fights (or the call failed)
CARGO_ALREADY = "already"
CARGO_NONE = "none"                                   # no such attack


@dataclass
class CargoLoss:
    status: str                                       # applied | pending | already | none
    caravans: List[int] = field(default_factory=list)
    notices: List[law_notify.Notice] = field(default_factory=list)


def _loss_pct(db: Session) -> float:
    import econ_tick                                  # late: econ_tick imports most of the service
    return float(getattr(econ_tick.load_params(db), "caravan_sea_loss_pct", 0.0) or 0.0)


def _escorts_by_caravan(db: Session, caravan_ids: Sequence[int]) -> Dict[int, List[tuple]]:
    """Active escorts ``{caravan_id: [(character_id, user_id)]}`` (plain read — notices only)."""
    ids = sorted({int(c) for c in caravan_ids})
    if not ids:
        return {}
    ph, params = core.in_params("c", ids)
    rows = db.execute(text(
        f"SELECT e.caravan_id, e.character_id, ch.user_id FROM econ_caravan_escorts e "
        f"LEFT JOIN characters ch ON ch.id = e.character_id WHERE e.caravan_id IN ({ph}) AND e.status = :st "
        f"ORDER BY e.id"), {**params, "st": escort_crud.STATUS_ACTIVE}).fetchall()
    out: Dict[int, List[tuple]] = {}
    for r in rows:
        out.setdefault(int(r[0]), []).append((int(r[1]), int(r[2]) if r[2] is not None else None))
    return out


def apply_cargo_loss(db: Session, key: str, now: Optional[datetime] = None) -> CargoLoss:
    """Apply the cargo loss of the attack ``key`` once all its group rows are final (commits; never twice):
    ``lost`` / ``decided`` = lost / (won + lost) groups (aborted / expired ignored; 0 decided → no loss). Every
    in-transit caravan of ``caravan_ids`` loses ``cargo_loss_units(units − stolen − sunk, caravan_sea_loss_pct,
    lost, decided)``; the UNIQUE ``(caravan_id, attack_key)`` row makes a concurrent / repeated call a no-op. Then
    ``cargo_settled_at`` is set on every row of the attack (also when nothing was lost). No money moves."""
    now = now or now_utc()
    rows = db.query(models.SeaRaid).filter(models.SeaRaid.attack_key == str(key)).order_by(models.SeaRaid.id).all()
    if not rows:
        db.rollback()
        return CargoLoss(CARGO_NONE)
    if any(r.cargo_settled_at is not None for r in rows):
        db.rollback()
        return CargoLoss(CARGO_ALREADY)
    if any(r.status not in sea_core.RAID_FINAL_STATUSES for r in rows):
        db.rollback()
        return CargoLoss(CARGO_PENDING)
    lost = sum(1 for r in rows if r.status == sea_core.RAID_LOST)
    decided = lost + sum(1 for r in rows if r.status == sea_core.RAID_WON)
    cargo = sorted({c for r in rows for c in _ids(r.caravan_ids)})
    ship_id = int(rows[0].ship_id)
    monster = rows[0].monster_name or "монстр"
    result = CargoLoss(CARGO_APPLIED)
    hit: List[tuple] = []
    if cargo and lost > 0:
        pct = max(0.0, min(100.0, _loss_pct(db)))
        C = models.EconCaravan
        caravans = sea_crud._locked(db.query(C).filter(C.id.in_(cargo), C.status == caravan_crud.STATUS_IN_TRANSIT)
                                    .order_by(C.id), db).all()
        for caravan in caravans:
            units = econ_caravan.cargo_loss_units(caravan_crud._remaining_units(caravan), pct, lost, decided)
            if units <= 0:
                continue
            try:
                with db.begin_nested():
                    db.add(models.EconCaravanSeaLoss(
                        caravan_id=int(caravan.id), ship_id=ship_id, attack_key=str(key), lost_groups=lost,
                        decided_groups=decided, loss_pct=round(pct, 2), units_lost=units, created_at=now))
                    db.flush()
            except IntegrityError:                    # this attack already took its share of this caravan
                continue
            caravan.sunk_units = caravan_crud._dec3(caravan_crud._dec3(caravan.sunk_units) + caravan_crud._dec3(units))
            hit.append((int(caravan.id), units))
    db.execute(text("UPDATE sea_raids SET cargo_settled_at = :now WHERE attack_key = :k AND cargo_settled_at IS NULL"),
               {"now": now, "k": str(key)})
    if hit:
        ship_name = db.execute(text("SELECT name FROM sea_ships WHERE id = :s"), {"s": ship_id}).scalar() or "корабль"
        escorts = _escorts_by_caravan(db, [c for c, _u in hit])
        for caravan_id, units in hit:
            message = MSG_CARGO_SUNK.format(monster=monster, units=f"{units:g}", ship=ship_name)
            for character_id, user_id in escorts.get(caravan_id, []):
                result.notices.append(escort_crud._notice(user_id, message, character_id, caravan_id,
                                                          event=EV_CARGO_SUNK, ship_id=ship_id))
        result.caravans = [c for c, _u in hit]
    db.commit()
    if hit:
        logger.info("sea attack %s: cargo lost %s (lost %s of %s groups)", key, hit, lost, decided)
    return result


def apply_cargo_loss_tx(factory: SessionFactory, key: str, now: Optional[datetime] = None) -> CargoLoss:
    """:func:`apply_cargo_loss` in its own session; publishes the escort notices. Never raises."""
    db = factory()
    try:
        result = apply_cargo_loss(db, key, now)
    except Exception:
        db.rollback()
        logger.exception("sea attack %s: cargo loss failed (the sea pass retries)", key)
        return CargoLoss(CARGO_PENDING)
    finally:
        db.close()
    if result.notices:
        law_notify.publish(result.notices)
    return result


def settle_cargo_of_raid(db: Session, raid_id: int, now: Optional[datetime] = None) -> Optional[CargoLoss]:
    """After a raid row became final (callback / poll, ``db`` clean): the cargo loss of its attack. Never raises —
    a failure is retried by :func:`cargo_followups`."""
    try:
        key = db.query(models.SeaRaid.attack_key).filter(models.SeaRaid.id == int(raid_id)).scalar()
        if key is None:
            db.rollback()
            return None
        result = apply_cargo_loss(db, key, now)
    except Exception:
        db.rollback()
        logger.exception("sea raid %s: cargo loss failed (the sea pass retries)", raid_id)
        return None
    if result.notices:
        law_notify.publish(result.notices)
    return result


def cargo_followups(factory: SessionFactory, now: Optional[datetime] = None) -> int:
    """Pass fallback: attacks with a final row whose cargo is not settled yet (lost callbacks, crashes, rows closed
    by ``abandon``). Returns the attacks settled now."""
    now = now or now_utc()
    final = ", ".join(f":f{i}" for i in range(len(sea_core.RAID_FINAL_STATUSES)))
    db = factory()
    try:
        keys = [r[0] for r in db.execute(text(
            f"SELECT attack_key FROM sea_raids WHERE cargo_settled_at IS NULL AND status IN ({final}) "
            f"GROUP BY attack_key ORDER BY MIN(id) LIMIT :n"),
            {**{f"f{i}": st for i, st in enumerate(sea_core.RAID_FINAL_STATUSES)}, "n": BATCH_SIZE}).fetchall()]
    except DBAPIError:
        db.rollback()
        logger.warning("sea pass: unsettled cargo attacks unreadable", exc_info=True)
        return 0
    finally:
        db.close()
    return sum(1 for k in keys if apply_cargo_loss_tx(factory, k, now).status == CARGO_APPLIED)


# =====================================================================================================================
# views (deck header / captain / admin)
# =====================================================================================================================

def active_raids(db: Session, ship_id: int) -> List["models.SeaRaid"]:
    return (db.query(models.SeaRaid).filter(models.SeaRaid.ship_id == int(ship_id),
                                            models.SeaRaid.status.in_(sea_core.RAID_ACTIVE_STATUSES))
            .order_by(models.SeaRaid.id).all())


def raid_state(db: Session, ship: "models.SeaShip") -> Optional[dict]:
    """``RaidStateOut`` of the ship (§3.10): ``{monster_name, hold_until, battles: [{battle_id}]}`` of its active
    raids; None when there is none (or the 053 tables are missing)."""
    try:
        with db.begin_nested():
            rows = active_raids(db, int(ship.id))
    except DBAPIError:
        return None
    if not rows:
        return None
    return {"monster_name": rows[0].monster_name,
            "hold_until": ship.hold_until,
            "battles": [{"battle_id": int(r.battle_id)} for r in rows
                        if r.status == sea_core.RAID_FIGHTING and r.battle_id]}
