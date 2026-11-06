"""FEAT-207 factions stage 3 — rank passives (battle-time injection), enemies + kill points, admin enemies / outlaw
regions. features/FEAT-207 §3.5, §3.6, §3.9. Sync SQLAlchemy.

Kill points (:func:`apply_battle`, the battle-service callback): winners = player participants of ``winner_team``
(alive AND fallen, Q3); every loser counts as defeated. Per winner faction A (its ``faction_enemies``): a mob loser of
an A ``mob`` template, an NPC loser listed as A ``npc``, or — only in ``pvp_death`` / ``pvp_attack`` (Q2) — a player
loser who is an ACTIVE member of a NON-secret faction hostile to A (secret members never count) when A has a
``hostile`` row, once per victim per ``pvp_kill_repeat_hours``. Daily cap per (character, faction, UTC day) in
``faction_donation_days.kill_points`` (own counter). Idempotent per battle via ``faction_log`` UNIQUE(event_key,
faction_id), key ``faction:kill:b<battle>:c<character>``.

One transaction per winner (§3.10): faction_members (asc id) -> faction_donation_days (asc faction) ->
faction_pvp_kills (asc faction, victim) (+ rank grants / debt INSERTs via ``recheck_ranks``). Victims are never named.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import faction_core as fc
import faction_crud as fcr
import faction_econ_crud as fec
import models
from faction_crud import FactionError, FlowResult
from faction_notify import CATEGORY_PROGRESS, Notice

logger = logging.getLogger("character-service.faction_kills")

MSG_ENEMY_KIND = "Неизвестный тип врага: {kind}"
MSG_ENEMY_POINTS = "Очки за победу: от 1 до 10000"
MSG_ENEMIES_MAX = "Врагов может быть не больше 50"
MSG_ENEMY_DUP = "Враг указан дважды"
MSG_ENEMY_HOSTILE_ONE = "Строка «участники враждебных фракций» может быть только одна"
MSG_ENEMY_MOB = "Шаблон моба не найден"
MSG_ENEMY_NPC = "NPC не найден (нужен NPC, не моб)"
MSG_KILL_CAP = "Лимит очков за победы в день: от 0 до 100000 (или пусто — общий)"
MSG_OUTLAW_MAX = "Краёв может быть не больше 50"
MSG_OUTLAW_REGION = "Край не найден"
MSG_OUTLAW_LEVEL = "Неизвестная тяжесть: {code}"
MSG_OUTLAW_DUP = "Край указан дважды"
MSG_CAP_REACHED = "лимит на сегодня исчерпан"


def load_territory_settings(db: Session) -> fc.TerritorySettings:
    return fc.territory_settings_from_row(db.get(models.FactionSettings, 1))


# =====================================================================================================================
# passives (§3.5)
# =====================================================================================================================

def _passive_ranks(ranks: Sequence["models.FactionRank"]) -> List[fc.PassiveRank]:
    return [fc.PassiveRank(int(r.id), int(r.sort_order), r.name, r.passive_name, r.passive_description,
                           fc.clean_modifiers(r.passive_modifiers)) for r in ranks]


def passive_brief(rank: "models.FactionRank") -> Optional[dict]:
    mods = fc.clean_modifiers(rank.passive_modifiers)
    if not mods:
        return None
    return {"name": rank.passive_name or rank.name, "description": rank.passive_description, "modifiers": mods}


def member_passives(ranks: Sequence["models.FactionRank"], held_rank_id: Optional[int]) -> List[dict]:
    return [{"rank_id": p.id, "rank_name": p.name, "name": p.passive_name or p.name,
             "description": p.passive_description, "modifiers": dict(p.modifiers)}
            for p in fc.active_passives(_passive_ranks(ranks), held_rank_id)]


def passive_modifiers(db: Session, character_id: int) -> dict:
    """``GET /internal/factions/{cid}/passive-modifiers``: the sum over every ACTIVE membership (hidden factions too)."""
    row = db.execute(text("SELECT is_npc FROM characters WHERE id = :c"), {"c": int(character_id)}).first()
    if row is None or bool(row[0]):
        return {"modifiers": {}}
    members = (db.query(models.FactionMember)
               .filter(models.FactionMember.character_id == int(character_id),
                       models.FactionMember.status == fc.STATUS_ACTIVE).all())
    if not members:
        return {"modifiers": {}}
    ranks = fcr.load_ranks(db, [m.faction_id for m in members])
    groups = []
    for m in members:
        for p in fc.active_passives(_passive_ranks(ranks.get(int(m.faction_id), [])), m.rank_id):
            groups.append(p.modifiers)
    return {"modifiers": fc.sum_modifiers(groups)}


# =====================================================================================================================
# kill points (§3.6)
# =====================================================================================================================

def _characters(db: Session, ids: Sequence[int]) -> Dict[int, Tuple[bool, Optional[str], Optional[int]]]:
    """id -> (is_npc, npc_role, user_id)."""
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    ph, params = fcr.in_clause("c", ids)
    rows = db.execute(text(f"SELECT id, is_npc, npc_role, user_id FROM characters WHERE id IN ({ph})"),
                      params).fetchall()
    return {int(r[0]): (bool(r[1]), r[2], int(r[3]) if r[3] is not None else None) for r in rows}


def _active_memberships(db: Session, character_ids: Sequence[int], *, open_only: bool = False) -> Dict[int, Set[int]]:
    ids = sorted({int(i) for i in character_ids})
    if not ids:
        return {}
    ph, params = fcr.in_clause("c", ids)
    sql = (f"SELECT m.character_id, m.faction_id FROM faction_members m JOIN factions f ON f.id = m.faction_id "
           f"WHERE m.status = :s AND m.character_id IN ({ph})")
    if open_only:
        sql += " AND f.is_secret = 0"
    out: Dict[int, Set[int]] = {}
    for cid, fid in db.execute(text(sql), {"s": fc.STATUS_ACTIVE, **params}).fetchall():
        out.setdefault(int(cid), set()).add(int(fid))
    return out


def _enemies(db: Session, faction_ids: Iterable[int]) -> Dict[int, List["models.FactionEnemy"]]:
    ids = sorted({int(f) for f in faction_ids})
    out: Dict[int, List[models.FactionEnemy]] = {fid: [] for fid in ids}
    if not ids:
        return out
    for row in (db.query(models.FactionEnemy).filter(models.FactionEnemy.faction_id.in_(ids))
                .order_by(models.FactionEnemy.id).all()):
        out[int(row.faction_id)].append(row)
    return out


def kill_key(battle_id: int, character_id: int) -> str:
    return f"faction:kill:b{int(battle_id)}:c{int(character_id)}"


def _points_for(faction_id: int, enemies: Sequence["models.FactionEnemy"], losers: Sequence[dict],
                chars: Dict[int, tuple], victim_factions: Dict[int, Set[int]], hostile: Dict[int, Set[int]],
                pvp: bool) -> Tuple[List[int], List[Tuple[int, int]]]:
    """(points of non-PvP enemies, [(victim_id, points)] of PvP victims) for one winner faction."""
    mob_pts = {int(e.ref_id): int(e.points) for e in enemies if e.kind == fc.ENEMY_MOB}
    npc_pts = {int(e.ref_id): int(e.points) for e in enemies if e.kind == fc.ENEMY_NPC}
    hostile_pts = next((int(e.points) for e in enemies if e.kind == fc.ENEMY_HOSTILE), 0)
    plain: List[int] = []
    victims: List[Tuple[int, int]] = []
    enemies_of_a = hostile.get(int(faction_id), set())
    for d in losers:
        cid = int(d["character_id"])
        info = chars.get(cid)
        if info is None:
            continue
        is_npc, role = info[0], info[1]
        if is_npc:
            if (role or "") == "mob":
                template = d.get("mob_template_id")
                if template is not None and int(template) in mob_pts:
                    plain.append(mob_pts[int(template)])
            elif cid in npc_pts:
                plain.append(npc_pts[cid])
            continue
        if pvp and hostile_pts > 0 and victim_factions.get(cid, set()) & enemies_of_a:
            victims.append((cid, hostile_pts))
    return plain, victims


def apply_battle(db: Session, payload, now: Optional[datetime] = None) -> FlowResult:
    """The battle-result callback (§3.6). Commits per winner (own transactions); returns the merged result."""
    now = now or fcr.now_utc()
    battle_id = int(payload.battle_id)
    winner_team = int(payload.winner_team)
    parts = [{"character_id": int(p.character_id), "team": int(p.team), "alive": bool(p.alive),
              "mob_template_id": p.mob_template_id} for p in payload.participants]
    result = FlowResult(data={"applied": [], "duplicate": False})
    chars = _characters(db, [p["character_id"] for p in parts])
    winners = sorted({p["character_id"] for p in parts
                      if p["team"] == winner_team and p["character_id"] in chars and not chars[p["character_id"]][0]})
    losers = [p for p in parts if p["team"] != winner_team]
    if not winners or not losers:
        db.rollback()
        return result
    memberships = _active_memberships(db, winners)
    if not memberships:
        db.rollback()
        return result
    pvp = str(payload.battle_type) in fc.PVP_KILL_BATTLE_TYPES
    player_losers = [p["character_id"] for p in losers if p["character_id"] in chars and not chars[p["character_id"]][0]]
    victim_factions = _active_memberships(db, player_losers, open_only=True) if pvp else {}
    hostile = fcr.hostile_map(db)
    enemies = _enemies(db, {f for fids in memberships.values() for f in fids})
    ts = load_territory_settings(db)
    caps = {int(f.id): fc.kill_cap(f.kill_points_daily_cap, ts) for f in db.query(models.Faction).filter(
        models.Faction.id.in_(sorted(enemies))).all()} if enemies else {}

    plans: Dict[int, Dict[int, Tuple[List[int], List[Tuple[int, int]]]]] = {}
    for w in winners:
        for fid in sorted(memberships.get(w, set())):
            plain, victims = _points_for(fid, enemies.get(fid, []), losers, chars, victim_factions, hostile, pvp)
            victims = [(v, pts) for v, pts in victims if v != w]
            if plain or victims:
                plans.setdefault(w, {})[fid] = (plain, victims)
    db.rollback()
    for w in sorted(plans):
        try:
            sub = _apply_winner(db, battle_id, w, plans[w], chars, caps, ts, now)
            db.commit()
        except IntegrityError:
            db.rollback()
            result.data["duplicate"] = True
            continue
        except Exception:
            db.rollback()
            logger.exception("faction kills: battle %s winner %s failed", battle_id, w)
            continue
        if sub.data.get("duplicate"):
            result.data["duplicate"] = True
        result.data["applied"].extend(sub.data.get("applied", []))
        result.merge(sub)
    return result


def _apply_winner(db: Session, battle_id: int, character_id: int,
                  plan: Dict[int, Tuple[List[int], List[Tuple[int, int]]]], chars: Dict[int, tuple],
                  caps: Dict[int, int], ts: fc.TerritorySettings, now: datetime) -> FlowResult:
    day = fec.today_utc(now)
    for fid in sorted(plan):
        fec.ensure_day_row(db, character_id, fid, day)      # own short transactions, nothing open before
    s_core = fcr.load_settings(db)
    hostile = fcr.hostile_map(db)
    lock_ids = set(plan)
    for fid in plan:
        lock_ids |= hostile.get(int(fid), set())
    members = fec._lock_members(db, character_id, lock_ids)
    day_rows = {int(r.faction_id): r for r in fec._lock(db, db.query(models.FactionDonationDay).filter(
        models.FactionDonationDay.character_id == int(character_id),
        models.FactionDonationDay.faction_id.in_(sorted(plan)),
        models.FactionDonationDay.day == day).order_by(models.FactionDonationDay.faction_id)).all()}
    key = kill_key(battle_id, character_id)
    result = FlowResult(data={"applied": [], "duplicate": False})
    factions = {int(f.id): f for f in db.query(models.Faction).filter(models.Faction.id.in_(sorted(plan))).all()}
    repeat = timedelta(hours=int(ts.pvp_kill_repeat_hours))
    user_id = chars.get(int(character_id), (False, None, None))[2]
    for fid in sorted(plan):
        member = members.get(int(fid))
        faction = factions.get(int(fid))
        if member is None or member.status != fc.STATUS_ACTIVE or faction is None:
            continue
        if fcr.log_key_exists(db, key, fid):
            result.data["duplicate"] = True
            continue
        plain, victims = plan[fid]
        points = list(plain)
        if victims:
            ids = sorted({v for v, _p in victims})
            rows = {int(r.victim_id): r for r in fec._lock(db, db.query(models.FactionPvpKill).filter(
                models.FactionPvpKill.character_id == int(character_id), models.FactionPvpKill.faction_id == int(fid),
                models.FactionPvpKill.victim_id.in_(ids)).order_by(models.FactionPvpKill.victim_id)).all()}
            for victim, pts in sorted(dict(victims).items()):
                row = rows.get(int(victim))
                if row is not None and repeat.total_seconds() > 0 and row.last_at is not None \
                        and row.last_at > now - repeat:
                    continue
                if row is None:
                    db.add(models.FactionPvpKill(character_id=int(character_id), faction_id=int(fid),
                                                 victim_id=int(victim), last_at=now))
                else:
                    row.last_at = now
                points.append(int(pts))
        if not points:
            continue
        day_row = day_rows.get(int(fid))
        if day_row is None:
            day_row = models.FactionDonationDay(character_id=int(character_id), faction_id=int(fid), day=day,
                                               marks=0, points=0, kill_points=0)
            db.add(day_row)
            db.flush()
        gain, today_after = fc.kill_gain(points, caps.get(int(fid), ts.kill_points_daily_cap),
                                         int(day_row.kill_points or 0))
        day_row.kill_points = today_after
        if gain > 0:
            actual = fcr.change_points(db, member, gain, fc.EV_KILL, now, event_key=key, reason=f"battle:{battle_id}")
            penalty = fc.hostile_penalty(gain, s_core.hostile_penalty_pct)
            for other in sorted(hostile.get(int(fid), set())):
                if penalty <= 0:
                    break
                other_member = members.get(int(other))
                if other_member is None or other_member.status != fc.STATUS_ACTIVE:
                    continue
                fcr.change_points(db, other_member, -penalty, fc.EV_HOSTILE, now,
                                  event_key=f"{key}:hostile:{int(fid)}", reason=f"faction:{int(fid)}")
            result.notices.append(Notice(user_id, f"Победа над врагами фракции «{faction.name}»: +{actual} очков",
                                         CATEGORY_PROGRESS, {"faction_id": int(fid), "character_id": int(character_id),
                                                             "event": fc.EV_KILL}))
        else:
            actual = 0
            fcr.log_event(db, character_id=character_id, faction_id=fid, event_type=fc.EV_KILL, now=now,
                          points_delta=0, points_after=int(member.points), rank_id=member.rank_id, event_key=key,
                          reason="cap")
        result.data["applied"].append({"character_id": int(character_id), "faction_id": int(fid),
                                       "points_delta": int(actual)})
    db.flush()
    result.merge(fcr.recheck_ranks(db, character_id, now))
    return result


# =====================================================================================================================
# admin: enemies / outlaw regions (§3.9)
# =====================================================================================================================

def _err(detail: str, status: int = 422) -> FactionError:
    return FactionError(status, detail)


def enemies_out(db: Session, faction_id: int) -> dict:
    faction = fcr.faction_or_404(db, faction_id)
    rows = _enemies(db, [faction.id]).get(int(faction.id), [])
    mob_ids = [int(r.ref_id) for r in rows if r.kind == fc.ENEMY_MOB]
    npc_ids = [int(r.ref_id) for r in rows if r.kind == fc.ENEMY_NPC]
    mob_names: Dict[int, str] = {}
    if mob_ids:
        ph, params = fcr.in_clause("m", mob_ids)
        mob_names = {int(r[0]): r[1] for r in db.execute(text(f"SELECT id, name FROM mob_templates WHERE id IN ({ph})"),
                                                         params).fetchall()}
    npc_names = {cid: v["name"] for cid, v in fcr.character_brief(db, npc_ids).items()}
    items = []
    for r in rows:
        name = mob_names.get(int(r.ref_id)) if r.kind == fc.ENEMY_MOB else (
            npc_names.get(int(r.ref_id)) if r.kind == fc.ENEMY_NPC else None)
        items.append({"kind": r.kind, "ref_id": int(r.ref_id) if r.kind != fc.ENEMY_HOSTILE else None,
                      "points": int(r.points), "name": name})
    return {"enemies": items, "kill_points_daily_cap": faction.kill_points_daily_cap}


def put_enemies(db: Session, faction_id: int, body) -> dict:
    faction = fcr.faction_or_404(db, faction_id)
    if len(body.enemies) > fc.MAX_ENEMIES:
        raise _err(MSG_ENEMIES_MAX)
    cap = body.kill_points_daily_cap
    if cap is not None and (isinstance(cap, bool) or not 0 <= int(cap) <= fc.MAX_KILL_CAP):
        raise _err(MSG_KILL_CAP)
    rows: List[Tuple[str, int, int]] = []
    seen = set()
    for e in body.enemies:
        kind = (e.kind or "").strip()
        if kind not in fc.ENEMY_KINDS:
            raise _err(MSG_ENEMY_KIND.format(kind=kind))
        points = e.points
        if isinstance(points, bool) or not 1 <= int(points) <= fc.MAX_ENEMY_POINTS:
            raise _err(MSG_ENEMY_POINTS)
        ref = 0 if kind == fc.ENEMY_HOSTILE else int(e.ref_id or 0)
        if kind == fc.ENEMY_HOSTILE and any(k == fc.ENEMY_HOSTILE for k, _r, _p in rows):
            raise _err(MSG_ENEMY_HOSTILE_ONE)
        if (kind, ref) in seen:
            raise _err(MSG_ENEMY_DUP)
        seen.add((kind, ref))
        rows.append((kind, ref, int(points)))
    mob_ids = [r for k, r, _p in rows if k == fc.ENEMY_MOB]
    if mob_ids:
        ph, params = fcr.in_clause("m", mob_ids)
        found = {int(x[0]) for x in db.execute(text(f"SELECT id FROM mob_templates WHERE id IN ({ph})"),
                                               params).fetchall()}
        if set(mob_ids) - found:
            raise _err(MSG_ENEMY_MOB)
    npc_ids = [r for k, r, _p in rows if k == fc.ENEMY_NPC]
    if npc_ids:
        ph, params = fcr.in_clause("n", npc_ids)
        found = {int(x[0]) for x in db.execute(text(
            f"SELECT id FROM characters WHERE id IN ({ph}) AND is_npc = 1 AND (npc_role IS NULL OR npc_role != 'mob')"),
            params).fetchall()}
        if set(npc_ids) - found:
            raise _err(MSG_ENEMY_NPC)
    db.query(models.FactionEnemy).filter(models.FactionEnemy.faction_id == int(faction.id)).delete(
        synchronize_session=False)
    for kind, ref, points in rows:
        db.add(models.FactionEnemy(faction_id=int(faction.id), kind=kind, ref_id=ref, points=points))
    faction.kill_points_daily_cap = int(cap) if cap is not None else None
    db.flush()
    return enemies_out(db, faction.id)


def outlaw_out(db: Session, faction_id: int) -> dict:
    import faction_territory
    faction = fcr.faction_or_404(db, faction_id)
    return {"regions": faction_territory.outlaw_regions_of(db, [faction.id]).get(int(faction.id), [])}


def put_outlaw(db: Session, faction_id: int, body) -> dict:
    import law_crud
    faction = fcr.faction_or_404(db, faction_id)
    if len(body.regions) > fc.MAX_OUTLAW_REGIONS:
        raise _err(MSG_OUTLAW_MAX)
    codes = {lv.code for lv in law_crud.load_levels(db)}
    rows: List[Tuple[int, str]] = []
    for r in body.regions:
        region_id = r.region_id
        if isinstance(region_id, bool) or int(region_id) < 1:
            raise _err(MSG_OUTLAW_REGION)
        code = (r.level_code or "").strip()
        if code not in codes:
            raise _err(MSG_OUTLAW_LEVEL.format(code=code))
        if any(x == int(region_id) for x, _c in rows):
            raise _err(MSG_OUTLAW_DUP)
        rows.append((int(region_id), code))
    if rows:
        ph, params = fcr.in_clause("r", [x for x, _c in rows])
        found = {int(x[0]) for x in db.execute(text(f"SELECT id FROM Regions WHERE id IN ({ph})"), params).fetchall()}
        if {x for x, _c in rows} - found:
            raise _err(MSG_OUTLAW_REGION)
    db.query(models.FactionOutlawRegion).filter(models.FactionOutlawRegion.faction_id == int(faction.id)).delete(
        synchronize_session=False)
    for region_id, code in rows:
        db.add(models.FactionOutlawRegion(faction_id=int(faction.id), region_id=region_id, level_code=code))
    db.flush()
    return outlaw_out(db, faction.id)
