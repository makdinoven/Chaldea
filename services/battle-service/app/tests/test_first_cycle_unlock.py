"""The first cycle must end even if the initiator dies during it.

FEAT-143 limits everyone to one skill type per turn until the turn comes back
to the fighter who started the battle. That unlock was keyed to the initiator
personally: `first_cycle` was cleared at the start of their SECOND turn. Dead
participants are skipped when the turn advances, so an initiator who fell in
the first round never got a second turn — and the battle spent the rest of its
life stuck on one skill per turn, with no way for a player to tell it was a
malfunction rather than a rule.

The unlock is now keyed to the turn order wrapping round, which is the same
moment in a battle where nobody dies and still happens when the initiator is
gone.
"""

import pytest


def advance_turn(turn_order, participants, actor_pid, first_cycle):
    """The turn-advance arithmetic from main.py, isolated.

    Mirrors: pick the next living participant walking forward through the fixed
    order, and clear `first_cycle` once that walk wraps past the end.
    Returns (next_actor, first_cycle).
    """
    current_index = turn_order.index(actor_pid)
    next_actor = actor_pid
    total = len(turn_order)
    for step in range(1, total + 1):
        cand = turn_order[(current_index + step) % total]
        if participants[cand]["hp"] > 0:
            next_actor = cand
            break
    if first_cycle:
        if turn_order.index(next_actor) <= current_index:
            first_cycle = False
    return next_actor, first_cycle


def _alive(*pids):
    return {pid: {"hp": 100} for pid in pids}


def test_cycle_ends_when_the_order_wraps():
    order = [1, 2, 3]
    parts = _alive(1, 2, 3)
    first_cycle = True

    nxt, first_cycle = advance_turn(order, parts, 1, first_cycle)
    assert (nxt, first_cycle) == (2, True)
    nxt, first_cycle = advance_turn(order, parts, 2, first_cycle)
    assert (nxt, first_cycle) == (3, True)
    nxt, first_cycle = advance_turn(order, parts, 3, first_cycle)
    assert nxt == 1
    assert first_cycle is False, "everyone has acted once — the cycle is over"


def test_cycle_ends_even_though_the_initiator_died():
    """The regression. 1 starts the battle and is killed on 2's turn."""
    order = [1, 2, 3]
    parts = _alive(1, 2, 3)
    first_cycle = True

    _, first_cycle = advance_turn(order, parts, 1, first_cycle)
    parts[1]["hp"] = 0                       # инициатор пал
    _, first_cycle = advance_turn(order, parts, 2, first_cycle)
    assert first_cycle is True, "not yet — 3 has not acted"

    nxt, first_cycle = advance_turn(order, parts, 3, first_cycle)
    assert nxt == 2, "1 is dead and is skipped"
    assert first_cycle is False, "the wrap still ends the cycle"


def test_cycle_ends_for_a_duel():
    order = [1, 2]
    parts = _alive(1, 2)
    first_cycle = True

    nxt, first_cycle = advance_turn(order, parts, 1, first_cycle)
    assert (nxt, first_cycle) == (2, True)
    nxt, first_cycle = advance_turn(order, parts, 2, first_cycle)
    assert (nxt, first_cycle) == (1, False)


def test_a_late_joiner_at_the_end_of_the_order_does_not_reopen_the_cycle():
    """Joiners are appended to turn_order; the flag is already down by then."""
    order = [1, 2, 3, 4]
    parts = _alive(1, 2, 3, 4)
    first_cycle = False
    for actor in (1, 2, 3, 4):
        _, first_cycle = advance_turn(order, parts, actor, first_cycle)
    assert first_cycle is False


@pytest.mark.parametrize("dead", [[1], [1, 2], [2]])
def test_the_cycle_always_ends_within_one_pass(dead):
    """Whoever dies, the flag must not survive a full pass of the order."""
    order = [1, 2, 3]
    parts = _alive(1, 2, 3)
    first_cycle = True
    for pid in order:
        if pid in dead:
            parts[pid]["hp"] = 0
            continue
        _, first_cycle = advance_turn(order, parts, pid, first_cycle)
    assert first_cycle is False
