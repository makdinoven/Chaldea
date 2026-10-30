"""Region events (FEAT-187) — DB helpers.

Tick part (B3): loaders of the events pass, expiry, the neighbour map and :func:`start_event` (shared with the admin
start). The admin part (templates CRUD, active list, manual start, cancel, history, card / regions-list / runs-list
read helpers) lives further below (B4).

Locks: these helpers only INSERT / UPDATE ``econ_region_events`` rows and read everything else plainly (lock order
3.6.1 — a region transaction locks its event rows after ``econ_regions`` / ``econ_region_goods``; the events pass and
the admin flows hold nothing else while touching event rows, so no cycle is possible). Uniqueness of ``origin_key``
(idempotent rolls of a resumed run) and ``active_key`` (one active instance per template per region) is enforced by
the DB; :func:`start_event` pre-checks both and the caller maps a remaining ``IntegrityError`` (race) to a skip / 409.
"""

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import econ_core as core
import econ_events
import models

logger = logging.getLogger("character-service.economy_events_crud")

STATUS_ACTIVE = "active"
STATUS_ENDED = "ended"
STATUS_CANCELLED = "cancelled"

TRIGGER_LOW_STABILITY = "low_stability"

# Skip reasons of a start (one per target region that got no instance).
SKIP_ALREADY_ACTIVE = "already_active"
SKIP_MAX_ACTIVE = "max_active"
SKIP_NOT_PARTICIPATING = "not_participating"
SKIP_DUPLICATE = "duplicate"               # origin_key already used (resumed run / same manual request_id)

SKIP_MESSAGES = {
    SKIP_ALREADY_ACTIVE: "В регионе уже идёт «{name}» — отмените его или дождитесь конца",
    SKIP_MAX_ACTIVE: "В регионе уже слишком много событий",
    SKIP_NOT_PARTICIPATING: "Регион не участвует в пересчёте — у него нет шаблона или населения",
    SKIP_DUPLICATE: "Событие уже запущено",
}

SQL_EVENT_REGIONS = (
    "SELECT e.region_id, e.template_code, r.country_id, e.low_stability_since, r.name FROM econ_regions e "
    "JOIN Regions r ON r.id = e.region_id "
    "WHERE e.template_code IS NOT NULL AND e.population > 0 ORDER BY e.region_id"
)

SQL_EXPIRE = (
    "UPDATE econ_region_events SET status = 'ended', ended_at = ends_at, active_key = NULL "
    "WHERE status = 'active' AND ends_at <= :now"
)


def skip_message(reason: str, event_name: str = "") -> str:
    """Russian text of a skip reason (admin start answers / skipped list)."""
    return SKIP_MESSAGES.get(reason, reason).format(name=event_name)


def _json(value: Any) -> Any:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def active_key(region_id: int, code: str) -> str:
    return f"r{int(region_id)}:{code}"


def events_available(session: Session) -> bool:
    """True when migration 033 is applied (the tick tolerates its absence)."""
    names = set(sa_inspect(session.get_bind()).get_table_names())
    return "econ_region_events" in names and "econ_event_templates" in names


# --------------------------------------------------------------------------------------------- loaders

@dataclass(frozen=True)
class EventRegion:
    """A participating region as the events pass sees it (plain read)."""

    region_id: int
    template_code: Optional[str]
    country_id: Optional[int]
    low_stability_since: Optional[datetime]
    name: Optional[str]


def load_event_regions(session: Session) -> Dict[int, EventRegion]:
    """{region_id: EventRegion} of participating regions (template set, population > 0, Regions row exists)."""
    result: Dict[int, EventRegion] = {}
    for r in session.execute(text(SQL_EVENT_REGIONS)).fetchall():
        low = r[3]
        if isinstance(low, str):  # SQLite returns text for raw DATETIME selects
            low = datetime.fromisoformat(low)
        result[int(r[0])] = EventRegion(region_id=int(r[0]), template_code=r[1],
                                        country_id=int(r[2]) if r[2] is not None else None,
                                        low_stability_since=low, name=r[4])
    return result


def load_templates(session: Session) -> List["models.EconEventTemplate"]:
    """Every template (enabled or not), ascending id — callers filter."""
    return session.query(models.EconEventTemplate).order_by(models.EconEventTemplate.id).all()


def load_active(session: Session, now: datetime, region_ids: Optional[Iterable[int]] = None
                ) -> Dict[int, List["models.EconRegionEvent"]]:
    """{region_id: [active instances, ascending id]} (status active and ``ends_at > now``)."""
    query = (session.query(models.EconRegionEvent)
             .filter(models.EconRegionEvent.status == STATUS_ACTIVE, models.EconRegionEvent.ends_at > now))
    if region_ids is not None:
        ids = sorted({int(r) for r in region_ids})
        if not ids:
            return {}
        query = query.filter(models.EconRegionEvent.region_id.in_(ids))
    result: Dict[int, List[models.EconRegionEvent]] = {}
    for row in query.order_by(models.EconRegionEvent.id).all():
        result.setdefault(int(row.region_id), []).append(row)
    return result


def last_riot_ends(session: Session) -> Dict[int, datetime]:
    """{region_id: end of its latest finished riot} (ended or cancelled ``low_stability`` instances)."""
    rows = session.execute(text(
        "SELECT region_id, MAX(COALESCE(ended_at, ends_at)) FROM econ_region_events "
        "WHERE trigger_kind = :t AND status <> 'active' GROUP BY region_id"
    ), {"t": TRIGGER_LOW_STABILITY}).fetchall()
    result: Dict[int, datetime] = {}
    for region_id, moment in rows:
        if isinstance(moment, str):
            moment = datetime.fromisoformat(moment)
        if moment is not None:
            result[int(region_id)] = moment
    return result


def neighbour_map(session: Session, regions: Mapping[int, EventRegion]) -> Dict[int, List[int]]:
    """{region_id: [participating neighbours, ascending]}.

    Neighbours = ``region_transition_arrows`` in both directions (locations-service table, read by SQL). A region
    without any arrow falls back to the other participating regions of its country (Q3).
    """
    links: Dict[int, set] = {}
    if "region_transition_arrows" in set(sa_inspect(session.get_bind()).get_table_names()):
        for a, b in session.execute(text(
                "SELECT region_id, target_region_id FROM region_transition_arrows "
                "WHERE region_id IS NOT NULL AND target_region_id IS NOT NULL")).fetchall():
            a, b = int(a), int(b)
            if a == b:
                continue
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)
    by_country: Dict[Optional[int], List[int]] = {}
    for rid, info in regions.items():
        by_country.setdefault(info.country_id, []).append(rid)
    result: Dict[int, List[int]] = {}
    for rid, info in regions.items():
        if rid in links:
            result[rid] = sorted(n for n in links[rid] if n in regions)
        elif info.country_id is not None:
            result[rid] = sorted(n for n in by_country.get(info.country_id, []) if n != rid)
        else:
            result[rid] = []
    return result


def expire_events(session: Session, now: datetime, region_ids: Optional[Iterable[int]] = None) -> int:
    """End every active instance whose time is up (``ended_at = ends_at``). The caller commits."""
    sql, params = SQL_EXPIRE, {"now": now}
    if region_ids is not None:
        ids = sorted({int(r) for r in region_ids})
        if not ids:
            return 0
        placeholders, id_params = core.in_params("r", ids)
        sql += f" AND region_id IN ({placeholders})"
        params.update(id_params)
    return int(session.execute(text(sql), params).rowcount or 0)


# --------------------------------------------------------------------------------------------- start

@dataclass(frozen=True)
class EventSnapshot:
    """What an instance copies at start (from a template, or from a source instance when spreading)."""

    template_id: Optional[int]
    code: str
    name: str
    icon: str
    kind: str
    player_text: str
    trigger_kind: str
    effects: Any
    chains: Any
    spread_chance: float
    scope: str = "region"
    duration_min_days: float = 1.0
    duration_max_days: float = 1.0


def snapshot_of_template(t: Any) -> EventSnapshot:
    return EventSnapshot(
        template_id=int(_get(t, "id")) if _get(t, "id") is not None else None,
        code=str(_get(t, "code")), name=str(_get(t, "name")), icon=str(_get(t, "icon") or "alert"),
        kind=str(_get(t, "kind")), player_text=str(_get(t, "player_text") or ""),
        trigger_kind=str(_get(t, "trigger_kind") or "random"),
        effects=_json(_get(t, "effects")) or [], chains=_json(_get(t, "chains")),
        spread_chance=float(_get(t, "spread_chance") or 0), scope=str(_get(t, "scope") or "region"),
        duration_min_days=float(_get(t, "duration_min_days") or 1),
        duration_max_days=float(_get(t, "duration_max_days") or 1),
    )


def snapshot_of_instance(row: "models.EconRegionEvent") -> EventSnapshot:
    """A running instance's own snapshot (spreading keeps the source's name / effects, Q5)."""
    seconds = max(60.0, (row.ends_at - row.started_at).total_seconds())
    days = seconds / econ_events.DAY
    return EventSnapshot(
        template_id=row.template_id, code=row.template_code, name=row.name, icon=row.icon, kind=row.kind,
        player_text=row.player_text, trigger_kind=row.trigger_kind, effects=_json(row.effects) or [],
        chains=_json(row.chains), spread_chance=float(row.spread_chance or 0), scope="region",
        duration_min_days=days, duration_max_days=days,
    )


@dataclass
class StartResult:
    started: List["models.EconRegionEvent"] = field(default_factory=list)
    skipped: List[tuple] = field(default_factory=list)     # (region_id, region_name, reason)

    @property
    def root(self) -> Optional["models.EconRegionEvent"]:
        return self.started[0] if self.started else None


def scope_targets(region_id: int, scope: str, regions: Mapping[int, EventRegion],
                  neighbours: Optional[Mapping[int, Sequence[int]]]) -> List[int]:
    """Target regions of a start, the origin region first (only participating ones besides the origin)."""
    region_id = int(region_id)
    if scope == "neighbours":
        extra = list((neighbours or {}).get(region_id, ()))
    elif scope == "country":
        country = regions[region_id].country_id if region_id in regions else None
        extra = [] if country is None else [r for r in sorted(regions) if regions[r].country_id == country]
    elif scope == "world":
        extra = sorted(regions)
    else:
        extra = []
    targets = [region_id]
    for r in extra:
        if r != region_id and r in regions and r not in targets:
            targets.append(r)
    return targets


def _active_codes(session: Session, region_ids: Sequence[int]) -> Dict[int, List[str]]:
    placeholders, params = core.in_params("r", list(region_ids))
    result: Dict[int, List[str]] = {}
    for rid, code in session.execute(text(
            f"SELECT region_id, template_code FROM econ_region_events WHERE status = 'active' "
            f"AND region_id IN ({placeholders}) ORDER BY id"), params).fetchall():
        result.setdefault(int(rid), []).append(code)
    return result


def start_event(
    session: Session,
    source: Any,
    region_id: int,
    *,
    origin: str,
    origin_key: Optional[str],
    now: datetime,
    run_id: Optional[int] = None,
    segment: Optional[str] = None,
    parent: Any = None,
    generation: int = 0,
    scope: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    user_id: Optional[int] = None,
    rng: Optional[random.Random] = None,
    regions: Optional[Mapping[int, EventRegion]] = None,
    neighbours: Optional[Mapping[int, Sequence[int]]] = None,
    max_active: Optional[int] = None,
) -> StartResult:
    """Start one event (a template row / dict or an :class:`EventSnapshot`) in ``region_id`` and, by its scope, in
    the other target regions. Inserts only — never commits; the caller commits (or rolls back on IntegrityError).

    Every target gets its own instance with the same ``started_at`` / ``ends_at``; the first one is the root, the
    others carry ``root_event_id``. Targets that already run this event (or have ``max_active`` active events, when
    given) are skipped. ``parent`` is the source instance (row or id) of a spread / chain. ``origin_key`` (None for a manual start without request id) gets ``:r<target>`` for the
    non-root targets; an already used key skips the whole start as a duplicate.
    """
    snap = source if isinstance(source, EventSnapshot) else snapshot_of_template(source)
    parent_id = None if parent is None else int(parent if isinstance(parent, int) else parent.id)
    if regions is None:
        regions = load_event_regions(session)
    region_id = int(region_id)
    if region_id not in regions:
        return StartResult(skipped=[(region_id, None, SKIP_NOT_PARTICIPATING)])
    scope = scope or snap.scope or "region"
    if scope == "neighbours" and neighbours is None:
        neighbours = neighbour_map(session, regions)
    targets = scope_targets(region_id, scope, regions, neighbours)

    if origin_key is not None and session.execute(
            text("SELECT 1 FROM econ_region_events WHERE origin_key = :k"), {"k": origin_key}).first():
        return StartResult(skipped=[(region_id, regions[region_id].name, SKIP_DUPLICATE)])

    # Instances whose time is up but which the tick has not ended yet would still hold their active_key.
    expire_events(session, now, targets)
    active = _active_codes(session, targets)

    if duration_seconds is None:
        duration_seconds = econ_events.roll_duration_seconds(rng or random.Random(), snap.duration_min_days,
                                                             snap.duration_max_days)
    duration_seconds = max(60, int(duration_seconds))
    ends_at = now + timedelta(seconds=duration_seconds)

    result = StartResult()
    for target in targets:
        info = regions[target]
        codes = active.get(target, [])
        if snap.code in codes:
            result.skipped.append((target, info.name, SKIP_ALREADY_ACTIVE))
            continue
        if max_active is not None and len(codes) >= int(max_active):
            result.skipped.append((target, info.name, SKIP_MAX_ACTIVE))
            continue
        root = result.root
        key = origin_key
        if key is not None and root is not None:
            key = f"{origin_key}:r{target}"
        row = models.EconRegionEvent(
            region_id=target, region_name=info.name, country_id=info.country_id, template_id=snap.template_id,
            template_code=snap.code, name=snap.name, icon=snap.icon, kind=snap.kind, player_text=snap.player_text,
            trigger_kind=snap.trigger_kind, effects=snap.effects, chains=snap.chains,
            spread_chance=round(float(snap.spread_chance), 4), origin=origin,
            parent_event_id=parent_id,
            root_event_id=int(root.id) if root is not None else None, generation=int(generation),
            origin_key=key, active_key=active_key(target, snap.code), status=STATUS_ACTIVE,
            started_at=now, ends_at=ends_at, game_segment=segment, run_id=run_id, started_by_user_id=user_id,
        )
        session.add(row)
        session.flush()  # the unique keys fire here; the id is needed by the next targets
        result.started.append(row)
    return result


# ============================================================================================= admin (B4)
# Contract 3.7. Like the other economy cruds: functions never commit (the router commits after success and rolls
# back on any exception); business refusals raise ``EconomyApiError`` with a Russian message.

ERR_TEMPLATE_NOT_FOUND = "Шаблон события не найден"
ERR_EVENT_NOT_FOUND = "Событие не найдено"
ERR_EVENT_OVER = "Событие уже закончилось"
ERR_REGION_NOT_FOUND = "Регион не найден"
ERR_CODE_TAKEN = "Шаблон с кодом «{code}» уже есть"
ERR_UNKNOWN_GROUP = "Неизвестная группа товаров: {code}"
ERR_UNKNOWN_REGION_TEMPLATE = "Неизвестный шаблон региона: {code}"
ERR_UNKNOWN_CHAIN = "Цепочка ссылается на неизвестное событие: {code}"
ERR_SELF_CHAIN = "Событие не может вызывать само себя"
ERR_REFERENCED = "На это событие ссылаются цепочки: {names}"
ERR_DATES = "Дата начала периода позже даты конца"

# Fields of a template the admin edits (everything but code / id / audit columns).
TEMPLATE_FIELDS = ("name", "icon", "kind", "player_text", "admin_note", "trigger_kind", "weight", "duration_min_days",
                   "duration_max_days", "scope", "spread_chance", "region_templates", "seasons", "effects", "chains",
                   "is_enabled")


def utcnow() -> datetime:
    """Naive UTC without microseconds (the DATETIME columns are naive UTC)."""
    return datetime.utcnow().replace(microsecond=0)


def _api_error(status_code: int, detail: str) -> Exception:
    from economy_crud import EconomyApiError  # late: keeps this module importable by the tick alone
    return EconomyApiError(status_code, detail)


def _num(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _list(value: Any) -> list:
    value = _json(value)
    return list(value) if isinstance(value, (list, tuple)) else []


def _active_counts(session: Session, now: datetime) -> Dict[int, int]:
    rows = session.execute(text(
        "SELECT template_id, COUNT(*) FROM econ_region_events WHERE status = 'active' AND ends_at > :now "
        "AND template_id IS NOT NULL GROUP BY template_id"), {"now": now}).fetchall()
    return {int(t): int(n) for t, n in rows}


def template_dict(row: "models.EconEventTemplate", active_count: int = 0) -> dict:
    return {
        "id": int(row.id), "code": row.code, "name": row.name, "icon": row.icon, "kind": row.kind,
        "player_text": row.player_text, "admin_note": row.admin_note, "trigger_kind": row.trigger_kind,
        "weight": _num(row.weight), "duration_min_days": _num(row.duration_min_days),
        "duration_max_days": _num(row.duration_max_days), "scope": row.scope,
        "spread_chance": _num(row.spread_chance), "region_templates": _list(row.region_templates),
        "seasons": _list(row.seasons), "effects": [e for e in _list(row.effects) if isinstance(e, dict)],
        "chains": [c for c in _list(row.chains) if isinstance(c, dict)], "is_enabled": bool(row.is_enabled),
        "active_count": int(active_count), "updated_at": row.updated_at,
    }


def event_dict(row: "models.EconRegionEvent") -> dict:
    outcome = _json(row.outcome)
    return {
        "id": int(row.id), "region_id": int(row.region_id), "region_name": row.region_name,
        "country_id": int(row.country_id) if row.country_id is not None else None,
        "template_id": int(row.template_id) if row.template_id is not None else None,
        "template_code": row.template_code, "name": row.name, "icon": row.icon, "kind": row.kind,
        "player_text": row.player_text, "trigger_kind": row.trigger_kind,
        "effects": [e for e in _list(row.effects) if isinstance(e, dict)], "origin": row.origin,
        "parent_event_id": int(row.parent_event_id) if row.parent_event_id is not None else None,
        "root_event_id": int(row.root_event_id) if row.root_event_id is not None else None,
        "generation": int(row.generation or 0), "status": row.status, "started_at": row.started_at,
        "ends_at": row.ends_at, "ended_at": row.ended_at, "game_segment": row.game_segment,
        "started_by_user_id": row.started_by_user_id, "cancelled_by_user_id": row.cancelled_by_user_id,
        "cancel_comment": row.cancel_comment, "applied_at": row.applied_at,
        "population_before": row.population_before, "population_after": row.population_after,
        "outcome": outcome if isinstance(outcome, dict) else None,
    }


def list_event_templates(session: Session, now: Optional[datetime] = None) -> List[dict]:
    """Every template ordered by kind (bad first), name; each with its running instances count."""
    counts = _active_counts(session, now or utcnow())
    rows = (session.query(models.EconEventTemplate)
            .order_by(models.EconEventTemplate.kind, models.EconEventTemplate.name, models.EconEventTemplate.id)
            .all())
    return [template_dict(row, counts.get(int(row.id), 0)) for row in rows]


def _check_references(session: Session, body: Any, own_code: str) -> None:
    """Group / region-template / chain codes must exist (400 with the first unknown code)."""
    groups = {r[0] for r in session.execute(text("SELECT code FROM econ_goods_groups")).fetchall()}
    for effect in body.effects:
        for code in effect.groups or ():
            if code != econ_events.ALL_GROUPS and code not in groups:
                raise _api_error(400, ERR_UNKNOWN_GROUP.format(code=code))
    if body.region_templates:
        known = {r[0] for r in session.execute(text("SELECT code FROM econ_region_templates")).fetchall()}
        for code in body.region_templates:
            if code not in known:
                raise _api_error(400, ERR_UNKNOWN_REGION_TEMPLATE.format(code=code))
    if body.chains:
        known = {r[0] for r in session.execute(text("SELECT code FROM econ_event_templates")).fetchall()}
        for chain in body.chains:
            if chain.code == own_code:
                raise _api_error(400, ERR_SELF_CHAIN)
            if chain.code not in known:
                raise _api_error(400, ERR_UNKNOWN_CHAIN.format(code=chain.code))


def _apply_body(row: "models.EconEventTemplate", body: Any, user_id: Optional[int]) -> None:
    for name in TEMPLATE_FIELDS:
        value = getattr(body, name)
        if name == "effects":
            value = [effect.stored() for effect in value]
        elif name == "chains":
            value = [{"code": c.code, "chance": float(c.chance)} for c in value]
        elif name in ("weight", "duration_min_days", "duration_max_days"):
            value = round(float(value), 2)
        elif name == "spread_chance":
            value = round(float(value), 4)
        setattr(row, name, value)
    row.updated_by_user_id = user_id


def _flush_template(session: Session, code: str) -> None:
    try:
        session.flush()
    except IntegrityError:
        raise _api_error(409, ERR_CODE_TAKEN.format(code=code))


def create_template(session: Session, body: Any, user_id: Optional[int]) -> dict:
    if session.query(models.EconEventTemplate.id).filter(models.EconEventTemplate.code == body.code).first():
        raise _api_error(409, ERR_CODE_TAKEN.format(code=body.code))
    _check_references(session, body, body.code)
    row = models.EconEventTemplate(code=body.code)
    _apply_body(row, body, user_id)
    session.add(row)
    _flush_template(session, body.code)
    session.refresh(row)
    return template_dict(row, 0)


def _template_or_404(session: Session, template_id: int) -> "models.EconEventTemplate":
    row = session.get(models.EconEventTemplate, int(template_id)) if template_id > 0 else None
    if row is None:
        raise _api_error(404, ERR_TEMPLATE_NOT_FOUND)
    return row


def update_template(session: Session, template_id: int, body: Any, user_id: Optional[int]) -> dict:
    """Edits apply to new starts only: running instances keep their snapshot (Q5)."""
    row = _template_or_404(session, template_id)
    _check_references(session, body, row.code)
    _apply_body(row, body, user_id)
    _flush_template(session, row.code)
    session.refresh(row)
    return template_dict(row, _active_counts(session, utcnow()).get(int(row.id), 0))


def delete_template(session: Session, template_id: int) -> str:
    """Delete a template unless other templates' chains refer to it; instances keep their snapshot (SET NULL)."""
    row = _template_or_404(session, template_id)
    referring = []
    for other in session.query(models.EconEventTemplate).order_by(models.EconEventTemplate.id).all():
        if int(other.id) == int(row.id):
            continue
        if any(isinstance(c, dict) and c.get("code") == row.code for c in _list(other.chains)):
            referring.append(f"«{other.name}»")
    if referring:
        raise _api_error(409, ERR_REFERENCED.format(names=", ".join(referring)))
    # Explicit (portable) SET NULL: SQLite does not enforce the FK action.
    session.execute(text("UPDATE econ_region_events SET template_id = NULL WHERE template_id = :t"),
                    {"t": int(row.id)})
    code = row.code
    session.delete(row)
    session.flush()
    return code


def list_active_events(session: Session, region_id: Optional[int] = None, now: Optional[datetime] = None
                       ) -> List[dict]:
    """Running instances (status active, ``ends_at > now``), the soonest to end first."""
    query = (session.query(models.EconRegionEvent)
             .filter(models.EconRegionEvent.status == STATUS_ACTIVE,
                     models.EconRegionEvent.ends_at > (now or utcnow())))
    if region_id is not None:
        query = query.filter(models.EconRegionEvent.region_id == int(region_id))
    rows = query.order_by(models.EconRegionEvent.ends_at, models.EconRegionEvent.id).all()
    return [event_dict(row) for row in rows]


def _region_exists(session: Session, region_id: int) -> bool:
    return session.execute(text("SELECT 1 FROM Regions WHERE id = :r"), {"r": int(region_id)}).first() is not None


def manual_origin_key(request_id: Optional[str], region_id: int) -> Optional[str]:
    return f"manual:{request_id}:r{int(region_id)}" if request_id else None


def start_manual(session: Session, body: Any, *, user_id: Optional[int], segment: Optional[str],
                 now: Optional[datetime] = None) -> dict:
    """Admin start (3.7): any template (disabled too, any trigger), ``event_max_active`` ignored, one-shots at the
    next recount. Started instances + skipped regions with Russian reasons; nothing started -> 409 (first reason)."""
    template = _template_or_404(session, body.template_id)
    if not _region_exists(session, body.region_id):
        raise _api_error(404, ERR_REGION_NOT_FOUND)
    regions = load_event_regions(session)
    if int(body.region_id) not in regions:
        raise _api_error(409, skip_message(SKIP_NOT_PARTICIPATING))
    duration = None if body.duration_days is None else int(round(float(body.duration_days) * econ_events.DAY))
    key = manual_origin_key(body.request_id, body.region_id)
    try:
        result = start_event(session, template, body.region_id, origin="manual", origin_key=key,
                             now=now or utcnow(), segment=segment, scope=body.scope, duration_seconds=duration,
                             user_id=user_id, regions=regions)
    except IntegrityError:
        # A concurrent start (tick or another admin) took the same active_key / origin_key first.
        session.rollback()
        duplicate = key is not None and session.execute(
            text("SELECT 1 FROM econ_region_events WHERE origin_key = :k"), {"k": key}).first() is not None
        raise _api_error(409, skip_message(SKIP_DUPLICATE if duplicate else SKIP_ALREADY_ACTIVE, template.name))
    skipped = [{"region_id": int(rid), "region_name": name, "reason": skip_message(reason, template.name)}
               for rid, name, reason in result.skipped]
    if not result.started:
        raise _api_error(409, skipped[0]["reason"] if skipped else skip_message(SKIP_NOT_PARTICIPATING))
    return {"started": [event_dict(row) for row in result.started], "skipped": skipped}


def cancel_event(session: Session, event_id: int, *, comment: str, user_id: Optional[int],
                 now: Optional[datetime] = None) -> dict:
    """Stop an active instance: ongoing effects end now; one-shot results are not rolled back (Q1)."""
    now = now or utcnow()
    query = session.query(models.EconRegionEvent).filter(models.EconRegionEvent.id == int(event_id))
    if session.get_bind().dialect.name != "sqlite":
        query = query.with_for_update()
    row = query.first() if event_id > 0 else None
    if row is None:
        raise _api_error(404, ERR_EVENT_NOT_FOUND)
    if row.status != STATUS_ACTIVE or row.ends_at <= now:
        raise _api_error(409, ERR_EVENT_OVER)
    row.status = STATUS_CANCELLED
    row.ended_at = now
    row.active_key = None
    row.cancelled_by_user_id = user_id
    row.cancel_comment = comment
    session.flush()
    return event_dict(row)


def history_page(session: Session, *, region_id: Optional[int] = None, template_code: Optional[str] = None,
                 kind: Optional[str] = None, status: Optional[str] = None, origin: Optional[str] = None,
                 date_from: Optional[date] = None, date_to: Optional[date] = None, page: int = 1,
                 page_size: int = 50) -> dict:
    """Every instance ever started (newest first) — the same rows the future newspaper reads."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise _api_error(400, ERR_DATES)
    E = models.EconRegionEvent
    query = session.query(E)
    if region_id is not None:
        query = query.filter(E.region_id == int(region_id))
    if template_code is not None:
        query = query.filter(E.template_code == template_code)
    if kind is not None:
        query = query.filter(E.kind == kind)
    if status is not None:
        query = query.filter(E.status == status)
    if origin is not None:
        query = query.filter(E.origin == origin)
    if date_from is not None:
        query = query.filter(E.started_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        query = query.filter(E.started_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    total = query.count()
    rows = (query.order_by(E.started_at.desc(), E.id.desc())
            .offset((int(page) - 1) * int(page_size)).limit(int(page_size)).all())
    return {"items": [event_dict(row) for row in rows], "total": int(total), "page": int(page),
            "page_size": int(page_size)}


# --------------------------------------------------------------------------------------------- read helpers

def card_events(session: Session, region_id: int, now: Optional[datetime] = None) -> List[dict]:
    """Active events of a region as players see them (no effect numbers). [] when the tables are missing."""
    try:
        rows = load_active(session, now or utcnow(), [region_id]).get(int(region_id), [])
    except SQLAlchemyError:
        session.rollback()
        logger.warning("region card: region events unavailable")
        return []
    rows = sorted(rows, key=lambda r: (r.ends_at, r.id))
    return [{"code": r.template_code, "name": r.name, "icon": r.icon, "kind": r.kind, "text": r.player_text,
             "started_at": r.started_at, "ends_at": r.ends_at} for r in rows]


def badges_by_region(session: Session, now: Optional[datetime] = None) -> Dict[int, List[dict]]:
    """{region_id: [EventBadge]} of every running instance ({} when the tables are missing)."""
    try:
        rows = session.execute(text(
            "SELECT region_id, name, icon, kind FROM econ_region_events WHERE status = 'active' AND ends_at > :now "
            "ORDER BY region_id, id"), {"now": now or utcnow()}).fetchall()
    except SQLAlchemyError:
        session.rollback()
        logger.warning("regions list: region events unavailable")
        return {}
    result: Dict[int, List[dict]] = {}
    for region_id, name, icon, kind in rows:
        result.setdefault(int(region_id), []).append({"name": name, "icon": icon, "kind": kind})
    return result


RUN_COUNTER_KEYS = ("events_ended", "events_started", "events_spread", "events_chained", "riots_started",
                    "events_applied", "event_expense_ops", "events_failed")
_ORIGIN_COUNTER = {"random": "events_started", "spread": "events_spread", "chain": "events_chained",
                   "riot": "riots_started"}


def run_counters(session: Session, runs: Sequence["models.EconTickRun"], events_error_prefix: str
                 ) -> Dict[int, dict]:
    """Events counters of past runs for the runs list (``econ_tick_runs`` has no such columns): derived from the
    instances (``run_id`` = rolled by the run, ``applied_run_id`` = one-shots applied by it, outcome operation =
    expense posted), ``events_ended`` = instances whose end falls between the previous run's start and this run's
    start (approximate: an admin start also ends overdue instances), ``events_failed`` = parts of the run's events
    error text. Missing tables -> zeros."""
    runs = list({int(r.id): r for r in runs}.values())       # the running run may also be in the list
    result = {int(r.id): {k: 0 for k in RUN_COUNTER_KEYS} for r in runs}
    for run in runs:
        error = run.error or ""
        if events_error_prefix in error:
            tail = error.split(events_error_prefix, 1)[1].split(";", 1)[0]
            result[int(run.id)]["events_failed"] = len([p for p in tail.split(",") if p.strip()])
    if not runs:
        return result
    ids = sorted(result)
    try:
        placeholders, params = core.in_params("u", ids)
        for run_id, origin, n in session.execute(text(
                f"SELECT run_id, origin, COUNT(*) FROM econ_region_events WHERE run_id IN ({placeholders}) "
                f"GROUP BY run_id, origin"), params).fetchall():
            key = _ORIGIN_COUNTER.get(origin)
            if key is not None and int(run_id) in result:
                result[int(run_id)][key] += int(n)
        for run_id, outcome in session.execute(text(
                f"SELECT applied_run_id, outcome FROM econ_region_events WHERE applied_run_id IN ({placeholders})"),
                params).fetchall():
            counters = result.get(int(run_id))
            if counters is None:
                continue
            counters["events_applied"] += 1
            outcome = _json(outcome)
            if isinstance(outcome, dict) and outcome.get("operation_id"):
                counters["event_expense_ops"] += 1
        ordered = sorted(runs, key=lambda r: (r.started_at, r.id))
        previous = session.execute(text("SELECT MAX(started_at) FROM econ_tick_runs WHERE started_at < :t"),
                                   {"t": ordered[0].started_at}).scalar()
        for run in ordered:
            if isinstance(previous, str):
                previous = datetime.fromisoformat(previous)
            sql = "SELECT COUNT(*) FROM econ_region_events WHERE status = 'ended' AND ended_at <= :cur"
            values: Dict[str, Any] = {"cur": run.started_at}
            if previous is not None:
                sql += " AND ended_at > :prev"
                values["prev"] = previous
            result[int(run.id)]["events_ended"] = int(session.execute(text(sql), values).scalar() or 0)
            previous = run.started_at
    except SQLAlchemyError:
        session.rollback()
        logger.warning("runs list: region events counters unavailable")
    return result
