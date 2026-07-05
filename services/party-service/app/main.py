import logging
from typing import List, Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import crud
import schemas
from config import settings
from database import get_db, engine
from auth_http import get_current_user_via_http, UserRead

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("party-service")

app = FastAPI(title="Party Service")

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")] if settings.CORS_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/party")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_owned(db: Session, character_id: int, current_user: UserRead) -> dict:
    """Fetch character info and assert the JWT user owns it."""
    info = crud.get_character_info(db, character_id)
    if not info:
        raise HTTPException(404, "Персонаж не найден")
    if info["user_id"] != current_user.id:
        raise HTTPException(403, "Это не ваш персонаж")
    return info


def _charge_active_xp(character_id: int, amount: int) -> None:
    """Deduct active experience for creating a squad (no-op while cost is 0)."""
    if amount <= 0:
        return
    try:
        httpx.put(
            f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/active_experience",
            json={"amount": -amount},
            timeout=5.0,
        )
    except Exception as e:
        logger.warning(f"Не удалось списать активный опыт у {character_id}: {e}")


def _award_passive_xp(character_id: int, amount: int) -> None:
    """Grant passive XP (the party bonus/trickle). Non-fatal."""
    if amount == 0:
        return
    try:
        httpx.put(
            f"{settings.ATTRIBUTES_SERVICE_URL}{character_id}/passive_experience",
            json={"amount": amount},
            timeout=5.0,
        )
    except Exception as e:
        logger.warning(f"Не удалось начислить пассивный опыт {character_id}: {e}")


# ---------------------------------------------------------------------------
# Endpoints (literal paths before parametric ones)
# ---------------------------------------------------------------------------
@router.post("/", response_model=schemas.PartyOut, status_code=201)
def create_party(
    req: schemas.PartyCreate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    _require_owned(db, req.leader_character_id, current_user)
    if crud.get_accepted_membership(db, req.leader_character_id):
        raise HTTPException(409, "Персонаж уже состоит в отряде")

    _charge_active_xp(req.leader_character_id, settings.PARTY_CREATE_COST_ACTIVE_XP)

    party = models.Party(
        name=req.name, avatar=req.avatar,
        leader_character_id=req.leader_character_id,
    )
    db.add(party)
    db.flush()
    db.add(models.PartyMember(
        party_id=party.id,
        character_id=req.leader_character_id,
        user_id=current_user.id,
        is_leader=True,
        status=models.MemberStatus.accepted,
    ))
    db.commit()
    db.refresh(party)
    return crud.build_party_out(db, party)


@router.post("/internal/xp-bonus", response_model=schemas.XpBonusResult)
def xp_bonus(req: schemas.XpBonusRequest, db: Session = Depends(get_db)):
    """Internal (service-to-service): distribute the party XP bonus for an
    XP-earning event (FEAT-144 §5).

    - self-bonus +N% to the actor (any source), but only when at least one
      squadmate is co-located (green);
    - trickle +N% to each other green squadmate for combat/dungeon (not posts),
      excluding those who already earned base XP from the same event.
    """
    if req.base_xp <= 0 or req.location_id is None:
        return schemas.XpBonusResult(applied=False)
    membership = crud.get_accepted_membership(db, req.character_id)
    if not membership:
        return schemas.XpBonusResult(applied=False)

    others = [
        m for m in crud.get_members(db, membership.party_id)
        if m.status == models.MemberStatus.accepted and m.character_id != req.character_id
    ]
    info = crud.get_characters_map(db, [m.character_id for m in others])
    green_others = [
        m.character_id for m in others
        if info.get(m.character_id, {}).get("current_location_id") == req.location_id
    ]
    if not green_others:
        # Actor is alone on the location — no party bonus at all.
        return schemas.XpBonusResult(applied=False)

    bonus = round(req.base_xp * settings.PARTY_XP_BONUS_PCT / 100)
    if bonus <= 0:
        return schemas.XpBonusResult(applied=False)

    _award_passive_xp(req.character_id, bonus)
    result = schemas.XpBonusResult(
        applied=True, bonus_per_member=bonus, self_bonus=bonus, trickle=[],
    )
    if req.source in ("combat", "dungeon"):
        participants = set(req.participant_character_ids)
        for cid in green_others:
            if cid in participants:
                continue
            _award_passive_xp(cid, bonus)
            result.trickle.append({"character_id": cid, "amount": bonus})
    return result


@router.get("/mine", response_model=Optional[schemas.PartyOut])
def my_party(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    _require_owned(db, character_id, current_user)
    membership = crud.get_accepted_membership(db, character_id)
    if not membership:
        return None
    party = crud.get_party(db, membership.party_id)
    if not party:
        return None
    return crud.build_party_out(db, party)


@router.get("/invites/incoming", response_model=List[schemas.IncomingInvite])
def incoming_invites(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    _require_owned(db, character_id, current_user)
    invites = (
        db.query(models.PartyMember)
        .filter(
            models.PartyMember.character_id == character_id,
            models.PartyMember.status == models.MemberStatus.invited,
        )
        .all()
    )
    out = []
    for inv in invites:
        party = crud.get_party(db, inv.party_id)
        if not party:
            continue
        leader = crud.get_character_info(db, party.leader_character_id)
        out.append(schemas.IncomingInvite(
            party_id=party.id,
            party_name=party.name,
            party_avatar=party.avatar,
            leader_character_id=party.leader_character_id,
            leader_name=leader.get("name") if leader else None,
        ))
    return out


@router.post("/{party_id}/invite", response_model=schemas.PartyOut)
def invite_member(
    party_id: int,
    req: schemas.PartyInvite,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    party = crud.get_party(db, party_id)
    if not party:
        raise HTTPException(404, "Отряд не найден")
    leader = _require_owned(db, party.leader_character_id, current_user)  # leader-only

    target = crud.get_character_info(db, req.character_id)
    if not target:
        raise HTTPException(404, "Приглашаемый персонаж не найден")
    if target["current_location_id"] is None or target["current_location_id"] != leader["current_location_id"]:
        raise HTTPException(400, "Пригласить можно только игрока на вашей локации")
    if crud.count_committed_members(db, party_id) >= settings.PARTY_MAX_SIZE:
        raise HTTPException(400, f"В отряде максимум {settings.PARTY_MAX_SIZE} участников")

    existing = (
        db.query(models.PartyMember)
        .filter(
            models.PartyMember.party_id == party_id,
            models.PartyMember.character_id == req.character_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(409, "Игрок уже приглашён или состоит в отряде")
    if crud.get_accepted_membership(db, req.character_id):
        raise HTTPException(409, "Игрок уже состоит в другом отряде")

    db.add(models.PartyMember(
        party_id=party_id,
        character_id=req.character_id,
        user_id=target["user_id"],
        is_leader=False,
        status=models.MemberStatus.invited,
    ))
    db.commit()
    db.refresh(party)
    return crud.build_party_out(db, party)


@router.post("/{party_id}/respond", response_model=Optional[schemas.PartyOut])
def respond_invite(
    party_id: int,
    req: schemas.PartyRespond,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    _require_owned(db, req.character_id, current_user)  # the invitee acts
    member = (
        db.query(models.PartyMember)
        .filter(
            models.PartyMember.party_id == party_id,
            models.PartyMember.character_id == req.character_id,
            models.PartyMember.status == models.MemberStatus.invited,
        )
        .first()
    )
    if not member:
        raise HTTPException(404, "Приглашение не найдено")

    if not req.accept:
        db.delete(member)
        db.commit()
        return None

    if crud.get_accepted_membership(db, req.character_id):
        raise HTTPException(409, "Вы уже состоите в отряде")
    if crud.count_committed_members(db, party_id) > settings.PARTY_MAX_SIZE:
        raise HTTPException(400, "Отряд уже заполнен")

    member.status = models.MemberStatus.accepted
    # Drop this character's pending invites to OTHER parties (one squad only).
    db.query(models.PartyMember).filter(
        models.PartyMember.character_id == req.character_id,
        models.PartyMember.status == models.MemberStatus.invited,
        models.PartyMember.party_id != party_id,
    ).delete(synchronize_session=False)
    db.commit()
    party = crud.get_party(db, party_id)
    return crud.build_party_out(db, party)


@router.post("/{party_id}/leave")
def leave_party(
    party_id: int,
    req: schemas.PartyLeave,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    _require_owned(db, req.character_id, current_user)
    party = crud.get_party(db, party_id)
    if not party:
        raise HTTPException(404, "Отряд не найден")
    member = (
        db.query(models.PartyMember)
        .filter(
            models.PartyMember.party_id == party_id,
            models.PartyMember.character_id == req.character_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(404, "Вы не состоите в этом отряде")

    was_leader = member.is_leader
    if was_leader:
        successor = (
            db.query(models.PartyMember)
            .filter(
                models.PartyMember.party_id == party_id,
                models.PartyMember.status == models.MemberStatus.accepted,
                models.PartyMember.character_id != req.character_id,
            )
            .order_by(models.PartyMember.joined_at.asc())
            .first()
        )
        if successor:
            db.delete(member)
            successor.is_leader = True
            party.leader_character_id = successor.character_id
            db.commit()
            return {"detail": "left", "disbanded": False, "new_leader": successor.character_id}
        # No accepted successor — disband the whole squad.
        db.query(models.PartyMember).filter(models.PartyMember.party_id == party_id).delete(synchronize_session=False)
        db.delete(party)
        db.commit()
        return {"detail": "left", "disbanded": True}

    db.delete(member)
    db.commit()
    return {"detail": "left", "disbanded": False}


@router.patch("/{party_id}", response_model=schemas.PartyOut)
def update_party(
    party_id: int,
    req: schemas.PartyUpdate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    party = crud.get_party(db, party_id)
    if not party:
        raise HTTPException(404, "Отряд не найден")
    _require_owned(db, party.leader_character_id, current_user)  # leader-only
    if req.name is not None:
        party.name = req.name
    if req.avatar is not None:
        party.avatar = req.avatar
    db.commit()
    db.refresh(party)
    return crud.build_party_out(db, party)


@router.delete("/{party_id}")
def disband_party(
    party_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    party = crud.get_party(db, party_id)
    if not party:
        raise HTTPException(404, "Отряд не найден")
    _require_owned(db, party.leader_character_id, current_user)  # leader-only
    db.query(models.PartyMember).filter(models.PartyMember.party_id == party_id).delete(synchronize_session=False)
    db.delete(party)
    db.commit()
    return {"detail": "disbanded"}


app.include_router(router)


@app.get("/party/health")
def health():
    return {"status": "ok"}
