"""FEAT-205 factions — admin flows (features/FEAT-205 §3.10 admin table). Sync SQLAlchemy, caller commits.

Validation errors are ``FactionError(422 | 409, <Russian text>)`` -> ``{"detail": "<текст>"}``. Referenced ids
(locations, NPCs, titles, items, quests, regions, classes, races, factions) are verified to exist; raw SQL is
parameterised only. Condition / rank quests must be NON-repeatable (§1 decision).
"""

import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

import faction_core as fc
import faction_econ as fe
import faction_crud as fcr
import models
import reputation_core as rc
import shadow_core as sc
from faction_crud import FactionError, FlowResult
from faction_notify import CATEGORY_PROGRESS, CATEGORY_SYSTEM, Notice

PAGE_SIZE_MAX = 50
MAX_RANK_MARKS = 1_000_000
MAX_QM_DISCOUNT = 50

MSG_NAME = "Название: от 1 до 100 символов"
MSG_NAME_TAKEN = "Фракция с таким названием уже есть"
MSG_DESCRIPTION = "Описание слишком длинное (до 5000 символов)"
MSG_EMBLEM = "Герб: нужна ссылка https:// (до 512 символов)"
MSG_HQ = "Локация штаба не найдена"
MSG_LEADERS_MAX = "Руководителей может быть не больше 5"
MSG_LEADER_NPC = "Руководителем может быть только существующий NPC"
MSG_MEMBER_LIMIT = "Лимит участников: от 1 до 100000 (или пусто — без лимита)"
MSG_SORT = "Порядок: от -100000 до 100000"
MSG_DELETE_USED = "Фракцию, в которой были участники, можно только скрыть"
MSG_DELETE_TREASURY = "В казне фракции остались марки — сначала обнулите казну"
MSG_DELETE_DEBTS = "У фракции есть долги перед игроками — её можно только скрыть"
MSG_RANK_IN_QM = "Звание используется в ассортименте интенданта"
MSG_RANK_IN_ACCESS = "Звание используется как условие доступа к территории"
MSG_DELETE_ITEM_STOCK = "На складе фракции остались предметы"
MSG_RANK_MARKS = "Марки за звание: от 0 до 1000000"
MSG_RANK_DISCOUNT = "Скидка у интенданта для звания: от 0 до 50 %"
MSG_RANK_NOT_FOUND = "Звание не найдено"
MSG_RANK_USED = "Звание уже получено участниками — его нельзя удалить"
MSG_RANK_POINTS = "Очки для звания: от 0 до 10000000"
MSG_RANK_LEVEL = "Уровень для звания: от 0 до 1000"
MSG_RANK_XP = "Опыт за звание: от 0 до 10000000"
MSG_QUEST_NOT_FOUND = "Задание не найдено"
MSG_QUEST_REPEATABLE = "Условием может быть только неповторяемое задание"
MSG_TITLE_NOT_FOUND = "Титул не найден"
MSG_ITEMS_MAX = "Предметов в награде может быть не больше 10"
MSG_ITEM_QTY = "Количество предмета: от 1 до 999"
MSG_ITEM_NOT_FOUND = "Предмет не найден: #{id}"
MSG_ITEM_DUP = "Предмет указан дважды: #{id}"
MSG_VOUCHER_LOCATION = "Локация для права на дом / участок не найдена"
MSG_ORDER = "Нужно перечислить все звания фракции ровно по одному разу"
MSG_COND_MAX = "Условий вступления может быть не больше 20"
MSG_COND_TYPE = "Неизвестный тип условия: {type}"
MSG_COND_KEYS = "Лишние параметры условия «{type}»: {keys}"
MSG_HOST_SELF = "Фракция не может враждовать сама с собой"
MSG_HOST_DUP = "Такая пара враждебных фракций уже есть"
MSG_HOST_NOT_FOUND = "Пара враждебных фракций не найдена"
MSG_REASON = "Причина: от 3 до 500 символов"
MSG_DELTA = "Изменение очков: от -100000 до 100000, не 0"
MSG_MEMBER_NOT_FOUND = "Участник не найден"
MSG_MEMBER_NOT_ACTIVE = "Персонаж не состоит во фракции"
MSG_DELIVERY_NOT_FOUND = "Выдача награды не найдена"
MSG_DELIVERY_NOT_FAILED = "Повторить можно только неудавшуюся выдачу"
MSG_STATUS = "Неизвестный статус"

SETTINGS_LABELS = {
    "warning_days": "Дней до исключения после предупреждения",
    "rejoin_cooldown_days": "Дней до повторного вступления",
    "leave_burn_pct": "Сгорает очков при выходе, %",
    "hostile_penalty_pct": "Штраф враждебной фракции, %",
    "reapply_cooldown_hours": "Часов до повторной заявки",
}

_COND_KEYS = {
    fc.COND_REGION: ({"region_id", "min_tier"}, {"region_id", "min_tier"}),
    fc.COND_FAME: (set(), {"min_tier", "max_tier"}),
    fc.COND_INFAMY: (set(), {"min_tier", "max_tier"}),
    fc.COND_LEVEL: ({"min_level"}, {"min_level"}),
    fc.COND_CLASS: ({"class_ids"}, {"class_ids"}),
    fc.COND_SUBCLASS: ({"subclass_keys"}, {"subclass_keys"}),
    fc.COND_RACE: ({"race_ids"}, {"race_ids", "subrace_ids"}),
    fc.COND_QUEST: ({"quest_id"}, {"quest_id"}),
    fc.COND_NOT_IN: ({"faction_id"}, {"faction_id"}),
}


def _err(detail: str, status: int = 422) -> FactionError:
    return FactionError(status, detail)


def _int(value, message: str) -> int:
    if isinstance(value, bool):
        raise _err(message)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _err(message)


def _existing_ids(db: Session, sql_table: str, id_col: str, ids: Iterable[int], extra: str = "") -> Set[int]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return set()
    ph, params = fcr.in_clause("x", ids)
    rows = db.execute(text(f"SELECT {id_col} FROM {sql_table} WHERE {id_col} IN ({ph}){extra}"), params).fetchall()
    return {int(r[0]) for r in rows}


def _location_exists(db: Session, location_id: int) -> bool:
    return bool(_existing_ids(db, "Locations", "id", [location_id]))


def _check_quest(db: Session, quest_id) -> int:
    qid = _int(quest_id, MSG_QUEST_NOT_FOUND)
    row = db.execute(text("SELECT quest_type FROM quests WHERE id = :q"), {"q": qid}).first()
    if row is None:
        raise _err(MSG_QUEST_NOT_FOUND)
    if (row[0] or "standard") == "repeatable":
        raise _err(MSG_QUEST_REPEATABLE)
    return qid


def _reason(value: Optional[str]) -> str:
    reason = (value or "").strip()
    if not 3 <= len(reason) <= 500:
        raise _err(MSG_REASON)
    return reason


def _page(page: int, page_size: int) -> Tuple[int, int]:
    return max(1, int(page)), max(1, min(PAGE_SIZE_MAX, int(page_size)))


# =====================================================================================================================
# factions
# =====================================================================================================================

def _validate_faction(db: Session, body, faction_id: Optional[int]) -> dict:
    name = (body.name or "").strip()
    if not 1 <= len(name) <= 100:
        raise _err(MSG_NAME)
    clash = db.query(models.Faction.id).filter(models.Faction.name == name)
    if faction_id is not None:
        clash = clash.filter(models.Faction.id != int(faction_id))
    if clash.first() is not None:
        raise _err(MSG_NAME_TAKEN, 409)
    description = (body.description or "").strip() or None
    if description and len(description) > 5000:
        raise _err(MSG_DESCRIPTION)
    emblem = (body.emblem_url or "").strip() or None
    if emblem and (not emblem.lower().startswith("https://") or len(emblem) > 512):
        raise _err(MSG_EMBLEM)
    hq = body.hq_location_id
    if hq is not None and not _location_exists(db, hq):
        raise _err(MSG_HQ)
    leaders = list(dict.fromkeys(int(x) for x in (body.leader_npc_ids or [])))
    if len(leaders) > fc.MAX_LEADERS:
        raise _err(MSG_LEADERS_MAX)
    if leaders and _existing_ids(db, "characters", "id", leaders, " AND is_npc = 1") != set(leaders):
        raise _err(MSG_LEADER_NPC)
    limit = body.member_limit
    if limit is not None and not 1 <= int(limit) <= fc.MAX_MEMBER_LIMIT:
        raise _err(MSG_MEMBER_LIMIT)
    if not -100000 <= int(body.sort_order) <= 100000:
        raise _err(MSG_SORT)
    return {"name": name, "description": description, "emblem_url": emblem,
            "hq_location_id": int(hq) if hq is not None else None, "leader_npc_ids": leaders or None,
            "member_limit": int(limit) if limit is not None else None, "is_invite_only": bool(body.is_invite_only),
            "is_secret": bool(body.is_secret), "is_active": bool(body.is_active), "sort_order": int(body.sort_order)}


def create_faction(db: Session, body, now: Optional[datetime] = None) -> int:
    now = now or fcr.now_utc()
    faction = models.Faction(**_validate_faction(db, body, None), created_at=now, updated_at=now)
    db.add(faction)
    db.flush()
    db.add(models.FactionEconomy(faction_id=int(faction.id), updated_at=now))      # FEAT-206: 1:1 economy row
    db.flush()
    return int(faction.id)


def update_faction(db: Session, faction_id: int, body, now: Optional[datetime] = None) -> int:
    now = now or fcr.now_utc()
    faction = fcr.faction_or_404(db, faction_id)
    for key, value in _validate_faction(db, body, faction.id).items():
        setattr(faction, key, value)
    faction.updated_at = now
    db.flush()
    return int(faction.id)


def delete_faction(db: Session, faction_id: int) -> None:
    faction = fcr.faction_or_404(db, faction_id)
    fid = int(faction.id)
    used = (db.query(models.FactionMember.id).filter(models.FactionMember.faction_id == fid).first()
            or db.query(models.FactionApplication.id).filter(models.FactionApplication.faction_id == fid).first()
            or db.query(models.FactionRankGrant.id).filter(models.FactionRankGrant.faction_id == fid).first())
    if used is not None:
        raise _err(MSG_DELETE_USED, 409)
    # FEAT-206 §3.3: money in the treasury or any debt row blocks the delete
    import econ_core as core
    import econ_ledger
    import faction_econ_crud
    if faction_econ_crud.treasury_balance(db, fid) != 0:
        raise _err(MSG_DELETE_TREASURY, 409)
    if db.query(models.FactionDebt.id).filter(models.FactionDebt.faction_id == fid).first() is not None:
        raise _err(MSG_DELETE_DEBTS, 409)
    if db.query(models.FactionItemStock.item_id).filter(models.FactionItemStock.faction_id == fid,
                                                        models.FactionItemStock.quantity > 0).first() is not None:
        raise _err(MSG_DELETE_ITEM_STOCK, 409)                                       # FEAT-207
    econ_ledger.deactivate_account(db, core.AccountRef.faction(fid))
    # FEAT-207 rows (ON DELETE CASCADE in MySQL; explicit for engines without FK enforcement)
    for model in (models.FactionAccessRule, models.FactionEnemy, models.FactionOutlawRegion, models.FactionPvpKill,
                  models.FactionItemStock):
        db.query(model).filter(model.faction_id == fid).delete(synchronize_session=False)
    db.query(models.FactionQmItem).filter(models.FactionQmItem.faction_id == fid).delete(synchronize_session=False)
    db.query(models.FactionQuartermaster).filter(models.FactionQuartermaster.faction_id == fid).delete(
        synchronize_session=False)
    for model in (models.FactionEconHistory, models.FactionDonationDay, models.FactionQmPurchase,
                  models.FactionEconomy):
        db.query(model).filter(model.faction_id == fid).delete(synchronize_session=False)
    db.query(models.FactionLog).filter(models.FactionLog.faction_id == fid).delete(synchronize_session=False)
    db.query(models.FactionHostility).filter(or_(models.FactionHostility.faction_a_id == fid,
                                                 models.FactionHostility.faction_b_id == fid)).delete(
        synchronize_session=False)
    db.query(models.FactionCondition).filter(models.FactionCondition.faction_id == fid).delete(
        synchronize_session=False)
    db.query(models.FactionRank).filter(models.FactionRank.faction_id == fid).delete(synchronize_session=False)
    db.delete(faction)
    db.flush()


def _counts(db: Session, model, column, ids: Sequence[int], *filters) -> Dict[int, int]:
    if not ids:
        return {}
    rows = (db.query(column, func.count(model.id)).filter(column.in_(list(ids)), *filters)
            .group_by(column).all())
    return {int(r[0]): int(r[1]) for r in rows}


def admin_list(db: Session) -> List[dict]:
    factions = db.query(models.Faction).order_by(models.Faction.sort_order, models.Faction.id).all()
    ids = [int(f.id) for f in factions]
    members = _counts(db, models.FactionMember, models.FactionMember.faction_id, ids,
                      models.FactionMember.status == fc.STATUS_ACTIVE)
    pending = _counts(db, models.FactionApplication, models.FactionApplication.faction_id, ids,
                      models.FactionApplication.status == fc.APP_PENDING)
    ranks = _counts(db, models.FactionRank, models.FactionRank.faction_id, ids)
    conds = _counts(db, models.FactionCondition, models.FactionCondition.faction_id, ids)
    return [{"id": int(f.id), "name": f.name, "emblem_url": f.emblem_url, "is_active": bool(f.is_active),
             "is_secret": bool(f.is_secret), "is_invite_only": bool(f.is_invite_only),
             "member_limit": f.member_limit, "sort_order": int(f.sort_order),
             "member_count": members.get(int(f.id), 0), "pending_applications": pending.get(int(f.id), 0),
             "rank_count": ranks.get(int(f.id), 0), "condition_count": conds.get(int(f.id), 0)} for f in factions]


def _rank_out(rank: "models.FactionRank") -> dict:
    return {"id": int(rank.id), "faction_id": int(rank.faction_id), "name": rank.name,
            "description": rank.description, "sort_order": int(rank.sort_order),
            "min_points": int(rank.min_points or 0), "min_level": int(rank.min_level or 0),
            "required_quest_id": int(rank.required_quest_id) if rank.required_quest_id else None,
            "reward_xp": int(rank.reward_xp or 0), "reward_title_id": rank.reward_title_id,
            "reward_items": list(rank.reward_items or []),
            "reward_house_location_id": rank.reward_house_location_id,
            "reward_plot_location_id": rank.reward_plot_location_id,
            "reward_marks": int(rank.reward_marks or 0), "qm_discount_pct": int(rank.qm_discount_pct or 0),
            # FEAT-207: battle-time passive (cumulative up the ladder)
            "passive_name": rank.passive_name, "passive_description": rank.passive_description,
            "passive_modifiers": fc.clean_modifiers(rank.passive_modifiers) or None}


def _admin_conditions(db: Session, conditions: List[Tuple[str, dict]]) -> List[dict]:
    refs = fcr.load_refs(db, conditions)
    return [{"type": t, "params": p, "text": fc.condition_text(t, p, refs, reveal_secret=True)}
            for t, p in conditions]


def _hostilities_out(db: Session, rows) -> List[dict]:
    ids = {int(r.faction_a_id) for r in rows} | {int(r.faction_b_id) for r in rows}
    names = {int(f.id): f.name for f in db.query(models.Faction).filter(models.Faction.id.in_(sorted(ids))).all()} \
        if ids else {}
    return [{"id": int(r.id), "faction_a_id": int(r.faction_a_id), "faction_a_name": names.get(int(r.faction_a_id)),
             "faction_b_id": int(r.faction_b_id), "faction_b_name": names.get(int(r.faction_b_id)),
             "irreconcilable": bool(r.irreconcilable), "created_at": r.created_at} for r in rows]


def admin_detail(db: Session, faction_id: int) -> dict:
    f = fcr.faction_or_404(db, faction_id)
    fid = int(f.id)
    ranks = fcr.load_ranks(db, [fid]).get(fid, [])
    conds = fcr.load_conditions(db, [fid]).get(fid, [])
    hostilities = (db.query(models.FactionHostility)
                   .filter(or_(models.FactionHostility.faction_a_id == fid, models.FactionHostility.faction_b_id == fid))
                   .order_by(models.FactionHostility.id).all())
    hq_name = fcr.location_names(db, [f.hq_location_id]).get(int(f.hq_location_id)) if f.hq_location_id else None
    leaders = fcr.character_brief(db, f.leader_npc_ids or [])
    return {
        "id": fid, "name": f.name, "description": f.description, "emblem_url": f.emblem_url,
        "hq_location_id": f.hq_location_id, "hq_location_name": hq_name,
        "leader_npc_ids": list(f.leader_npc_ids or []),
        "leaders": [{"id": int(x), "name": leaders.get(int(x), {}).get("name"),
                     "avatar": leaders.get(int(x), {}).get("avatar")} for x in f.leader_npc_ids or []],
        "member_limit": f.member_limit, "is_invite_only": bool(f.is_invite_only), "is_secret": bool(f.is_secret),
        "is_active": bool(f.is_active), "sort_order": int(f.sort_order), "created_at": f.created_at,
        "updated_at": f.updated_at, "member_count": fcr.active_count(db, fid),
        "ranks": [_rank_out(r) for r in ranks],
        "conditions": _admin_conditions(db, conds),
        "hostilities": _hostilities_out(db, hostilities),
    }


# =====================================================================================================================
# ranks
# =====================================================================================================================

def _validate_rank(db: Session, body) -> dict:
    name = (body.name or "").strip()
    if not 1 <= len(name) <= 100:
        raise _err(MSG_NAME)
    description = (body.description or "").strip() or None
    if description and len(description) > 5000:
        raise _err(MSG_DESCRIPTION)
    if not 0 <= int(body.min_points) <= fc.MAX_POINTS_VALUE:
        raise _err(MSG_RANK_POINTS)
    if not 0 <= int(body.min_level) <= fc.MAX_LEVEL:
        raise _err(MSG_RANK_LEVEL)
    if not 0 <= int(body.reward_xp) <= fc.MAX_RANK_XP:
        raise _err(MSG_RANK_XP)
    quest_id = _check_quest(db, body.required_quest_id) if body.required_quest_id is not None else None
    title_id = body.reward_title_id
    if title_id is not None and db.query(models.Title.id_title).filter(
            models.Title.id_title == int(title_id)).first() is None:
        raise _err(MSG_TITLE_NOT_FOUND)
    items = []
    for item in body.reward_items or []:
        if not 1 <= int(item.quantity) <= fc.MAX_ITEM_QTY:
            raise _err(MSG_ITEM_QTY)
        if any(i["item_id"] == int(item.item_id) for i in items):
            raise _err(MSG_ITEM_DUP.format(id=int(item.item_id)))
        items.append({"item_id": int(item.item_id), "quantity": int(item.quantity)})
    if len(items) > fc.MAX_REWARD_ITEMS:
        raise _err(MSG_ITEMS_MAX)
    found = _existing_ids(db, "items", "id", [i["item_id"] for i in items])
    for item in items:
        if item["item_id"] not in found:
            raise _err(MSG_ITEM_NOT_FOUND.format(id=item["item_id"]))
    for loc in (body.reward_house_location_id, body.reward_plot_location_id):
        if loc is not None and not _location_exists(db, loc):
            raise _err(MSG_VOUCHER_LOCATION)
    extra = {}
    if getattr(body, "reward_marks", None) is not None:            # FEAT-206; omitted = keep / default 0
        marks = _int(body.reward_marks, MSG_RANK_MARKS)
        if not 0 <= marks <= MAX_RANK_MARKS:
            raise _err(MSG_RANK_MARKS)
        extra["reward_marks"] = marks
    if getattr(body, "qm_discount_pct", None) is not None:
        discount = _int(body.qm_discount_pct, MSG_RANK_DISCOUNT)
        if not 0 <= discount <= MAX_QM_DISCOUNT:
            raise _err(MSG_RANK_DISCOUNT)
        extra["qm_discount_pct"] = discount
    # FEAT-207: passive — omitted modifiers on update keep the stored passive; {} / null with the key present clears
    if "passive_modifiers" in getattr(body, "__fields_set__", set()) or getattr(body, "passive_modifiers", None):
        try:
            p_name, p_desc, p_mods = fc.validate_passive(getattr(body, "passive_name", None),
                                                         getattr(body, "passive_description", None),
                                                         getattr(body, "passive_modifiers", None))
        except fc.PassiveError as exc:
            raise _err(str(exc))
        extra.update(passive_name=p_name, passive_description=p_desc, passive_modifiers=p_mods)
    return {**extra,"name": name, "description": description, "min_points": int(body.min_points),
            "min_level": int(body.min_level), "required_quest_id": quest_id, "reward_xp": int(body.reward_xp),
            "reward_title_id": int(title_id) if title_id is not None else None, "reward_items": items or None,
            "reward_house_location_id": int(body.reward_house_location_id)
            if body.reward_house_location_id is not None else None,
            "reward_plot_location_id": int(body.reward_plot_location_id)
            if body.reward_plot_location_id is not None else None}


def _rank_or_404(db: Session, rank_id: int) -> "models.FactionRank":
    rank = db.get(models.FactionRank, int(rank_id))
    if rank is None:
        raise _err(MSG_RANK_NOT_FOUND, 404)
    return rank


def create_rank(db: Session, faction_id: int, body, now: Optional[datetime] = None) -> dict:
    now = now or fcr.now_utc()
    faction = fcr.faction_or_404(db, faction_id)
    data = _validate_rank(db, body)
    top = db.query(func.max(models.FactionRank.sort_order)).filter(
        models.FactionRank.faction_id == int(faction.id)).scalar()
    rank = models.FactionRank(faction_id=int(faction.id), sort_order=int(top or 0) + 1, created_at=now, **data)
    db.add(rank)
    db.flush()
    return _rank_out(rank)


def update_rank(db: Session, rank_id: int, body) -> dict:
    rank = _rank_or_404(db, rank_id)
    for key, value in _validate_rank(db, body).items():
        setattr(rank, key, value)
    db.flush()
    return _rank_out(rank)


def delete_rank(db: Session, rank_id: int) -> None:
    rank = _rank_or_404(db, rank_id)
    held = db.query(models.FactionMember.id).filter(models.FactionMember.rank_id == int(rank.id)).first()
    granted = db.query(models.FactionRankGrant.id).filter(models.FactionRankGrant.rank_id == int(rank.id)).first()
    if held is not None or granted is not None:
        raise _err(MSG_RANK_USED, 409)
    if db.query(models.FactionQmItem.id).filter(models.FactionQmItem.min_rank_id == int(rank.id)).first():
        raise _err(MSG_RANK_IN_QM, 409)
    if db.query(models.FactionAccessRule.id).filter(models.FactionAccessRule.min_rank_id == int(rank.id)).first():
        raise _err(MSG_RANK_IN_ACCESS, 409)                                          # FEAT-207
    db.delete(rank)
    db.flush()


def reorder_ranks(db: Session, faction_id: int, rank_ids: List[int]) -> List[dict]:
    faction = fcr.faction_or_404(db, faction_id)
    ranks = fcr.load_ranks(db, [faction.id]).get(int(faction.id), [])
    wanted = [int(r) for r in rank_ids]
    if len(wanted) != len(set(wanted)) or set(wanted) != {int(r.id) for r in ranks}:
        raise _err(MSG_ORDER)
    by_id = {int(r.id): r for r in ranks}
    for position, rid in enumerate(wanted, start=1):
        by_id[rid].sort_order = position
    db.flush()
    return [_rank_out(by_id[rid]) for rid in wanted]


# =====================================================================================================================
# entry conditions
# =====================================================================================================================

def _id_list(value, max_items: int, message: str) -> List[int]:
    if not isinstance(value, list) or not 1 <= len(value) <= max_items:
        raise _err(message)
    out = list(dict.fromkeys(_int(v, message) for v in value))
    if any(v < 1 for v in out):
        raise _err(message)
    return out


def _tier_range(params: dict, codes: Sequence[str], label: str) -> dict:
    lo, hi = params.get("min_tier"), params.get("max_tier")
    lo = lo or None
    hi = hi or None
    if lo is None and hi is None:
        raise _err(f"{label}: укажите ступень «не ниже» и/или «не выше»")
    for code in (lo, hi):
        if code is not None and code not in codes:
            raise _err(f"{label}: неизвестная ступень «{code}»")
    if lo is not None and hi is not None and codes.index(lo) > codes.index(hi):
        raise _err(f"{label}: «не ниже» должна быть не выше «не выше»")
    out = {}
    if lo is not None:
        out["min_tier"] = lo
    if hi is not None:
        out["max_tier"] = hi
    return out


def validate_condition(db: Session, faction_id: int, cond_type: str, params: dict) -> dict:
    if cond_type not in _COND_KEYS:
        raise _err(MSG_COND_TYPE.format(type=cond_type))
    required, allowed = _COND_KEYS[cond_type]
    params = dict(params or {})
    extra = set(params) - allowed
    if extra:
        raise _err(MSG_COND_KEYS.format(type=cond_type, keys=", ".join(sorted(extra))))
    missing = required - {k for k, v in params.items() if v is not None}
    if missing:
        raise _err(f"Условие «{cond_type}»: не заполнено — {', '.join(sorted(missing))}")
    if cond_type == fc.COND_REGION:
        region_id = _int(params["region_id"], "Край не найден")
        if not _existing_ids(db, "Regions", "id", [region_id]):
            raise _err("Край не найден")
        if params["min_tier"] not in rc.TIER_CODES:
            raise _err(f"Репутация: неизвестная ступень «{params['min_tier']}»")
        return {"region_id": region_id, "min_tier": params["min_tier"]}
    if cond_type == fc.COND_FAME:
        return _tier_range(params, sc.FAME_CODES, "Слава")
    if cond_type == fc.COND_INFAMY:
        return _tier_range(params, sc.INFAMY_CODES, "Слухи")
    if cond_type == fc.COND_LEVEL:
        level = _int(params["min_level"], "Уровень: от 1 до 1000")
        if not 1 <= level <= fc.MAX_LEVEL:
            raise _err("Уровень: от 1 до 1000")
        return {"min_level": level}
    if cond_type == fc.COND_CLASS:
        ids = _id_list(params["class_ids"], fc.MAX_CLASS_IDS, "Классы: от 1 до 20")
        if _existing_ids(db, "classes", "id_class", ids) != set(ids):
            raise _err("Класс не найден")
        return {"class_ids": ids}
    if cond_type == fc.COND_SUBCLASS:
        keys = params["subclass_keys"]
        if not isinstance(keys, list) or not 1 <= len(keys) <= fc.MAX_SUBCLASS_KEYS:
            raise _err("Подклассы: от 1 до 30")
        keys = list(dict.fromkeys(str(k) for k in keys))
        if any(not re.match(fc.SUBCLASS_KEY_RE, k) for k in keys):
            raise _err("Подкласс: неверный ключ")
        return {"subclass_keys": keys}
    if cond_type == fc.COND_RACE:
        ids = _id_list(params["race_ids"], fc.MAX_RACE_IDS, "Расы: от 1 до 30")
        if _existing_ids(db, "races", "id_race", ids) != set(ids):
            raise _err("Раса не найдена")
        out = {"race_ids": ids}
        if params.get("subrace_ids"):
            sub = _id_list(params["subrace_ids"], fc.MAX_RACE_IDS, "Подрасы: от 1 до 30")
            if _existing_ids(db, "subraces", "id_subrace", sub) != set(sub):
                raise _err("Подраса не найдена")
            out["subrace_ids"] = sub
        return out
    if cond_type == fc.COND_QUEST:
        return {"quest_id": _check_quest(db, params["quest_id"])}
    other = _int(params["faction_id"], MSG_FACTION_NOT_FOUND_TEXT)
    if other == int(faction_id):
        raise _err("Условие не может ссылаться на саму фракцию")
    if db.get(models.Faction, other) is None:
        raise _err(MSG_FACTION_NOT_FOUND_TEXT)
    return {"faction_id": other}


MSG_FACTION_NOT_FOUND_TEXT = fcr.MSG_FACTION_NOT_FOUND


def set_conditions(db: Session, faction_id: int, conditions) -> List[dict]:
    faction = fcr.faction_or_404(db, faction_id)
    if len(conditions) > fc.MAX_CONDITIONS:
        raise _err(MSG_COND_MAX)
    validated = [(c.type, validate_condition(db, faction.id, c.type, c.params)) for c in conditions]
    db.query(models.FactionCondition).filter(models.FactionCondition.faction_id == int(faction.id)).delete(
        synchronize_session=False)
    for position, (cond_type, params) in enumerate(validated):
        db.add(models.FactionCondition(faction_id=int(faction.id), cond_type=cond_type, params=params,
                                       sort_order=position))
    db.flush()
    return _admin_conditions(db, validated)


# =====================================================================================================================
# hostilities
# =====================================================================================================================

def list_hostilities(db: Session) -> List[dict]:
    return _hostilities_out(db, fcr.hostility_rows(db))


def _validate_pair(db: Session, body, hostility_id: Optional[int]) -> Tuple[int, int]:
    if int(body.faction_a_id) == int(body.faction_b_id):
        raise _err(MSG_HOST_SELF)
    a, b = fc.pair(body.faction_a_id, body.faction_b_id)
    if db.get(models.Faction, a) is None or db.get(models.Faction, b) is None:
        raise _err(fcr.MSG_FACTION_NOT_FOUND)
    clash = db.query(models.FactionHostility.id).filter(models.FactionHostility.faction_a_id == a,
                                                        models.FactionHostility.faction_b_id == b)
    if hostility_id is not None:
        clash = clash.filter(models.FactionHostility.id != int(hostility_id))
    if clash.first() is not None:
        raise _err(MSG_HOST_DUP, 409)
    return a, b


def create_hostility(db: Session, body, now: Optional[datetime] = None) -> dict:
    a, b = _validate_pair(db, body, None)
    row = models.FactionHostility(faction_a_id=a, faction_b_id=b, irreconcilable=bool(body.irreconcilable),
                                  created_at=now or fcr.now_utc())
    db.add(row)
    db.flush()
    return _hostilities_out(db, [row])[0]


def _hostility_or_404(db: Session, hostility_id: int) -> "models.FactionHostility":
    row = db.get(models.FactionHostility, int(hostility_id))
    if row is None:
        raise _err(MSG_HOST_NOT_FOUND, 404)
    return row


def update_hostility(db: Session, hostility_id: int, body) -> dict:
    row = _hostility_or_404(db, hostility_id)
    row.faction_a_id, row.faction_b_id = _validate_pair(db, body, row.id)
    row.irreconcilable = bool(body.irreconcilable)
    db.flush()
    return _hostilities_out(db, [row])[0]


def delete_hostility(db: Session, hostility_id: int) -> None:
    db.delete(_hostility_or_404(db, hostility_id))
    db.flush()


# =====================================================================================================================
# applications
# =====================================================================================================================

def _class_names(db: Session, ids: Iterable) -> Dict[int, str]:
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    return {int(c.id_class): c.name for c in db.query(models.Class).filter(models.Class.id_class.in_(ids)).all()}


def list_applications(db: Session, status: Optional[str], faction_id: Optional[int], page: int,
                      page_size: int) -> dict:
    page, page_size = _page(page, page_size)
    if status is not None and status not in fc.APP_STATUSES:
        raise _err(MSG_STATUS)
    query = db.query(models.FactionApplication)
    if status:
        query = query.filter(models.FactionApplication.status == status)
    if faction_id:
        query = query.filter(models.FactionApplication.faction_id == int(faction_id))
    total = query.count()
    rows = (query.order_by((models.FactionApplication.status != fc.APP_PENDING), models.FactionApplication.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    chars = fcr.character_brief(db, [r.character_id for r in rows])
    classes = _class_names(db, [c["class_id"] for c in chars.values()])
    fids = sorted({int(r.faction_id) for r in rows})
    factions = {int(f.id): f for f in db.query(models.Faction).filter(models.Faction.id.in_(fids)).all()} \
        if fids else {}
    conds = fcr.load_conditions(db, fids)
    irr = fcr.hostile_map(db, irreconcilable_only=True)
    items = []
    for row in rows:
        ch = chars.get(int(row.character_id))
        conditions = []
        if row.status == fc.APP_PENDING:
            entry = fcr.entry_conditions(int(row.faction_id), conds, irr)
            refs = fcr.load_refs(db, entry)
            ch_row = fcr.character_row(db, row.character_id)
            facts = fcr.load_facts(db, ch_row, entry, refs) if ch_row is not None else None
            conditions = [{"type": t, "text": fc.condition_text(t, p, refs, reveal_secret=True),
                           "met": None if facts is None else fc.condition_met(t, p, facts, refs)}
                          for t, p in entry]
        faction = factions.get(int(row.faction_id))
        items.append({
            "id": int(row.id), "status": row.status, "message": row.message, "created_at": row.created_at,
            "decided_at": row.decided_at, "decided_by_user_id": row.decided_by_user_id,
            "reject_reason": row.reject_reason,
            "faction": {"id": int(row.faction_id), "name": faction.name if faction else None},
            "character": {"id": int(row.character_id), "name": ch["name"] if ch else None,
                          "level": ch["level"] if ch else None, "avatar": ch["avatar"] if ch else None,
                          "class_id": ch["class_id"] if ch else None,
                          "class_name": classes.get(int(ch["class_id"])) if ch and ch["class_id"] else None},
            "conditions": conditions,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


def _application_or_404(db: Session, application_id: int) -> "models.FactionApplication":
    row = db.get(models.FactionApplication, int(application_id))
    if row is None:
        raise _err(fcr.MSG_APP_NOT_FOUND, 404)
    return row


def approve(db: Session, application_id: int, actor_user_id: int, now: Optional[datetime] = None) -> FlowResult:
    now = now or fcr.now_utc()
    application = _application_or_404(db, application_id)
    updated = db.execute(text(
        "UPDATE faction_applications SET status = :a, pending_key = NULL, decided_by_user_id = :u, decided_at = :now "
        "WHERE id = :id AND status = :p"),
        {"a": fc.APP_APPROVED, "p": fc.APP_PENDING, "u": actor_user_id, "now": now, "id": int(application.id)}).rowcount
    if not updated:
        raise _err(fcr.MSG_APP_NOT_PENDING, 409)
    ch = fcr.require_character(db, application.character_id)
    faction = fcr.faction_or_404(db, application.faction_id, lock=True)
    member = fcr.member_row(db, ch.id, faction.id, lock=True)
    own, irreconcilable, refs, facts = fcr._entry_context(db, ch, faction.id)
    error = fcr.entry_check(db, ch, faction, member, fcr.load_settings(db), now, mode=fcr.MODE_APPROVE,
                            conditions=own, irreconcilable=irreconcilable, facts=facts, refs=refs)
    if error is not None:
        raise _err(error.detail, 409)          # rollback upstream: the application stays pending
    fcr.log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_APP_APPROVED, now=now,
                  actor_user_id=actor_user_id)
    result = fcr.admit(db, ch, faction, member, now, facts=facts, actor_user_id=actor_user_id)
    result.notices.insert(0, Notice(ch.user_id, f"Ваша заявка во фракцию «{faction.name}» одобрена",
                                    CATEGORY_PROGRESS, {"faction_id": int(faction.id), "character_id": ch.id,
                                                        "event": fc.EV_APP_APPROVED}))
    result.data["application_id"] = int(application.id)
    return result


def reject(db: Session, application_id: int, reason: Optional[str], actor_user_id: int,
           now: Optional[datetime] = None) -> FlowResult:
    now = now or fcr.now_utc()
    application = _application_or_404(db, application_id)
    reason = (reason or "").strip() or None
    if reason and len(reason) > 500:
        raise _err(MSG_REASON)
    updated = db.execute(text(
        "UPDATE faction_applications SET status = :r, pending_key = NULL, decided_by_user_id = :u, decided_at = :now, "
        "reject_reason = :reason WHERE id = :id AND status = :p"),
        {"r": fc.APP_REJECTED, "p": fc.APP_PENDING, "u": actor_user_id, "now": now, "reason": reason,
         "id": int(application.id)}).rowcount
    if not updated:
        raise _err(fcr.MSG_APP_NOT_PENDING, 409)
    faction = fcr.faction_or_404(db, application.faction_id)
    fcr.log_event(db, character_id=application.character_id, faction_id=faction.id, event_type=fc.EV_APP_REJECTED,
                  now=now, reason=reason, actor_user_id=actor_user_id)
    ch = fcr.character_row(db, application.character_id)
    result = FlowResult(data={"application_id": int(application.id)})
    if ch is not None:
        message = f"Ваша заявка во фракцию «{faction.name}» отклонена"
        if reason:
            message += f": {reason}"
        result.notices.append(Notice(ch.user_id, message, CATEGORY_SYSTEM,
                                     {"faction_id": int(faction.id), "character_id": ch.id,
                                      "event": fc.EV_APP_REJECTED}))
    return result


# =====================================================================================================================
# members
# =====================================================================================================================

def _member_out(member: "models.FactionMember", ch: Optional[dict], rank_names: Dict[int, str],
                s: fc.FactionSettings, now: datetime) -> dict:
    warning = None
    if member.status == fc.STATUS_ACTIVE and member.warning_at is not None:
        warning = {"at": member.warning_at, "reasons": list(member.warning_reasons or []),
                   "remaining_seconds": fc.remaining_seconds(fc.warning_deadline(member.warning_at, s), now)}
    return {"membership_id": int(member.id), "faction_id": int(member.faction_id),
            "character": {"id": int(member.character_id), "name": ch["name"] if ch else None,
                          "level": ch["level"] if ch else None, "avatar": ch["avatar"] if ch else None},
            "status": member.status, "points": int(member.points),
            "rank": ({"id": int(member.rank_id), "name": rank_names.get(int(member.rank_id))}
                     if member.rank_id else None),
            "warning": warning, "joined_at": member.joined_at, "left_at": member.left_at,
            "rejoin_after": member.rejoin_after}


def list_members(db: Session, faction_id: int, status: Optional[str], q: Optional[str], page: int,
                 page_size: int, now: Optional[datetime] = None) -> dict:
    now = now or fcr.now_utc()
    page, page_size = _page(page, page_size)
    faction = fcr.faction_or_404(db, faction_id)
    if status is not None and status not in fc.MEMBER_STATUSES:
        raise _err(MSG_STATUS)
    query = (db.query(models.FactionMember)
             .join(models.Character, models.Character.id == models.FactionMember.character_id)
             .filter(models.FactionMember.faction_id == int(faction.id)))
    if status:
        query = query.filter(models.FactionMember.status == status)
    needle = (q or "").strip()
    if needle:
        query = query.filter(models.Character.name.ilike(f"%{needle[:100]}%"))
    total = query.count()
    rows = (query.order_by(models.FactionMember.points.desc(), models.FactionMember.id)
            .offset((page - 1) * page_size).limit(page_size).all())
    chars = fcr.character_brief(db, [r.character_id for r in rows])
    rank_names = {int(r.id): r.name for r in fcr.load_ranks(db, [faction.id]).get(int(faction.id), [])}
    s = fcr.load_settings(db)
    return {"items": [_member_out(r, chars.get(int(r.character_id)), rank_names, s, now) for r in rows],
            "total": int(total), "page": page, "page_size": page_size}


def _member_or_404(db: Session, membership_id: int) -> "models.FactionMember":
    query = db.query(models.FactionMember).filter(models.FactionMember.id == int(membership_id))
    if fcr.for_update(db):
        query = query.with_for_update().populate_existing()
    member = query.first()
    if member is None:
        raise _err(MSG_MEMBER_NOT_FOUND, 404)
    return member


def admin_points(db: Session, membership_id: int, delta: int, reason: str, actor_user_id: int,
                 now: Optional[datetime] = None) -> FlowResult:
    """Manual points: no hostility penalty (§3.0 default 1); rank re-check after."""
    now = now or fcr.now_utc()
    if int(delta) == 0 or abs(int(delta)) > fc.MAX_ADMIN_DELTA:
        raise _err(MSG_DELTA)
    reason = _reason(reason)
    member = _member_or_404(db, membership_id)
    if member.status != fc.STATUS_ACTIVE:
        raise _err(MSG_MEMBER_NOT_ACTIVE, 409)
    faction = fcr.faction_or_404(db, member.faction_id)
    actual = fcr.change_points(db, member, int(delta), fc.EV_ADMIN_POINTS, now, reason=reason,
                               actor_user_id=actor_user_id)
    db.flush()
    result = fcr.recheck_ranks(db, member.character_id, now)
    ch = fcr.character_row(db, member.character_id)
    if ch is not None and actual:
        signed = f"+{actual}" if actual > 0 else f"−{abs(actual)}"
        result.notices.insert(0, Notice(ch.user_id, f"Очки фракции «{faction.name}»: {signed} ({reason})",
                                        CATEGORY_PROGRESS, {"faction_id": int(faction.id), "character_id": ch.id,
                                                            "event": fc.EV_ADMIN_POINTS}))
    result.data = {"membership_id": int(member.id), "points_delta": actual, "points_after": int(member.points),
                   "rank_id": member.rank_id}
    return result


def expel(db: Session, membership_id: int, reason: str, actor_user_id: int,
          now: Optional[datetime] = None) -> FlowResult:
    now = now or fcr.now_utc()
    reason = _reason(reason)
    member = _member_or_404(db, membership_id)
    if member.status != fc.STATUS_ACTIVE:
        raise _err(MSG_MEMBER_NOT_ACTIVE, 409)
    faction = fcr.faction_or_404(db, member.faction_id)
    points_after = fcr.depart(db, member, fc.STATUS_EXPELLED, now, fcr.load_settings(db), reason=reason,
                              actor_user_id=actor_user_id)
    result = FlowResult(data={"membership_id": int(member.id), "points_after": points_after,
                              "rejoin_in_seconds": fc.remaining_seconds(member.rejoin_after, now)})
    ch = fcr.character_row(db, member.character_id)
    if ch is not None:
        result.notices.append(fcr.expel_notice(ch, faction, reason))
    return result


# =====================================================================================================================
# admin character card, deliveries, settings
# =====================================================================================================================

def admin_character(db: Session, character_id: int, now: Optional[datetime] = None) -> dict:
    now = now or fcr.now_utc()
    ch = fcr.require_character(db, character_id)
    members = db.query(models.FactionMember).filter(models.FactionMember.character_id == ch.id).order_by(
        models.FactionMember.id).all()
    grants = db.query(models.FactionRankGrant).filter(models.FactionRankGrant.character_id == ch.id).order_by(
        models.FactionRankGrant.id).all()
    deliveries = (db.query(models.FactionRewardDelivery)
                  .filter(models.FactionRewardDelivery.character_id == ch.id)
                  .order_by(models.FactionRewardDelivery.id.desc()).limit(200).all())
    fids = sorted({int(m.faction_id) for m in members} | {int(g.faction_id) for g in grants})
    factions = {int(f.id): f for f in db.query(models.Faction).filter(models.Faction.id.in_(fids)).all()} \
        if fids else {}
    rank_names = {int(r.id): r.name for lst in fcr.load_ranks(db, fids).values() for r in lst}
    s = fcr.load_settings(db)
    brief = {"name": ch.name, "level": ch.level, "avatar": ch.avatar}
    memberships = []
    for m in members:
        f = factions.get(int(m.faction_id))
        out = _member_out(m, brief, rank_names, s, now)
        out["faction"] = {"id": int(m.faction_id), "name": f.name if f else None,
                          "is_secret": bool(f.is_secret) if f else False,
                          "is_active": bool(f.is_active) if f else False}
        memberships.append(out)
    grant_rows = {int(g.id): g for g in grants}
    return {
        "character": {"id": ch.id, "name": ch.name, "level": ch.level, "is_npc": ch.is_npc},
        "memberships": memberships,
        "grants": [{"id": int(g.id), "faction_id": int(g.faction_id),
                    "faction_name": factions[int(g.faction_id)].name if int(g.faction_id) in factions else None,
                    "rank_id": int(g.rank_id), "rank_name": rank_names.get(int(g.rank_id)),
                    "granted_at": g.granted_at} for g in grants],
        "deliveries": [{"id": int(d.id), "grant_id": int(d.grant_id),
                        "rank_name": rank_names.get(int(grant_rows[int(d.grant_id)].rank_id))
                        if int(d.grant_id) in grant_rows else None,
                        "kind": d.kind, "payload": d.payload, "status": d.status, "attempts": int(d.attempts),
                        "next_attempt_at": d.next_attempt_at, "last_error": d.last_error,
                        "updated_at": d.updated_at} for d in deliveries],
        "history": fcr.history(db, ch.id, 1, PAGE_SIZE_MAX, include_hidden=True)["items"],
        **_economy_extras(db, ch.id, factions),
    }


def _economy_extras(db: Session, character_id: int, factions: Dict[int, "models.Faction"]) -> dict:
    """FEAT-206: the character's faction debts (all statuses) and quartermaster purchases."""
    import faction_econ_crud
    import faction_qm_crud
    rows = (db.query(models.FactionDebt).filter(models.FactionDebt.character_id == int(character_id))
            .order_by(models.FactionDebt.id.desc()).limit(200).all())
    names = fcr.character_brief(db, [character_id])
    debts = []
    for row in rows:
        out = faction_econ_crud.debt_out(row, names)
        f = factions.get(int(row.faction_id)) or db.get(models.Faction, int(row.faction_id))
        out["faction_name"] = f.name if f is not None else None
        debts.append(out)
    return {"debts": debts, "qm_purchases": faction_qm_crud.character_purchases(db, character_id)}


def retry_delivery(db: Session, delivery_id: int, now: Optional[datetime] = None) -> int:
    """failed -> pending (attempts reset); returns the character id to deliver after the commit."""
    now = now or fcr.now_utc()
    row = db.get(models.FactionRewardDelivery, int(delivery_id))
    if row is None:
        raise _err(MSG_DELIVERY_NOT_FOUND, 404)
    updated = db.execute(text(
        "UPDATE faction_reward_deliveries SET status = :p, attempts = 0, next_attempt_at = :now, last_error = NULL, "
        "updated_at = :now WHERE id = :id AND status = :f"),
        {"p": fc.DLV_PENDING, "f": fc.DLV_FAILED, "now": now, "id": int(row.id)}).rowcount
    if not updated:
        raise _err(MSG_DELIVERY_NOT_FAILED, 409)
    return int(row.character_id)


def settings_out(db: Session) -> dict:
    import faction_econ_crud
    s = fcr.load_settings(db)
    out = {name: int(getattr(s, name)) for name in fc.SETTINGS_BOUNDS}
    econ = faction_econ_crud.load_econ_settings(db)                 # FEAT-206
    out.update({name: int(getattr(econ, name)) for name in fe.ECON_SETTINGS_BOUNDS})
    out["econ_enabled"] = bool(econ.econ_enabled)
    territory = fc.territory_settings_from_row(db.get(models.FactionSettings, 1))    # FEAT-207
    out.update({name: int(getattr(territory, name)) for name in fc.TERRITORY_SETTINGS_BOUNDS})
    return out


def update_settings(db: Session, body) -> dict:
    values = {}
    for name, (lo, hi) in fc.SETTINGS_BOUNDS.items():
        value = _int(getattr(body, name), f"{SETTINGS_LABELS[name]}: от {lo} до {hi}")
        if not lo <= value <= hi:
            raise _err(f"{SETTINGS_LABELS[name]}: от {lo} до {hi}")
        values[name] = value
    # FEAT-206 / FEAT-207: optional (an old client omitting them keeps the stored values)
    for name, (lo, hi, label) in list(fe.ECON_SETTINGS_BOUNDS.items()) + list(fc.TERRITORY_SETTINGS_BOUNDS.items()):
        raw = getattr(body, name, None)
        if raw is None:
            continue
        value = _int(raw, f"{label}: от {lo} до {hi}")
        if not lo <= value <= hi:
            raise _err(f"{label}: от {lo} до {hi}")
        values[name] = value
    if getattr(body, "econ_enabled", None) is not None:
        values["econ_enabled"] = bool(body.econ_enabled)
    row = db.get(models.FactionSettings, 1)
    if row is None:
        row = models.FactionSettings(id=1)
        db.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    db.flush()
    return settings_out(db)
