"""Background scheduler of the living-regions tick (FEAT-182, section 3.5).

A daemon thread in the character-service process polls every ``ECON_TICK_POLL_SECONDS`` (default 60 s, first check
:data:`FIRST_DELAY_SECONDS` after startup) and calls :func:`econ_tick.run_tick` with ``trigger='auto'``. The slot
claim in ``econ_tick`` makes it safe to run in several processes at once (``uvicorn --reload`` restarts, replicas):
only one of them steps a slot, a dead run is resumed after its heartbeat goes stale.

Two kill switches: env ``ECON_TICK_ENABLED`` (``1``/``true``/``yes``/``on``; unset = off, so tests and scripts never
start the thread) and the DB toggle ``econ_sim_settings.tick_enabled`` read on every iteration. The thread is never
started under pytest unless a test asks for it explicitly. The manual admin run ignores both switches.
"""

import logging
import os
import sys
import threading
from typing import Callable, Optional

from sqlalchemy.orm import Session

import econ_tick

logger = logging.getLogger("character-service.econ_scheduler")

ENV_ENABLED = "ECON_TICK_ENABLED"
ENV_POLL_SECONDS = "ECON_TICK_POLL_SECONDS"
DEFAULT_POLL_SECONDS = 60
MIN_POLL_SECONDS = 5
FIRST_DELAY_SECONDS = 30
THREAD_NAME = "econ-tick-scheduler"
_TRUTHY = {"1", "true", "yes", "on"}

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def env_enabled() -> bool:
    return os.getenv(ENV_ENABLED, "").strip().lower() in _TRUTHY


def poll_seconds() -> int:
    raw = os.getenv(ENV_POLL_SECONDS, "").strip()
    try:
        value = int(raw) if raw else DEFAULT_POLL_SECONDS
    except ValueError:
        logger.warning("%s=%r is not an integer, using %d", ENV_POLL_SECONDS, raw, DEFAULT_POLL_SECONDS)
        value = DEFAULT_POLL_SECONDS
    return max(MIN_POLL_SECONDS, value)


def _under_pytest() -> bool:
    return "pytest" in sys.modules


def _default_factory() -> Callable[[], Session]:
    import database  # late: tests patch database.SessionLocal
    return database.SessionLocal


def run_scheduled_once(session_factory: Optional[Callable[[], Session]] = None) -> Optional[econ_tick.RunSummary]:
    """One scheduler iteration: respects the DB switch, then claims/runs the current slot (None = nothing done)."""
    factory = session_factory or _default_factory()
    session = factory()
    try:
        enabled = econ_tick.is_tick_enabled(session)
    finally:
        session.close()
    if not enabled:
        return None
    return econ_tick.run_tick(factory, trigger=econ_tick.TRIGGER_AUTO)


def _loop(session_factory: Optional[Callable[[], Session]], first_delay: float, interval: float) -> None:
    logger.info("economy tick scheduler started (first check in %ss, then every %ss)", first_delay, interval)
    if _stop.wait(first_delay):
        return
    while True:
        try:
            run_scheduled_once(session_factory)
        except Exception:  # the thread must never die
            logger.exception("economy tick scheduler iteration failed")
        if _stop.wait(interval):
            logger.info("economy tick scheduler stopped")
            return


def start_scheduler(
    session_factory: Optional[Callable[[], Session]] = None,
    *,
    first_delay: float = FIRST_DELAY_SECONDS,
    interval: Optional[float] = None,
    allow_under_pytest: bool = False,
) -> bool:
    """Start the daemon thread once per process. Returns True when a thread was started by this call."""
    global _thread
    if not env_enabled():
        logger.info("economy tick scheduler disabled (%s is not set)", ENV_ENABLED)
        return False
    if _under_pytest() and not allow_under_pytest:
        logger.info("economy tick scheduler not started under pytest")
        return False
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(
            target=_loop, name=THREAD_NAME, daemon=True,
            args=(session_factory, first_delay, interval if interval is not None else poll_seconds()),
        )
        _thread.start()
        return True


def stop_scheduler(timeout: float = 5.0) -> None:
    """Ask the thread to stop (tests / shutdown); a run in progress is finished first, then the loop exits."""
    global _thread
    _stop.set()
    with _lock:
        thread, _thread = _thread, None
    if thread is not None:
        thread.join(timeout)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
