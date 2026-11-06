"""FEAT-205 QA (task 10): the pure faction rules of ``faction_core`` (no DB).

* every entry condition type: region tier, fame / infamy TIER ranges (min / max / both, «no row» = lowest tier),
  level, class, subclass, race (+ subraces), quest, not_in_faction; unknown type never passes;
* player texts: tier NAMES only (never numbers), a secret faction is never named (``reveal_secret`` for staff only),
  ``public_params`` hides a secret faction id;
* implicit irreconcilable conditions (deduplicated, never the faction itself);
* the rank walk: entry rank unconditional, several ranks at once, stop at the first unmet, quest / level / points,
  current rank deleted -> walk from the entry rank, ``next_rank``;
* points: clamp at 0, hostility penalty = share of a GAIN only, burn, countdown helpers, pair normalisation.
"""

from datetime import datetime, timedelta

import pytest

import faction_core as fc

REP = {"wanderer": (4, "Скиталец"), "familiar": (5, "Знакомое лицо"), "trusted": (6, "Свой человек")}
FAME = {"nameless": (1, "Безвестный"), "familiar": (2, "Знакомое имя"), "known": (3, "Известный"),
        "famous": (4, "Знаменитый"), "legend": (5, "Легенда")}
INFAMY = {"none": (1, "О вас не говорят"), "whispers": (2, "Шёпот в тавернах"), "rumored": (3, "О вас ходят слухи"),
          "notorious": (4, "Дурная слава"), "dreaded": (5, "Имя, которое произносят шёпотом")}


def refs(**over):
    base = dict(rep_tiers=REP, fame_tiers=FAME, infamy_tiers=INFAMY, regions={10: "Ост"},
                classes={1: "Воин", 3: "Маг"}, races={1: "Человек", 2: "Эльф"}, subraces={4: "Лесной"},
                quests={700: "Испытание"}, factions={5: ("Орден Зари", False), 6: ("Тени", True)})
    base.update(over)
    return fc.Refs(**base)


def facts(**over):
    return fc.Facts(**over)


# ============================================================================================ conditions

class TestConditionMet:

    def test_region_tier(self):
        p = {"region_id": 10, "min_tier": "familiar"}
        assert not fc.condition_met(fc.COND_REGION, p, facts(region_ranks={10: 4}), refs())
        assert fc.condition_met(fc.COND_REGION, p, facts(region_ranks={10: 5}), refs())
        assert fc.condition_met(fc.COND_REGION, p, facts(region_ranks={10: 6}), refs())
        assert not fc.condition_met(fc.COND_REGION, p, facts(region_ranks={11: 8}), refs())   # other region
        assert not fc.condition_met(fc.COND_REGION, p, facts(), refs())                       # not loaded

    @pytest.mark.parametrize("params,rank,met", [
        ({"min_tier": "known"}, 2, False), ({"min_tier": "known"}, 3, True), ({"min_tier": "known"}, 5, True),
        ({"max_tier": "familiar"}, 2, True), ({"max_tier": "familiar"}, 3, False),
        ({"min_tier": "familiar", "max_tier": "known"}, 1, False),
        ({"min_tier": "familiar", "max_tier": "known"}, 2, True),
        ({"min_tier": "familiar", "max_tier": "known"}, 3, True),
        ({"min_tier": "familiar", "max_tier": "known"}, 4, False),
    ])
    def test_fame_tier_range(self, params, rank, met):
        assert fc.condition_met(fc.COND_FAME, params, facts(fame_rank=rank), refs()) is met

    def test_fame_without_a_row_is_the_lowest_tier(self):
        assert fc.condition_met(fc.COND_FAME, {"max_tier": "nameless"}, facts(fame_rank=None), refs())
        assert not fc.condition_met(fc.COND_FAME, {"min_tier": "familiar"}, facts(fame_rank=None), refs())

    @pytest.mark.parametrize("params,rank,met", [
        ({"max_tier": "whispers"}, 1, True), ({"max_tier": "whispers"}, 2, True),
        ({"max_tier": "whispers"}, 3, False), ({"min_tier": "notorious"}, 3, False),
        ({"min_tier": "notorious"}, 4, True),
    ])
    def test_infamy_tier_range(self, params, rank, met):
        assert fc.condition_met(fc.COND_INFAMY, params, facts(infamy_rank=rank), refs()) is met

    def test_infamy_and_fame_scales_are_independent(self):
        assert fc.condition_met(fc.COND_INFAMY, {"max_tier": "none"}, facts(fame_rank=5, infamy_rank=1), refs())

    def test_level(self):
        assert not fc.condition_met(fc.COND_LEVEL, {"min_level": 5}, facts(level=4), refs())
        assert fc.condition_met(fc.COND_LEVEL, {"min_level": 5}, facts(level=5), refs())

    def test_class(self):
        p = {"class_ids": [1, 3]}
        assert fc.condition_met(fc.COND_CLASS, p, facts(class_id=3), refs())
        assert not fc.condition_met(fc.COND_CLASS, p, facts(class_id=2), refs())
        assert not fc.condition_met(fc.COND_CLASS, p, facts(class_id=None), refs())

    def test_subclass(self):
        p = {"subclass_keys": ["paladin", "berserker"]}
        assert fc.condition_met(fc.COND_SUBCLASS, p, facts(subclass_key="paladin"), refs())
        assert not fc.condition_met(fc.COND_SUBCLASS, p, facts(subclass_key="assassin"), refs())
        assert not fc.condition_met(fc.COND_SUBCLASS, p, facts(subclass_key=None), refs())

    def test_race_and_subrace(self):
        assert fc.condition_met(fc.COND_RACE, {"race_ids": [2]}, facts(race_id=2, subrace_id=5), refs())
        assert not fc.condition_met(fc.COND_RACE, {"race_ids": [2]}, facts(race_id=1), refs())
        p = {"race_ids": [2], "subrace_ids": [4]}
        assert fc.condition_met(fc.COND_RACE, p, facts(race_id=2, subrace_id=4), refs())
        assert not fc.condition_met(fc.COND_RACE, p, facts(race_id=2, subrace_id=5), refs())

    def test_quest(self):
        assert fc.condition_met(fc.COND_QUEST, {"quest_id": 700}, facts(completed_quests={700}), refs())
        assert not fc.condition_met(fc.COND_QUEST, {"quest_id": 700}, facts(completed_quests={701}), refs())

    def test_not_in_faction(self):
        assert fc.condition_met(fc.COND_NOT_IN, {"faction_id": 5}, facts(active_factions={6}), refs())
        assert not fc.condition_met(fc.COND_NOT_IN, {"faction_id": 5}, facts(active_factions={5}), refs())

    def test_unknown_type_never_passes(self):
        assert not fc.condition_met("bogus", {}, facts(level=100), refs())


class TestConditionText:

    def test_texts_use_tier_names_never_numbers(self):
        r = refs()
        assert fc.condition_text(fc.COND_FAME, {"min_tier": "known"}, r) == "Слава: не ниже «Известный»"
        assert fc.condition_text(fc.COND_FAME, {"max_tier": "familiar"}, r) == "Слава: не выше «Знакомое имя»"
        assert (fc.condition_text(fc.COND_INFAMY, {"min_tier": "whispers", "max_tier": "rumored"}, r)
                == "Слухи: от «Шёпот в тавернах» до «О вас ходят слухи»")
        assert (fc.condition_text(fc.COND_REGION, {"region_id": 10, "min_tier": "trusted"}, r)
                == "Репутация в крае «Ост»: не ниже «Свой человек»")
        for t, p in ((fc.COND_FAME, {"min_tier": "legend"}), (fc.COND_INFAMY, {"max_tier": "dreaded"})):
            assert not any(ch.isdigit() for ch in fc.condition_text(t, p, r))

    def test_other_texts(self):
        r = refs()
        assert fc.condition_text(fc.COND_LEVEL, {"min_level": 7}, r) == "Уровень от 7"
        assert fc.condition_text(fc.COND_CLASS, {"class_ids": [1, 3]}, r) == "Класс: Воин или Маг"
        assert fc.condition_text(fc.COND_SUBCLASS, {"subclass_keys": ["paladin"]}, r) == "Подкласс: paladin"
        named = refs(subclasses={"paladin": "Паладин"})
        assert (fc.condition_text(fc.COND_SUBCLASS, {"subclass_keys": ["paladin", "berserker"]}, named)
                == "Подкласс: Паладин или berserker")              # review #1: name, key fallback
        assert (fc.condition_text(fc.COND_RACE, {"race_ids": [2], "subrace_ids": [4]}, r)
                == "Раса: Эльф (подраса: Лесной)")
        assert fc.condition_text(fc.COND_QUEST, {"quest_id": 700}, r) == "Выполнено задание «Испытание»"
        assert fc.condition_text(fc.COND_QUEST, {"quest_id": 999}, r) == "Выполнено задание «#999»"
        assert fc.condition_text("bogus", {}, r) == "Неизвестное условие"

    def test_secret_faction_is_never_named_to_a_player(self):
        r = refs()
        assert fc.condition_text(fc.COND_NOT_IN, {"faction_id": 5}, r) == "Не состоит во фракции «Орден Зари»"
        masked = fc.condition_text(fc.COND_NOT_IN, {"faction_id": 6}, r)
        assert masked == fc.SECRET_FACTION_TEXT and "Тени" not in masked
        assert fc.condition_text(fc.COND_NOT_IN, {"faction_id": 6}, r, reveal_secret=True) == \
            "Не состоит во фракции «Тени»"

    def test_public_params_hide_a_secret_faction_id(self):
        r = refs()
        assert fc.public_params(fc.COND_NOT_IN, {"faction_id": 6}, r) is None
        assert fc.public_params(fc.COND_NOT_IN, {"faction_id": 5}, r) == {"faction_id": 5}
        assert fc.public_params(fc.COND_LEVEL, {"min_level": 3}, r) == {"min_level": 3}

    def test_evaluate_and_unmet(self):
        conds = [(fc.COND_LEVEL, {"min_level": 3}), (fc.COND_NOT_IN, {"faction_id": 6})]
        out = fc.evaluate(conds, facts(level=2, active_factions={6}), refs())
        assert [c["met"] for c in out] == [False, False]
        assert fc.unmet_texts(out) == ["Уровень от 3", fc.SECRET_FACTION_TEXT]
        assert out[1]["params"] is None
        assert [c["met"] for c in fc.evaluate(conds, None, refs())] == [None, None]
        assert fc.unmet_texts(fc.evaluate(conds, None, refs())) == []


class TestEntryConditions:

    def test_irreconcilable_adds_implicit_not_in(self):
        own = [(fc.COND_LEVEL, {"min_level": 2})]
        out = fc.entry_conditions(1, own, [3, 2])
        assert out == own + [(fc.COND_NOT_IN, {"faction_id": 2}), (fc.COND_NOT_IN, {"faction_id": 3})]

    def test_deduplicated_and_never_self(self):
        own = [(fc.COND_NOT_IN, {"faction_id": 2})]
        assert fc.entry_conditions(1, own, [2, 1]) == own


# ============================================================================================ ranks

LADDER = [fc.RankDef(10, 1, "Послушник"), fc.RankDef(11, 2, "Брат", min_points=10),
          fc.RankDef(12, 3, "Рыцарь", min_points=20), fc.RankDef(13, 4, "Капитан", min_points=20, min_level=5),
          fc.RankDef(14, 5, "Магистр", required_quest_id=701)]


def ids(ranks):
    return [r.id for r in ranks]


class TestClimb:

    def test_entry_rank_is_unconditional(self):
        assert ids(fc.climb(LADDER, None, 0, 1, set())) == [10]
        strict_entry = [fc.RankDef(1, 1, "Вход", min_points=999, min_level=99, required_quest_id=5)]
        assert ids(fc.climb(strict_entry, None, 0, 1, set())) == [1]          # its own conditions are ignored

    def test_several_ranks_at_once(self):
        assert ids(fc.climb(LADDER, None, 25, 1, set())) == [10, 11, 12]
        assert ids(fc.climb(LADDER, 10, 25, 1, set())) == [11, 12]

    def test_stops_at_the_first_unmet(self):
        # level 5 would pass the captain, the quest rank is unmet -> stops at the captain
        assert ids(fc.climb(LADDER, 12, 25, 5, set())) == [13]
        # quest met but the captain (level) is not: the walk never skips a rank
        assert ids(fc.climb(LADDER, 12, 25, 4, {701})) == []

    def test_quest_condition(self):
        assert ids(fc.climb(LADDER, 13, 25, 5, {701})) == [14]
        assert ids(fc.climb(LADDER, 14, 99, 99, {701})) == []

    def test_deleted_current_rank_walks_from_the_entry(self):
        assert ids(fc.climb(LADDER, 999, 10, 1, set())) == [10, 11]

    def test_empty_ladder(self):
        assert fc.climb([], None, 100, 10, set()) == []
        assert fc.next_rank([], None) is None

    def test_order_is_by_sort_order_not_by_list_order(self):
        shuffled = list(reversed(LADDER))
        assert ids(fc.climb(shuffled, None, 10, 1, set())) == [10, 11]

    def test_next_rank(self):
        assert fc.next_rank(LADDER, None).id == 10
        assert fc.next_rank(LADDER, 11).id == 12
        assert fc.next_rank(LADDER, 14) is None
        assert fc.next_rank(LADDER, 999).id == 10

    def test_rank_requirements(self):
        req = fc.rank_requirements(LADDER[3], 15, 5, set(), {})
        assert [(r["type"], r["met"]) for r in req] == [("points", False), ("level", True)]
        assert req[0]["text"] == "Очки фракции: 15 / 20"
        req = fc.rank_requirements(LADDER[4], 0, 1, {701}, {701: "Поручение магистра"})
        assert req == [{"type": "quest", "text": "Выполнено задание «Поручение магистра»", "met": True}]


# ============================================================================================ points / time

class TestPoints:

    def test_apply_points_clamps_at_zero(self):
        assert fc.apply_points(5, -20) == 0
        assert fc.apply_points(5, 10) == 15

    @pytest.mark.parametrize("gain,pct,penalty", [(10, 50, 5), (11, 50, 5), (1, 50, 0), (100, 0, 0),
                                                  (0, 50, 0), (-40, 50, 0), (7, 100, 7)])
    def test_hostile_penalty_is_a_share_of_a_gain(self, gain, pct, penalty):
        assert fc.hostile_penalty(gain, pct) == penalty

    @pytest.mark.parametrize("points,pct,kept", [(31, 50, 15), (30, 50, 15), (100, 0, 100), (100, 100, 0),
                                                 (0, 50, 0)])
    def test_burn(self, points, pct, kept):
        assert fc.burn(points, pct) == kept

    def test_countdowns(self):
        t = datetime(2026, 11, 6, 12, 0, 0)
        s = fc.FactionSettings(warning_days=3, rejoin_cooldown_days=7)
        assert fc.rejoin_after(t, s) == t + timedelta(days=7)
        assert fc.warning_deadline(t, s) == t + timedelta(days=3)
        assert fc.remaining_seconds(t + timedelta(hours=1), t) == 3600
        assert fc.remaining_seconds(t - timedelta(hours=1), t) == 0
        assert fc.remaining_seconds(None, t) is None

    def test_pair_is_normalised(self):
        assert fc.pair(7, 3) == (3, 7) and fc.pair(3, 7) == (3, 7)

    def test_settings_from_row_defaults(self):
        assert fc.settings_from_row(None) == fc.FactionSettings(3, 7, 50, 50, 24)
