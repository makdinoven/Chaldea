"""FEAT-161 (T9/T10) — turn deadlines must live in NAIVE UTC.

Before the fix, ``battle-service`` built turn deadlines as
``datetime.now(timezone.utc).astimezone(moscow_tz)`` (offset-aware ``+03:00``)
while the resume path wrote the very same ``state["deadline_at"]`` field naive.
Two consequences, both proven on live data:

* pausing a battle raised ``TypeError: can't subtract offset-naive and
  offset-aware datetimes`` (naive ``utcnow()`` minus an aware deadline);
* ``battle_turns.deadline_at`` (note: the column is on ``battle_turns``, NOT on
  ``battles`` as §2.3 of the feature file says — verified in ``models.py``) was
  stored in Moscow wall-clock, so existing rows show **27 h** between
  ``submitted_at`` and ``deadline_at`` instead of ``TURN_TIMEOUT_HOURS`` (24).

These tests pin the fixed behaviour:

* a freshly built deadline is naive UTC and exactly ``TURN_TIMEOUT_HOURS`` ahead;
* pause + resume never raise, for BOTH a legacy ``+03:00`` state string (battles
  in flight across the deploy: Redis already holds those) and a naive one;
* the value handed to ``battle_turns.deadline_at`` is UTC, not UTC+3;
* the ZSET deadline score is the correct absolute epoch for both string forms;
* ``parse_deadline`` is total — ``None``/``''``/whitespace/garbage/malformed ISO
  all return ``None`` instead of raising.

No real Redis, MySQL or Mongo is touched: the Redis client is an ``AsyncMock``
and the DB session is a stub, so nothing is written anywhere to clean up.
"""

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Env vars must exist before config/database are imported — they have no defaults.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

APP_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, APP_DIR)

import database  # noqa: E402

database.engine = MagicMock()

# Heavy external clients — mocked only if nobody imported them for real yet, so
# this file behaves the same run alone or inside the full suite.
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())
for _mod_name in (
    "mongo_client", "mongo_helpers", "tasks", "inventory_client",
    "character_client", "skills_client", "rabbitmq_publisher",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()
_tasks_mock = sys.modules["tasks"]
if isinstance(_tasks_mock, MagicMock):
    _tasks_mock.save_log = MagicMock()
    _tasks_mock.save_log.delay = MagicMock()

import main  # noqa: E402
import crud  # noqa: E402
import models  # noqa: E402
from config import settings  # noqa: E402

# ---------------------------------------------------------------------------
# The REAL redis_state helpers.
#
# Earlier test files (test_admin_battles, test_battle_fixes, …) replace the
# ``redis_state`` module in ``sys.modules`` with a MagicMock before importing
# ``main``, so ``main.utc_now`` / ``parse_deadline`` / ``deadline_epoch`` may be
# MagicMock attributes by the time this file is collected. Load the real module
# from disk under a private name — this does NOT touch ``sys.modules`` and so
# cannot disturb any other test file — and bind the real helpers into ``main``
# for the duration of each test via ``patch.object`` (no ``create=True``: if T9
# were reverted the names would not exist in ``main`` and these tests would fail
# loudly, which is exactly what we want).
# ---------------------------------------------------------------------------
_spec = importlib.util.spec_from_file_location(
    "_real_redis_state_for_tz_tests", os.path.join(APP_DIR, "redis_state.py")
)
real_redis_state = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(real_redis_state)

utc_now = real_redis_state.utc_now
to_naive_utc = real_redis_state.to_naive_utc
parse_deadline = real_redis_state.parse_deadline
deadline_epoch = real_redis_state.deadline_epoch
_real_init_battle_state = real_redis_state.init_battle_state

assert not isinstance(utc_now, MagicMock)
assert not isinstance(parse_deadline, MagicMock)

TIMEOUT_HOURS = settings.TURN_TIMEOUT_HOURS
MOSCOW = timezone(timedelta(hours=3))


class _RealHelpers:
    """Bind main's time helpers to the genuine implementations for a test."""

    def __enter__(self):
        # Only rebind what main actually imported: if the helpers were gone
        # (T9 reverted) the tests must fail on main's real behaviour — the
        # TypeError on pause, the offset-aware deadline — not on a patch error.
        self._patches = [
            patch.object(main, name, fn)
            for name, fn in (
                ("utc_now", utc_now),
                ("parse_deadline", parse_deadline),
                ("deadline_epoch", deadline_epoch),
            )
            if hasattr(main, name)
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        return False


def _fake_db():
    """AsyncSession stub: pending-request count of 0, no participants."""
    result = MagicMock()
    result.scalar = MagicMock(return_value=0)
    result.fetchall = MagicMock(return_value=[])
    result.fetchone = MagicMock(return_value=None)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _state(deadline_raw, next_actor=11):
    return {
        "turn_number": 3,
        "deadline_at": deadline_raw,
        "next_actor": next_actor,
        "first_actor": next_actor,
        "turn_order": [11, 12],
        "participants": {"11": {"hp": 100}, "12": {"hp": 100}},
    }


# ===========================================================================
# 1. The helpers themselves
# ===========================================================================
class TestDeadlineHelpers:
    def test_utc_now_is_naive_and_really_utc(self):
        now = utc_now()
        assert now.tzinfo is None, "deadlines must be naive, like every other DB timestamp"
        reference = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((now - reference).total_seconds()) < 5, (
            "utc_now() must be UTC, not Moscow wall-clock"
        )
        # The old bug in one assertion: Moscow wall-clock is 3 h ahead of this.
        moscow_wall = datetime.now(MOSCOW).replace(tzinfo=None)
        assert abs((now - moscow_wall).total_seconds()) > 3000

    def test_to_naive_utc_converts_offset_aware(self):
        aware = datetime(2026, 9, 13, 23, 10, 0, tzinfo=MOSCOW)
        assert to_naive_utc(aware) == datetime(2026, 9, 13, 20, 10, 0)
        assert to_naive_utc(aware).tzinfo is None

    def test_to_naive_utc_leaves_naive_untouched(self):
        naive = datetime(2026, 9, 13, 20, 10, 0)
        assert to_naive_utc(naive) == naive

    def test_parse_legacy_moscow_string(self):
        """The migration case: Redis already holds '+03:00' strings."""
        assert parse_deadline("2026-09-13T23:10:00+03:00") == datetime(2026, 9, 13, 20, 10, 0)

    def test_parse_naive_string(self):
        assert parse_deadline("2026-09-13T20:10:00") == datetime(2026, 9, 13, 20, 10, 0)

    def test_parse_z_suffix(self):
        assert parse_deadline("2026-09-13T20:10:00Z") == datetime(2026, 9, 13, 20, 10, 0)

    def test_all_three_forms_are_the_same_instant(self):
        forms = [
            "2026-09-13T20:10:00",
            "2026-09-13T20:10:00Z",
            "2026-09-13T23:10:00+03:00",
        ]
        parsed = {parse_deadline(f) for f in forms}
        assert len(parsed) == 1, f"forms disagree: {parsed}"

    def test_parse_accepts_datetime_objects(self):
        aware = datetime(2026, 9, 13, 23, 10, tzinfo=MOSCOW)
        assert parse_deadline(aware) == datetime(2026, 9, 13, 20, 10)

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "   ",
            "\t\n",
            "garbage",
            "not-a-date-at-all",
            "2026-13-45T99:99:99",
            "2026-09-13T25:61:00",
            "2026-09-13T20:10:00+99:99",
        ],
        ids=[
            "none", "empty", "spaces", "whitespace", "garbage", "words",
            "impossible-date", "impossible-time", "bad-offset",
        ],
    )
    def test_parse_deadline_is_total(self, raw):
        """Never raises — §3.6 requires the parser to be total."""
        assert parse_deadline(raw) is None

    def test_deadline_epoch_treats_naive_as_utc(self):
        naive = datetime(2026, 9, 13, 20, 10, 0)
        aware = datetime(2026, 9, 13, 23, 10, 0, tzinfo=MOSCOW)
        expected = aware.timestamp()
        assert deadline_epoch(naive) == expected
        assert deadline_epoch(aware) == expected
        assert deadline_epoch(naive) == datetime(
            2026, 9, 13, 20, 10, 0, tzinfo=timezone.utc
        ).timestamp()


# ===========================================================================
# 2. A newly created deadline
# ===========================================================================
class TestNewDeadlineIsNaiveUtc:
    @pytest.mark.asyncio
    async def test_assemble_battle_deadline_is_naive_utc_and_exact_timeout(self):
        """The real battle-creation path returns a naive UTC deadline, +24 h (not +27 h)."""
        participants = [
            SimpleNamespace(id=11, character_id=101, team=0),
            SimpleNamespace(id=12, character_id=102, team=1),
        ]
        battle_obj = SimpleNamespace(id=777)

        async def _info(character_id, participant_id):
            return {
                "participant_id": participant_id,
                "character_id": character_id,
                "fast_slots": [],
                "equipment_durability": {},
                "attributes": {
                    "current_health": 100, "current_mana": 50,
                    "current_energy": 50, "current_stamina": 50,
                    "max_health": 100, "max_mana": 100,
                    "max_energy": 100, "max_stamina": 100,
                    "agility": 10, "strength": 10, "intelligence": 5,
                },
            }

        before = utc_now()
        with _RealHelpers(), \
                patch.object(main, "create_battle",
                             new=AsyncMock(return_value=(battle_obj, participants))), \
                patch.object(main, "build_participant_info", new=AsyncMock(side_effect=_info)), \
                patch.object(main, "save_snapshot", new=AsyncMock()), \
                patch.object(main, "cache_snapshot", new=AsyncMock()), \
                patch.object(main, "init_battle_state", new=AsyncMock()) as init_mock, \
                patch.object(main, "get_redis_client", new=AsyncMock(return_value=AsyncMock())):
            _b, _p, _first, deadline = await main._assemble_battle(
                _fake_db(), [101, 102], [0, 1], "pvp", 5
            )
        after = utc_now()

        assert deadline.tzinfo is None, "deadline must be naive UTC, not offset-aware +03:00"
        assert deadline >= before + timedelta(hours=TIMEOUT_HOURS) - timedelta(seconds=5)
        assert deadline <= after + timedelta(hours=TIMEOUT_HOURS) + timedelta(seconds=5)
        hours_ahead = (deadline - before).total_seconds() / 3600
        assert abs(hours_ahead - TIMEOUT_HOURS) < 0.01, (
            f"turn window is {hours_ahead:.2f} h, expected {TIMEOUT_HOURS} h "
            f"(the Moscow bug produced {TIMEOUT_HOURS + 3})"
        )
        # The same naive value is what the Redis state is initialised with.
        assert init_mock.await_args.kwargs["deadline_at"] is deadline

    @pytest.mark.asyncio
    async def test_init_battle_state_stores_naive_utc_even_for_legacy_aware_input(self):
        """redis_state normalises before writing: no '+03:00' ever reaches Redis."""
        aware = datetime(2026, 9, 13, 23, 10, 0, tzinfo=MOSCOW)
        mock_redis = AsyncMock()
        payload = [
            {
                "participant_id": 11, "character_id": 101, "team": 0,
                "hp": 100, "mana": 50, "energy": 50, "stamina": 50,
                "max_hp": 100, "max_mana": 100, "max_energy": 100,
                "max_stamina": 100, "fast_slots": [],
            },
            {
                "participant_id": 12, "character_id": 102, "team": 1,
                "hp": 100, "mana": 50, "energy": 50, "stamina": 50,
                "max_hp": 100, "max_mana": 100, "max_energy": 100,
                "max_stamina": 100, "fast_slots": [],
            },
        ]
        with patch.object(real_redis_state, "get_redis_client",
                          new=AsyncMock(return_value=mock_redis)):
            await _real_init_battle_state(
                battle_id=777,
                participants_payload=payload,
                first_actor_participant_id=11,
                deadline_at=aware,
                location_id=5,
            )

        set_calls = [c for c in mock_redis.set.call_args_list if "state" in str(c)]
        assert set_calls, "state was not written"
        stored = json.loads(set_calls[0].args[1])["deadline_at"]
        assert "+03:00" not in stored and not stored.endswith("Z")
        assert parse_deadline(stored) == datetime(2026, 9, 13, 20, 10, 0)

        zadd_calls = [c for c in mock_redis.zadd.call_args_list
                      if c.args and c.args[0] == real_redis_state.ZSET_DEADLINES]
        assert zadd_calls, "deadline was not added to the ZSET"
        score = list(zadd_calls[0].args[1].values())[0]
        assert score == aware.timestamp(), "ZSET score must be the absolute epoch"

    @pytest.mark.asyncio
    async def test_value_written_to_battle_turns_deadline_at_is_utc(self):
        """battle_turns.deadline_at — UTC, so deadline − submitted_at == 24 h, not 27 h.

        ``submitted_at`` defaults to ``datetime.utcnow`` (models.py); that is the
        exact comparison which showed 27 h on live rows.
        """
        deadline = utc_now() + timedelta(hours=TIMEOUT_HOURS)

        captured = {}
        db = AsyncMock()
        db.add = MagicMock(side_effect=lambda obj: captured.setdefault("turn", obj))
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        skills = SimpleNamespace(
            attack_skill_id=1, defense_skill_id=None,
            support_skill_id=None, item_id=None,
        )
        await crud.write_turn(
            db, battle_id=777, actor_participant_id=11,
            turn_number=4, skills=skills, deadline_at=deadline,
        )
        turn = captured["turn"]
        assert isinstance(turn, models.BattleTurn)
        assert turn.deadline_at.tzinfo is None, "aiomysql would silently strip a tzinfo here"

        # SQLAlchemy wraps a zero-arg default so it takes an execution context.
        submitted_default = models.BattleTurn.__table__.c.submitted_at.default
        assert submitted_default.is_callable
        submitted_at = submitted_default.arg(None)
        assert submitted_at.tzinfo is None
        gap_hours = (turn.deadline_at - submitted_at).total_seconds() / 3600
        assert abs(gap_hours - TIMEOUT_HOURS) < 0.01, (
            f"TIMESTAMPDIFF(submitted_at, deadline_at) would be {gap_hours:.2f} h; "
            f"expected {TIMEOUT_HOURS} h (live rows showed {TIMEOUT_HOURS + 3})"
        )


# ===========================================================================
# 3. Pause / resume across both state-string forms
# ===========================================================================
class TestPauseResumeBothStateForms:
    """A battle in flight across the deploy keeps a '+03:00' string in Redis."""

    @staticmethod
    def _legacy_state(seconds_ahead=3600, next_actor=11):
        moscow_deadline = datetime.now(MOSCOW) + timedelta(seconds=seconds_ahead)
        return _state(moscow_deadline.isoformat(), next_actor)

    @staticmethod
    def _naive_state(seconds_ahead=3600, next_actor=11):
        return _state((utc_now() + timedelta(seconds=seconds_ahead)).isoformat(), next_actor)

    async def _pause(self, state):
        saved = {}
        rds = AsyncMock()
        with _RealHelpers(), \
                patch.object(main, "load_state", new=AsyncMock(return_value=state)), \
                patch.object(main, "save_state",
                             new=AsyncMock(side_effect=lambda bid, st: saved.update(st))), \
                patch.object(main, "get_redis_client", new=AsyncMock(return_value=rds)):
            await main.pause_battle(_fake_db(), 777)
        return saved, rds

    async def _resume(self, state):
        saved = {}
        rds = AsyncMock()
        with _RealHelpers(), \
                patch.object(main, "load_state", new=AsyncMock(return_value=state)), \
                patch.object(main, "save_state",
                             new=AsyncMock(side_effect=lambda bid, st: saved.update(st))), \
                patch.object(main, "get_redis_client", new=AsyncMock(return_value=rds)), \
                patch.object(main, "publish_notification", new=AsyncMock()):
            resumed = await main.resume_battle_if_ready(_fake_db(), 777)
        return resumed, saved, rds

    @staticmethod
    def _zset_calls(rds):
        return [c for c in rds.zadd.await_args_list
                if c.args and c.args[0] == main.ZSET_DEADLINES]

    @pytest.mark.asyncio
    async def test_pause_with_legacy_offset_state_does_not_raise(self):
        """This is the reported crash: naive utcnow() − aware '+03:00' deadline."""
        saved, rds = await self._pause(self._legacy_state())
        assert saved["paused"] is True
        assert abs(saved["remaining_deadline_seconds"] - 3600) < 5, (
            "legacy '+03:00' state must not be read as 3 h further away"
        )
        assert rds.zrem.await_count == 2

    @pytest.mark.asyncio
    async def test_pause_with_naive_state_does_not_raise(self):
        saved, rds = await self._pause(self._naive_state())
        assert saved["paused"] is True
        assert abs(saved["remaining_deadline_seconds"] - 3600) < 5
        assert rds.zrem.await_count == 2

    @pytest.mark.asyncio
    async def test_both_state_forms_give_the_same_remaining_time(self):
        legacy, _ = await self._pause(self._legacy_state())
        naive, _ = await self._pause(self._naive_state())
        assert abs(
            legacy["remaining_deadline_seconds"] - naive["remaining_deadline_seconds"]
        ) < 5, "the two representations describe the same instant"

    @pytest.mark.asyncio
    async def test_pause_with_unparseable_deadline_does_not_raise(self):
        saved, _ = await self._pause(_state("garbage"))
        assert saved["paused"] is True
        assert saved["remaining_deadline_seconds"] == 0

    @pytest.mark.asyncio
    async def test_pause_with_expired_deadline_clamps_to_zero(self):
        past = (datetime.now(MOSCOW) - timedelta(hours=2)).isoformat()
        saved, _ = await self._pause(_state(past))
        assert saved["remaining_deadline_seconds"] == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("form", ["legacy", "naive"])
    async def test_resume_writes_naive_utc_and_correct_zset_score(self, form):
        state = self._legacy_state() if form == "legacy" else self._naive_state()
        paused_state, _ = await self._pause(state)
        full_state = dict(state)
        full_state.update(paused_state)

        before = utc_now()
        resumed, saved, rds = await self._resume(full_state)
        assert resumed is True

        new_deadline = saved["deadline_at"]
        assert "+03:00" not in new_deadline and not new_deadline.endswith("Z"), (
            f"resume must write naive UTC, got {new_deadline!r}"
        )
        parsed = parse_deadline(new_deadline)
        assert parsed.tzinfo is None
        assert abs((parsed - (before + timedelta(seconds=3600))).total_seconds()) < 10

        zadd_calls = self._zset_calls(rds)
        assert zadd_calls, "resume must re-arm the ZSET deadline"
        member, score = list(zadd_calls[0].args[1].items())[0]
        assert member == "777:11"
        expected_epoch = (
            before.replace(tzinfo=timezone.utc) + timedelta(seconds=3600)
        ).timestamp()
        assert abs(score - expected_epoch) < 10, (
            "ZSET score must be the absolute epoch of the deadline; a Moscow-built "
            "value would be off by 10800 s"
        )
        assert abs(score - deadline_epoch(parsed)) < 0.001

    @pytest.mark.asyncio
    async def test_resume_zset_score_matches_for_both_forms(self):
        legacy_paused, _ = await self._pause(self._legacy_state())
        naive_paused, _ = await self._pause(self._naive_state())

        scores = []
        for paused in (legacy_paused, naive_paused):
            state = _state("2026-09-13T20:10:00")
            state.update(paused)
            _resumed, _saved, rds = await self._resume(state)
            call = self._zset_calls(rds)[0]
            scores.append(list(call.args[1].values())[0])

        assert abs(scores[0] - scores[1]) < 10, (
            f"legacy and naive state must resume to the same instant: {scores}"
        )
