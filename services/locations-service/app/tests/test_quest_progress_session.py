"""Quest auto-progress runs as a background task, after `get_db` has closed the request session.

It must use (and close) a session of its own: reusing the closed request session re-opened a connection that
nobody closed, which stayed `Sleep` with an open InnoDB transaction after every quick move (ISSUES, FEAT-202).
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # noqa: E402


class _OwnSession:
    def __init__(self):
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *exc):
        self.exited = True
        return False


def test_auto_progress_uses_its_own_session_and_closes_it():
    own = _OwnSession()
    request_session = MagicMock(name="request_session")
    progress = AsyncMock(return_value=[])
    with patch.object(main, "async_session", lambda: own), \
            patch.object(main.crud, "auto_progress_quests", progress):
        asyncio.run(main._auto_progress_quest(request_session, 7, "visit_location", 1, 42))
    progress.assert_awaited_once_with(own, 7, "visit_location", 1, 42, None)
    assert own.entered and own.exited
    request_session.execute.assert_not_called()


def test_auto_progress_errors_are_swallowed_and_the_session_still_closes():
    own = _OwnSession()
    with patch.object(main, "async_session", lambda: own), \
            patch.object(main.crud, "auto_progress_quests", AsyncMock(side_effect=RuntimeError("boom"))):
        asyncio.run(main._auto_progress_quest(MagicMock(), 7, "write_posts"))
    assert own.exited
