"""Эпизоды (FEAT-179) — истории игроков вне основного мира.

A player opens an episode (a section with its own picture and description,
filed under «Истории мира» or «Отдельные истории»), adds locations to it,
invites members and gives them mini-roles. Posts are written from a mini-role
and give nothing to the main character: no experience, no battles, no limits.

Access:
- a private episode opens only to its members — and to the top staff role
  (`admin`); moderators don't pass;
- an episode hidden by staff is seen by its members and staff only;
- the owner and the masters run the episode (locations, members, roles);
  only the owner names masters and deletes the episode.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, constr, validator
from sqlalchemy import bindparam, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import models
from auth_http import AUTH_SERVICE_URL, UserRead, get_current_user_via_http
from crud import strip_html_tags
from database import get_db
from rabbitmq_publisher import publish_notification_sync

router = APIRouter(prefix="/locations/episodes", tags=["episodes"])

OWNED_EPISODES_LIMIT = 3
POSTS_PAGE = 30
MAX_POST_CHARS = 200_000
# Pictures come from photo-service's episode upload, nowhere else.
IMAGE_PATH_MARK = "/episode_images/"

CATEGORIES = ("world", "separate")
MANAGER_ROLES = ("owner", "master")

_OPTIONAL_TOKEN = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def get_viewer(token: Optional[str] = Depends(_OPTIONAL_TOKEN)) -> Optional[UserRead]:
    """The signed-in user, or None for a guest."""
    if not token:
        return None
    try:
        resp = requests.get(f"{AUTH_SERVICE_URL}/users/me",
                            headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if resp.status_code == 200:
            return UserRead(**resp.json())
    except requests.RequestException:
        pass
    return None


def _is_admin(user: Optional[UserRead]) -> bool:
    return bool(user) and user.role == "admin"


def _is_staff(user: Optional[UserRead]) -> bool:
    return bool(user) and user.role in ("admin", "moderator")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def _image(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    if not value.startswith("https://") or IMAGE_PATH_MARK not in value or len(value) > 512:
        raise ValueError("Картинку нужно загрузить через форму")
    return value


class EpisodeIn(BaseModel):
    category: str
    title: constr(strip_whitespace=True, min_length=1, max_length=120)
    description: constr(strip_whitespace=True, min_length=1, max_length=5000)
    image_url: Optional[str] = None
    is_private: bool = False

    _img = validator("image_url", allow_reuse=True)(_image)

    @validator("category")
    def _category(cls, v):
        if v not in CATEGORIES:
            raise ValueError("Неизвестная категория")
        return v


class LocationIn(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=120)
    description: constr(strip_whitespace=True, max_length=5000) = ""
    image_url: Optional[str] = None
    sort_order: int = 0

    _img = validator("image_url", allow_reuse=True)(_image)


class PostIn(BaseModel):
    role_id: int
    content: str


class PostEditIn(BaseModel):
    content: str


class MemberIn(BaseModel):
    user_id: int


class MemberRoleIn(BaseModel):
    role: str

    @validator("role")
    def _role(cls, v):
        if v not in ("master", "player"):
            raise ValueError("Можно назначить только мастера или игрока")
        return v


class RoleSlotIn(BaseModel):
    user_id: int
    name: constr(strip_whitespace=True, max_length=100) = ""


class RoleIn(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=100)
    avatar_url: Optional[str] = None
    description: constr(strip_whitespace=True, max_length=5000) = ""

    _img = validator("avatar_url", allow_reuse=True)(_image)


class JoinIn(BaseModel):
    message: constr(strip_whitespace=True, max_length=500) = ""


class HideIn(BaseModel):
    hidden: bool


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

async def _users(db: AsyncSession, ids) -> Dict[int, dict]:
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    rows = await db.execute(
        text("SELECT id, username, avatar FROM users WHERE id IN :ids")
        .bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )
    return {r[0]: {"id": r[0], "username": r[1], "avatar": r[2]} for r in rows.fetchall()}


async def _episode(db: AsyncSession, episode_id: int) -> models.Episode:
    ep = await db.get(models.Episode, episode_id)
    if not ep:
        raise HTTPException(404, "Эпизод не найден")
    return ep


async def _membership(db: AsyncSession, episode_id: int, user_id: Optional[int]) -> Optional[models.EpisodeMember]:
    if user_id is None:
        return None
    return (await db.execute(select(models.EpisodeMember).where(
        models.EpisodeMember.episode_id == episode_id,
        models.EpisodeMember.user_id == user_id,
    ))).scalar_one_or_none()


def _can_view(ep: models.Episode, user: Optional[UserRead], member) -> bool:
    if member or _is_admin(user):
        return True
    if ep.is_private:
        return False
    if ep.is_hidden:
        return _is_staff(user)
    return True


def _can_manage(user: Optional[UserRead], member) -> bool:
    return _is_admin(user) or (member is not None and member.role in MANAGER_ROLES)


async def _open(db, episode_id, user):
    """The episode and the viewer's membership, or 403/404 if it is shut to them."""
    ep = await _episode(db, episode_id)
    member = await _membership(db, episode_id, user.id if user else None)
    if not _can_view(ep, user, member):
        if ep.is_private:
            raise HTTPException(403, "Это закрытый эпизод — он открыт только участникам")
        raise HTTPException(404, "Эпизод не найден")
    return ep, member


async def _manage(db, episode_id, user):
    ep, member = await _open(db, episode_id, user)
    if not _can_manage(user, member):
        raise HTTPException(403, "Это могут только владелец и мастера эпизода")
    return ep, member


async def _location(db, episode_id: int, location_id: int) -> models.EpisodeLocation:
    loc = await db.get(models.EpisodeLocation, location_id)
    if not loc or loc.episode_id != episode_id:
        raise HTTPException(404, "Локация не найдена")
    return loc


async def _role(db, episode_id: int, role_id: int) -> models.EpisodeRole:
    role = await db.get(models.EpisodeRole, role_id)
    if not role or role.episode_id != episode_id:
        raise HTTPException(404, "Роль не найдена")
    return role


def _notify(background: BackgroundTasks, user_id: int, message: str) -> None:
    background.add_task(publish_notification_sync, user_id, message)


def _episode_out(ep: models.Episode) -> dict:
    return {
        "id": ep.id, "owner_user_id": ep.owner_user_id, "category": ep.category,
        "title": ep.title, "description": ep.description, "image_url": ep.image_url,
        "is_private": bool(ep.is_private), "is_hidden": bool(ep.is_hidden),
        "created_at": ep.created_at,
    }


def _role_out(role: models.EpisodeRole) -> dict:
    return {
        "id": role.id, "user_id": role.user_id, "name": role.name, "avatar_url": role.avatar_url,
        "description": role.description or "", "archived": bool(role.archived),
    }


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------

@router.get("")
async def list_episodes(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: Optional[UserRead] = Depends(get_viewer),
):
    q = select(models.Episode).order_by(models.Episode.id.desc())
    if category:
        q = q.where(models.Episode.category == category)
    episodes = (await db.execute(q)).scalars().all()

    mine: Dict[int, str] = {}
    if user:
        rows = await db.execute(select(models.EpisodeMember.episode_id, models.EpisodeMember.role)
                                .where(models.EpisodeMember.user_id == user.id))
        mine = {r[0]: r[1] for r in rows.fetchall()}

    # Private episodes are not even listed to outsiders.
    visible = [e for e in episodes if e.id in mine or _is_admin(user)
               or (not e.is_private and (not e.is_hidden or _is_staff(user)))]
    ids = [e.id for e in visible]
    members: Dict[int, int] = {}
    posts: Dict[int, tuple] = {}
    if ids:
        rows = await db.execute(select(models.EpisodeMember.episode_id, func.count())
                                .where(models.EpisodeMember.episode_id.in_(ids))
                                .group_by(models.EpisodeMember.episode_id))
        members = {r[0]: r[1] for r in rows.fetchall()}
        rows = await db.execute(
            select(models.EpisodeLocation.episode_id, func.count(models.EpisodePost.id),
                   func.max(models.EpisodePost.created_at))
            .join(models.EpisodePost, models.EpisodePost.location_id == models.EpisodeLocation.id)
            .where(models.EpisodeLocation.episode_id.in_(ids))
            .group_by(models.EpisodeLocation.episode_id))
        posts = {r[0]: (r[1], r[2]) for r in rows.fetchall()}
    owners = await _users(db, [e.owner_user_id for e in visible])
    return [
        {
            **_episode_out(e),
            "owner": owners.get(e.owner_user_id),
            "members_count": members.get(e.id, 0),
            "posts_count": posts.get(e.id, (0, None))[0],
            "last_post_at": posts.get(e.id, (0, None))[1],
            "my_role": mine.get(e.id),
        }
        for e in visible
    ]


@router.post("")
async def create_episode(
    body: EpisodeIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    owned = (await db.execute(select(func.count()).select_from(models.Episode)
                              .where(models.Episode.owner_user_id == user.id))).scalar() or 0
    if owned >= OWNED_EPISODES_LIMIT and not _is_admin(user):
        raise HTTPException(409, f"Можно вести не больше {OWNED_EPISODES_LIMIT} эпизодов")
    ep = models.Episode(owner_user_id=user.id, **body.dict())
    db.add(ep)
    await db.flush()
    db.add(models.EpisodeMember(episode_id=ep.id, user_id=user.id, role="owner"))
    await db.commit()
    await db.refresh(ep)
    return _episode_out(ep)


@router.get("/{episode_id}")
async def get_episode(
    episode_id: int,
    db: AsyncSession = Depends(get_db),
    user: Optional[UserRead] = Depends(get_viewer),
):
    ep, member = await _open(db, episode_id, user)
    can_manage = _can_manage(user, member)

    locs = (await db.execute(select(models.EpisodeLocation)
                             .where(models.EpisodeLocation.episode_id == episode_id)
                             .order_by(models.EpisodeLocation.sort_order, models.EpisodeLocation.id))).scalars().all()
    counts: Dict[int, tuple] = {}
    if locs:
        rows = await db.execute(select(models.EpisodePost.location_id, func.count(), func.max(models.EpisodePost.created_at))
                                .where(models.EpisodePost.location_id.in_([l.id for l in locs]))
                                .group_by(models.EpisodePost.location_id))
        counts = {r[0]: (r[1], r[2]) for r in rows.fetchall()}

    member_rows = (await db.execute(select(models.EpisodeMember)
                                    .where(models.EpisodeMember.episode_id == episode_id)
                                    .order_by(models.EpisodeMember.id))).scalars().all()
    roles = (await db.execute(select(models.EpisodeRole)
                              .where(models.EpisodeRole.episode_id == episode_id,
                                     models.EpisodeRole.archived.is_(False))
                              .order_by(models.EpisodeRole.id))).scalars().all()
    users = await _users(db, [m.user_id for m in member_rows])
    by_user: Dict[int, list] = {}
    for r in roles:
        by_user.setdefault(r.user_id, []).append(_role_out(r))

    requests_count = 0
    my_request = False
    if can_manage:
        requests_count = (await db.execute(select(func.count()).select_from(models.EpisodeJoinRequest)
                                           .where(models.EpisodeJoinRequest.episode_id == episode_id))).scalar() or 0
    elif user and not member:
        my_request = (await db.execute(select(models.EpisodeJoinRequest.id).where(
            models.EpisodeJoinRequest.episode_id == episode_id,
            models.EpisodeJoinRequest.user_id == user.id))).first() is not None

    return {
        **_episode_out(ep),
        "owner": users.get(ep.owner_user_id),
        "my_role": member.role if member else None,
        "can_manage": can_manage,
        "is_owner": bool(member and member.role == "owner"),
        # Owner's powers: masters, deleting the episode. The top admin has them too.
        "can_own": bool(member and member.role == "owner") or _is_admin(user),
        "can_moderate": _is_staff(user),
        "my_request": my_request,
        "requests_count": requests_count,
        "locations": [
            {"id": l.id, "name": l.name, "description": l.description, "image_url": l.image_url,
             "sort_order": l.sort_order, "posts_count": counts.get(l.id, (0, None))[0],
             "last_post_at": counts.get(l.id, (0, None))[1]}
            for l in locs
        ],
        "members": [
            {"user_id": m.user_id, "role": m.role,
             "username": (users.get(m.user_id) or {}).get("username"),
             "avatar": (users.get(m.user_id) or {}).get("avatar"),
             "roles": by_user.get(m.user_id, [])}
            for m in member_rows
        ],
    }


@router.put("/{episode_id}")
async def update_episode(
    episode_id: int,
    body: EpisodeIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    ep, _ = await _manage(db, episode_id, user)
    for k, v in body.dict().items():
        setattr(ep, k, v)
    await db.commit()
    return _episode_out(ep)


@router.delete("/{episode_id}")
async def delete_episode(
    episode_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    ep, member = await _open(db, episode_id, user)
    if not (_is_staff(user) or (member and member.role == "owner")):
        raise HTTPException(403, "Удалить эпизод может только его владелец")
    await db.delete(ep)
    await db.commit()
    return {"ok": True}


@router.post("/{episode_id}/hide")
async def hide_episode(
    episode_id: int,
    body: HideIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    if not _is_staff(user):
        raise HTTPException(403, "Скрывать эпизоды могут только администраторы и модераторы")
    ep, _ = await _open(db, episode_id, user)
    ep.is_hidden = body.hidden
    await db.commit()
    return _episode_out(ep)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@router.post("/{episode_id}/locations")
async def create_location(
    episode_id: int,
    body: LocationIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _manage(db, episode_id, user)
    loc = models.EpisodeLocation(episode_id=episode_id, **body.dict())
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return {"id": loc.id}


@router.put("/{episode_id}/locations/{location_id}")
async def update_location(
    episode_id: int,
    location_id: int,
    body: LocationIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _manage(db, episode_id, user)
    loc = await _location(db, episode_id, location_id)
    for k, v in body.dict().items():
        setattr(loc, k, v)
    await db.commit()
    return {"id": loc.id}


@router.delete("/{episode_id}/locations/{location_id}")
async def delete_location(
    episode_id: int,
    location_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _manage(db, episode_id, user)
    loc = await _location(db, episode_id, location_id)
    await db.delete(loc)
    await db.commit()
    return {"ok": True}


@router.get("/{episode_id}/locations/{location_id}")
async def get_location(
    episode_id: int,
    location_id: int,
    db: AsyncSession = Depends(get_db),
    user: Optional[UserRead] = Depends(get_viewer),
):
    ep, member = await _open(db, episode_id, user)
    loc = await _location(db, episode_id, location_id)
    my_roles = []
    if member:
        my_roles = [_role_out(r) for r in (await db.execute(select(models.EpisodeRole).where(
            models.EpisodeRole.episode_id == episode_id, models.EpisodeRole.user_id == user.id,
            models.EpisodeRole.archived.is_(False)).order_by(models.EpisodeRole.id))).scalars().all()]
    others = (await db.execute(select(models.EpisodeLocation.id, models.EpisodeLocation.name)
                               .where(models.EpisodeLocation.episode_id == episode_id)
                               .order_by(models.EpisodeLocation.sort_order, models.EpisodeLocation.id))).fetchall()
    return {
        "episode": {"id": ep.id, "title": ep.title, "category": ep.category, "image_url": ep.image_url,
                    "is_private": bool(ep.is_private)},
        "location": {"id": loc.id, "name": loc.name, "description": loc.description,
                     "image_url": loc.image_url, "sort_order": loc.sort_order},
        "locations": [{"id": r[0], "name": r[1]} for r in others],
        "my_roles": my_roles,
        "is_member": member is not None,
        "can_manage": _can_manage(user, member),
        "can_moderate": _is_staff(user),
    }


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

async def _posts_out(db, posts: List[models.EpisodePost], user: Optional[UserRead]) -> list:
    if not posts:
        return []
    ids = [p.id for p in posts]
    roles = {r.id: r for r in (await db.execute(select(models.EpisodeRole).where(
        models.EpisodeRole.id.in_({p.role_id for p in posts})))).scalars().all()}
    likes: Dict[int, int] = {r[0]: r[1] for r in (await db.execute(
        select(models.EpisodePostLike.post_id, func.count()).where(models.EpisodePostLike.post_id.in_(ids))
        .group_by(models.EpisodePostLike.post_id))).fetchall()}
    liked = set()
    if user:
        liked = {r[0] for r in (await db.execute(select(models.EpisodePostLike.post_id).where(
            models.EpisodePostLike.post_id.in_(ids), models.EpisodePostLike.user_id == user.id))).fetchall()}
    users = await _users(db, [p.user_id for p in posts])
    out = []
    for p in posts:
        role = roles.get(p.role_id)
        out.append({
            "id": p.id, "location_id": p.location_id, "user_id": p.user_id,
            "username": (users.get(p.user_id) or {}).get("username"),
            "role": _role_out(role) if role else None,
            "content": p.content, "created_at": p.created_at, "edited_at": p.edited_at,
            "likes_count": likes.get(p.id, 0), "liked": p.id in liked,
            "length": len(strip_html_tags(p.content)),
        })
    return out


@router.get("/{episode_id}/locations/{location_id}/posts")
async def list_posts(
    episode_id: int,
    location_id: int,
    before_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: Optional[UserRead] = Depends(get_viewer),
):
    await _open(db, episode_id, user)
    await _location(db, episode_id, location_id)
    q = (select(models.EpisodePost).where(models.EpisodePost.location_id == location_id)
         .order_by(models.EpisodePost.id.desc()).limit(POSTS_PAGE + 1))
    if before_id:
        q = q.where(models.EpisodePost.id < before_id)
    posts = (await db.execute(q)).scalars().all()
    return {"posts": await _posts_out(db, posts[:POSTS_PAGE], user), "has_more": len(posts) > POSTS_PAGE}


def _content(raw: str) -> str:
    if not strip_html_tags(raw or "").replace("&nbsp;", "").strip():
        raise HTTPException(400, "Пост пустой")
    if len(raw) > MAX_POST_CHARS:
        raise HTTPException(400, "Пост слишком длинный")
    return raw


@router.post("/{episode_id}/locations/{location_id}/posts")
async def create_post(
    episode_id: int,
    location_id: int,
    body: PostIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    _, member = await _open(db, episode_id, user)
    if not member:
        raise HTTPException(403, "Писать могут только участники эпизода")
    await _location(db, episode_id, location_id)
    role = await _role(db, episode_id, body.role_id)
    if role.user_id != user.id or role.archived:
        raise HTTPException(403, "Это не ваша роль")
    post = models.EpisodePost(location_id=location_id, role_id=role.id, user_id=user.id,
                              content=_content(body.content))
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return (await _posts_out(db, [post], user))[0]


async def _post(db, episode_id: int, post_id: int) -> models.EpisodePost:
    post = await db.get(models.EpisodePost, post_id)
    if post:
        loc = await db.get(models.EpisodeLocation, post.location_id)
        if loc and loc.episode_id == episode_id:
            return post
    raise HTTPException(404, "Пост не найден")


@router.put("/{episode_id}/posts/{post_id}")
async def edit_post(
    episode_id: int,
    post_id: int,
    body: PostEditIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _open(db, episode_id, user)
    post = await _post(db, episode_id, post_id)
    if post.user_id != user.id and not _is_admin(user):
        raise HTTPException(403, "Править можно только свои посты")
    post.content = _content(body.content)
    post.edited_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    return (await _posts_out(db, [post], user))[0]


@router.delete("/{episode_id}/posts/{post_id}")
async def delete_post(
    episode_id: int,
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    _, member = await _open(db, episode_id, user)
    post = await _post(db, episode_id, post_id)
    if post.user_id != user.id and not _can_manage(user, member) and not _is_staff(user):
        raise HTTPException(403, "Удалять чужие посты могут только владелец и мастера")
    await db.delete(post)
    await db.commit()
    return {"ok": True}


@router.post("/{episode_id}/posts/{post_id}/like")
async def like_post(
    episode_id: int,
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _open(db, episode_id, user)
    await _post(db, episode_id, post_id)
    exists = (await db.execute(select(models.EpisodePostLike.id).where(
        models.EpisodePostLike.post_id == post_id, models.EpisodePostLike.user_id == user.id))).first()
    if not exists:
        db.add(models.EpisodePostLike(post_id=post_id, user_id=user.id))
        await db.commit()
    return {"ok": True}


@router.delete("/{episode_id}/posts/{post_id}/like")
async def unlike_post(
    episode_id: int,
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _open(db, episode_id, user)
    await db.execute(delete(models.EpisodePostLike).where(
        models.EpisodePostLike.post_id == post_id, models.EpisodePostLike.user_id == user.id))
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@router.get("/{episode_id}/user-search")
async def search_users(
    episode_id: int,
    q: str = Query(..., min_length=2, max_length=50),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _manage(db, episode_id, user)
    like = "%" + q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    rows = await db.execute(text("SELECT id, username, avatar FROM users WHERE username LIKE :q ESCAPE '!' "
                                 "ORDER BY username LIMIT 10"), {"q": like})
    return [{"id": r[0], "username": r[1], "avatar": r[2]} for r in rows.fetchall()]


async def _add_member(db, ep: models.Episode, user_id: int, background: BackgroundTasks):
    exists = (await db.execute(select(models.EpisodeMember.id).where(
        models.EpisodeMember.episode_id == ep.id, models.EpisodeMember.user_id == user_id))).first()
    if exists:
        raise HTTPException(409, "Этот игрок уже участник")
    db.add(models.EpisodeMember(episode_id=ep.id, user_id=user_id, role="player"))
    await db.execute(delete(models.EpisodeJoinRequest).where(
        models.EpisodeJoinRequest.episode_id == ep.id, models.EpisodeJoinRequest.user_id == user_id))
    await db.commit()
    _notify(background, user_id, f"Вас приняли в эпизод «{ep.title}»")


@router.post("/{episode_id}/members")
async def add_member(
    episode_id: int,
    body: MemberIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    ep, _ = await _manage(db, episode_id, user)
    if not await _users(db, [body.user_id]):
        raise HTTPException(404, "Игрок не найден")
    await _add_member(db, ep, body.user_id, background)
    return {"ok": True}


@router.put("/{episode_id}/members/{user_id}")
async def set_member_role(
    episode_id: int,
    user_id: int,
    body: MemberRoleIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    _, me = await _open(db, episode_id, user)
    if not (_is_admin(user) or (me and me.role == "owner")):
        raise HTTPException(403, "Назначать мастеров может только владелец")
    target = await _membership(db, episode_id, user_id)
    if not target:
        raise HTTPException(404, "Участник не найден")
    if target.role == "owner":
        raise HTTPException(400, "Владельца нельзя переназначить")
    target.role = body.role
    await db.commit()
    return {"ok": True}


@router.delete("/{episode_id}/members/{user_id}")
async def remove_member(
    episode_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    _, me = await _open(db, episode_id, user)
    target = await _membership(db, episode_id, user_id)
    if not target:
        raise HTTPException(404, "Участник не найден")
    if target.role == "owner":
        raise HTTPException(400, "Владелец не может покинуть свой эпизод — его можно только удалить")
    leaving = user.id == user_id
    if not leaving:
        if not _can_manage(user, me):
            raise HTTPException(403, "Исключать участников могут только владелец и мастера")
        if target.role == "master" and not (_is_admin(user) or me.role == "owner"):
            raise HTTPException(403, "Мастера может исключить только владелец")
    # The roles stay with their posts but can no longer write.
    roles = (await db.execute(select(models.EpisodeRole).where(
        models.EpisodeRole.episode_id == episode_id, models.EpisodeRole.user_id == user_id))).scalars().all()
    for r in roles:
        r.archived = True
    await db.delete(target)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Mini-roles
# ---------------------------------------------------------------------------

@router.post("/{episode_id}/roles")
async def create_role(
    episode_id: int,
    body: RoleSlotIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    ep, _ = await _manage(db, episode_id, user)
    holder = await _membership(db, episode_id, body.user_id)
    if not holder:
        raise HTTPException(400, "Роль можно выдать только участнику эпизода")
    role = models.EpisodeRole(episode_id=episode_id, user_id=body.user_id, name=body.name or "Новая роль")
    db.add(role)
    await db.commit()
    await db.refresh(role)
    if body.user_id != user.id:
        _notify(background, body.user_id, f"В эпизоде «{ep.title}» вам выдали роль — оформите её")
    return _role_out(role)


@router.put("/{episode_id}/roles/{role_id}")
async def update_role(
    episode_id: int,
    role_id: int,
    body: RoleIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    _, member = await _open(db, episode_id, user)
    role = await _role(db, episode_id, role_id)
    if role.user_id != user.id and not _can_manage(user, member):
        raise HTTPException(403, "Оформлять роль может её владелец или мастер")
    if role.archived:
        raise HTTPException(400, "Роль в архиве")
    role.name, role.avatar_url, role.description = body.name, body.avatar_url, body.description
    await db.commit()
    return _role_out(role)


@router.delete("/{episode_id}/roles/{role_id}")
async def delete_role(
    episode_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _manage(db, episode_id, user)
    role = await _role(db, episode_id, role_id)
    wrote = (await db.execute(select(models.EpisodePost.id).where(models.EpisodePost.role_id == role_id))).first()
    if wrote:
        role.archived = True  # its posts keep their author
    else:
        await db.delete(role)
    await db.commit()
    return {"ok": True, "archived": bool(wrote)}


# ---------------------------------------------------------------------------
# Join requests
# ---------------------------------------------------------------------------

@router.post("/{episode_id}/requests")
async def request_to_join(
    episode_id: int,
    body: JoinIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    ep, member = await _open(db, episode_id, user)
    if member:
        raise HTTPException(409, "Вы уже участник")
    if ep.is_private:
        raise HTTPException(403, "В закрытый эпизод принимает только владелец")
    exists = (await db.execute(select(models.EpisodeJoinRequest.id).where(
        models.EpisodeJoinRequest.episode_id == episode_id, models.EpisodeJoinRequest.user_id == user.id))).first()
    if exists:
        raise HTTPException(409, "Заявка уже отправлена")
    db.add(models.EpisodeJoinRequest(episode_id=episode_id, user_id=user.id, message=body.message or None))
    await db.commit()
    _notify(background, ep.owner_user_id, f"{user.username} просится в эпизод «{ep.title}»")
    return {"ok": True}


@router.delete("/{episode_id}/requests/mine")
async def withdraw_request(
    episode_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await db.execute(delete(models.EpisodeJoinRequest).where(
        models.EpisodeJoinRequest.episode_id == episode_id, models.EpisodeJoinRequest.user_id == user.id))
    await db.commit()
    return {"ok": True}


@router.get("/{episode_id}/requests")
async def list_requests(
    episode_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _manage(db, episode_id, user)
    rows = (await db.execute(select(models.EpisodeJoinRequest)
                             .where(models.EpisodeJoinRequest.episode_id == episode_id)
                             .order_by(models.EpisodeJoinRequest.id))).scalars().all()
    users = await _users(db, [r.user_id for r in rows])
    return [{"id": r.id, "user_id": r.user_id, "username": (users.get(r.user_id) or {}).get("username"),
             "avatar": (users.get(r.user_id) or {}).get("avatar"), "message": r.message or "",
             "created_at": r.created_at} for r in rows]


async def _request(db, episode_id: int, request_id: int) -> models.EpisodeJoinRequest:
    req = await db.get(models.EpisodeJoinRequest, request_id)
    if not req or req.episode_id != episode_id:
        raise HTTPException(404, "Заявка не найдена")
    return req


@router.post("/{episode_id}/requests/{request_id}/accept")
async def accept_request(
    episode_id: int,
    request_id: int,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    ep, _ = await _manage(db, episode_id, user)
    req = await _request(db, episode_id, request_id)
    await _add_member(db, ep, req.user_id, background)
    return {"ok": True}


@router.post("/{episode_id}/requests/{request_id}/decline")
async def decline_request(
    episode_id: int,
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _manage(db, episode_id, user)
    req = await _request(db, episode_id, request_id)
    await db.delete(req)
    await db.commit()
    return {"ok": True}
