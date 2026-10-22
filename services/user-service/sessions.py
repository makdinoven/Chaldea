"""Login sessions (migration 0031).

Every login/registration creates a `user_sessions` row; its id travels as the
`sid` claim in both tokens of the pair. Deleting the row revokes both tokens
at once (checked in `auth.get_current_user` and `/users/refresh`).

Open WebSockets in notification-service were authenticated once at the
handshake, so revoking a session alone would not close them. After every
revocation user-service tells notification-service which sessions are gone
(`notify_sessions_revoked`); that call is best effort and never fails the
request that triggered it.
"""
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from models import UserSession

logger = logging.getLogger(__name__)

# Must match auth.REFRESH_TOKEN_EXPIRE_DAYS: a session unused for longer has
# no live refresh token left, so it can never be used again.
SESSION_IDLE_LIFETIME = timedelta(days=7)

# `last_used_at` is bumped at most this often, so an authenticated request is
# not a DB write every time.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)

USER_AGENT_MAX_LENGTH = 255

NOTIFICATION_KICK_TIMEOUT = 3.0


def new_session_id() -> str:
    return uuid.uuid4().hex


def create_session(db: Session, user_id: int, user_agent: Optional[str]) -> UserSession:
    """Create and commit a new session row for the user."""
    now = datetime.utcnow()
    session = UserSession(
        id=new_session_id(),
        user_id=user_id,
        created_at=now,
        last_used_at=now,
        user_agent=(user_agent or None) and user_agent[:USER_AGENT_MAX_LENGTH],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def purge_stale_sessions(db: Session, user_id: int) -> None:
    """Delete the user's sessions unused for longer than the refresh lifetime.

    Lazy cleanup: called on login, refresh and when listing sessions, scoped
    to one user so it stays an indexed delete.
    """
    cutoff = datetime.utcnow() - SESSION_IDLE_LIFETIME
    db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.last_used_at < cutoff,
    ).delete(synchronize_session=False)
    db.commit()


def get_live_session(db: Session, session_id: str, user_id: int) -> Optional[UserSession]:
    """The session row if it exists, belongs to the user and is not stale."""
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == user_id,
    ).first()
    if session is None:
        return None
    if session.last_used_at is not None and \
            session.last_used_at < datetime.utcnow() - SESSION_IDLE_LIFETIME:
        return None
    return session


def touch_session(db: Session, session: UserSession, force: bool = False) -> None:
    """Bump last_used_at, at most once per SESSION_TOUCH_INTERVAL unless forced."""
    now = datetime.utcnow()
    if not force and session.last_used_at is not None and \
            now - session.last_used_at < SESSION_TOUCH_INTERVAL:
        return
    try:
        db.query(UserSession).filter(UserSession.id == session.id).update(
            {UserSession.last_used_at: now}, synchronize_session=False
        )
        db.commit()
    except Exception:
        # Bookkeeping only: a failed touch must not fail authentication.
        db.rollback()
        logger.warning("Не удалось обновить last_used_at сессии", exc_info=True)


def list_sessions(db: Session, user_id: int) -> List[UserSession]:
    return (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .order_by(UserSession.last_used_at.desc(), UserSession.created_at.desc())
        .all()
    )


def notify_sessions_revoked(
    user_id: int,
    session_ids: Optional[List[str]] = None,
    all_except: Optional[str] = None,
) -> None:
    """Ask notification-service to close WebSockets of revoked sessions.

    At most one of `session_ids` / `all_except`:
    - session_ids: close sockets opened with tokens of these sessions;
    - all_except: close every socket of the user except those of this session
      (sockets opened with legacy tokens without `sid` are closed too);
    - neither: close every socket of the user.

    Best effort: any failure is logged and swallowed. Runs as a background
    task, so the caller's response never waits for it.
    """
    base_url = os.environ.get("NOTIFICATION_SERVICE_URL", "http://notification-service:8007")
    body = {"user_id": user_id}
    if session_ids is not None:
        body["session_ids"] = list(session_ids)
    if all_except is not None:
        body["all_except"] = all_except
    try:
        resp = httpx.post(
            f"{base_url}/notifications/internal/sessions/revoked",
            json=body,
            headers={"X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", "")},
            timeout=NOTIFICATION_KICK_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(
                "notification-service не закрыл сокеты отозванных сессий: HTTP %s",
                resp.status_code,
            )
    except Exception as e:
        logger.warning("notification-service недоступен для закрытия сокетов: %r", e)
