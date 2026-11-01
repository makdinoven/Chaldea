"""FEAT-191: pure math of the mint and the season quota (no DB, no I/O).

* Game «season» period (section 3.3): a season together with the festival after it — 49 real days, 4 per game year.
  The calendar layout mirrors ``locations-service/app/crud.py`` ``YEAR_SEGMENTS`` / ``compute_game_time`` and the
  frontend ``src/utils/gameTime.ts``; keep the three in sync.
* Court mint amount (3.6): marks from the capital's ``ore_metal`` surplus above a threshold of its norm.
* Season quota split (3.7): largest-remainder split by population, the legs sum to the amount exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Dict, List, Mapping, Optional, Tuple

# --------------------------------------------------------------------------------------------- calendar mirror

# Copy of locations-service/app/crud.py YEAR_SEGMENTS (and frontend src/utils/gameTime.ts). Order matters.
YEAR_SEGMENTS: Tuple[Tuple[str, str, int], ...] = (
    ("spring", "season", 39),
    ("beltane", "transition", 10),
    ("summer", "season", 39),
    ("lughnasad", "transition", 10),
    ("autumn", "season", 39),
    ("samhain", "transition", 10),
    ("winter", "season", 39),
    ("imbolc", "transition", 10),
)
DAYS_PER_YEAR = sum(days for _, _, days in YEAR_SEGMENTS)

# One period = a season + the festival after it.
SEASONS: Tuple[str, ...] = tuple(name for name, kind, _ in YEAR_SEGMENTS if kind == "season")
PERIODS_PER_YEAR = len(SEASONS)
PERIOD_DAYS = YEAR_SEGMENTS[0][2] + YEAR_SEGMENTS[1][2]

assert all(YEAR_SEGMENTS[i][1] == "season" and YEAR_SEGMENTS[i + 1][1] == "transition"
           for i in range(0, len(YEAR_SEGMENTS), 2)), "calendar must alternate season / festival"
assert all(YEAR_SEGMENTS[i][2] + YEAR_SEGMENTS[i + 1][2] == PERIOD_DAYS
           for i in range(0, len(YEAR_SEGMENTS), 2)), "every season + festival pair must be equally long"
assert PERIODS_PER_YEAR * PERIOD_DAYS == DAYS_PER_YEAR == 196

SECONDS_PER_DAY = 86400


@dataclass(frozen=True)
class SeasonPeriod:
    """One game season period. ``index`` is absolute and monotonic across years (keys use it)."""

    index: int
    year: int
    season: str
    starts_at: datetime     # naive UTC
    ends_at: datetime       # naive UTC, exclusive

    def to_dict(self) -> dict:
        return {"index": self.index, "year": self.year, "season": self.season,
                "starts_at": self.starts_at, "ends_at": self.ends_at}


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        from datetime import timezone
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def elapsed_days(epoch: datetime, offset_days: int, now: datetime) -> int:
    """Same formula as locations-service ``compute_game_time`` (clamped at 0)."""
    seconds = (_naive_utc(now) - _naive_utc(epoch)).total_seconds()
    return max(0, math.floor(seconds / SECONDS_PER_DAY) + int(offset_days or 0))


def period_of(epoch: datetime, offset_days: int, now: datetime) -> SeasonPeriod:
    """The season period containing ``now``."""
    epoch = _naive_utc(epoch)
    offset = int(offset_days or 0)
    index = elapsed_days(epoch, offset, now) // PERIOD_DAYS
    starts_at = epoch + timedelta(days=index * PERIOD_DAYS - offset)
    return SeasonPeriod(
        index=index,
        year=index // PERIODS_PER_YEAR + 1,
        season=SEASONS[index % PERIODS_PER_YEAR],
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=PERIOD_DAYS),
    )


# --------------------------------------------------------------------------------------------- court mint

_MILLI = Decimal("0.001")


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class CourtMint:
    marks: int
    units: Decimal          # region units of ore_metal taken (3 decimals, never more than the excess)
    excess: Decimal


def court_mint(stock, norm, threshold_pct, marks_per_unit, remaining) -> CourtMint:
    """How much the court mints from the capital's ore stock in one tick (3.6).

    ``excess = max(0, stock - norm * threshold_pct / 100)``; ``marks = min(floor(excess * rate), remaining)``;
    ``units = min(excess, ceil_3(marks / rate))``. Nothing when the rate, the excess or the remaining limit is 0.
    """
    stock_d, norm_d = _dec(stock), _dec(norm)
    rate = _dec(marks_per_unit)
    remaining = max(0, int(remaining))
    threshold = norm_d * _dec(threshold_pct) / Decimal(100)
    excess = max(Decimal(0), stock_d - threshold).quantize(_MILLI, rounding=ROUND_FLOOR)
    if rate <= 0 or excess <= 0 or remaining <= 0:
        return CourtMint(0, Decimal("0.000"), excess)
    marks = min(int((excess * rate).to_integral_value(rounding=ROUND_FLOOR)), remaining)
    if marks <= 0:
        return CourtMint(0, Decimal("0.000"), excess)
    units = min(excess, (Decimal(marks) / rate).quantize(_MILLI, rounding=ROUND_CEILING))
    return CourtMint(marks, units, excess)


def remaining_limit(limit: int, minted_court: int, minted_players: int) -> int:
    return max(0, int(limit) - int(minted_court) - int(minted_players))


# --------------------------------------------------------------------------------------------- quota

def split_quota(amount: int, populations: Mapping[int, int]) -> Dict[int, int]:
    """Largest-remainder split of ``amount`` by population; legs sum to ``amount`` exactly (3.7).

    Floors first, then the leftover marks go one each to the largest fractional parts (ties -> lower region id).
    Regions with population <= 0 and zero-amount shares are dropped. Empty when nothing can be split.
    """
    amount = int(amount)
    pops = {int(rid): int(pop) for rid, pop in populations.items() if int(pop) > 0}
    total = sum(pops.values())
    if amount <= 0 or total <= 0:
        return {}
    shares: Dict[int, int] = {}
    remainders: List[Tuple[int, int]] = []   # (-remainder numerator, region_id) for sorting
    for rid, pop in pops.items():
        q, r = divmod(amount * pop, total)
        shares[rid] = q
        remainders.append((-r, rid))
    leftover = amount - sum(shares.values())
    for _, rid in sorted(remainders)[:leftover]:
        shares[rid] += 1
    return {rid: amt for rid, amt in sorted(shares.items()) if amt > 0}


# --------------------------------------------------------------------------------------------- formatting

def fmt_date(value: Optional[datetime]) -> str:
    """``dd.mm.yyyy`` for the Russian messages (``{date}`` = the period's ``ends_at``)."""
    return value.strftime("%d.%m.%Y") if value else "—"
