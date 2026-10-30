"""FEAT-182 living regions — read models and admin actions of the economy simulation API (contract 3.7).

Regions / goods groups / templates / item groups / simulation settings, the «Заполнить регионы по шаблонам» fill and
the public region card. Like ``economy_crud``: functions never commit (the router commits after success and rolls back
on any exception), money moves only through ``econ_ledger.post_operation``, raw SQL is parameterised and portable
(MySQL 8 / SQLite). The tick itself lives in ``econ_tick`` (its loaders are reused here), the math in ``econ_sim``.
"""

import logging
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
import econ_bank
import econ_sim
import econ_tick
import economy_bank_crud
import economy_events_crud
import models
from economy_crud import EconomyApiError, _like_pattern

logger = logging.getLogger("character-service.economy")

SOURCE_SERVICE = "character-service"

RUNS_LIMIT = 20
QUEST_ITEM_OBJECTIVES = ("collect", "deliver")
# items.item_type ENUM (inventory-service) — the item-groups filter accepts only these.
ITEM_TYPES = frozenset({
    "head", "body", "cloak", "belt", "ring", "necklace", "bracelet", "weapon", "consumable", "resource", "scroll",
    "misc", "recipe", "gem", "rune", "gathering_tool", "furniture",
})
GROUP_NONE = "none"
SOURCE_AUTO, SOURCE_MANUAL = "auto", "manual"

# Column scales (Numeric(p, s)) — values are rounded before storing.
_SCALE_STOCK = 3
_SCALE_PRICE = 3

ERR_REGION_NOT_FOUND = "Регион не найден"
ERR_TEMPLATE_UNKNOWN = "Неизвестный шаблон региона"
ERR_NO_TEMPLATE = "Сначала выберите шаблон региона"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(value) -> float:
    return float(value or 0)


def _i(value) -> int:
    return int(value or 0)


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _region_row(db: Session, region_id: int):
    """(id, name, country_id) of an existing ``Regions`` row or None."""
    return db.execute(text("SELECT id, name, country_id FROM Regions WHERE id = :id"), {"id": region_id}).first()


def _require_region(db: Session, region_id: int):
    row = _region_row(db, region_id)
    if row is None:
        raise EconomyApiError(404, ERR_REGION_NOT_FOUND)
    return row


def _lock_econ_region(db: Session, region_id: int) -> Optional["models.EconRegion"]:
    query = db.query(models.EconRegion).filter(models.EconRegion.region_id == region_id)
    return (query.with_for_update() if _for_update(db) else query).first()


def _templates(db: Session) -> Dict[str, "models.EconRegionTemplate"]:
    rows = db.query(models.EconRegionTemplate).order_by(models.EconRegionTemplate.sort_order,
                                                        models.EconRegionTemplate.code).all()
    return {row.code: row for row in rows}


def _template_goods(db: Session, template_code: str) -> Dict[str, Tuple[float, float]]:
    rows = db.query(models.EconTemplateGood).filter(models.EconTemplateGood.template_code == template_code).all()
    return {row.group_code: (_f(row.production_per_1000), _f(row.consumption_mult)) for row in rows}


def _goods_rows(db: Session, region_id: int) -> Dict[str, "models.EconRegionGood"]:
    rows = db.query(models.EconRegionGood).filter(models.EconRegionGood.region_id == region_id).all()
    return {row.group_code: row for row in rows}


def _round(value: float, scale: int):
    return econ_tick._round(value, scale)


def _recompute_norms(goods_rows: Dict[str, "models.EconRegionGood"], groups: Dict[str, econ_sim.GroupDef],
                     population: int, params: econ_sim.SimParams, reset_stocks: bool = False) -> None:
    """Norm stock of every row from the current production/consumption; ``reset_stocks`` → stock = norm, price ×1.

    ``population`` is the lore number; norms are computed for the simulated one (FEAT-186 ``population_scale``)."""
    sim_pop = econ_sim.sim_population(population, params)
    states = {code: econ_tick.good_state(row) for code, row in goods_rows.items() if code in groups}
    for code, row in goods_rows.items():
        if code not in groups:
            continue
        norm = econ_sim.norm_stock(code, groups, states, sim_pop)
        row.norm_stock = _round(norm, _SCALE_STOCK)
        if reset_stocks:
            row.stock = _round(norm, _SCALE_STOCK)
            row.price_mult = _round(1.0, _SCALE_PRICE)
            row.prev_price_mult = _round(1.0, _SCALE_PRICE)


def _apply_template_goods(db: Session, region: "models.EconRegion", groups: Dict[str, econ_sim.GroupDef],
                          template_goods: Dict[str, Tuple[float, float]], reset_stocks: bool,
                          params: econ_sim.SimParams) -> Dict[str, "models.EconRegionGood"]:
    """Copy production/consumption of the template into all 12 goods rows (rows created when missing)."""
    rows = _goods_rows(db, int(region.region_id))
    for code in groups:
        production, cmult = template_goods.get(code, (0.0, 1.0))
        row = rows.get(code)
        if row is None:
            row = models.EconRegionGood(region_id=region.region_id, group_code=code, stock=0, norm_stock=0,
                                        price_mult=1, prev_price_mult=1, last_produced=0, last_consumed=0,
                                        last_demand=0, last_spoiled=0)
            db.add(row)
            rows[code] = row
        row.production_per_1000 = _round(production, 3)
        row.consumption_mult = _round(cmult, 3)
    _recompute_norms(rows, groups, _i(region.population), params, reset_stocks=reset_stocks)
    db.flush()
    return rows


def _balances(db: Session, kind: str) -> Dict[int, int]:
    return {int(r[0]): _i(r[1]) for r in db.execute(
        text("SELECT ref_id, balance FROM econ_accounts WHERE kind = :kind"), {"kind": kind}).fetchall()}


def _last_posting_id(db: Session, ref: core.AccountRef) -> int:
    """Id of the newest posting touching the account (0 when the account or postings do not exist).

    Part of the fill idempotency key: it changes after any movement of the account, so a re-fill after ticks gets a
    fresh key, while two concurrent identical fills compute the same key and the second one is rejected.
    """
    account_id = db.execute(text(core.SQL_SELECT_ACCOUNT), {"kind": ref.kind, "ref_id": ref.ref_id}).scalar()
    if account_id is None:
        return 0
    return _i(db.execute(text(
        "SELECT MAX(id) FROM econ_postings WHERE from_account_id = :a OR to_account_id = :a"
    ), {"a": int(account_id)}).scalar())


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

SQL_REGIONS = """
SELECT r.id, r.name, r.country_id, co.name, e.template_code, t.name, e.population, e.tax_rate, e.stability,
       e.prosperity, e.hunger, e.satisfaction, e.treasury_target, e.last_income, e.last_tax, e.last_wages,
       e.last_grant, e.last_tick_at
FROM Regions r
LEFT JOIN Countries co ON co.id = r.country_id
LEFT JOIN econ_regions e ON e.region_id = r.id
LEFT JOIN econ_region_templates t ON t.code = e.template_code
"""


def _region_item(row, purses: Dict[int, int], treasuries: Dict[int, int], banks: Iterable[int] = (),
                 params: econ_sim.SimParams = econ_sim.DEFAULT_PARAMS) -> dict:
    region_id = int(row[0])
    has_econ = row[6] is not None
    population = _i(row[6])
    return {
        "region_id": region_id,
        "name": row[1],
        "country_id": int(row[2]) if row[2] is not None else None,
        "country_name": row[3],
        "template_code": row[4],
        "template_name": row[5],
        "population": population,                 # lore number (FEAT-186)
        "sim_population": round(econ_sim.sim_population(population, params), 2),   # what the sim computes with
        "tax_rate": _f(row[7]) if has_econ else 0.1,
        "stability": _f(row[8]) if has_econ else 70.0,
        "prosperity": _f(row[9]) if has_econ else 50.0,
        "hunger": _f(row[10]),
        "satisfaction": _f(row[11]) if has_econ else 1.0,
        "purse": purses.get(region_id, 0),
        "treasury": treasuries.get(region_id, 0),
        "treasury_target": _i(row[12]),
        "last_income": _i(row[13]),
        "last_tax": _i(row[14]),
        "last_wages": _i(row[15]),
        "last_grant": _i(row[16]),
        "last_tick_at": row[17],
        "simulated": row[4] is not None and population > 0,
        "bank_enabled": region_id in banks,       # FEAT-184 «Банк есть»
    }


def list_regions(db: Session) -> List[dict]:
    purses = _balances(db, core.KIND_POPULATION_PURSE)
    treasuries = _balances(db, core.KIND_REGION_TREASURY)
    rows = db.execute(text(SQL_REGIONS + " ORDER BY co.name, r.name, r.id")).fetchall()
    banks = economy_bank_crud.enabled_bank_ids(db)
    params = econ_tick.load_params(db)
    badges = economy_events_crud.badges_by_region(db)        # FEAT-187: running events per region
    items = [_region_item(row, purses, treasuries, banks, params) for row in rows]
    for item in items:
        item["active_events"] = badges.get(item["region_id"], [])
    return items


def get_region(db: Session, region_id: int) -> dict:
    row = db.execute(text(SQL_REGIONS + " WHERE r.id = :id"), {"id": region_id}).first()
    if row is None:
        raise EconomyApiError(404, ERR_REGION_NOT_FOUND)
    purse = econ_tick.account_balance(db, core.AccountRef.purse(region_id))
    treasury = econ_tick.account_balance(db, core.AccountRef.region(region_id))
    item = _region_item(row, {region_id: purse}, {region_id: treasury},
                        economy_bank_crud.enabled_bank_ids(db, [region_id]), econ_tick.load_params(db))
    groups = econ_tick.load_groups(db)
    rows = _goods_rows(db, region_id)
    order = list(groups) + sorted(code for code in rows if code not in groups)
    item["goods"] = [
        {
            "group_code": code,
            "name": groups[code].name if code in groups else code,
            "production_per_1000": _f(g.production_per_1000),
            "consumption_mult": _f(g.consumption_mult),
            "stock": _f(g.stock),
            "norm_stock": _f(g.norm_stock),
            "price_mult": _f(g.price_mult),
            "prev_price_mult": _f(g.prev_price_mult),
            "last_produced": _f(g.last_produced),
            "last_consumed": _f(g.last_consumed),
            "last_demand": _f(g.last_demand),
            "last_spoiled": _f(g.last_spoiled),
        }
        for code in order if code in rows for g in [rows[code]]
    ]
    return item


def update_region(db: Session, region_id: int, body) -> dict:
    """PUT /regions/{id}: create/update the economy row. A new row (or one without goods) with a template gets the
    template goods with stock = norm; a template change on a row with goods does NOT overwrite them (apply-template)."""
    region = _lock_econ_region(db, region_id)  # first statement: the lock (fresh read view afterwards)
    _require_region(db, region_id)
    templates = _templates(db)
    if body.template_code is not None and body.template_code not in templates:
        raise EconomyApiError(400, ERR_TEMPLATE_UNKNOWN)
    groups = econ_tick.load_groups(db)

    if region is None:
        region = models.EconRegion(region_id=region_id, stability=70, prosperity=50, hunger=0, satisfaction=1,
                                   treasury_target=0, last_income=0, last_tax=0, last_wages=0, last_grant=0)
        db.add(region)
    region.template_code = body.template_code
    region.population = int(body.population)
    region.tax_rate = _round(body.tax_rate, 4)
    if body.stability is not None:
        region.stability = _round(body.stability, 2)
    if body.prosperity is not None:
        region.prosperity = _round(body.prosperity, 2)
    db.flush()

    rows = _goods_rows(db, region_id)
    params = econ_tick.load_params(db)
    if not rows and body.template_code is not None:
        rows = _apply_template_goods(db, region, groups, _template_goods(db, body.template_code), reset_stocks=True,
                                     params=params)

    for good in body.goods or []:
        row = rows.get(good.group_code)
        if row is None:
            row = models.EconRegionGood(region_id=region_id, group_code=good.group_code, stock=0, norm_stock=0,
                                        price_mult=1, prev_price_mult=1, last_produced=0, last_consumed=0,
                                        last_demand=0, last_spoiled=0)
            db.add(row)
            rows[good.group_code] = row
        row.production_per_1000 = _round(good.production_per_1000, 3)
        row.consumption_mult = _round(good.consumption_mult, 3)
        if good.stock is not None:
            row.stock = _round(good.stock, _SCALE_STOCK)
    _recompute_norms(rows, groups, int(region.population), params)
    db.flush()
    return get_region(db, region_id)


def apply_template(db: Session, region_id: int, reset_stocks: bool) -> dict:
    """Copy template goods and tax into the region; population is kept; stocks → norm when ``reset_stocks``."""
    region = _lock_econ_region(db, region_id)
    _require_region(db, region_id)
    if region is None or region.template_code is None:
        raise EconomyApiError(400, ERR_NO_TEMPLATE)
    template = db.get(models.EconRegionTemplate, region.template_code)
    if template is None:
        raise EconomyApiError(400, ERR_TEMPLATE_UNKNOWN)
    region.tax_rate = template.tax_rate
    _apply_template_goods(db, region, econ_tick.load_groups(db), _template_goods(db, template.code), reset_stocks,
                          econ_tick.load_params(db))
    return get_region(db, region_id)


def region_history(db: Session, region_id: int, limit: int) -> List[dict]:
    rows = (db.query(models.EconRegionHistory)
            .filter(models.EconRegionHistory.region_id == region_id)
            .order_by(models.EconRegionHistory.id.desc())
            .limit(limit).all())
    items = []
    for row in rows:
        goods = econ_tick._json(row.goods) or {}
        items.append({
            "id": int(row.id), "run_id": int(row.run_id), "region_id": int(row.region_id),
            "created_at": row.created_at, "population": _i(row.population), "stability": _f(row.stability),
            "prosperity": _f(row.prosperity), "hunger": _f(row.hunger), "purse": _i(row.purse),
            "treasury": _i(row.treasury), "income": _i(row.income), "tax": _i(row.tax), "wages": _i(row.wages),
            "grant_amount": _i(row.grant_amount),
            "goods": {code: {"stock": _f(g.get("stock")), "price_mult": _f(g.get("price_mult")),
                             "produced": _f(g.get("produced")), "consumed": _f(g.get("consumed"))}
                      for code, g in goods.items() if isinstance(g, dict)},
        })
    return items


# ---------------------------------------------------------------------------
# «Заполнить регионы по шаблонам»
# ---------------------------------------------------------------------------

def fill_regions(db: Session, *, region_ids: Optional[List[int]], population_from_template: bool,
                 reset_stocks: bool, fund_purses: bool, treasury_to_reserve: bool, comment: str,
                 actor_user_id: Optional[int], open_banks: bool = False, return_purse_excess: bool = False,
                 return_treasury_excess: bool = False) -> dict:
    """Apply template goods (stocks → norm), optionally population from the template (rows with population 0), and
    top up money via admin emission: the population purse to ``starting_purse`` and (``treasury_to_reserve``, added
    by B6) the region treasury to its wage reserve target. Top-up = ``max(0, target − balance)``, so a re-click emits 0.

    One ``admin_emission`` operation per region (tagged with the region, so the journal filters by region), key
    ``econ_fill:r:<region>:p<last purse posting>:t<last treasury posting>`` — stable for a given account state.

    FEAT-186 «Привести к масштабу»: ``return_purse_excess`` / ``return_treasury_excess`` move the part of the purse /
    region treasury above the same targets back into ``emission`` (legs ``purse → emission`` / ``treasury → emission``
    of the same ``admin_emission`` operation). With ``return_purse_excess`` the residents' positions in an existing
    bank are first brought to the scaled targets (``econ_bank.resident_rescale``: deposits above target ``bank → purse``,
    loans above target repaid ``purse → bank``, netted into one leg of that operation; player deposits / the vault are
    not touched). Together with the top-up the balance ends exactly at the target, so a
    second click moves nothing; the world sum stays 0 (money only leaves through the source account).
    """
    lock_sql = "SELECT region_id FROM econ_regions WHERE "
    params: dict = {}
    if region_ids:
        placeholders, params = core.in_params("r", region_ids)
        lock_sql += f"region_id IN ({placeholders})"
    else:
        lock_sql += "template_code IS NOT NULL"
    lock_sql += " ORDER BY region_id" + (" FOR UPDATE" if _for_update(db) else "")
    db.execute(text(lock_sql), params)  # first statement: serialises fills/ticks per region

    if region_ids:
        targets = []
        for region_id in region_ids:
            region_row = _region_row(db, region_id)
            if region_row is None:
                raise EconomyApiError(400, f"Регион {region_id} не найден")
            econ = db.get(models.EconRegion, region_id)
            if econ is None or econ.template_code is None:
                raise EconomyApiError(400, f"У региона «{region_row[1]}» не выбран шаблон")
            targets.append(econ)
    else:
        ids = [int(r[0]) for r in db.execute(text(
            "SELECT e.region_id FROM econ_regions e JOIN Regions r ON r.id = e.region_id "
            "WHERE e.template_code IS NOT NULL ORDER BY e.region_id")).fetchall()]
        targets = [db.get(models.EconRegion, rid) for rid in ids]

    sim_params = econ_tick.load_params(db)
    groups = econ_tick.load_groups(db)
    templates = _templates(db)
    country_tax_rate = float(econ_ledger.get_economy_settings(db).country_tax_rate)
    bank_targets = _bank_targets(targets, templates, population_from_template) if open_banks else []
    # FEAT-184 lock order: econ_banks before any account the fill's postings lock. FEAT-186: the rescale also
    # touches the residents' positions of every target region's existing bank.
    lock_ids = set(bank_targets) | ({int(r.region_id) for r in targets} if return_purse_excess else set())
    bank_rows = economy_bank_crud.lock_banks(db, lock_ids)

    processed, skipped = 0, []
    operation_ids: List[int] = []
    emitted_purses = emitted_treasuries = 0
    returned_purses = returned_treasuries = 0
    returned_bank_deposits = repaid_bank_loans = 0
    for region in targets:
        template = templates.get(region.template_code)
        if template is None:
            raise EconomyApiError(400, ERR_TEMPLATE_UNKNOWN)
        region_id = int(region.region_id)
        if population_from_template and _i(region.population) == 0:
            region.population = int(template.default_population)
        rows = _apply_template_goods(db, region, groups, _template_goods(db, template.code), reset_stocks,
                                     sim_params)
        processed += 1
        population = _i(region.population)
        if population <= 0:
            skipped.append(region_id)  # not simulated: no money for it
            continue

        goods = {code: econ_tick.good_state(row) for code, row in rows.items() if code in groups}
        purse_target = econ_sim.starting_purse(groups, goods, econ_sim.sim_population(population, sim_params),
                                               sim_params)
        # Dry run of one tick from the filled state: its treasury_target is the wage reserve the tick will use.
        probe = econ_sim.simulate_region(econ_tick.region_state(region), goods, groups, purse=purse_target,
                                         treasury=0, grant=0, country_tax_rate=country_tax_rate, params=sim_params)
        treasury_target = int(probe.region.treasury_target)
        region.treasury_target = treasury_target

        purse_ref, treasury_ref = core.AccountRef.purse(region_id), core.AccountRef.region(region_id)
        purse_balance = econ_tick.account_balance(db, purse_ref)
        treasury_balance = econ_tick.account_balance(db, treasury_ref)
        # FEAT-186: residents' bank positions first (their savings / debts belong to the purse side).
        rescale = None
        bank = bank_rows.get(region_id) if return_purse_excess else None
        if bank is not None:
            rescale = econ_bank.resident_rescale(
                purse=purse_balance, bank_balance=economy_bank_crud.bank_account_balance(db, region_id),
                deposits=_i(bank.resident_deposits), loans=_i(bank.resident_loans), purse_target=purse_target,
                enabled=bool(bank.is_enabled), params=sim_params)
            purse_balance += rescale.net_to_purse
        purse_amount = max(0, purse_target - purse_balance) if fund_purses else 0
        treasury_amount = max(0, treasury_target - treasury_balance) if treasury_to_reserve else 0
        purse_back = max(0, purse_balance - purse_target) if return_purse_excess else 0
        treasury_back = max(0, treasury_balance - max(0, treasury_target)) if return_treasury_excess else 0
        legs = []
        if rescale is not None and rescale.net_to_purse > 0:
            legs.append(core.Leg(core.AccountRef.bank(region_id), purse_ref, rescale.net_to_purse))
        elif rescale is not None and rescale.net_to_purse < 0:
            legs.append(core.Leg(purse_ref, core.AccountRef.bank(region_id), -rescale.net_to_purse))
        if purse_amount > 0:
            legs.append(core.Leg(core.AccountRef.emission(), purse_ref, purse_amount))
        if treasury_amount > 0:
            legs.append(core.Leg(core.AccountRef.emission(), treasury_ref, treasury_amount))
        if purse_back > 0:
            legs.append(core.Leg(purse_ref, core.AccountRef.emission(), purse_back))
        if treasury_back > 0:
            legs.append(core.Leg(treasury_ref, core.AccountRef.emission(), treasury_back))
        if rescale is not None and (rescale.deposits_out or rescale.loans_repaid):
            # the row moves with the money: when the posting fails the whole request rolls back
            bank.resident_deposits = rescale.deposits_after
            bank.resident_loans = rescale.loans_after
            returned_bank_deposits += rescale.deposits_out
            repaid_bank_loans += rescale.loans_repaid
        if not legs:
            continue
        key = (f"econ_fill:r:{region_id}:p{_last_posting_id(db, purse_ref)}"
               f":t{_last_posting_id(db, treasury_ref)}")
        try:
            result = econ_ledger.post_operation(
                db, op_type=core.OP_ADMIN_EMISSION, legs=legs, source_service=SOURCE_SERVICE, region_id=region_id,
                actor_user_id=actor_user_id, comment=comment, idempotency_key=key, apply_tax=False,
                metadata={"fill": True, "purse_target": purse_target, "treasury_target": treasury_target,
                          "returned_purse": purse_back, "returned_treasury": treasury_back,
                          "resident_deposits_out": rescale.deposits_out if rescale else 0,
                          "resident_loans_repaid": rescale.loans_repaid if rescale else 0},
            )
        except core.DuplicateOperation:
            logger.info("economy fill: region %s already topped up by a concurrent request", region_id)
            continue
        except core.InsufficientFunds:
            raise EconomyApiError(409, "Баланс региона изменился во время заполнения, повторите")
        if result.operation_id is not None:
            operation_ids.append(int(result.operation_id))
            emitted_purses += purse_amount
            emitted_treasuries += treasury_amount
            returned_purses += purse_back
            returned_treasuries += treasury_back
    banks_opened = _open_banks(db, bank_targets, bank_rows, sim_params, actor_user_id)
    db.flush()
    return {
        "regions": processed,
        "operation_id": operation_ids[-1] if operation_ids else None,
        "operation_ids": operation_ids,
        "emitted": emitted_purses + emitted_treasuries,
        "emitted_purses": emitted_purses,
        "emitted_treasuries": emitted_treasuries,
        "returned": returned_purses + returned_treasuries,     # FEAT-186: excess moved back into emission
        "returned_purses": returned_purses,
        "returned_treasuries": returned_treasuries,
        "resident_deposits_out": returned_bank_deposits,    # FEAT-186: residents' bank deposits -> purse
        "resident_loans_repaid": repaid_bank_loans,         # FEAT-186: residents' bank loans repaid from the purse
        "skipped_no_population": skipped,
        "banks_opened": banks_opened,
    }


def _bank_targets(targets, templates, population_from_template: bool) -> List[int]:
    """FEAT-184: regions of the fill whose template opens a bank and that will have residents after it."""
    ids = []
    for region in targets:
        if region.template_code not in economy_bank_crud.BANK_TEMPLATE_CODES:
            continue
        population = _i(region.population)
        template = templates.get(region.template_code)
        if population == 0 and population_from_template and template is not None:
            population = int(template.default_population)
        if population > 0:
            ids.append(int(region.region_id))
    return sorted(ids)


def _open_banks(db: Session, region_ids: List[int], rows: dict, sim_params, actor_user_id: Optional[int]) -> List[int]:
    """Switch the banks on (rows created when missing) and seed the start capital once — after the treasury
    top-up. Returns the regions whose bank this fill switched on."""
    opened = []
    now = economy_bank_crud.now_utc()
    for region_id in region_ids:
        bank = rows.get(region_id) or economy_bank_crud.ensure_bank_row(db, region_id, now)
        if not bank.is_enabled:
            bank.is_enabled = True
            opened.append(region_id)
        economy_bank_crud.seed_capital(db, bank, params=sim_params, actor_user_id=actor_user_id, now=now)
    return opened


# ---------------------------------------------------------------------------
# Goods groups
# ---------------------------------------------------------------------------

def _group_dict(row: "models.EconGoodsGroup", inputs: Dict[str, List[dict]]) -> dict:
    return {
        "code": row.code, "name": row.name, "sort_order": _i(row.sort_order), "is_food": bool(row.is_food),
        "base_price": _i(row.base_price), "norm_per_1000": _f(row.norm_per_1000), "norm_days": _f(row.norm_days),
        "prosperity_elasticity": _f(row.prosperity_elasticity), "price_elasticity": _f(row.price_elasticity),
        "inputs": inputs.get(row.code, []), "updated_at": row.updated_at,
    }


def _inputs_by_group(db: Session) -> Dict[str, List[dict]]:
    result: Dict[str, List[dict]] = {}
    for row in db.query(models.EconGroupInput).order_by(models.EconGroupInput.group_code,
                                                        models.EconGroupInput.input_code).all():
        result.setdefault(row.group_code, []).append({"input_code": row.input_code, "ratio": _f(row.ratio)})
    return result


def list_goods_groups(db: Session) -> List[dict]:
    inputs = _inputs_by_group(db)
    rows = db.query(models.EconGoodsGroup).order_by(models.EconGoodsGroup.sort_order, models.EconGoodsGroup.code)
    return [_group_dict(row, inputs) for row in rows.all()]


def _has_cycle(edges: Dict[str, Iterable[str]]) -> bool:
    """True when the «group needs input» graph has a cycle (iterative DFS, white/grey/black)."""
    state: Dict[str, int] = {}
    for start in edges:
        if state.get(start):
            continue
        stack = [(start, iter(edges.get(start, ())))]
        state[start] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
            elif state.get(nxt) == 1:
                return True
            elif not state.get(nxt):
                state[nxt] = 1
                stack.append((nxt, iter(edges.get(nxt, ()))))
    return False


def update_goods_group(db: Session, code: str, body) -> dict:
    row = db.get(models.EconGoodsGroup, code)
    if row is None:
        raise EconomyApiError(404, "Группа товаров не найдена")
    new_inputs = {item.input_code: item.ratio for item in body.inputs}
    if code in new_inputs:
        raise EconomyApiError(400, "Группа не может быть сырьём сама для себя")
    edges: Dict[str, Set[str]] = {}
    for item in db.query(models.EconGroupInput).all():
        if item.group_code != code:
            edges.setdefault(item.group_code, set()).add(item.input_code)
    edges[code] = set(new_inputs)
    if _has_cycle(edges):
        raise EconomyApiError(400, "Цепочка производства замыкается в круг")

    row.name = body.name
    row.base_price = int(body.base_price)
    row.norm_per_1000 = _round(body.norm_per_1000, 3)
    row.norm_days = _round(body.norm_days, 2)
    row.prosperity_elasticity = _round(body.prosperity_elasticity, 3)
    row.price_elasticity = _round(body.price_elasticity, 3)
    db.query(models.EconGroupInput).filter(models.EconGroupInput.group_code == code).delete(
        synchronize_session=False)
    for input_code, ratio in new_inputs.items():
        db.add(models.EconGroupInput(group_code=code, input_code=input_code, ratio=_round(ratio, 3)))
    db.flush()
    db.refresh(row)
    return _group_dict(row, _inputs_by_group(db))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _template_dict(db: Session, row: "models.EconRegionTemplate", order: List[str],
                   params: econ_sim.SimParams = econ_sim.DEFAULT_PARAMS) -> dict:
    goods = _template_goods(db, row.code)
    codes = [c for c in order if c in goods] + sorted(c for c in goods if c not in order)
    return {
        "code": row.code, "name": row.name, "description": row.description,
        "settlement_noun": row.settlement_noun, "noun_gender": row.noun_gender,
        "default_population": _i(row.default_population), "tax_rate": _f(row.tax_rate),
        "default_sim_population": round(econ_sim.sim_population(_i(row.default_population), params), 2),
        "sort_order": _i(row.sort_order), "updated_at": row.updated_at,
        "goods": [{"group_code": c, "production_per_1000": goods[c][0], "consumption_mult": goods[c][1]}
                  for c in codes],
    }


def _group_order(db: Session) -> List[str]:
    return [r[0] for r in db.query(models.EconGoodsGroup.code)
            .order_by(models.EconGoodsGroup.sort_order, models.EconGoodsGroup.code).all()]


def list_templates(db: Session) -> List[dict]:
    order = _group_order(db)
    params = econ_tick.load_params(db)
    return [_template_dict(db, row, order, params) for row in _templates(db).values()]


def update_template(db: Session, code: str, body) -> dict:
    row = db.get(models.EconRegionTemplate, code)
    if row is None:
        raise EconomyApiError(404, "Шаблон региона не найден")
    row.name = body.name
    row.description = body.description
    row.settlement_noun = body.settlement_noun
    row.noun_gender = body.noun_gender
    row.default_population = int(body.default_population)
    row.tax_rate = _round(body.tax_rate, 4)
    existing = {g.group_code: g for g in db.query(models.EconTemplateGood)
                .filter(models.EconTemplateGood.template_code == code).all()}
    for good in body.goods:
        target = existing.get(good.group_code)
        if target is None:
            target = models.EconTemplateGood(template_code=code, group_code=good.group_code)
            db.add(target)
        target.production_per_1000 = _round(good.production_per_1000, 3)
        target.consumption_mult = _round(good.consumption_mult, 3)
    db.flush()
    db.refresh(row)
    return _template_dict(db, row, _group_order(db), econ_tick.load_params(db))


# ---------------------------------------------------------------------------
# Item → group
# ---------------------------------------------------------------------------

SQL_ITEM_GROUPS = """
SELECT i.id, i.name, i.item_type, i.item_rarity, i.resource_subcategory, i.is_food, i.price, i.image,
       o.item_id, o.group_code, o.off_market,
       CASE WHEN EXISTS (SELECT 1 FROM quest_objectives q
                         WHERE q.target_id = i.id AND q.objective_type IN (:obj_collect, :obj_deliver))
            THEN 1 ELSE 0 END AS in_quests
FROM items i
LEFT JOIN econ_item_groups o ON o.item_id = i.id
WHERE (:q IS NULL OR i.name LIKE :q ESCAPE '!')
  AND (:item_type IS NULL OR i.item_type = :item_type)
ORDER BY i.name, i.id
"""


def list_item_groups(db: Session, *, q: Optional[str], item_type: Optional[str], group: Optional[str],
                     source: Optional[str], off_market: Optional[bool], page: int, page_size: int
                     ) -> Tuple[List[dict], int]:
    """Items with their auto / override / effective group. ``q`` and ``item_type`` filter in SQL; the effective
    group, source and off-market filters need the Python auto rule, so they run over the SQL result (the items
    catalogue is small — hundreds of rows) before paging. FEAT-183: auto and effective values come from
    ``econ_core.effective_item_group`` (the rule the merchants use) — an item without a group is off-market."""
    rows = db.execute(text(SQL_ITEM_GROUPS), {
        "q": _like_pattern(q) if q else None, "item_type": item_type,
        "obj_collect": QUEST_ITEM_OBJECTIVES[0], "obj_deliver": QUEST_ITEM_OBJECTIVES[1],
    }).fetchall()
    items = []
    for r in rows:
        auto_group, auto_off = core.effective_item_group(r[2], r[4], r[5], r[3])
        override_group = r[9]
        override_off = None if r[10] is None else bool(r[10])
        manual = r[8] is not None and (override_group is not None or override_off is not None)
        effective_group, effective_off = core.effective_item_group(r[2], r[4], r[5], r[3], override_group, override_off)
        if group is not None and (effective_group is not None if group == GROUP_NONE else effective_group != group):
            continue
        if source is not None and (source == SOURCE_MANUAL) != manual:
            continue
        if off_market is not None and effective_off != off_market:
            continue
        items.append({
            "item_id": int(r[0]), "name": r[1], "item_type": r[2], "item_rarity": r[3],
            "resource_subcategory": r[4], "is_food": bool(r[5]), "price": _i(r[6]), "image": r[7],
            "auto_group": auto_group, "auto_off_market": bool(auto_off),
            "override_group": override_group, "override_off_market": override_off,
            "group": effective_group, "off_market": bool(effective_off), "in_quests": bool(r[11]),
        })
    total = len(items)
    start = (page - 1) * page_size
    return items[start:start + page_size], total


def update_item_groups(db: Session, *, item_ids: List[int], fields_set: Set[str], group_code: Optional[str],
                       off_market: Optional[bool], reset: bool, actor_user_id: Optional[int]) -> int:
    set_group, set_off = "group_code" in fields_set, "off_market" in fields_set
    if reset and (set_group or set_off):
        raise EconomyApiError(400, "Сброс нельзя совмещать с назначением группы или «вне рынка»")
    if not reset and not set_group and not set_off:
        raise EconomyApiError(400, "Не указано, что менять")
    placeholders, params = core.in_params("i", item_ids)
    existing = [int(r[0]) for r in db.execute(
        text(f"SELECT id FROM items WHERE id IN ({placeholders}) ORDER BY id"), params).fetchall()]
    if not existing:
        return 0
    if reset:
        ph, p = core.in_params("i", existing)
        db.execute(text(f"DELETE FROM econ_item_groups WHERE item_id IN ({ph})"), p)
        return len(existing)
    overrides = {row.item_id: row for row in db.query(models.EconItemGroup)
                 .filter(models.EconItemGroup.item_id.in_(existing)).all()}
    for item_id in existing:
        row = overrides.get(item_id)
        if row is None:
            row = models.EconItemGroup(item_id=item_id)
            db.add(row)
        if set_group:
            row.group_code = group_code
        if set_off:
            row.off_market = off_market
        row.updated_by_user_id = actor_user_id
        if row.group_code is None and row.off_market is None:
            if item_id in overrides:
                db.delete(row)
            else:
                db.expunge(row)
    db.flush()
    return len(existing)


# ---------------------------------------------------------------------------
# Simulation settings / runs
# ---------------------------------------------------------------------------

def _merchant_ops(db: Session, run_id: int) -> int:
    """merchant_trade operations posted by a run (FEAT-183; keyed merchant_trade:<run>:r:<region>)."""
    return _i(db.execute(text(
        "SELECT COUNT(*) FROM econ_operations WHERE op_type = :op AND idempotency_key LIKE :key"
    ), {"op": core.OP_MERCHANT_TRADE, "key": f"merchant_trade:{int(run_id)}:r:%"}).scalar())


def _run_ops(db: Session, op_type: str, key_prefix: str) -> int:
    """Operations of one type posted by a run, by idempotency-key prefix (FEAT-184 bank / collection counters)."""
    return _i(db.execute(text(
        "SELECT COUNT(*) FROM econ_operations WHERE op_type = :op AND idempotency_key LIKE :key"
    ), {"op": op_type, "key": f"{key_prefix}%"}).scalar())


def _run_dict(run: "models.EconTickRun", db: Optional[Session] = None, events: Optional[dict] = None) -> dict:
    return {
        # FEAT-187: events pass counters derived from the instances (economy_events_crud.run_counters)
        **(events or {}),
        "id": int(run.id), "slot": run.slot, "trigger_kind": run.trigger_kind, "actor_user_id": run.actor_user_id,
        "status": run.status, "regions_total": _i(run.regions_total), "regions_done": _i(run.regions_done),
        "regions_failed": _i(run.regions_failed), "error": run.error, "started_at": run.started_at,
        "heartbeat_at": run.heartbeat_at, "finished_at": run.finished_at,
        # FEAT-183: derived (econ_tick_runs has no merchant columns)
        "merchant_ops_posted": _merchant_ops(db, int(run.id)) if db is not None else 0,
        "merchant_failures": econ_tick.merchant_failures_from_error(run.error),
        # FEAT-184: derived the same way (banks_processed is only in the run-now summary)
        "bank_ops_posted": _run_ops(db, core.OP_BANK_TICK, f"bank_tick:{int(run.id)}:b:") if db is not None else 0,
        "bank_failures": econ_tick.bank_failures_from_error(run.error),
        "loans_collected": (_run_ops(db, core.OP_LOAN_COLLECT, f"loan_collect:{int(run.id)}:l:")
                            if db is not None else 0),
    }


def sim_state(db: Session, *, env_enabled: bool, now: Optional[datetime] = None) -> dict:
    slot = econ_tick.slot_of(now)
    running = (db.query(models.EconTickRun).filter(models.EconTickRun.status == econ_tick.STATUS_RUNNING)
               .order_by(models.EconTickRun.id.desc()).first())
    runs = db.query(models.EconTickRun).order_by(models.EconTickRun.id.desc()).limit(RUNS_LIMIT).all()
    counters = economy_events_crud.run_counters(db, runs + ([running] if running is not None else []),
                                                econ_tick.EVENTS_ERROR_PREFIX)
    return {
        "tick_enabled": econ_tick.is_tick_enabled(db),
        "env_enabled": env_enabled,
        "params": econ_tick.load_params(db).to_dict(),
        "current_slot_start": econ_tick.slot_start(slot),
        "next_slot_at": econ_tick.slot_start(slot + 1),
        "running": _run_dict(running, db, counters.get(int(running.id))) if running is not None else None,
        "runs": [_run_dict(run, db, counters.get(int(run.id))) for run in runs],
    }


def update_sim(db: Session, *, tick_enabled: bool, params_in: dict, user_id: Optional[int]) -> None:
    """Merge the given params over the stored ones (missing keys keep their value) and validate cross-field rules."""
    current = econ_tick.load_params(db).to_dict()
    merged = {**current, **{k: v for k, v in params_in.items() if v is not None}}
    if not merged["price_min"] < merged["price_max"]:
        raise EconomyApiError(400, "Минимальный множитель цены должен быть меньше максимального")
    if not merged["prod_price_min"] < merged["prod_price_max"]:
        raise EconomyApiError(400, "Нижняя граница отклика производства на цену должна быть меньше верхней")
    params = econ_sim.SimParams.from_mapping(merged).to_dict()
    row = db.get(models.EconSimSettings, 1)
    if row is None:
        row = models.EconSimSettings(id=1)
        db.add(row)
    row.tick_enabled = bool(tick_enabled)
    row.params = params
    row.updated_by_user_id = user_id
    db.flush()


# ---------------------------------------------------------------------------
# Public region card
# ---------------------------------------------------------------------------

def region_card(db: Session, region_id: int) -> dict:
    if region_id <= 0:
        return {"region_id": region_id, "participating": False, "has_bank": False, "events": []}
    has_bank = bool(economy_bank_crud.enabled_bank_ids(db, [region_id]))   # FEAT-184, in both shapes
    # FEAT-187: in both shapes too; events only ever run in participating regions -> [] in the hidden one
    hidden = {"region_id": region_id, "participating": False, "has_bank": has_bank, "events": []}
    region = db.get(models.EconRegion, region_id)
    if region is None or region.template_code is None or _i(region.population) <= 0:
        return hidden
    if _region_row(db, region_id) is None:
        return hidden
    template = db.get(models.EconRegionTemplate, region.template_code)
    groups = econ_tick.load_groups(db)
    goods = {code: econ_tick.good_state(row) for code, row in _goods_rows(db, region_id).items() if code in groups}
    treasury = econ_tick.account_balance(db, core.AccountRef.region(region_id))
    card = econ_sim.region_card(
        econ_tick.region_state(region), goods, groups, treasury=treasury,
        noun=template.settlement_noun if template is not None else "Регион",
        gender=template.noun_gender if template is not None else "m",
        group_order=list(groups),
    )
    return {"region_id": region_id, "participating": True, "updated_at": region.last_tick_at, **card,
            "has_bank": has_bank, "events": economy_events_crud.card_events(db, region_id)}
