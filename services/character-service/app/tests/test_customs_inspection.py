"""FEAT-216 task 4: the inspection of a legal caravan at its customs post (focused DB checks on the FEAT-211 world).

A foreign caravan (seller country 2 → buyer country 1, value 400, duty 40) gets a post on its road by hand
(``customs_index`` / ``customs_location_id`` / ``customs_state = 'pending'`` — what task 3's dispatch stores). The full
flows (officers, contraband, seizure) are task 15. After every pass: world sum 0 and
``escrow == Σ (paid − raid_paid − freight_paid − duty_paid)`` of caravans in transit. Pass times sit a minute past
the due time: SQLite compares the ORM's microsecond DATETIME strings with the plain bound ``now`` textually.
"""

from datetime import timedelta

import pytest

import caravan_pass
import customs_crud
import econ_caravan as ec
import econ_tick
import economy_caravan_crud as crud
from tests.econ_contract_cases import WORLD_SUM_SQL
from tests.test_econ_tick import _balance, _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec
from tests.test_econ_tick_events import calendar  # noqa: F401  (autouse: no calendar HTTP)
from tests.test_physical_caravans import (  # noqa: F401
    L_GATE1, L_GATE2, L_ROAD2, RAIDER, START, ROAD_1_2, _add_raider, _arrive, _dispatch, _fake_raid, _physical_world,
    _row, raider, world,
)


def _check(f):
    assert int(_scalar(f, WORLD_SUM_SQL)) == 0
    expected = int(_scalar(f, "SELECT COALESCE(SUM(paid_purse + paid_treasury - raid_paid - freight_paid - duty_paid), "
                              "0) FROM econ_caravans WHERE status = 'in_transit'"))
    assert _balance(f, "caravan_escrow", 0) == expected
    db = f()
    try:
        assert crud.escrow_expected(db) == expected == crud.escrow_balance(db)
    finally:
        db.close()


def _pass(f, now):
    stats = caravan_pass.run_pass(f, now=now, force=True, rng=lambda: 0.5)
    _check(f)
    return stats


def _post(f, index):
    _exec(f, "UPDATE econ_caravans SET customs_index = :i, customs_location_id = :l, customs_state = 'pending'",
          i=index, l=ROAD_1_2[index])


def _duty_ops(f):
    return _rows(f, "SELECT id FROM econ_operations WHERE op_type = 'caravan_duty'")


def _foreign(f, **params):
    _physical_world(f, seller_country=2, **params)
    _dispatch(f)
    row = _row(f)
    assert (row.value, row.duty, row.to_country_id) == (400, 40, 1)
    return row


def test_stops_at_a_road_post_pays_duty_once_then_delivers(world):
    _foreign(world)
    _post(world, 2)
    country, seller = _balance(world, "country_treasury", 1), _balance(world, "population_purse", 1)
    _pass(world, START)                                                        # → 102
    stats = _pass(world, START + timedelta(minutes=30))                        # → 202 = the post
    assert stats[caravan_pass.INSPECTING] == 1
    row = _row(world)
    assert (row.route_index, row.customs_state, row.duty_paid, row.arrived_at) == (2, "inspecting", 40, None)
    assert row.customs_until == START + timedelta(minutes=60) == row.next_move_at
    assert row.hold_started_at is None and row.duty_op_id is not None
    assert _balance(world, "country_treasury", 1) == country + 40
    assert _pass(world, START + timedelta(minutes=50))["moved"] == 0           # still inspected
    stats = _pass(world, START + timedelta(minutes=61))                        # cleared → 201 → delivered
    assert (stats["arrived"], stats["delivered"]) == (1, 1)
    row = _row(world)
    assert (row.status, row.customs_state, row.duty_paid) == ("delivered", "cleared", 40)
    assert _balance(world, "country_treasury", 1) == country + 40              # no second duty on delivery
    assert _balance(world, "population_purse", 1) == seller + 400
    assert len(_duty_ops(world)) == 1


def test_post_at_the_final_node_inspects_before_arriving(world):
    _foreign(world)
    _post(world, 3)
    for i in range(3):
        _pass(world, START + timedelta(minutes=30 * i))
    row = _row(world)
    assert (row.route_index, row.current_location_id, row.customs_state, row.arrived_at) == \
        (3, L_GATE2, "inspecting", None)
    assert row.status == "in_transit"
    stats = _pass(world, row.customs_until + timedelta(minutes=1))
    assert (stats["arrived"], stats["delivered"]) == (1, 1)
    assert _row(world).status == "delivered"


def test_post_at_the_seller_gate_inspects_on_the_first_due_step(world):
    _foreign(world)
    _post(world, 0)
    assert _pass(world, START)[caravan_pass.INSPECTING] == 1
    row = _row(world)
    assert (row.route_index, row.current_location_id, row.customs_state) == (0, L_GATE1, "inspecting")
    _pass(world, row.customs_until + timedelta(minutes=1))
    assert (_row(world).route_index, _row(world).customs_state) == (1, "cleared")


def test_zero_minutes_charges_duty_without_a_stop(world):
    _foreign(world, customs_inspection_minutes=0)
    _post(world, 1)
    stats = _pass(world, START)
    assert stats["moved"] == 1 and stats[caravan_pass.INSPECTING] == 0
    row = _row(world)
    assert (row.route_index, row.customs_state, row.duty_paid) == (1, "cleared", 40)


def test_raid_after_duty_takes_only_from_the_seller_part(world, raider):
    _foreign(world)
    _post(world, 1)
    _pass(world, START)
    row = _row(world)
    assert (row.customs_state, row.duty_paid) == ("inspecting", 40)
    assert ec.raid_marks_cap(440, 0, 0, duty_paid=40) == 400
    _fake_raid(world, row.id, marks=88, stolen_units=60)
    _check(world)
    seller, country = _balance(world, "population_purse", 1), _balance(world, "country_treasury", 1)
    _arrive(world)
    assert _pass(world, START + timedelta(minutes=5))["delivered"] == 1
    assert _balance(world, "population_purse", 1) == seller + 440 - 40 - 88
    assert _balance(world, "country_treasury", 1) == country                   # the duty was paid at the post


def test_raid_before_the_post_prorates_the_duty(world, raider):
    _foreign(world)
    _post(world, 2)
    row = _row(world)
    _fake_raid(world, row.id, marks=88, stolen_units=60)
    _pass(world, START)
    _pass(world, START + timedelta(minutes=30))
    _seller, expected = ec.remaining_payout(400, 40, 440, 88)
    assert _row(world).duty_paid == expected == 32


def test_cancel_after_duty_keeps_the_duty_in_the_treasury(world):
    _foreign(world, treasury=1000)
    _post(world, 1)
    _pass(world, START)
    row = _row(world)
    country = _balance(world, "country_treasury", 1)
    buyer = _balance(world, "population_purse", 2) + _balance(world, "region_treasury", 2)
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    _arrive(world)
    assert _pass(world, START + timedelta(minutes=5))["cancelled"] == 1
    assert _balance(world, "population_purse", 2) + _balance(world, "region_treasury", 2) == \
        buyer + row.paid_purse + row.paid_treasury - 40
    assert _balance(world, "country_treasury", 1) == country


def test_charge_duty_is_idempotent(world):
    _foreign(world)
    _post(world, 1)
    db = world()
    try:
        row = crud._lock_caravan(db, _row(world).id)
        first = customs_crud.charge_duty(db, row, START)
        assert customs_crud.charge_duty(db, row, START) == first
        db.commit()
    finally:
        db.close()
    assert len(_duty_ops(world)) == 1
    _check(world)


def test_customs_alert_holds_without_opening_the_post_window(world):
    _foreign(world)
    _exec(world, "UPDATE econ_caravans SET customs_alert_officer_id = 7, customs_alert_until = :t",
          t=START + timedelta(minutes=10))
    assert _pass(world, START)["held"] == 1
    row = _row(world)
    assert (row.route_index, row.hold_started_at) == (0, None)
    db = world()
    try:
        assert crud.held_by(db, row, START, econ_tick.load_params(db)) == "customs"
        detail = crud.caravan_detail(db, row.id, now=START)
    finally:
        db.close()
    assert detail["held_by"] == "customs" and detail["is_contraband"] is False
    assert _pass(world, START + timedelta(minutes=11))["moved"] == 1           # alert expired → moves on


def test_admin_detail_carries_the_customs_fields(world):
    _foreign(world)
    _post(world, 2)
    _pass(world, START)
    _pass(world, START + timedelta(minutes=30))
    db = world()
    try:
        detail = crud.caravan_detail(db, _row(world).id, now=START + timedelta(minutes=31))
        listed = crud.list_caravans(db, kind=crud.KIND_CONTRABAND)
    finally:
        db.close()
    assert (detail["customs_state"], detail["customs_index"], detail["customs_location_id"], detail["duty_paid"]) == \
        ("inspecting", 2, L_ROAD2, 40)
    assert detail["customs_location_name"] == "Перевал" and detail["customs_until"] is not None
    assert detail["seized_region_id"] is None and detail["seized_country_name"] is None
    assert listed["total"] == 0
