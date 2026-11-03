"""FEAT-197 region reputation — read side of locations-service (§3.7, §3.8).

The reputation tables (character_reputation, reputation_settings, reputation_tiers) and
``characters.reputation_min_tier`` belong to character-service; this module only READS them with raw
parameterised SQL (the shared constants of ``reputation_core``) and computes the effective (lazily decayed)
value and its tier exactly like character-service. No HTTP, no writes: safe inside money transactions.

Empty seed tables fall back to the ``reputation_core`` defaults (``settings_from_row`` / ``tiers_from_rows``).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import econ_core
import econ_ledger
import reputation_core as rc

GATE_STATUS = 403
REFUSED_STATUS = 409
MSG_TRADE_REFUSED = "Торговцы этого края отказываются иметь с вами дело (репутация: {tier})"

REASON_CHARISMA = "charisma"
REASON_REPUTATION = "reputation"
LABEL_CHARISMA = "Скидка за харизму"
LABEL_REP_DISCOUNT = "Скидка за репутацию ({tier})"
LABEL_REP_MARKUP = "Наценка за репутацию ({tier})"
LABEL_REP_BID_CUT = "Скупка дешевле из-за репутации ({tier})"

SQL_NPC_GATE = "SELECT reputation_min_tier, current_location_id FROM characters WHERE id = :id"


def now_utc() -> datetime:
    """Naive UTC, like the DATETIME columns character-service writes."""
    return datetime.utcnow()


# --------------------------------------------------------------------------------------------------- raw reads

async def load_settings(session: AsyncSession) -> rc.Settings:
    return rc.settings_from_row((await session.execute(text(rc.SQL_SELECT_SETTINGS))).first())


async def load_tiers(session: AsyncSession) -> List[rc.Tier]:
    return rc.tiers_from_rows((await session.execute(text(rc.SQL_SELECT_TIERS))).fetchall())


async def effective_value(session: AsyncSession, character_id: int, region_id: Optional[int], *,
                          now: Optional[datetime] = None) -> int:
    """Effective value in the region: 0 without a row / region; the negative decay applied up to now."""
    if not region_id:
        return 0
    row = (await session.execute(text(rc.SQL_SELECT_VALUE), {
        "character_id": int(character_id), "region_id": int(region_id)})).first()
    if row is None:
        return 0
    settings = await load_settings(session)
    return rc.effective_value(int(row[0]), row[1], now or now_utc(), settings.decay_per_day)


async def get_tier(session: AsyncSession, character_id: int, region_id: Optional[int], *,
                   tiers: Optional[Sequence[rc.Tier]] = None) -> rc.Tier:
    tiers = tiers or await load_tiers(session)
    return rc.tier_for(await effective_value(session, character_id, region_id), tiers)


async def location_region(session: AsyncSession, location_id: Optional[int]) -> Optional[int]:
    region_id, _country = await econ_ledger.resolve_location(session, location_id)
    return int(region_id) if region_id else None


SQL_CHARACTER_LOCATION = "SELECT current_location_id FROM characters WHERE id = :id"


async def quest_reward_region(session: AsyncSession, npc_id: Optional[int], character_id: int) -> Optional[int]:
    """Region of a quest's reputation (§3.4): the quest giver's location, else the character's — the same
    place the quest gold is paid from."""
    location_id = None
    if npc_id:
        row = (await session.execute(text(SQL_CHARACTER_LOCATION), {"id": int(npc_id)})).first()
        location_id = row[0] if row is not None else None
    if location_id is None:
        row = (await session.execute(text(SQL_CHARACTER_LOCATION), {"id": int(character_id)})).first()
        location_id = row[0] if row is not None else None
    return await location_region(session, location_id)


# --------------------------------------------------------------------------------------------------- gates

async def gate_failure(session: AsyncSession, character_id: int, region_id: Optional[int],
                       min_code: Optional[str], *, tiers: Optional[Sequence[rc.Tier]] = None) -> Optional[str]:
    """«Нужна репутация: X» when the character misses tier ``min_code`` in the region, else None.
    No code / unknown code / no region = open (same rule as character-service)."""
    if not min_code or not region_id:
        return None
    tiers = tiers or await load_tiers(session)
    if rc.tier_by_code(min_code, tiers) is None:
        return None
    if rc.meets(await effective_value(session, character_id, region_id), min_code, tiers):
        return None
    return rc.gate_message(min_code, tiers)


async def require_tier(session: AsyncSession, character_id: int, region_id: Optional[int],
                       min_code: Optional[str]) -> None:
    message = await gate_failure(session, character_id, region_id, min_code)
    if message:
        raise HTTPException(status_code=GATE_STATUS, detail=message)


async def npc_gate(session: AsyncSession, npc_id: int) -> Tuple[Optional[str], Optional[int]]:
    """(``reputation_min_tier``, ``current_location_id``) of the NPC; (None, None) for an unknown id."""
    row = (await session.execute(text(SQL_NPC_GATE), {"id": int(npc_id)})).first()
    if row is None:
        return None, None
    return (row[0] or None), (int(row[1]) if row[1] else None)


async def npc_gate_failure(session: AsyncSession, character_id: int, npc_id: int) -> Optional[str]:
    """The NPC-level gate in the NPC's region (D8: dialogue, trade, quests)."""
    min_code, location_id = await npc_gate(session, npc_id)
    if not min_code:
        return None
    return await gate_failure(session, character_id, await location_region(session, location_id), min_code)


async def require_npc_tier(session: AsyncSession, character_id: int, npc_id: int) -> None:
    message = await npc_gate_failure(session, character_id, npc_id)
    if message:
        raise HTTPException(status_code=GATE_STATUS, detail=message)


class QuestGates:
    """NPC gate + per-quest gates of one quest giver, read once (quest list / accept)."""

    def __init__(self, npc_message: Optional[str], value: int, tiers: Sequence[rc.Tier],
                 has_region: bool = True):
        self.npc_message = npc_message
        self.value = value
        self.tiers = tiers
        self.has_region = has_region  # False = quest giver without a region -> no gates at all

    def reason(self, quest_min_code: Optional[str]) -> Optional[str]:
        if not self.has_region:
            return None
        if self.npc_message:
            return self.npc_message
        if quest_min_code and rc.tier_by_code(quest_min_code, self.tiers) is not None \
                and not rc.meets(self.value, quest_min_code, self.tiers):
            return rc.gate_message(quest_min_code, self.tiers)
        return None


async def quest_gates(session: AsyncSession, character_id: int, npc_id: Optional[int],
                      quest_codes: Sequence[Optional[str]]) -> QuestGates:
    """Reads only what is needed: nothing beyond the NPC row when neither the NPC nor any quest has a gate.
    The region is the quest giver's (the NPC's location); a quest giver without a region = no gates."""
    npc_code, location_id = (await npc_gate(session, npc_id)) if npc_id else (None, None)
    if not npc_code and not any(quest_codes):
        return QuestGates(None, 0, rc.DEFAULT_TIERS)
    region_id = await location_region(session, location_id)
    if not region_id:
        return QuestGates(None, 0, rc.DEFAULT_TIERS, has_region=False)
    tiers = await load_tiers(session)
    value = await effective_value(session, character_id, region_id)
    npc_message = None
    if npc_code and rc.tier_by_code(npc_code, tiers) is not None and not rc.meets(value, npc_code, tiers):
        npc_message = rc.gate_message(npc_code, tiers)
    return QuestGates(npc_message, value, tiers)


# --------------------------------------------------------------------------------------------------- trade

@dataclass(frozen=True)
class TradeTerms:
    """The character's standing with the merchants of a region."""
    tier: Optional[rc.Tier]          # None = no region (no reputation effect)
    price_pct: Decimal = Decimal(0)  # > 0 discount, < 0 markup on asks
    sell_pct: Decimal = Decimal(0)   # <= 0 cut of merchant bids
    refused: bool = False


NEUTRAL_TERMS = TradeTerms(tier=None)


async def trade_terms(session: AsyncSession, character_id: int, region_id: Optional[int]) -> TradeTerms:
    if not region_id:
        return NEUTRAL_TERMS
    tier = await get_tier(session, character_id, region_id)
    return TradeTerms(tier=tier, price_pct=Decimal(tier.price_pct),
                      sell_pct=min(Decimal(0), Decimal(tier.sell_pct)), refused=bool(tier.trade_refused))


def require_trade(terms: TradeTerms) -> None:
    """Вне закона (trade_refused tier): ordinary merchants refuse — 409."""
    if terms.refused and terms.tier is not None:
        raise HTTPException(status_code=REFUSED_STATUS, detail=MSG_TRADE_REFUSED.format(tier=terms.tier.name))


def ask_reasons(charisma_pct, terms: TradeTerms) -> Tuple[List[dict], float]:
    """(price_reasons, net discount percent) of a purchase. Percent signed in the player's favour:
    + discount, − markup; the reputation share is the APPLIED one (after the 50 % cap)."""
    charisma, rep = econ_core.reputation_discount_split(charisma_pct, terms.price_pct)
    reasons: List[dict] = []
    if charisma > 0:
        reasons.append({"source": REASON_CHARISMA, "percent": float(charisma), "label": LABEL_CHARISMA})
    if rep != 0 and terms.tier is not None:
        label = LABEL_REP_DISCOUNT if rep > 0 else LABEL_REP_MARKUP
        reasons.append({"source": REASON_REPUTATION, "percent": float(rep),
                        "label": label.format(tier=terms.tier.name)})
    return reasons, float(charisma + rep)


def bid_reasons(terms: TradeTerms) -> List[dict]:
    """price_reasons of a sale to a merchant: only a low tier's bid cut (negative percent)."""
    if terms.sell_pct < 0 and terms.tier is not None:
        return [{"source": REASON_REPUTATION, "percent": float(terms.sell_pct),
                 "label": LABEL_REP_BID_CUT.format(tier=terms.tier.name)}]
    return []
