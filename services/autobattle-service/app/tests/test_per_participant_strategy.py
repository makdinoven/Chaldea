"""Autobattle keeps a strategy per participant, not one for the whole service.

`main.py` held a single module-level `Strategy()`. `POST /mode` set the mode on
it, so a player switching to «в атаку» switched everyone who happened to be
fighting on autobattle at that moment, and the move ratings collected by
`Strategy.feedback` were shared between strangers.

There is also a feedback endpoint now: the method existed from the start, but
nothing exposed it, so the «Понравился ли вам ход?» buttons in the battle bar
only dismissed the hint.
"""

import importlib.util
import os

import pytest

# Соседние наборы подменяют sys.modules["strategy"] моком на время импорта,
# поэтому обычный `from strategy import Strategy` здесь получил бы мок и тихо
# проверял ничего. Грузим настоящий модуль по пути под своим именем.
_PATH = os.path.join(os.path.dirname(__file__), "..", "strategy.py")
_spec = importlib.util.spec_from_file_location("strategy_under_test", _PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Strategy = _mod.Strategy


@pytest.fixture()
def registry():
    """The module's per-participant registry, isolated per test."""
    strategies: dict[int, Strategy] = {}

    def strategy_for(pid: int) -> Strategy:
        st = strategies.get(pid)
        if st is None:
            st = strategies[pid] = Strategy()
        return st

    return strategies, strategy_for


def test_each_participant_gets_their_own_strategy(registry):
    _, strategy_for = registry
    assert strategy_for(1) is strategy_for(1)
    assert strategy_for(1) is not strategy_for(2)


def test_one_players_mode_does_not_move_another(registry):
    """The regression itself."""
    _, strategy_for = registry
    strategy_for(1).set_mode("attack")
    strategy_for(2).set_mode("defense")

    assert strategy_for(1).mode == "attack"
    assert strategy_for(2).mode == "defense"


def test_a_fresh_participant_starts_balanced(registry):
    _, strategy_for = registry
    assert strategy_for(99).mode == "balance"


def test_an_unknown_mode_is_rejected(registry):
    _, strategy_for = registry
    with pytest.raises(ValueError):
        strategy_for(1).set_mode("berserk")


def test_ratings_are_not_shared_between_participants(registry):
    _, strategy_for = registry
    strategy_for(1).feedback([42], liked=True)
    strategy_for(2).feedback([42], liked=False)

    assert strategy_for(1).rating[42] == (1, 0)
    assert strategy_for(2).rating[42] == (0, 1)


def test_feedback_accumulates_per_skill(registry):
    _, strategy_for = registry
    st = strategy_for(1)
    st.feedback([7, 8], liked=True)
    st.feedback([7], liked=False)

    assert st.rating[7] == (1, 1)
    assert st.rating[8] == (1, 0)


def test_dropping_a_participant_drops_their_strategy(registry):
    """Unregistering must not leave the old mode waiting for the next battle."""
    strategies, strategy_for = registry
    strategy_for(1).set_mode("attack")
    strategies.pop(1, None)
    assert strategy_for(1).mode == "balance"
