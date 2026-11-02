"""
FEAT-195 — soft/hard stat caps in dungeon-service.

Stat checks (`perform_stat_check`) and minigame challengers (`_challenger`)
compare floor(eff(total)) for the 10 primary attributes; cumulative counters
(`cumulative_stats`, e.g. kills / dungeons cleared) stay raw. The reported
best value / rolled number is the effective one (what was compared).
Also pins the stat_caps.py copy to the canonical file.
"""

import hashlib
import os

import pytest

import challenges
import gameplay
import stat_caps
from stat_caps import effective_stat

PRIMARIES = ("strength", "agility", "intelligence", "endurance", "health",
             "mana", "energy", "stamina", "charisma", "luck")


@pytest.fixture()
def party(monkeypatch):
    """{character_id: attrs} served by a fake http_clients."""
    attrs_by_id = {}
    names = {}

    async def _attrs(cid):
        value = attrs_by_id[cid]
        if isinstance(value, Exception):
            raise value
        return value

    async def _profile(cid):
        return {"character_name": names.get(cid, f"Герой {cid}"), "character_class_id": 1}

    monkeypatch.setattr(gameplay.http_clients, "get_character_attributes", _attrs)
    monkeypatch.setattr(gameplay.http_clients, "get_character_profile", _profile)
    return attrs_by_id


def _state(*ids, dead=()):
    members = {str(cid): {"status": "alive"} for cid in ids}
    for cid in dead:
        members[str(cid)] = {"status": "dead"}
    return {"members": members}


# ===========================================================================
# _check_stat_value
# ===========================================================================

class TestCheckStatValue:

    @pytest.mark.parametrize("raw, expected", [
        (0, 0), (99, 99), (100, 100), (101, 100), (150, 125), (199, 149), (200, 150),
        (203, 150), (204, 151), (250, 162), (530, 232), (-10, -10), (150.9, 125),
    ])
    def test_primary_is_floor_eff(self, raw, expected):
        assert gameplay._check_stat_value({"strength": raw}, "strength") == expected

    @pytest.mark.parametrize("stat", PRIMARIES)
    def test_every_primary_is_capped(self, stat):
        assert gameplay._check_stat_value({stat: 250}, stat) == 162

    def test_cumulative_counter_stays_raw(self):
        attrs = {"strength": 50, "cumulative_stats": {"total_kills": 530}}
        assert gameplay._check_stat_value(attrs, "total_kills") == 530

    def test_cumulative_wins_over_attribute_of_same_name(self):
        attrs = {"strength": 250, "cumulative_stats": {"strength": 400}}
        assert gameplay._check_stat_value(attrs, "strength") == 400

    def test_unknown_stat_raw_and_missing_zero(self):
        assert gameplay._check_stat_value({"level": 250}, "level") == 250
        assert gameplay._check_stat_value({}, "strength") == 0
        assert gameplay._check_stat_value({"cumulative_stats": None}, "agility") == 0

    @pytest.mark.parametrize("garbage", [None, "250", True, [250]])
    def test_non_numeric_passes_through_uncapped(self, garbage):
        assert gameplay._check_stat_value({"strength": garbage}, "strength") == garbage

    def test_primary_set(self):
        assert gameplay.PRIMARY_ATTRIBUTES == frozenset(PRIMARIES)


# ===========================================================================
# perform_stat_check
# ===========================================================================

class TestPerformStatCheck:

    @pytest.mark.asyncio
    async def test_spec_example_250_vs_170_fails(self, party):
        party[1] = {"strength": 250}
        passed, name, value = await gameplay.perform_stat_check(_state(1), "strength", 170, 1.0)
        assert passed is False
        assert value == 162
        assert name == "Герой 1"

    @pytest.mark.asyncio
    async def test_threshold_exact(self, party):
        party[1] = {"agility": 250}
        assert (await gameplay.perform_stat_check(_state(1), "agility", 162, 1.0))[0] is True
        assert (await gameplay.perform_stat_check(_state(1), "agility", 163, 1.0))[0] is False

    @pytest.mark.asyncio
    async def test_below_soft_cap_unchanged(self, party):
        party[1] = {"intelligence": 80}
        assert await gameplay.perform_stat_check(_state(1), "intelligence", 80, 1.0) == \
            (True, "Герой 1", 80)

    @pytest.mark.asyncio
    async def test_difficulty_modifier_applies_to_difficulty_only(self, party):
        party[1] = {"strength": 300}  # eff 175
        passed, _, value = await gameplay.perform_stat_check(_state(1), "strength", 140, 1.25)
        assert value == 175 and passed is True   # ceil(140 * 1.25) = 175
        passed, _, _ = await gameplay.perform_stat_check(_state(1), "strength", 141, 1.25)
        assert passed is False                   # ceil(176.25) = 177

    @pytest.mark.asyncio
    async def test_best_member_is_chosen_by_effective_value(self, party):
        party[1] = {"luck": 530}   # eff 232
        party[2] = {"luck": 220}   # eff 155
        party[3] = {"luck": 999}   # dead
        passed, name, value = await gameplay.perform_stat_check(_state(1, 2, dead=(3,)), "luck", 200, 1.0)
        assert (passed, name, value) == (True, "Герой 1", 232)

    @pytest.mark.asyncio
    async def test_cumulative_counter_raw(self, party):
        party[1] = {"strength": 10, "cumulative_stats": {"total_kills": 250}}
        passed, _, value = await gameplay.perform_stat_check(_state(1), "total_kills", 250, 1.0)
        assert passed is True and value == 250

    @pytest.mark.asyncio
    async def test_member_with_failing_attributes_skipped(self, party):
        party[1] = RuntimeError("attributes down")
        party[2] = {"strength": 150}
        passed, name, value = await gameplay.perform_stat_check(_state(1, 2), "strength", 125, 1.0)
        assert (passed, name, value) == (True, "Герой 2", 125)

    @pytest.mark.asyncio
    async def test_no_alive_members(self, party):
        assert await gameplay.perform_stat_check(_state(dead=(1,)), "strength", 1, 1.0) == (False, "", 0)


# ===========================================================================
# _challenger (minigames)
# ===========================================================================

class TestChallenger:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", sorted(challenges.KIND_STAT))
    async def test_every_kind_uses_effective_primary(self, party, kind):
        stat = challenges.KIND_STAT[kind]
        party[7] = {stat: 250}
        value, _ = await gameplay._challenger(7, kind)
        if stat in gameplay.PRIMARY_ATTRIBUTES:
            assert value == 162
        else:
            assert value == 250

    @pytest.mark.asyncio
    async def test_below_cap_and_floor(self, party):
        party[7] = {"agility": 99, "strength": 201}
        assert (await gameplay._challenger(7, challenges.KIND_LOCKPICK))[0] == 99
        assert (await gameplay._challenger(7, challenges.KIND_RUBBLE))[0] == 150  # floor(150.25)

    @pytest.mark.asyncio
    async def test_cumulative_counter_raw(self, party):
        stat = challenges.KIND_STAT[challenges.KIND_LOCKPICK]
        party[7] = {stat: 10, "cumulative_stats": {stat: 300}}
        assert (await gameplay._challenger(7, challenges.KIND_LOCKPICK))[0] == 300

    @pytest.mark.asyncio
    async def test_attributes_down_502(self, party):
        from fastapi import HTTPException

        party[7] = RuntimeError("down")
        with pytest.raises(HTTPException) as exc:
            await gameplay._challenger(7, challenges.KIND_LOCKPICK)
        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_garbage_value_is_zero(self, party):
        party[7] = {"agility": "много"}
        assert (await gameplay._challenger(7, challenges.KIND_LOCKPICK))[0] == 0


# ===========================================================================
# stat_caps copy
# ===========================================================================

class TestStatCapsCopy:

    def test_identical_to_canonical(self):
        app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        canonical = os.path.normpath(os.path.join(
            app_dir, "..", "..", "character-attributes-service", "app", "stat_caps.py"))
        if not os.path.exists(canonical):
            msg = f"canonical stat_caps.py not found at {canonical} (needs a full checkout)"
            if os.environ.get("CI"):
                pytest.fail(msg)
            pytest.skip(msg)
        digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
        assert digest(os.path.join(app_dir, "stat_caps.py")) == digest(canonical)

    def test_values(self):
        assert effective_stat(250) == 162.5 and effective_stat(530) == 232.5
        assert stat_caps.effective_delta(100, 200) == 50
