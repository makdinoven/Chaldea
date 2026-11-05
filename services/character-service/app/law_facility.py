"""FEAT-202: where a sentenced character is held — the region guard station or the country prison (§3.3).

* station  (отделение стражи края) = ``Regions.jail_location_id``, one location (FEAT-198 column);
* country  (тюрьма страны)        = ``Countries.prison_district_id``, a district SUBTREE (nested sub-districts over
  ``Districts.parent_district_id`` + locations hanging off them through ``Locations.parent_id``).

All tables here belong to locations-service and are read by raw SQL (sync, the caller's transaction, no commits).
:func:`resolve_jail` is THE single "where / whether to jail" decision: the encounter snapshot, the choice options,
the forced move and the term all go through it. The pure choice is ``law_core.pick_facility``.

Deploy skew: before locations-service migration 057 the ``Countries.prison_district_id`` column is missing — ONLY
that error is caught (WARNING + "no country prison"); any other DB error re-raises.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import law_core as lc
import reputation_crud

logger = logging.getLogger("character-service.law_facility")

# The prison subtree, ordered (default cell first after the entrance). Valid on MySQL 8 and SQLite. Both recursive
# branches carry a depth guard (a cyclic parent_district_id / parent_id cannot loop); GROUP BY removes the duplicates
# a cycle or a double path would produce. FEAT-202: locations-service crud.prison_location_ids keeps the SAME text.
SQL_PRISON_LOCATIONS = (
    "WITH RECURSIVE dtree(id, depth) AS ("
    " SELECT id, 0 FROM Districts WHERE id = :d"
    " UNION ALL"
    " SELECT c.id, t.depth + 1 FROM Districts c JOIN dtree t ON c.parent_district_id = t.id WHERE t.depth < 10"
    "), ltree(id, depth, sort_order, hops) AS ("
    " SELECT l.id, t.depth, COALESCE(l.sort_order, 0), 0 FROM Locations l JOIN dtree t ON l.district_id = t.id"
    " UNION ALL"
    " SELECT l.id, t.depth, COALESCE(l.sort_order, 0), t.hops + 1 FROM Locations l JOIN ltree t"
    " ON l.parent_id = t.id WHERE t.hops < 10"
    ") SELECT id, MIN(depth) AS min_depth, MIN(sort_order) AS min_sort FROM ltree GROUP BY id"
    " ORDER BY min_depth, min_sort, id"
)


@dataclass(frozen=True)
class JailTarget:
    facility: str                   # law_core.FACILITY_STATION | FACILITY_COUNTRY
    location_id: int                # the station location / the default cell
    region_id: Optional[int]        # the facility's own region (station: the encounter region; country: the district's)
    country_id: Optional[int]
    district_id: Optional[int]      # country only
    name: str                       # law_core.facility_title(...)
    district_name: Optional[str]    # country only


def _missing_prison_column(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "prison_district_id" in message and ("unknown column" in message or "no such column" in message)


def station_location(db: Session, region_id: Optional[int]) -> Optional[int]:
    """``Regions.jail_location_id`` — the region guard station (FEAT-198 ``region_jail_location``)."""
    if not region_id:
        return None
    row = db.execute(text("SELECT jail_location_id FROM Regions WHERE id = :r"), {"r": int(region_id)}).first()
    return int(row[0]) if row is not None and row[0] is not None else None


def prison_location_ids(db: Session, district_id: Optional[int]) -> List[int]:
    """The ordered locations of the district subtree; [] for no / an unknown district."""
    if not district_id:
        return []
    rows = db.execute(text(SQL_PRISON_LOCATIONS), {"d": int(district_id)}).fetchall()
    return [int(r[0]) for r in rows]


def prison_district_of(db: Session, country_id: Optional[int]) -> Optional[int]:
    """``Countries.prison_district_id`` (None before locations migration 057, with a WARNING)."""
    if not country_id:
        return None
    try:
        with db.begin_nested():
            row = db.execute(text("SELECT prison_district_id FROM Countries WHERE id = :c"),
                             {"c": int(country_id)}).first()
    except DBAPIError as exc:
        if not _missing_prison_column(exc):
            raise
        logger.warning("Countries.prison_district_id is missing (locations migration 057 not applied?) "
                       "— no country prison")
        return None
    return int(row[0]) if row is not None and row[0] is not None else None


def country_name(db: Session, country_id: Optional[int]) -> Optional[str]:
    if not country_id:
        return None
    row = db.execute(text("SELECT name FROM Countries WHERE id = :c"), {"c": int(country_id)}).first()
    return row[0] if row is not None else None


def district_name(db: Session, district_id: Optional[int]) -> Optional[str]:
    if not district_id:
        return None
    row = db.execute(text("SELECT name FROM Districts WHERE id = :d"), {"d": int(district_id)}).first()
    return row[0] if row is not None else None


def country_prison(db: Session, country_id: Optional[int], *,
                   name_of_country: Optional[str] = None) -> Optional[JailTarget]:
    """The usable country prison (§3.3 P3/P4) or None: the district is assigned, still exists, its region still
    belongs to THIS country, and the subtree has a location. Cell = the district entrance if it is in the subtree,
    else the first subtree location."""
    district_id = prison_district_of(db, country_id)
    if district_id is None:
        return None
    row = db.execute(text(
        "SELECT d.name, d.region_id, d.entrance_location_id, r.country_id FROM Districts d "
        "JOIN Regions r ON r.id = d.region_id WHERE d.id = :d"), {"d": int(district_id)}).first()
    if row is None or row[3] is None or int(row[3]) != int(country_id):
        logger.info("law: prison district %s no longer belongs to country %s — no country prison",
                    district_id, country_id)
        return None
    ids = prison_location_ids(db, district_id)
    if not ids:
        return None
    entrance = int(row[2]) if row[2] is not None else None
    cell = entrance if entrance in ids else ids[0]
    name = name_of_country if name_of_country is not None else country_name(db, country_id)
    return JailTarget(facility=lc.FACILITY_COUNTRY, location_id=cell,
                      region_id=int(row[1]) if row[1] is not None else None, country_id=int(country_id),
                      district_id=int(district_id), name=lc.facility_title(lc.FACILITY_COUNTRY, name, None),
                      district_name=row[0])


def _load_settings(db: Session) -> lc.LawSettings:
    return lc.settings_from_row(db.execute(text(lc.SQL_SELECT_SETTINGS)).first())


def _load_levels(db: Session) -> List[lc.Level]:
    return lc.levels_from_rows(db.execute(text(lc.SQL_SELECT_LEVELS)).fetchall())


def resolve_jail(db: Session, region_id: Optional[int], level_code: Optional[str], *,
                 settings: Optional[lc.LawSettings] = None,
                 levels: Optional[Sequence[lc.Level]] = None) -> Optional[JailTarget]:
    """Where a character wanted at ``level_code`` in ``region_id`` is held (user decision 5); None = nowhere
    (no surrender, a forced fine)."""
    if not region_id:
        return None
    settings = settings or _load_settings(db)
    levels = levels if levels is not None else _load_levels(db)
    info = reputation_crud.region_infos(db, [region_id]).get(int(region_id))
    country_id = info.country_id if info is not None else None
    station = station_location(db, region_id)
    country = country_prison(db, country_id, name_of_country=info.country_name if info else None)
    facility = lc.pick_facility(level_code, settings.country_prison_min_level, levels,
                                station is not None, country is not None)
    if facility == lc.FACILITY_COUNTRY:
        return country
    if facility == lc.FACILITY_STATION:
        return JailTarget(facility=lc.FACILITY_STATION, location_id=int(station), region_id=int(region_id),
                          country_id=country_id, district_id=None,
                          name=lc.facility_title(lc.FACILITY_STATION, None, info.name if info else None),
                          district_name=None)
    return None
