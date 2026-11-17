"""FEAT-214 §3.5 / §3.7: sea weather — storms over the sea zones and the storm damage client (sync SQLAlchemy).

* storms live in ``sea_storms`` (+ covered zones in ``sea_storm_zones``); per-sea config in ``sea_storm_seas`` keyed by
  the locations-service ``Regions.id`` of the sea; the global numbers are in ``sea_settings`` (:class:`SeaParams`);
* :func:`run_weather` — the weather step, called by the sea pass once per pass (after the claim, before the ships) in
  its own transaction: ends / moves the due storms, then rolls a new storm for every enabled sea without one
  (chance per real hour × season multiplier, the elapsed time clamped to one hour). Storm start / move / end send no
  WS notice — ships report the effects when they enter a stormy zone;
* lookups for the ship hooks and views: :func:`storm_at` (one zone), :func:`storms_for` (bulk);
* admin helpers: :func:`create_storm`, :func:`end_storm`, :func:`sea_radius`, :func:`zone_seas`;
* :func:`apply_storm_damage` — the character-attributes-service ``/internal/storm-damage`` call (HP floor 1, settle
  regen first — enforced by CAS), made **after** the ship transaction commits; failure → WARNING, no retry.

Tolerant of a missing 053 (deploy skew / old fixtures): lookups read as «no storm», the weather step logs one WARNING
and skips. Nothing here publishes notices.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Sequence

import httpx
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
import models
import sea_core
import sea_crud
from config import settings

logger = logging.getLogger("character-service.sea_weather")

WEATHER_TABLES = ("sea_storm_seas", "sea_storms", "sea_storm_zones")
DEFAULT_ELAPSED_MINUTES = 1          # first weather step ever: one minute of chance
DEFAULT_RADIUS = 1                   # a sea without a config row (admin storm)
HTTP_TIMEOUT_SECONDS = 10.0
DAMAGE_BATCH_MAX = 200               # CAS StormDamageRequest.items limit
MIN_HEALTH = 1                       # a storm never kills

_warned = {"missing": False}


def _warn_missing_once() -> None:
    if not _warned["missing"]:
        _warned["missing"] = True
        logger.warning("sea weather: the 053 storm tables are not available — storms and raids are idle")


# =====================================================================================================================
# lookups
# =====================================================================================================================

@dataclass(frozen=True)
class StormInfo:
    storm_id: int
    zone_id: int                    # the looked-up zone (covered by the storm)
    center_zone_id: int
    region_id: Optional[int]
    source: str
    ends_at: datetime


_SQL_COVER = ("SELECT z.zone_id, s.id, s.center_zone_id, s.region_id, s.source, s.ends_at "
              "FROM sea_storm_zones z JOIN sea_storms s ON s.id = z.storm_id "
              "WHERE z.zone_id IN ({ph}) AND s.status = :active")  # ends_at > now is checked in Python (dialect-safe)


def _as_dt(value) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def storms_for(db: Session, zone_ids: Iterable[Optional[int]], now: datetime) -> Dict[int, StormInfo]:
    """``{zone_id: StormInfo}`` of the active storms over the zones (the one ending last wins when an admin storm
    overlaps another). Missing tables → ``{}``."""
    ids = sorted({int(z) for z in zone_ids if z})
    if not ids:
        return {}
    ph, params = core.in_params("z", ids)
    params["active"] = sea_core.STORM_ACTIVE
    rows = sea_crud._rows(db, _SQL_COVER.format(ph=ph), params)
    out: Dict[int, StormInfo] = {}
    for r in rows or ():
        ends_at = _as_dt(r[5])
        if ends_at is None or ends_at <= now:
            continue
        info = StormInfo(int(r[1]), int(r[0]), int(r[2]), int(r[3]) if r[3] is not None else None, str(r[4]), ends_at)
        prev = out.get(info.zone_id)
        if prev is None or (info.ends_at, info.storm_id) > (prev.ends_at, prev.storm_id):
            out[info.zone_id] = info
    return out


def storm_at(db: Session, zone_id: Optional[int], now: datetime) -> Optional[StormInfo]:
    """The active storm over ``zone_id`` (None = calm, unknown zone or missing tables)."""
    if not zone_id:
        return None
    return storms_for(db, [zone_id], now).get(int(zone_id))


def zone_seas(db: Session, zone_ids: Iterable[int]) -> Dict[int, Optional[int]]:
    """``{zone_id: region_id}`` — the sea (LS region) of every zone; None when the zone has no region."""
    return {int(z): econ_ledger.resolve_location(db, int(z))[0] for z in sorted({int(z) for z in zone_ids})}


def sea_radius(db: Session, region_id: Optional[int]) -> int:
    """The storm radius of a sea (no config row / no sea → :data:`DEFAULT_RADIUS`)."""
    if not region_id:
        return DEFAULT_RADIUS
    row = db.get(models.SeaStormSea, int(region_id))
    if row is None:
        return DEFAULT_RADIUS
    return sea_core.clamp(int(row.radius or 0), sea_core.STORM_RADIUS_RANGE)


def current_season(db: Session, now: datetime) -> Optional[str]:
    """One of :data:`sea_core.SEASONS` (festival folded into its season); None when the calendar is missing."""
    import economy_mint_crud  # late: heavy economy module
    period = economy_mint_crud.current_period(db, now)
    return period.season if period is not None else None


# =====================================================================================================================
# storm rows
# =====================================================================================================================

def _duration_minutes(params: sea_crud.SeaParams, rng) -> int:
    lo = sea_core.clamp(params.storm_min_minutes, sea_core.STORM_MINUTES_RANGE)
    hi = max(lo, sea_core.clamp(params.storm_max_minutes, sea_core.STORM_MINUTES_RANGE))
    return rng.randint(lo, hi)


def _set_zones(db: Session, storm_id: int, zones: Sequence[int]) -> None:
    db.query(models.SeaStormZone).filter(models.SeaStormZone.storm_id == int(storm_id)).delete(
        synchronize_session=False)
    for z in sorted({int(z) for z in zones}):
        db.add(models.SeaStormZone(storm_id=int(storm_id), zone_id=z))
    db.flush()


def create_storm(db: Session, *, region_id: Optional[int], center_zone_id: int, zones: Sequence[int],
                 minutes: int, now: datetime, source: str = sea_core.STORM_AUTO) -> "models.SeaStorm":
    """Insert an active storm covering ``zones`` (the centre is always covered) for ``minutes``. Flushes, no commit."""
    storm = models.SeaStorm(region_id=int(region_id) if region_id else None, center_zone_id=int(center_zone_id),
                            status=sea_core.STORM_ACTIVE, source=source, moves=0, started_at=now,
                            ends_at=now + timedelta(minutes=max(1, int(minutes))))
    db.add(storm)
    db.flush()
    _set_zones(db, int(storm.id), list(zones) + [int(center_zone_id)])
    return storm


def end_storm(db: Session, storm: "models.SeaStorm", now: datetime) -> None:
    """Mark the storm ended (zones are kept as history; lookups require ``status='active'``). No commit."""
    storm.status = sea_core.STORM_ENDED
    storm.ended_at = now
    db.flush()


def _sea_adj(adj: Dict[int, List[int]], zone_sea: Dict[int, Optional[int]], region_id) -> Dict[int, List[int]]:
    """Adjacency restricted to the zones of one sea."""
    return {z: [n for n in adj.get(z, ()) if n in zone_sea and zone_sea.get(n) == region_id]
            for z, sea in zone_sea.items() if sea == region_id}


# =====================================================================================================================
# the weather step (§3.5)
# =====================================================================================================================

def _move_or_end(db: Session, storm: "models.SeaStorm", now: datetime, params: sea_crud.SeaParams, rng,
                 adj: Dict[int, List[int]], zone_sea: Dict[int, Optional[int]]) -> str:
    """'moved' | 'ended' (a season change never affects a running storm)."""
    region_id = int(storm.region_id) if storm.region_id is not None else None
    max_moves = sea_core.clamp(params.storm_max_moves, sea_core.STORM_MAX_MOVES_RANGE)
    if int(storm.moves or 0) < max_moves and rng.random() * 100 < float(params.storm_move_pct):
        sea_adj = _sea_adj(adj, zone_sea, region_id)
        neighbours = sorted(set(sea_adj.get(int(storm.center_zone_id), ())))
        if neighbours:
            center = neighbours[rng.randrange(len(neighbours))]
            zones = sea_core.storm_zones(adj, zone_sea, center, sea_radius(db, region_id))
            storm.center_zone_id = center
            storm.moves = int(storm.moves or 0) + 1
            storm.ends_at = now + timedelta(minutes=_duration_minutes(params, rng))
            _set_zones(db, int(storm.id), zones)
            return "moved"
    end_storm(db, storm, now)
    return "ended"


_available_cache = {"ok": False}


def weather_available(db: Session) -> bool:
    """The 053 storm tables exist (a positive answer is cached for the process); missing → one WARNING."""
    if _available_cache["ok"]:
        return True
    try:
        names = set(sa_inspect(db.get_bind()).get_table_names())
    except Exception:  # noqa: BLE001 — an inspector failure means «not available»
        logger.exception("sea weather: tables check failed")
        return False
    if all(t in names for t in WEATHER_TABLES + ("sea_raids",)):
        _available_cache["ok"] = True
        return True
    _warn_missing_once()
    return False


def run_weather(db: Session, now: datetime, params: Optional[sea_crud.SeaParams] = None) -> Optional[Dict[str, int]]:
    """One weather step (commits). ``{"ended", "moved", "spawned"}`` or None when the 053 tables are missing / the
    step failed (logged; the ships are processed anyway)."""
    if not weather_available(db):
        return None
    try:
        params = params or sea_crud.load_params(db)
        stats = _run_weather(db, now, params)
        db.commit()
        return stats
    except Exception:  # noqa: BLE001 — the weather must never stop the ships
        db.rollback()
        logger.exception("sea weather: step failed")
        return None


def _run_weather(db: Session, now: datetime, params: sea_crud.SeaParams) -> Dict[str, int]:
    rng = sea_core.weather_rng()
    stats = {"ended": 0, "moved": 0, "spawned": 0}
    graph = sea_crud.zone_graph(db)
    zone_sea = zone_seas(db, graph.zone_ids)

    # 1. end / move the due storms
    due = sea_crud._locked(db.query(models.SeaStorm).filter(
        models.SeaStorm.status == sea_core.STORM_ACTIVE, models.SeaStorm.ends_at <= now)
        .order_by(models.SeaStorm.id), db).all()
    for storm in due:
        stats[_move_or_end(db, storm, now, params, rng, graph.adj, zone_sea)] += 1

    # 2. spawn — at most one active storm per sea
    setting = sea_crud._locked(db.query(models.SeaSetting).filter(models.SeaSetting.id == 1), db).first()
    last = setting.weather_last_run_at if setting is not None else None
    elapsed = DEFAULT_ELAPSED_MINUTES if last is None else max(0.0, (now - last).total_seconds() / 60.0)
    season = current_season(db, now)
    mult = sea_core.season_mult(season, params)
    busy = {int(r[0]) for r in db.execute(text(
        "SELECT DISTINCT region_id FROM sea_storms WHERE status = :a AND region_id IS NOT NULL"),
        {"a": sea_core.STORM_ACTIVE}).fetchall()}
    seas = (db.query(models.SeaStormSea)
            .filter(models.SeaStormSea.is_enabled == True)  # noqa: E712
            .order_by(models.SeaStormSea.region_id).all())
    for sea in seas:
        region_id = int(sea.region_id)
        if region_id in busy:
            continue
        zones = sorted(z for z, r in zone_sea.items() if r == region_id)
        if not zones:
            continue
        chance = sea_core.pass_chance(sea.chance_per_hour_pct, mult, elapsed)
        if chance <= 0 or rng.random() >= float(chance):
            continue
        center = zones[rng.randrange(len(zones))]
        covered = sea_core.storm_zones(graph.adj, zone_sea, center,
                                       sea_core.clamp(int(sea.radius or 0), sea_core.STORM_RADIUS_RANGE))
        create_storm(db, region_id=region_id, center_zone_id=center, zones=covered,
                     minutes=_duration_minutes(params, rng), now=now, source=sea_core.STORM_AUTO)
        busy.add(region_id)
        stats["spawned"] += 1

    # 3. the elapsed-time base
    if setting is not None:
        setting.weather_last_run_at = now
    db.flush()
    return stats


def weather_step(factory: Callable[[], Session], now: datetime) -> Optional[Dict[str, int]]:
    """:func:`run_weather` in its own session (what ``sea_pass.run_pass`` calls once per pass)."""
    db = factory()
    try:
        return run_weather(db, now)
    finally:
        db.close()


# =====================================================================================================================
# storm damage (CAS, §3.7)
# =====================================================================================================================

def damage_items(character_ids: Iterable[int], health_pct, stamina_pct) -> List[dict]:
    """The CAS request items (distinct ascending ids); empty when the storm deals no damage at all."""
    hp = min(100.0, max(0.0, float(health_pct or 0)))
    st = min(100.0, max(0.0, float(stamina_pct or 0)))
    if hp <= 0 and st <= 0:
        return []
    return [{"character_id": cid, "health_pct": hp, "stamina_pct": st}
            for cid in sorted({int(c) for c in character_ids if c and int(c) >= 1})]


def _damage_url() -> str:
    return f"{settings.ATTRIBUTES_SERVICE_URL.rstrip('/')}/internal/storm-damage"


def http_post(url: str, payload: dict) -> httpx.Response:
    """THE network seam of the storm damage (tests replace it)."""
    import crud  # late: crud is heavy and imports a lot
    return httpx.post(url, json=payload, headers=crud._internal_token_headers(), timeout=HTTP_TIMEOUT_SECONDS)


def apply_storm_damage(character_ids: Iterable[int], health_pct, stamina_pct) -> Optional[List[dict]]:
    """Rock everyone in ``character_ids`` (callers exclude players in a battle). Called after the ship transaction
    commits. Returns the CAS ``applied`` rows, ``[]`` when there is nothing to do, None on failure (WARNING, no
    retry — a missed rocking is harmless)."""
    items = damage_items(character_ids, health_pct, stamina_pct)
    if not items:
        return []
    applied: List[dict] = []
    failed = False
    for i in range(0, len(items), DAMAGE_BATCH_MAX):
        batch = items[i:i + DAMAGE_BATCH_MAX]
        try:
            resp = http_post(_damage_url(), {"items": batch, "min_health": MIN_HEALTH})
        except httpx.HTTPError:
            logger.warning("sea weather: storm damage call failed for %d characters", len(batch), exc_info=True)
            failed = True
            continue
        if resp.status_code != 200:
            logger.warning("sea weather: storm damage refused (%s) for %d characters", resp.status_code, len(batch))
            failed = True
            continue
        try:
            applied.extend(resp.json().get("applied") or [])
        except ValueError:
            logger.warning("sea weather: storm damage answer is not JSON")
    return None if failed and not applied else applied
