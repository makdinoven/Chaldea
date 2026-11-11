"""FEAT-211 3.11 — the fence («Скупщик», NPC role ``fence``): admin settings (A11/A12) and the 6 h cash refill.

* :func:`fence_out` / :func:`save_fence` — the admin API (caller's transaction, no commit). Settings are one
  ``econ_fences`` row per NPC (no row = defaults). Only an NPC whose saved role is ``fence`` can be configured;
* :func:`plan_refill` + :func:`refill_region` — the tick's ``_fence_pass``: per participating region one transaction
  ``econ_regions(row) FOR UPDATE → fence characters (asc id) → econ_accounts`` (by ``post_operation``); the region's
  fences (active, alive, role ``fence``, located in the region; ascending id) are topped up to their ``cash_target``
  from at most ``floor(purse × fence_purse_share)`` of the region's population purse: ONE ``merchant_trade`` operation
  (legs ``population_purse → character``, untaxed, key ``fence:<run>:r<region>``, metadata ``fence: true``). The key
  makes the refill idempotent per run (a resumed run gets ``DuplicateOperation``). Closed economy: purse → NPC only.

The locations-service player flows (A13/A14) read ``econ_fences`` by raw SQL; nothing here locks that table.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
import fence_schemas as fs
import models

logger = logging.getLogger("character-service.fence")

FENCE_ROLE = "fence"
SOURCE_SERVICE = "character-service"

MSG_NPC_NOT_FOUND = "НПС не найден"
MSG_ONLY_FENCE = "Настройки скупки доступны только скупщику"
MSG_UNKNOWN_GROUP = "Неизвестная группа товаров"
MSG_PRICE_PCT = f"Процент цены должен быть от {fs.FENCE_PRICE_PCT_MIN} до {fs.FENCE_PRICE_PCT_MAX}"
MSG_CASH_TARGET = f"Касса скупщика должна быть от {fs.FENCE_CASH_TARGET_MIN} до {fs.FENCE_CASH_TARGET_MAX}"

SQL_PARTICIPATES = (
    "SELECT 1 FROM econ_regions e JOIN Regions r ON r.id = e.region_id "
    "WHERE e.region_id = :r AND e.template_code IS NOT NULL AND e.population > 0"
)

# Fence candidates: alive NPCs with the role and their settings (LEFT JOIN: no row = defaults).
SQL_FENCES = (
    "SELECT c.id, c.current_location_id, f.is_active, f.cash_target FROM characters c "
    "LEFT JOIN econ_fences f ON f.npc_id = c.id "
    "WHERE c.is_npc = 1 AND c.npc_role = :role AND (c.npc_status IS NULL OR c.npc_status <> 'dead') "
)


class FenceError(Exception):
    """Business error of the fence layer (HTTP status + Russian text)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# =====================================================================================================================
# pure helpers
# =====================================================================================================================

def normalize_groups(groups: Iterable[str]) -> List[str]:
    """Validate goods group codes and return them unique, in the canonical order. Raises FenceError(400)."""
    wanted = set()
    for code in groups or ():
        code = (code or "").strip()
        if code not in core.GOODS_GROUPS:
            raise FenceError(400, MSG_UNKNOWN_GROUP)
        wanted.add(code)
    return [code for code in core.GOODS_GROUPS if code in wanted]


def parse_groups(raw) -> List[str]:
    """econ_fences.accepted_groups (JSON as str / bytes / list / None) -> known codes; [] = every group."""
    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, (list, tuple)):
        return []
    known = {str(g) for g in raw if g}
    return [code for code in core.GOODS_GROUPS if code in known]


def refill_budget(purse: int, share) -> int:
    """floor(purse × share); 0 for an empty / negative purse or a non-positive share."""
    if purse <= 0:
        return 0
    value = Decimal(int(purse)) * Decimal(str(share or 0))
    return max(0, int(value.to_integral_value(rounding=ROUND_FLOOR)))


def allocate(budget: int, needs: Sequence[Tuple[int, int, int]]) -> Dict[int, int]:
    """needs = [(npc_id, cash, cash_target)] in order -> {npc_id: amount > 0}, each min(target − cash, budget left)."""
    left = max(0, int(budget))
    out: Dict[int, int] = {}
    for npc_id, cash, target in needs:
        if left <= 0:
            break
        amount = min(max(0, int(target) - int(cash)), left)
        if amount > 0:
            out[int(npc_id)] = amount
            left -= amount
    return out


# =====================================================================================================================
# admin settings (A11 / A12)
# =====================================================================================================================

def require_npc(db: Session, npc_id: int) -> "models.Character":
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not bool(npc.is_npc) or npc.npc_role == "mob":
        raise FenceError(404, MSG_NPC_NOT_FOUND)
    return npc


def _region_of(db: Session, location_id: Optional[int]) -> Optional[int]:
    region_id, _country = econ_ledger.resolve_location(db, location_id)
    return region_id


def _participates(db: Session, region_id: Optional[int]) -> bool:
    if region_id is None:
        return False
    return db.execute(text(SQL_PARTICIPATES), {"r": int(region_id)}).first() is not None


def fence_out(db: Session, npc_id: int) -> dict:
    """A11 body: the saved settings (defaults without a row), the NPC's cash, region and whether the tick refills him."""
    npc = require_npc(db, npc_id)
    row = db.query(models.EconFence).filter(models.EconFence.npc_id == int(npc_id)).populate_existing().first()
    is_active = bool(row.is_active) if row is not None else True
    region_id = _region_of(db, npc.current_location_id)
    region_name = None
    if region_id is not None:
        region_name = db.execute(text("SELECT name FROM Regions WHERE id = :r"), {"r": region_id}).scalar()
    alive = npc.npc_status != "dead"
    return {
        "npc_id": int(npc.id),
        "is_active": is_active,
        "price_pct": int(row.price_pct) if row is not None and row.price_pct is not None
        else fs.FENCE_PRICE_PCT_DEFAULT,
        "accepted_groups": parse_groups(row.accepted_groups) if row is not None else [],
        "cash_target": int(row.cash_target) if row is not None and row.cash_target is not None
        else fs.FENCE_CASH_TARGET_DEFAULT,
        "cash": int(npc.currency_balance or 0),
        "region_id": region_id,
        "region_name": region_name,
        "refill_active": bool(npc.npc_role == FENCE_ROLE and is_active and alive and _participates(db, region_id)),
    }


def save_fence(db: Session, npc_id: int, body: "fs.FenceSettingsIn", *, user_id: Optional[int],
               now: Optional[datetime] = None) -> None:
    """A12: validate and upsert the settings (caller commits). 404 / 409 (role) / 400 (values)."""
    npc = require_npc(db, npc_id)
    if npc.npc_role != FENCE_ROLE:
        raise FenceError(409, MSG_ONLY_FENCE)
    price_pct = int(body.price_pct)
    if not fs.FENCE_PRICE_PCT_MIN <= price_pct <= fs.FENCE_PRICE_PCT_MAX:
        raise FenceError(400, MSG_PRICE_PCT)
    cash_target = int(body.cash_target)
    if not fs.FENCE_CASH_TARGET_MIN <= cash_target <= fs.FENCE_CASH_TARGET_MAX:
        raise FenceError(400, MSG_CASH_TARGET)
    groups = normalize_groups(body.accepted_groups)

    row = db.query(models.EconFence).filter(models.EconFence.npc_id == int(npc_id)).first()
    if row is None:
        row = models.EconFence(npc_id=int(npc_id))
        db.add(row)
    row.is_active = bool(body.is_active)
    row.price_pct = price_pct
    row.accepted_groups = groups or None            # NULL = every group (same meaning as [] for the readers)
    row.cash_target = cash_target
    row.updated_at = now or datetime.utcnow()
    row.updated_by = user_id
    db.flush()


# =====================================================================================================================
# refill (the tick's _fence_pass)
# =====================================================================================================================

@dataclass
class RefillOutcome:
    status: str                         # done | nothing | skipped
    fences: int = 0                     # fences that received money
    amount: int = 0
    posted: bool = False
    amounts: Dict[int, int] = field(default_factory=dict)


def _active_fences(db: Session, ids: Optional[Sequence[int]] = None) -> List[Tuple[int, Optional[int], int]]:
    """[(npc_id, location_id, cash_target)] of the active, alive fences (optionally only `ids`), ascending id."""
    sql, params = SQL_FENCES, {"role": FENCE_ROLE}
    if ids is not None:
        if not ids:
            return []
        placeholders, id_params = core.in_params("n", sorted({int(i) for i in ids}))
        sql += f"AND c.id IN ({placeholders}) "
        params.update(id_params)
    rows = db.execute(text(sql + "ORDER BY c.id"), params).fetchall()
    out = []
    for npc_id, location_id, is_active, cash_target in rows:
        if is_active is not None and not bool(is_active):
            continue
        target = int(cash_target) if cash_target is not None else fs.FENCE_CASH_TARGET_DEFAULT
        out.append((int(npc_id), int(location_id) if location_id else None, target))
    return out


def plan_refill(db: Session) -> Dict[int, List[int]]:
    """{region_id: [npc_id asc]} of the active fences standing in participating regions (plain reads)."""
    plan: Dict[int, List[int]] = {}
    participates: Dict[int, bool] = {}
    for npc_id, location_id, _target in _active_fences(db):
        region_id = _region_of(db, location_id)
        if region_id is None:
            continue
        if region_id not in participates:
            participates[region_id] = _participates(db, region_id)
        if participates[region_id]:
            plan.setdefault(region_id, []).append(npc_id)
    return dict(sorted(plan.items()))


def _purse_balance(db: Session, region_id: int) -> int:
    ref = core.AccountRef.purse(region_id)
    value = db.execute(text("SELECT balance FROM econ_accounts WHERE kind = :kind AND ref_id = :ref"),
                       {"kind": ref.kind, "ref": ref.ref_id}).scalar()
    return int(value or 0)


def refill_region(db: Session, *, run_id: int, region_id: int, npc_ids: Sequence[int], share) -> RefillOutcome:
    """One region's refill inside the caller's transaction (caller commits / rolls back).

    Raises ``core.DuplicateOperation`` when this run already refilled the region."""
    if core.supports_for_update(db.get_bind().dialect.name):
        db.execute(text("SELECT region_id FROM econ_regions WHERE region_id = :r FOR UPDATE"), {"r": int(region_id)})
    if not _participates(db, region_id):
        return RefillOutcome(status="skipped")
    cash = econ_ledger.lock_characters(db, npc_ids)
    # re-check under the locks: still an active alive fence of this region (an admin may have moved / changed him)
    needs = [(npc_id, cash[npc_id], target) for npc_id, location_id, target in _active_fences(db, list(cash))
             if _region_of(db, location_id) == int(region_id)]
    purse = _purse_balance(db, region_id)
    budget = refill_budget(purse, share)
    amounts = allocate(budget, needs)
    if not amounts:
        return RefillOutcome(status="nothing")
    purse_ref = core.AccountRef.purse(region_id)
    legs = [core.Leg(purse_ref, core.AccountRef.character(npc_id), amount) for npc_id, amount in amounts.items()]
    total = sum(amounts.values())
    posting = econ_ledger.post_operation(
        db, op_type=core.OP_MERCHANT_TRADE, legs=legs, source_service=SOURCE_SERVICE, region_id=int(region_id),
        idempotency_key=f"fence:{run_id}:r{region_id}", apply_tax=False,
        metadata={"fence": True, "run_id": run_id, "purse": purse, "budget": budget, "total": total,
                  "fences": {str(k): v for k, v in amounts.items()}},
    )
    return RefillOutcome(status="done", fences=len(amounts), amount=total,
                         posted=posting.operation_id is not None, amounts=amounts)
