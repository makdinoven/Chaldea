"""FEAT-205 §3.6-3.7: post-commit dispatch of faction results and the level-up hook.

* :func:`dispatch` — after the caller's commit: publish the notices and deliver the rank-reward outbox of the given
  characters (``faction_rewards.deliver_pending``, own sessions, HTTP allowed — never call inside a transaction).
* :func:`after_level_up` — called by ``crud.check_and_update_level`` right after its commit when the level grew:
  rank re-check in the same session (DB only) + commit, then notices / delivery with the threading rule of
  ``crud.notify_level_changed`` (event-loop thread -> daemon thread; otherwise inline).
* :func:`collecting` — a ContextVar collector: while it is set (inside ``faction_rewards.deliver_pending`` or the
  internal quest hook), the level-up hook only RECORDS (rank re-check + commit) and hands its notices / deliver ids to
  the outer caller, which publishes and delivers once — no recursion, no nested delivery.
"""

import asyncio
import contextlib
import contextvars
import logging
import threading
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import faction_crud
import faction_notify
import faction_rewards

logger = logging.getLogger("character-service.faction_hooks")

_collector: contextvars.ContextVar = contextvars.ContextVar("faction_collector", default=None)


@contextlib.contextmanager
def collecting():
    """Collect the level-up hook's results instead of dispatching them (re-entrant: an outer collector wins)."""
    outer = _collector.get()
    if outer is not None:
        yield outer
        return
    bucket = faction_crud.FlowResult()
    token = _collector.set(bucket)
    try:
        yield bucket
    finally:
        _collector.reset(token)


def is_collecting() -> bool:
    return _collector.get() is not None


def dispatch(notices: Iterable, character_ids: Iterable[int]) -> None:
    """Publish + deliver (sync, post-commit). Never raises."""
    try:
        faction_notify.publish(list(notices or ()))
    except Exception:
        logger.exception("faction notices not published")
    for character_id in sorted({int(c) for c in character_ids or ()}):
        try:
            faction_rewards.deliver_pending(character_id)
        except Exception:
            logger.exception("faction rewards of character %s not delivered", character_id)


def dispatch_result(result: Optional["faction_crud.FlowResult"]) -> None:
    if result is None:
        return
    dispatch(result.notices, result.deliver)


def _has_active_membership(db: Session, character_id: int) -> bool:
    return db.execute(text("SELECT 1 FROM faction_members WHERE character_id = :c AND status = 'active' LIMIT 1"),
                      {"c": int(character_id)}).first() is not None


def after_level_up(db: Session, character_id: int) -> None:
    """Rank re-check after a level-up (non-fatal; the caller wraps it in try/except as well)."""
    if not _has_active_membership(db, character_id):
        return
    result = faction_crud.recheck_ranks(db, character_id)
    db.commit()
    bucket = _collector.get()
    if bucket is not None:
        bucket.merge(result)
        return
    if not result.notices and not result.deliver:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        dispatch_result(result)
        return
    threading.Thread(target=dispatch_result, args=(result,), name=f"faction-levelup-{character_id}",
                     daemon=True).start()
