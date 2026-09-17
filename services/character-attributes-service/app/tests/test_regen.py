"""
FEAT-164 — passive regeneration in rest (character-attributes-service).

Covers:
  * pure interval math (merge_intervals / overlap_seconds / to_datetime);
  * settle_regen: 5%/h credit, fractional carry on small maxima (many reads ==
    one read), cap at max + carry reset, NULL anchor (no retroactive heal),
    NPC / missing character skip, idempotency;
  * busy exclusion for battle (active, late join via joined_at, dropped out,
    fallback to battles.created_at), dungeon (active, finished, forming lobby
    = rest, legacy wiped), gathering (active, finished, overdue active),
    overlapping busy intervals, other characters' sessions;
  * satiety split at expiry mid-window, bonus by rarity, expiry removes the
    modifiers exactly once, resource-point modifiers clamp on expiry;
  * busy-query failure: logged at ERROR, no credit, anchor not moved, expiry
    still runs;
  * endpoint wiring: GET /attributes/{id} settles and persists (schema
    unchanged), participant inserted before GET → time before joined_at
    credited, consume_stamina settles before the check.

The busy-state tables are created with the owners' REAL column names
(see regen_shared_tables.py). Most busy tests assert an exact partial credit:
if a busy query errors, the credit is 0; if it silently returns nothing, the
credit is the full window — both fail the assertion.
"""

import logging
import os
import re
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import models  # noqa: E402
import regen  # noqa: E402
from constants import SATIETY_REGEN_BONUS_BY_RARITY  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402

from tests.regen_shared_tables import (  # noqa: E402
    add_battle,
    add_character,
    add_dungeon,
    add_gathering,
    create_shared_tables,
    drop_shared_tables,
    skip_or_fail_missing,
)

T0 = datetime(2026, 9, 17, 0, 0, 0)
CID = 7


def h(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_tables():
    # Shared tables first: another test module registers a reduced `characters`
    # model in Base.metadata; create_all then skips the existing table.
    create_shared_tables(_test_engine)
    models.Base.metadata.create_all(bind=_test_engine)
    yield
    drop_shared_tables(_test_engine)
    models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    def _override_get_db():
        s = _TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def seed(
    db,
    character_id=CID,
    cur=50,
    mx=100,
    anchor=T0,
    is_npc=False,
    with_character=True,
    **overrides,
):
    """Character + attributes row. All four resources at ``cur``/``mx`` unless overridden."""
    if with_character:
        add_character(db, character_id, is_npc=is_npc)
    values = {}
    for r in ("health", "mana", "energy", "stamina"):
        values[f"current_{r}"] = cur
        values[f"max_{r}"] = mx
    values.update(overrides)
    row = models.CharacterAttributes(character_id=character_id, regen_anchor_at=anchor, **values)
    db.add(row)
    db.commit()
    return row


def settle(db, now, character_id=CID):
    attr = regen.lock_attributes(db, character_id)
    changed = regen.settle_regen(db, attr, now)
    db.commit()
    db.refresh(attr)
    return attr, changed


def add_satiety(db, rarity="rare", started=T0, expires=None, modifiers=None, character_id=CID):
    row = models.CharacterSatiety(
        character_id=character_id,
        item_id=1,
        source_item_name="Жаркое",
        rarity=rarity,
        regen_bonus=SATIETY_REGEN_BONUS_BY_RARITY[rarity],
        modifiers=modifiers or {},
        started_at=started,
        expires_at=expires or started + timedelta(hours=24),
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestPureIntervalMath:
    def test_merge_overlapping_and_touching(self):
        merged = regen.merge_intervals([(h(3), h(4)), (h(0), h(1)), (h(0.5), h(2)), (h(2), h(2.5))])
        assert merged == [(h(0), h(2.5)), (h(3), h(4))]

    def test_merge_drops_empty_inverted_and_none(self):
        merged = regen.merge_intervals([(h(1), h(1)), (h(2), h(1)), (None, h(1)), (h(1), None)])
        assert merged == []

    def test_merge_contained_interval(self):
        assert regen.merge_intervals([(h(0), h(5)), (h(1), h(2))]) == [(h(0), h(5))]

    def test_overlap_counts_union_once_and_clips(self):
        intervals = [(h(-1), h(1)), (h(0.5), h(1.5)), (h(3), h(10))]
        # window [0, 4]: [0,1.5] + [3,4] = 2.5 h
        assert regen.overlap_seconds(h(0), h(4), intervals) == pytest.approx(2.5 * 3600)

    def test_overlap_inverted_window_is_zero(self):
        assert regen.overlap_seconds(h(2), h(1), [(h(0), h(3))]) == 0.0

    def test_overlap_no_intervals(self):
        assert regen.overlap_seconds(h(0), h(1), []) == 0.0

    def test_to_datetime_accepts_strings_and_aware(self):
        assert regen.to_datetime("2026-09-17 01:02:03") == datetime(2026, 9, 17, 1, 2, 3)
        assert regen.to_datetime("2026-09-17T01:02:03.500000") == datetime(2026, 9, 17, 1, 2, 3, 500000)
        from datetime import timezone

        aware = datetime(2026, 9, 17, 1, 0, tzinfo=timezone.utc)
        assert regen.to_datetime(aware).tzinfo is None
        assert regen.to_datetime(None) is None
        with pytest.raises(TypeError):
            regen.to_datetime(123)

    def test_negate_modifiers_skips_zero(self):
        assert regen.negate_modifiers({"strength": 2, "luck": 0, "res_fire": -1.5}) == {
            "strength": -2,
            "res_fire": 1.5,
        }
        assert regen.negate_modifiers(None) == {}


# ---------------------------------------------------------------------------
# Rest credit, carry, cap, anchor
# ---------------------------------------------------------------------------


class TestRestCredit:
    def test_five_percent_per_hour_all_resources(self, db):
        seed(db, cur=50, mx=100, current_energy=10, max_energy=50)
        attr, changed = settle(db, h(2))
        assert changed is False
        assert attr.current_health == 60
        assert attr.current_mana == 60
        assert attr.current_stamina == 60
        assert attr.current_energy == 15  # 50 * 5% * 2h = 5
        assert attr.regen_anchor_at == h(2)

    def test_fractional_carry_small_maximum_many_reads_equal_one_read(self, db):
        # max_energy 50 → 2.5/h; 60 reads one minute apart must not round it away.
        seed(db, character_id=1, cur=0, mx=50)
        seed(db, character_id=2, cur=0, mx=50)
        for minute in range(1, 61):
            settle(db, T0 + timedelta(minutes=minute), character_id=1)
        many, _ = settle(db, h(1), character_id=1)
        single, _ = settle(db, h(1), character_id=2)

        assert many.current_energy == single.current_energy == 2
        assert many.regen_carry_energy == pytest.approx(single.regen_carry_energy, abs=1e-6)
        assert single.regen_carry_energy == pytest.approx(0.5)

        # Carry makes the next hour yield 3 (2.5 + 0.5).
        single, _ = settle(db, h(2), character_id=2)
        assert single.current_energy == 5

        # No point is ever lost: whatever is not yet credited stays in the carry.
        many, _ = settle(db, h(2), character_id=1)
        assert many.current_energy + many.regen_carry_energy == pytest.approx(5.0, abs=1e-6)

    def test_many_reads_match_single_read_at_integer_boundary(self, db):
        seed(db, character_id=1, cur=0, mx=50)
        for minute in range(1, 121):
            settle(db, T0 + timedelta(minutes=minute), character_id=1)
        many, _ = settle(db, h(2), character_id=1)
        assert many.current_energy == 5

    def test_cap_at_max_and_carry_reset(self, db):
        seed(db, cur=99, mx=100, regen_carry_health=0.9)
        attr, _ = settle(db, h(10))
        assert attr.current_health == 100
        assert attr.regen_carry_health == 0.0

    def test_full_resources_skip_busy_queries_and_move_anchor(self, db):
        seed(db, cur=100, mx=100, regen_carry_mana=0.4)
        with patch.object(regen, "load_busy_intervals", side_effect=AssertionError("must not query")):
            attr, _ = settle(db, h(5))
        assert attr.current_health == 100
        assert attr.regen_carry_mana == 0.0
        assert attr.regen_anchor_at == h(5)
        # Nothing "banked": damage right after → only new time counts.
        attr.current_health = 50
        db.commit()
        attr, _ = settle(db, h(6))
        assert attr.current_health == 55

    def test_null_anchor_no_retroactive_heal(self, db):
        seed(db, cur=10, mx=100, anchor=None)
        attr, _ = settle(db, h(100))
        assert attr.current_health == 10
        assert attr.regen_anchor_at == h(100)
        attr, _ = settle(db, h(101))
        assert attr.current_health == 15

    def test_now_not_after_anchor_is_noop(self, db):
        seed(db, cur=10, mx=100, anchor=h(5))
        attr, _ = settle(db, h(4))
        assert attr.current_health == 10
        assert attr.regen_anchor_at == h(5)

    def test_idempotent_second_settle_same_now(self, db):
        seed(db, cur=10, mx=100)
        settle(db, h(3))
        attr, _ = settle(db, h(3))
        assert attr.current_health == 25

    def test_zero_health_regenerates(self, db):
        seed(db, cur=0, mx=100)
        attr, _ = settle(db, h(1))
        assert attr.current_health == 5

    def test_zero_max_is_ignored(self, db):
        seed(db, cur=0, mx=100, max_mana=0, current_mana=0)
        attr, _ = settle(db, h(1))
        assert attr.current_mana == 0
        assert attr.current_health == 5

    def test_npc_is_skipped(self, db):
        seed(db, cur=10, mx=100, is_npc=True)
        attr, changed = settle(db, h(10))
        assert changed is False
        assert attr.current_health == 10
        assert attr.regen_anchor_at == T0  # untouched

    def test_missing_character_row_is_skipped(self, db):
        seed(db, cur=10, mx=100, with_character=False)
        attr, _ = settle(db, h(10))
        assert attr.current_health == 10
        assert attr.regen_anchor_at == T0


# ---------------------------------------------------------------------------
# Busy exclusion — battle
# ---------------------------------------------------------------------------


class TestBattleExclusion:
    def test_active_battle_falls_back_to_created_at(self, db):
        seed(db, cur=0, mx=100)
        add_battle(db, CID, status="in_progress", created_at=h(1), joined_at=None)
        attr, _ = settle(db, h(3))
        assert attr.current_health == 5  # rest only [0, 1]
        assert attr.regen_anchor_at == h(3)

    def test_pending_battle_is_busy(self, db):
        seed(db, cur=0, mx=100)
        add_battle(db, CID, status="pending", created_at=h(2), joined_at=h(2))
        attr, _ = settle(db, h(3))
        assert attr.current_health == 10

    def test_late_join_uses_joined_at(self, db):
        seed(db, cur=0, mx=100)
        add_battle(db, CID, status="in_progress", created_at=T0, joined_at=h(2))
        attr, _ = settle(db, h(3))
        assert attr.current_health == 10  # rest [0, 2]

    def test_dropped_out_participant_rests_after_dropout(self, db):
        seed(db, cur=0, mx=100)
        add_battle(db, CID, status="in_progress", created_at=h(1), joined_at=h(1), dropped_out_at=h(2))
        attr, _ = settle(db, h(4))
        assert attr.current_health == 15  # rest [0,1] + [2,4]

    def test_dropout_in_finished_battle_still_excluded(self, db):
        seed(db, cur=0, mx=100)
        add_battle(db, CID, status="finished", created_at=h(1), joined_at=h(1), dropped_out_at=h(2))
        attr, _ = settle(db, h(4))
        assert attr.current_health == 15

    def test_dropout_before_window_ignored(self, db):
        seed(db, cur=0, mx=100, anchor=h(3))
        add_battle(db, CID, status="finished", created_at=h(1), joined_at=h(1), dropped_out_at=h(2))
        attr, _ = settle(db, h(5))
        assert attr.current_health == 10

    def test_finished_battle_without_dropout_is_not_busy(self, db):
        # Finished battles are handled by the anchor reset at battle end.
        seed(db, cur=0, mx=100, anchor=h(2))
        add_battle(db, CID, status="finished", created_at=h(1), joined_at=h(1))
        attr, _ = settle(db, h(4))
        assert attr.current_health == 10

    def test_other_characters_battle_ignored(self, db):
        seed(db, cur=0, mx=100)
        add_battle(db, 999, status="in_progress", created_at=T0, joined_at=T0)
        attr, _ = settle(db, h(2))
        assert attr.current_health == 10

    def test_anchor_reset_at_battle_end_does_not_credit_battle_time(self, db):
        """Simulates battle-service: finish → raw UPDATE sets current_* and anchor."""
        seed(db, cur=80, mx=100)
        battle_id = add_battle(db, CID, status="in_progress", created_at=h(1), joined_at=h(1))
        attr, _ = settle(db, h(1))  # battle start snapshot settles up to joined_at
        assert attr.current_health == 85
        # battle ends at h(5): status finished + raw UPDATE like battle-service
        db.execute(text("UPDATE battles SET status='finished' WHERE id=:b"), {"b": battle_id})
        db.execute(
            text(
                "UPDATE character_attributes SET current_health = :hp, regen_anchor_at = :now "
                "WHERE character_id = :cid"
            ),
            {"hp": 30, "now": h(5), "cid": CID},
        )
        db.commit()
        db.expire_all()
        attr, _ = settle(db, h(6))
        assert attr.current_health == 35  # only [5, 6] credited


# ---------------------------------------------------------------------------
# Busy exclusion — dungeon
# ---------------------------------------------------------------------------


class TestDungeonExclusion:
    def test_active_dungeon_is_busy_until_now(self, db):
        seed(db, cur=0, mx=100)
        add_dungeon(db, CID, status="active", started_at=h(1))
        attr, _ = settle(db, h(3))
        assert attr.current_health == 5

    def test_finished_dungeon_interval(self, db):
        seed(db, cur=0, mx=100)
        add_dungeon(db, CID, status="completed", started_at=h(1), finished_at=h(2))
        attr, _ = settle(db, h(4))
        assert attr.current_health == 15

    @pytest.mark.parametrize("status", ["escaped", "wiped"])
    def test_other_final_statuses_with_finished_at(self, db, status):
        seed(db, cur=0, mx=100)
        add_dungeon(db, CID, status=status, started_at=h(1), finished_at=h(3))
        attr, _ = settle(db, h(4))
        assert attr.current_health == 10

    def test_forming_lobby_counts_as_rest(self, db):
        seed(db, cur=0, mx=100)
        add_dungeon(db, CID, status="forming", started_at=None)
        attr, _ = settle(db, h(4))
        assert attr.current_health == 20

    def test_legacy_wiped_without_finished_at_is_zero_length(self, db):
        seed(db, cur=0, mx=100)
        add_dungeon(db, CID, status="wiped", started_at=h(1), finished_at=None)
        attr, _ = settle(db, h(4))
        assert attr.current_health == 20

    def test_dungeon_finished_before_window_ignored(self, db):
        seed(db, cur=0, mx=100, anchor=h(3))
        add_dungeon(db, CID, status="completed", started_at=h(1), finished_at=h(2))
        attr, _ = settle(db, h(5))
        assert attr.current_health == 10

    def test_dungeon_started_before_window_active_clipped(self, db):
        seed(db, cur=0, mx=100, anchor=h(2))
        add_dungeon(db, CID, status="active", started_at=h(1))
        attr, _ = settle(db, h(5))
        assert attr.current_health == 0
        assert attr.regen_anchor_at == h(5)


# ---------------------------------------------------------------------------
# Busy exclusion — gathering
# ---------------------------------------------------------------------------


class TestGatheringExclusion:
    def test_active_gathering_until_now(self, db):
        seed(db, cur=0, mx=100)
        add_gathering(db, CID, started_at=h(1), complete_at=h(5), status="active")
        attr, _ = settle(db, h(3))
        assert attr.current_health == 5

    def test_finished_gathering_uses_finished_at(self, db):
        seed(db, cur=0, mx=100)
        add_gathering(db, CID, started_at=h(1), complete_at=h(2), status="completed", finished_at=h(1.5))
        attr, _ = settle(db, h(4))
        # rest 3.5 h → 17.5 → 17, carry 0.5
        assert attr.current_health == 17
        assert attr.regen_carry_health == pytest.approx(0.5)

    def test_cancelled_without_finished_at_uses_complete_at(self, db):
        seed(db, cur=0, mx=100)
        add_gathering(db, CID, started_at=h(1), complete_at=h(2), status="cancelled", finished_at=None)
        attr, _ = settle(db, h(4))
        assert attr.current_health == 15

    def test_overdue_active_gathering_ends_at_complete_at(self, db):
        seed(db, cur=0, mx=100)
        add_gathering(db, CID, started_at=h(1), complete_at=h(2), status="active")
        attr, _ = settle(db, h(4))
        assert attr.current_health == 15

    def test_overlapping_busy_intervals_not_double_counted(self, db):
        seed(db, cur=0, mx=100)
        add_gathering(db, CID, started_at=h(1), complete_at=h(3), status="interrupted_by_battle", finished_at=h(2))
        add_battle(db, CID, status="in_progress", created_at=h(1.5), joined_at=h(1.5))
        add_dungeon(db, CID, status="completed", started_at=h(0.5), finished_at=h(1.2))
        attr, _ = settle(db, h(4))
        # busy = [0.5, 4] → rest 0.5 h → 2.5 → 2
        assert attr.current_health == 2


# ---------------------------------------------------------------------------
# Satiety (regen bonus + expiry)
# ---------------------------------------------------------------------------


class TestSatietyInSettle:
    @pytest.mark.parametrize(
        "rarity,expected",
        [("common", 15), ("rare", 20), ("epic", 25), ("legendary", 30)],
    )
    def test_bonus_by_rarity(self, db, rarity, expected):
        seed(db, cur=0, mx=100)
        add_satiety(db, rarity=rarity, started=T0)
        attr, changed = settle(db, h(2))
        assert changed is False
        assert attr.current_health == expected  # 10 * (1 + bonus)

    def test_rarity_bonus_constants(self):
        assert SATIETY_REGEN_BONUS_BY_RARITY == {
            "common": 0.5, "rare": 1.0, "epic": 1.5, "legendary": 2.0,
        }

    def test_satiety_expiring_mid_window_splits_rate(self, db):
        seed(db, cur=0, mx=100)
        add_satiety(db, rarity="rare", started=h(-22), expires=h(2))
        attr, changed = settle(db, h(4))
        # [0,2] at 10%/h = 20, [2,4] at 5%/h = 10
        assert attr.current_health == 30
        assert changed is True
        assert regen.get_satiety(db, CID) is None

    def test_busy_time_inside_bonus_window_excluded(self, db):
        seed(db, cur=0, mx=100)
        add_satiety(db, rarity="legendary", started=h(-1), expires=h(3))
        add_battle(db, CID, status="finished", created_at=h(1), joined_at=h(1), dropped_out_at=h(2))
        attr, _ = settle(db, h(4))
        # bonus rest [0,1]+[2,3] = 2h * 15%/h = 30; plain [3,4] = 5
        assert attr.current_health == 35

    def test_satiety_expired_before_anchor_no_bonus(self, db):
        seed(db, cur=0, mx=100, anchor=h(5))
        add_satiety(db, rarity="legendary", started=h(-20), expires=h(4))
        attr, changed = settle(db, h(7))
        assert attr.current_health == 10
        assert changed is True

    def test_expiry_removes_modifiers_exactly_once(self, db):
        seed(db, cur=100, mx=100, strength=10, res_fire=1.0)
        # simulate bonuses applied when eaten
        attr = regen.lock_attributes(db, CID)
        attr.strength = 12
        attr.res_fire = 2.5
        db.commit()
        add_satiety(db, rarity="rare", started=h(-23), expires=h(1), modifiers={"strength": 2, "res_fire": 1.5})

        attr, changed = settle(db, h(2))
        assert changed is True
        assert attr.strength == 10
        assert attr.res_fire == pytest.approx(1.0)
        # derived stats are NOT touched (equipment-style removal)
        assert attr.res_physical == pytest.approx(0.0)

        attr, changed = settle(db, h(3))
        assert changed is False
        assert attr.strength == 10
        assert attr.res_fire == pytest.approx(1.0)

    def test_expiry_resource_modifier_shrinks_max_and_clamps_current(self, db):
        # food gave +2 health points → +20 max_health; character is at the bonus max
        seed(db, cur=120, mx=120, health=2)
        add_satiety(db, rarity="common", started=h(-23), expires=h(1), modifiers={"health": 2})
        attr, changed = settle(db, h(2))
        assert changed is True
        assert attr.health == 0
        assert attr.max_health == 100
        assert attr.current_health == 100

    def test_expiry_runs_for_npc_rows_too(self, db):
        # defensive: satiety row on a skipped character is still cleaned up
        seed(db, cur=50, mx=100, is_npc=True, strength=3)
        add_satiety(db, rarity="common", started=h(-30), expires=h(-6), modifiers={"strength": 3})
        attr, changed = settle(db, h(1))
        assert changed is True
        assert attr.strength == 0
        assert attr.current_health == 50


# ---------------------------------------------------------------------------
# Busy-query failure — must be loud and must not credit anything
# ---------------------------------------------------------------------------


class TestBusyQueryFailure:
    def test_missing_table_logs_error_and_credits_nothing(self, db, caplog):
        seed(db, cur=0, mx=100, strength=5)
        add_satiety(db, rarity="rare", started=h(-23), expires=h(1), modifiers={"strength": 5})
        with _test_engine.begin() as conn:
            conn.execute(text("DROP TABLE gathering_sessions"))

        with caplog.at_level(logging.ERROR, logger="regen"):
            attr, changed = settle(db, h(3))

        assert attr.current_health == 0
        assert attr.regen_anchor_at == T0  # not moved — safe direction
        assert changed is True  # expiry still processed
        assert attr.strength == 0
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "busy-query failure must be logged at ERROR"
        assert str(CID) in errors[0].getMessage()

    def test_renamed_column_is_not_silent(self, db, caplog):
        """A typo'd / renamed column in battle_participants must not look like rest."""
        seed(db, cur=0, mx=100)
        with _test_engine.begin() as conn:
            conn.execute(text("DROP TABLE battle_participants"))
            conn.execute(
                text(
                    "CREATE TABLE battle_participants (id INTEGER PRIMARY KEY, battle_id INTEGER, "
                    "character_id INTEGER, dropped_out_at DATETIME, join_time DATETIME)"
                )
            )
        with caplog.at_level(logging.ERROR, logger="regen"):
            attr, _ = settle(db, h(2))
        assert attr.current_health == 0
        assert any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_is_npc_lookup_failure_skips_regen(self, db, caplog):
        seed(db, cur=0, mx=100)
        with _test_engine.begin() as conn:
            conn.execute(text("DROP TABLE characters"))
        with caplog.at_level(logging.ERROR, logger="regen"):
            attr, _ = settle(db, h(2))
        assert attr.current_health == 0
        assert attr.regen_anchor_at == T0
        assert any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_busy_sql_has_no_server_clock(self):
        for stmt in (regen._BATTLE_INTERVALS_SQL, regen._DUNGEON_INTERVALS_SQL, regen._GATHERING_INTERVALS_SQL):
            sql = str(stmt).upper()
            assert "NOW()" not in sql
            assert "UTC_TIMESTAMP" not in sql
            assert "CURRENT_TIMESTAMP" not in sql


# ---------------------------------------------------------------------------
# Real column names must match the owner services' models
# ---------------------------------------------------------------------------

_SERVICES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

_OWNER_COLUMNS = [
    ("battle-service/app/models.py", "battles", ["status", "created_at"]),
    ("battle-service/app/models.py", "battle_participants", ["battle_id", "character_id", "dropped_out_at", "joined_at"]),
    ("dungeon-service/app/models.py", "dungeon_sessions", ["status", "started_at", "finished_at"]),
    ("dungeon-service/app/models.py", "dungeon_session_members", ["session_id", "character_id"]),
    ("locations-service/app/models.py", "gathering_sessions", ["character_id", "started_at", "complete_at", "status", "finished_at"]),
    ("character-service/app/models.py", "characters", ["is_npc"]),
]


def _class_body(source: str, table: str) -> str:
    m = re.search(r"__tablename__\s*=\s*['\"]%s['\"]" % re.escape(table), source)
    assert m, f"table {table} not found in owner model"
    nxt = re.search(r"\nclass \w+", source[m.end():])
    return source[m.end(): m.end() + nxt.start()] if nxt else source[m.end():]


class TestSharedSchemaMatchesOwners:
    @pytest.mark.parametrize("path,table,columns", _OWNER_COLUMNS)
    def test_owner_model_has_columns(self, path, table, columns):
        full = os.path.join(_SERVICES_DIR, path)
        if not os.path.exists(full):
            skip_or_fail_missing(full, f"owner model {path}")
        with open(full, encoding="utf-8") as f:
            body = _class_body(f.read(), table)
        for col in columns:
            assert re.search(r"^\s+%s\s*[:=]" % re.escape(col), body, re.M), (
                f"{table}.{col} not found in {path} — update regen.py SQL and the test DDL"
            )

    @pytest.mark.parametrize(
        "stmt_name,columns",
        [
            ("_BATTLE_INTERVALS_SQL", ["bp.joined_at", "b.created_at", "bp.dropped_out_at", "b.status", "bp.character_id"]),
            ("_DUNGEON_INTERVALS_SQL", ["ds.started_at", "ds.finished_at", "ds.status", "dsm.character_id", "dsm.session_id"]),
            ("_GATHERING_INTERVALS_SQL", ["started_at", "status", "complete_at", "finished_at", "character_id"]),
        ],
    )
    def test_regen_sql_uses_expected_columns(self, stmt_name, columns):
        sql = str(getattr(regen, stmt_name))
        for col in columns:
            assert col in sql


# ---------------------------------------------------------------------------
# Endpoint wiring
# ---------------------------------------------------------------------------


def _utcnow_s():
    return datetime.utcnow().replace(microsecond=0)


def reload_row(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterAttributes).filter_by(character_id=character_id).one()


class TestEndpointWiring:
    def test_get_attributes_settles_and_persists(self, client, db):
        seed(db, cur=0, mx=100, anchor=_utcnow_s() - timedelta(hours=2))
        resp = client.get(f"/attributes/{CID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_health"] == 10
        for hidden in ("regen_anchor_at", "regen_carry_health"):
            assert hidden not in body
        db.expire_all()
        row = db.query(models.CharacterAttributes).filter_by(character_id=CID).one()
        assert row.current_health == 10
        assert row.regen_anchor_at > _utcnow_s() - timedelta(minutes=1)
        # immediate second read gains nothing
        assert client.get(f"/attributes/{CID}").json()["current_health"] == 10

    def test_get_attributes_404(self, client):
        assert client.get("/attributes/424242").status_code == 404

    def test_participant_inserted_before_get_credits_time_before_joined_at(self, client, db):
        now = _utcnow_s()
        seed(db, cur=0, mx=100, anchor=now - timedelta(hours=2))
        # battle-service inserts the participant first, then fetches attributes
        add_battle(db, CID, status="pending", created_at=now - timedelta(hours=1), joined_at=now - timedelta(hours=1))
        body = client.get(f"/attributes/{CID}").json()
        row = reload_row(db)
        # 1 h before joined_at credited (5 points incl. carry); battle time not credited.
        assert body["current_health"] in (4, 5)
        assert row.current_health + row.regen_carry_health == pytest.approx(5.0, abs=1e-3)

    def test_participant_inserted_before_get_exact_points(self, client, db):
        now = _utcnow_s()
        seed(db, cur=0, mx=100, anchor=now - timedelta(hours=2))
        add_battle(db, CID, status="pending", created_at=now - timedelta(hours=1), joined_at=now - timedelta(hours=1))
        regen_now = datetime.utcnow().replace(microsecond=123457)
        attr = regen.lock_attributes(db, CID)
        regen.settle_regen(db, attr, regen_now)
        db.commit()
        assert attr.current_health == 5

    def test_consume_stamina_settles_before_check(self, client, db):
        seed(db, cur=0, mx=100, anchor=_utcnow_s() - timedelta(hours=2))
        resp = client.post(f"/attributes/{CID}/consume_stamina", json={"amount": 8})
        assert resp.status_code == 200, resp.text
        db.expire_all()
        row = db.query(models.CharacterAttributes).filter_by(character_id=CID).one()
        assert row.current_stamina == 2

    def test_consume_stamina_insufficient_still_commits_settle(self, client, db):
        seed(db, cur=0, mx=100, anchor=_utcnow_s() - timedelta(hours=2))
        resp = client.post(f"/attributes/{CID}/consume_stamina", json={"amount": 50})
        assert resp.status_code == 400
        db.expire_all()
        row = db.query(models.CharacterAttributes).filter_by(character_id=CID).one()
        assert row.current_stamina == 10

    def test_recover_settles_first(self, client, db):
        seed(db, cur=0, mx=100, anchor=_utcnow_s() - timedelta(hours=2))
        resp = client.post(f"/attributes/{CID}/recover", json={"health_recovery": 3})
        assert resp.status_code == 200, resp.text
        db.expire_all()
        row = db.query(models.CharacterAttributes).filter_by(character_id=CID).one()
        assert row.current_health == 13

    def test_expiry_via_get_twice_removes_bonus_once(self, client, db):
        now = _utcnow_s()
        seed(db, cur=100, mx=100, anchor=now, strength=7)
        add_satiety(db, started=now - timedelta(hours=25), expires=now - timedelta(hours=1), modifiers={"strength": 2})
        assert client.get(f"/attributes/{CID}").json()["strength"] == 5
        assert client.get(f"/attributes/{CID}").json()["strength"] == 5
        db.expire_all()
        assert regen.get_satiety(db, CID) is None
