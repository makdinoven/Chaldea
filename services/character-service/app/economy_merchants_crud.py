"""FEAT-183 NPC merchants — admin read model and «Пополнить кассы торговцев» (contract 3.7).

Like ``economy_crud`` / ``economy_sim_crud``: functions never commit (the router commits after success and rolls back
on any exception), money moves only through ``econ_ledger.post_operation``, raw SQL is parameterised and portable
(MySQL 8 / SQLite). Shop rows (``npc_shop_items``) belong to locations-service and are only read here; the living /
legacy rule, prices and the cash target come from the shared contract (``econ_core``) and ``econ_merchant``.
"""

import json
import logging
import zlib
from typing import Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
import econ_merchant
import econ_tick

logger = logging.getLogger("character-service.economy")

SOURCE_SERVICE = "character-service"

# Why a merchant got no money from the fund action (besides the econ_core legacy reasons).
FUND_SKIP_NOT_MERCHANT = "not_merchant"   # npc_ids entry without active shop rows
FUND_SKIP_NO_TARGET = "no_target"         # no restockable (admin, on-market) rows -> cash target 0
FUND_SKIP_AT_TARGET = "at_target"         # cash already >= target
FUND_SKIP_REGION = "region_filtered"      # npc_ids entry outside the requested region_ids

LAST_TRADE_LOOKBACK = 10                  # merchant_trade ops of a region searched for an NPC's last trade

SQL_ALL_SHOP_NPCS = "SELECT DISTINCT npc_id FROM npc_shop_items ORDER BY npc_id"


def _json(value):
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _shop_rows(db: Session, npc_ids: Sequence[int]) -> Dict[int, List[tuple]]:
    """{npc_id: [SHOP_ROW_COLUMNS tuples ascending id]} — plain read, no locks."""
    if not npc_ids:
        return {}
    placeholders, params = core.in_params("n", list(npc_ids))
    result: Dict[int, List[tuple]] = {}
    for row in db.execute(text(core.sql_lock_shop_rows(placeholders, False, "npc_id")), params).fetchall():
        result.setdefault(int(row[1]), []).append(tuple(row))
    return result


def _active_inputs(rows: Sequence[tuple], items: Dict[int, core.ItemMarket]) -> List[econ_merchant.ShopRow]:
    return [econ_tick.shop_row_input(r, items.get(int(r[2]))) for r in rows if r[8]]


def _region_mults(db: Session, region_id: int, cache: Dict[int, dict]) -> dict:
    if region_id not in cache:
        rows = db.execute(text(core.SQL_REGION_MARKET), {"region_id": region_id}).fetchall()
        cache[region_id] = core.region_goods_from_rows(rows)[0]
    return cache[region_id]


def _last_trades(db: Session, region_ids: Sequence[int]) -> Dict[int, List[tuple]]:
    """{region_id: [(op id, created_at, metadata) newest first]} of the recent merchant_trade operations."""
    result: Dict[int, List[tuple]] = {}
    for region_id in sorted(set(region_ids)):
        rows = db.execute(text(
            "SELECT id, created_at, metadata FROM econ_operations WHERE op_type = :op AND region_id = :r "
            "ORDER BY id DESC LIMIT :n"
        ), {"op": core.OP_MERCHANT_TRADE, "r": region_id, "n": LAST_TRADE_LOOKBACK}).fetchall()
        result[region_id] = [(int(r[0]), r[1], _json(r[2]) or {}) for r in rows]
    return result


def _last_trade(npc_id: int, ops: Sequence[tuple]) -> Optional[dict]:
    for op_id, created_at, meta in ops:
        entry = (meta.get("merchants") or {}).get(str(npc_id))
        if entry is not None:
            return {"operation_id": op_id, "run_id": meta.get("run_id"), "at": created_at,
                    "sold_items": int(entry.get("sold_items", 0)), "sold_value": int(entry.get("sold_value", 0)),
                    "tax": int(entry.get("tax", 0)), "restock_items": int(entry.get("restock_items", 0)),
                    "restock_value": int(entry.get("restock_value", 0)), "upkeep": int(entry.get("upkeep", 0))}
    return None


def list_merchants(db: Session, *, region_id: Optional[int] = None, living: Optional[bool] = None) -> dict:
    """Every NPC with shop rows (active or not): status, cash vs target, rows with current prices, last trade."""
    params = econ_tick.load_params(db)
    npc_ids = [int(r[0]) for r in db.execute(text(SQL_ALL_SHOP_NPCS)).fetchall()]
    if not npc_ids:
        return {"items": [], "totals": {"merchants": 0, "living": 0, "cash": 0}}

    placeholders, id_params = core.in_params("c", npc_ids)
    chars = {int(r[0]): (r[1], int(r[2] or 0)) for r in db.execute(text(
        f"SELECT id, name, currency_balance FROM characters WHERE id IN ({placeholders})"), id_params).fetchall()}
    places = {nid: econ_tick.merchant_place(db, nid) for nid in npc_ids}
    if region_id is not None:
        npc_ids = [n for n in npc_ids if places[n].region_id == region_id]
    if living is not None:
        npc_ids = [n for n in npc_ids if places[n].living == living]

    rows_by_npc = _shop_rows(db, npc_ids)
    items = econ_tick.load_item_markets(db, [r[2] for rows in rows_by_npc.values() for r in rows])
    region_ids = sorted({p.region_id for n, p in places.items() if n in npc_ids and p.region_id is not None})
    region_names: Dict[int, str] = {}
    if region_ids:
        ph, rp = core.in_params("r", region_ids)
        region_names = {int(r[0]): r[1] for r in db.execute(
            text(f"SELECT id, name FROM Regions WHERE id IN ({ph})"), rp).fetchall()}
    trades = _last_trades(db, [places[n].region_id for n in npc_ids if places[n].living])
    mults_cache: Dict[int, dict] = {}

    out = []
    total_cash = living_count = 0
    for npc_id in npc_ids:
        place = places[npc_id]
        name, cash = chars.get(npc_id, (None, 0))
        mults = _region_mults(db, place.region_id, mults_cache) if place.living else {}
        rows_out = []
        stock_value = 0
        for r in rows_by_npc.get(npc_id, []):
            item = items.get(int(r[2]))
            group, off_market = (item.group, item.off_market) if item is not None else (None, True)
            mult = core.market_mult(place.living, group, off_market, mults)
            ask = core.market_ask(r[3], mult)
            bid = core.market_bid(r[4], mult, ask)
            if place.living:
                stock = int(r[5] or 0)
            else:
                stock = int(r[5]) if r[5] is not None else None   # legacy NULL = unlimited
            if r[8] and stock:
                stock_value += stock * ask
            rows_out.append({
                "row_id": int(r[0]), "item_id": int(r[2]), "item_name": item.name if item is not None else None,
                "group": group, "off_market": bool(off_market), "origin": r[7] or core.SHOP_ORIGIN_ADMIN,
                "is_active": bool(r[8]), "base_buy": int(r[3] or 0), "base_sell": int(r[4] or 0),
                "ask": ask, "bid": bid, "market": bool(place.living and not off_market and group is not None),
                "stock": stock, "restock_target": int(r[6] or 0),
            })
        target = (econ_merchant.cash_target(_active_inputs(rows_by_npc.get(npc_id, []), items), params)
                  if place.living else 0)
        total_cash += cash
        living_count += 1 if place.living else 0
        out.append({
            "npc_id": npc_id, "name": name, "location_id": place.location_id, "region_id": place.region_id,
            "region_name": region_names.get(place.region_id) if place.region_id is not None else None,
            "living": place.living, "reason": place.reason, "tax_rate": place.tax_rate,
            "cash": cash, "cash_target": target, "rows": rows_out, "stock_value": stock_value,
            "last_trade": _last_trade(npc_id, trades.get(place.region_id, [])) if place.living else None,
        })
    return {"items": out, "totals": {"merchants": len(out), "living": living_count, "cash": total_cash}}


def _last_character_posting(db: Session, npc_ids: Sequence[int]) -> int:
    """Newest posting id over the NPCs' character accounts (0 when none) — part of the fund idempotency key."""
    placeholders, params = core.in_params("c", list(npc_ids))
    account_ids = [int(r[0]) for r in db.execute(text(
        f"SELECT id FROM econ_accounts WHERE kind = :kind AND ref_id IN ({placeholders})"
    ), {**params, "kind": core.KIND_CHARACTER}).fetchall()]
    if not account_ids:
        return 0
    ph, ap = core.in_params("a", account_ids)
    value = db.execute(text(
        f"SELECT MAX(id) FROM econ_postings WHERE from_account_id IN ({ph}) OR to_account_id IN ({ph})"), ap).scalar()
    return int(value or 0)


def fund_merchants(db: Session, *, region_ids: Optional[List[int]], npc_ids: Optional[List[int]], comment: str,
                   actor_user_id: Optional[int]) -> dict:
    """«Пополнить кассы торговцев» (Q1): top every living merchant up to ``econ_merchant.cash_target`` with new money.

    One ``admin_emission`` per region (``emission → NPC`` legs of ``max(0, target − cash)``), key
    ``merchant_fund:r:<region>:m<newest posting over those NPC accounts>:h<crc of the NPC set>`` — stable for a given
    state, so two identical concurrent clicks post once; a re-click emits 0 (cash already at the target).
    Lock order 3.5: NPC ``characters`` rows (ascending) → accounts (``post_operation``).
    """
    params = econ_tick.load_params(db)
    candidates = [int(r[0]) for r in db.execute(text(econ_tick.SQL_MERCHANT_NPCS)).fetchall()]
    skipped: List[dict] = []
    if npc_ids:
        known = set(candidates)
        skipped.extend({"npc_id": n, "reason": FUND_SKIP_NOT_MERCHANT} for n in npc_ids if n not in known)
        candidates = [n for n in candidates if n in set(npc_ids)]

    by_region: Dict[int, List[int]] = {}
    for npc_id in candidates:
        place = econ_tick.merchant_place(db, npc_id)
        if not place.living:
            if npc_ids:
                skipped.append({"npc_id": npc_id, "reason": place.reason})
            continue
        if region_ids and place.region_id not in region_ids:
            if npc_ids:
                skipped.append({"npc_id": npc_id, "reason": FUND_SKIP_REGION})
            continue
        by_region.setdefault(int(place.region_id), []).append(npc_id)

    living = sorted(n for ids in by_region.values() for n in ids)
    cash = econ_ledger.lock_characters(db, living)
    rows_by_npc = _shop_rows(db, living)
    items = econ_tick.load_item_markets(db, [r[2] for rows in rows_by_npc.values() for r in rows])

    operation_ids: List[int] = []
    emitted = funded = 0
    for region_id in sorted(by_region):
        legs, targets = [], {}
        for npc_id in sorted(by_region[region_id]):
            target = econ_merchant.cash_target(_active_inputs(rows_by_npc.get(npc_id, []), items), params)
            if target <= 0:
                skipped.append({"npc_id": npc_id, "reason": FUND_SKIP_NO_TARGET})
                continue
            amount = target - cash.get(npc_id, 0)
            if amount <= 0:
                skipped.append({"npc_id": npc_id, "reason": FUND_SKIP_AT_TARGET})
                continue
            legs.append(core.Leg(core.AccountRef.emission(), core.AccountRef.character(npc_id), int(amount)))
            targets[str(npc_id)] = target
        if not legs:
            continue
        npcs = sorted(int(t) for t in targets)
        key = (f"merchant_fund:r:{region_id}:m{_last_character_posting(db, npcs)}"
               f":h{zlib.crc32(','.join(map(str, npcs)).encode()):08x}")
        try:
            result = econ_ledger.post_operation(
                db, op_type=core.OP_ADMIN_EMISSION, legs=legs, source_service=SOURCE_SERVICE, region_id=region_id,
                actor_user_id=actor_user_id, comment=comment, idempotency_key=key, apply_tax=False,
                metadata={"merchant_fund": True, "targets": targets},
            )
        except core.DuplicateOperation:
            logger.info("merchant fund: region %s already topped up by a concurrent request", region_id)
            continue
        if result.operation_id is not None:
            operation_ids.append(int(result.operation_id))
            emitted += sum(leg.amount for leg in legs)
            funded += len(legs)
    db.flush()
    return {"merchants": len(living), "funded": funded, "operation_ids": operation_ids, "emitted": emitted,
            "skipped": sorted(skipped, key=lambda s: s["npc_id"])}
