"""FEAT-207 QA (task #10): faction membership as a crime in an outlawed region — features/FEAT-207 §3.7, §3.9.

``law_crud._check`` (entry / patrol): an OPEN member is stopped without a detection roll, a SECRET one only on a
successful roll (``law_crud.detection_rng`` seam), a slip records no crime; one crime per region per cooldown
(``outlaw_check_cooldown_hours``), regions independent; wanted lifted to the severity level's ``min_value``; the most
severe level wins, an open membership wins over a secret one; no guard / other region / left member -> nothing; crime
and law-log rows carry no faction data. ``patrol_crud._sweep_candidates`` finds zero-wanted outlawed members. Admin
outlaw regions: validation, names, permissions. The update_location path end to end.

The single happy path (open member, criminal, cooldown read) is in ``test_faction_stage3_sanity.py``.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

import law_core as lc
import law_crud
import models
import patrol_crud
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, GUARD, INTERNAL, R_OST, R_PASHNI, USER_ALPHA, add_rank, as_admin, as_user, exec_, fapi, fw,
    tw, join, make_faction, outlaw, place, q, rep_world, rows, run_flow, settings,
)
from tests.reputation_world import OVERRIDE

A = "/characters/admin/factions"
L_MARKET, L_NIVA = 100, 110


class FixedRng:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


class ExplodingRng:
    def random(self):
        raise AssertionError("no detection roll expected for an open member")


@pytest.fixture
def no_roll(monkeypatch):
    monkeypatch.setattr(law_crud, "detection_rng", lambda: ExplodingRng())


def roll(monkeypatch, value):
    monkeypatch.setattr(law_crud, "detection_rng", lambda: FixedRng(value))


def faction(f, name="Орден", *, secret=False, regions=((R_OST, "criminal"),), members=(ALPHA,)):
    fid = make_faction(f, name, secret=secret)
    add_rank(f, fid, "Послушник", 1)
    for cid in members:
        run_flow(f, __import__("faction_crud").join, cid, fid)
    for region, level in regions:
        outlaw(f, fid, region, level)
    return fid


def later(seconds):
    return datetime.utcnow().replace(microsecond=0) + timedelta(seconds=seconds)


def entry(f, cid, loc=L_MARKET, *, patrol=False, now=None):
    db = f()
    try:
        ch = db.get(models.Character, cid)
        if patrol:
            result = law_crud.check_patrol_arrival(db, ch, loc, guard_id=GUARD, now=now)
        else:
            result = law_crud.check_entry(db, ch, loc, lc.SOURCE_MOVE, now)
        enc = result.encounter                                   # read before the session closes
        out = SimpleNamespace(encounter=enc is not None, level=enc.level_code if enc else None,
                              source=enc.source if enc else None, slipped=result.slipped)
        db.commit()
        return out
    finally:
        db.close()


def crimes(f, cid=ALPHA):
    return rows(f, "SELECT crime_type, region_id FROM law_crimes WHERE character_id = :c ORDER BY id", c=cid)


def wanted(f, cid, region):
    return int(q(f, "SELECT value FROM character_wanted WHERE character_id = :c AND region_id = :r", c=cid, r=region)
               or 0)


def release(f, cid=ALPHA):
    """Close the open encounter so the next check runs again."""
    exec_(f, "UPDATE characters SET law_encounter_id = NULL WHERE id = :c", c=cid)


def level_min(code):
    return next(lv.min_value for lv in lc.DEFAULT_LEVELS if lv.code == code)


# ============================================================================================ open / secret


@pytest.mark.parametrize("level", ["suspect", "villain"])
def test_open_member_floor_is_the_level_threshold(fw, no_roll, level):
    faction(fw, regions=((R_OST, level),))
    result = entry(fw, ALPHA)
    assert result.encounter and result.level == level
    assert wanted(fw, ALPHA, R_OST) == level_min(level)
    assert q(fw, "SELECT wanted_floor FROM law_crimes WHERE character_id = :c", c=ALPHA) == level_min(level)


def test_secret_member_only_on_a_successful_roll(fw, monkeypatch):
    monkeypatch.setattr(law_crud, "detection_chance_for", lambda *a, **k: Decimal(50))   # 2 guards here = 100 %
    faction(fw, "Тень", secret=True)
    roll(monkeypatch, 0.9999)                                            # slip
    result = entry(fw, ALPHA)
    assert result.slipped is True and not result.encounter and crimes(fw) == []
    assert wanted(fw, ALPHA, R_OST) == 0
    roll(monkeypatch, 0.0)                                               # noticed
    result = entry(fw, ALPHA)
    assert result.encounter and crimes(fw) == [("faction_membership", R_OST)]


def test_most_severe_level_wins_and_open_beats_secret(fw, no_roll):
    faction(fw, "Орден", regions=((R_OST, "suspect"),))
    faction(fw, "Легион", regions=((R_OST, "villain"),))
    assert entry(fw, ALPHA).level == "villain"
    release(fw)
    faction(fw, "Тень", secret=True, regions=((R_OST, "enemy"),), members=(BETA,))
    faction(fw, "Свет", regions=((R_OST, "suspect"),), members=(BETA,))
    result = entry(fw, BETA)                                             # open «suspect» wins: no roll at all
    assert result.level == "suspect" and wanted(fw, BETA, R_OST) == level_min("suspect")


# ============================================================================================ cooldown / regions


def test_one_crime_per_region_per_cooldown(fw, monkeypatch):
    faction(fw, regions=((R_OST, "criminal"), (R_PASHNI, "criminal")))
    place(fw, OVERRIDE, L_NIVA)                                          # a live guard in region 11
    roll(monkeypatch, 0.0)
    entry(fw, ALPHA)
    release(fw)
    result = entry(fw, ALPHA)                                            # within the cooldown: wanted only
    assert result.encounter and crimes(fw) == [("faction_membership", R_OST)]
    release(fw)
    entry(fw, ALPHA, L_NIVA)                                             # another region: its own crime
    assert crimes(fw) == [("faction_membership", R_OST), ("faction_membership", R_PASHNI)]
    release(fw)
    exec_(fw, "UPDATE law_crimes SET created_at = :t", t=datetime.utcnow() - timedelta(hours=25))
    entry(fw, ALPHA, now=later(5))                                       # event keys are per second
    assert len(crimes(fw)) == 3
    release(fw)
    settings(fw, outlaw_check_cooldown_hours=48)
    exec_(fw, "UPDATE law_crimes SET created_at = :t", t=datetime.utcnow() - timedelta(hours=25))
    entry(fw, ALPHA, now=later(10))
    assert len(crimes(fw)) == 3                                          # 25 h < 48 h


def test_nothing_without_guard_other_region_or_membership(fw, no_roll):
    faction(fw, regions=((R_PASHNI, "criminal"),))
    assert not entry(fw, ALPHA).encounter and crimes(fw) == []         # outlawed elsewhere only
    fid = faction(fw, "Легион", members=(BETA, GAMMA))
    exec_(fw, "UPDATE faction_members SET status = 'left' WHERE character_id = :c AND faction_id = :fid",
          c=GAMMA, fid=fid)
    place(fw, GAMMA, L_MARKET)
    assert not entry(fw, GAMMA).encounter and crimes(fw, GAMMA) == []  # left member
    exec_(fw, "UPDATE characters SET current_location_id = 300 WHERE npc_role = 'guard'")
    assert not entry(fw, BETA).encounter and crimes(fw, BETA) == []    # no live guard
    assert not entry(fw, BETA, 300).encounter                          # no region at all


def test_crime_and_law_rows_carry_no_faction_data(fw, no_roll):
    faction(fw, "Орден Пепла")
    entry(fw, ALPHA)
    crime = rows(fw, "SELECT * FROM law_crimes WHERE character_id = :c", c=ALPHA)
    logs = rows(fw, "SELECT * FROM law_log WHERE character_id = :c", c=ALPHA)
    enc = rows(fw, "SELECT * FROM law_encounters WHERE character_id = :c", c=ALPHA)
    assert crime and logs and enc
    blob = repr(crime + logs + enc)
    assert "Пепла" not in blob and "Орден" not in blob
    assert q(fw, "SELECT victim_character_id FROM law_crimes WHERE character_id = :c", c=ALPHA) is None
    assert q(fw, "SELECT wanted_points FROM law_crimes WHERE character_id = :c", c=ALPHA) == 0


# ============================================================================================ patrols / move path


def test_patrol_prefilter_finds_zero_wanted_outlawed_members(fw):
    faction(fw, "Орден", regions=((R_OST, "criminal"),), members=(ALPHA,))
    faction(fw, "Легион", regions=((R_PASHNI, "criminal"),), members=(BETA,))
    fid = faction(fw, "Свет", regions=((R_OST, "criminal"),), members=(GAMMA,))
    exec_(fw, "UPDATE faction_members SET status = 'left' WHERE faction_id = :fid", fid=fid)
    place(fw, GAMMA, L_MARKET)
    db = fw()
    try:
        assert patrol_crud._sweep_candidates(db, L_MARKET) == [ALPHA]
    finally:
        db.close()


def test_patrol_arrival_stops_an_open_member(tw, no_roll):
    fw = tw                                                  # + the battle tables (active battle check)
    faction(fw)
    result = entry(fw, ALPHA, patrol=True)
    assert result.encounter and result.source == lc.SOURCE_PATROL
    assert crimes(fw) == [("faction_membership", R_OST)]


def test_update_location_records_the_membership_crime(fapi, fw, no_roll, stub_law_notify_send):
    faction(fw)
    place(fw, ALPHA, L_NIVA)
    r = fapi.put(f"/characters/internal/{ALPHA}/update_location", json={"new_location_id": L_MARKET},
                 headers=INTERNAL)
    assert r.status_code == 200, r.text
    assert crimes(fw) == [("faction_membership", R_OST)]
    assert q(fw, "SELECT law_encounter_id FROM characters WHERE id = :c", c=ALPHA) is not None


# ============================================================================================ admin


@pytest.mark.parametrize("regions, detail", [
    ([{"region_id": 999, "level_code": "criminal"}], "Край не найден"),
    ([{"region_id": 0, "level_code": "criminal"}], "Край не найден"),
    ([{"region_id": R_OST, "level_code": "tyrant"}], "Неизвестная тяжесть: tyrant"),
    ([{"region_id": R_OST, "level_code": "criminal"}, {"region_id": R_OST, "level_code": "enemy"}],
     "Край указан дважды"),
])
def test_admin_outlaw_validation(fapi, fw, regions, detail):
    fid = make_faction(fw, "Орден")
    as_admin()
    r = fapi.put(f"{A}/{fid}/outlaw-regions", json={"regions": regions})
    assert (r.status_code, r.json()["detail"]) == (422, detail)


def test_admin_outlaw_replace_names_and_permissions(fapi, fw):
    fid = make_faction(fw, "Орден")
    as_admin()
    body = {"regions": [{"region_id": R_PASHNI, "level_code": "enemy"}, {"region_id": R_OST, "level_code": "suspect"}]}
    out = fapi.put(f"{A}/{fid}/outlaw-regions", json=body).json()
    assert [(r["region_id"], r["region_name"], r["level_code"]) for r in out["regions"]] == [
        (R_OST, "Ост", "suspect"), (R_PASHNI, "Пашни", "enemy")]
    assert all(r["level_name"] for r in out["regions"])
    assert fapi.put(f"{A}/{fid}/outlaw-regions", json={"regions": []}).json() == {"regions": []}
    assert fapi.put(f"{A}/{fid}/outlaw-regions", json={"regions": [{"region_id": "x", "level_code": "a"}]}
                    ).status_code == 422
    as_user(2, "moderator", ["factions:read"])
    assert fapi.get(f"{A}/{fid}/outlaw-regions").status_code == 200
    assert fapi.put(f"{A}/{fid}/outlaw-regions", json=body).status_code == 403
    as_user(USER_ALPHA)
    assert fapi.get(f"{A}/{fid}/outlaw-regions").status_code == 403
