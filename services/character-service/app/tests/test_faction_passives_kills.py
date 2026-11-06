"""FEAT-207 QA (task #9): rank passives and kill points — features/FEAT-207 §3.3, §3.5, §3.6, §3.9.

Passives: validation (keys / values / count / name), tolerant stored values, the cumulative sum per membership, the
internal endpoint (multi-faction, left member, hidden faction, NPC), admin rank create / update / clear, the private view
(``passives``, ``passive_total``) and the catalog. Kill points (``POST /internal/factions/battle-result``): mob / NPC /
hostile enemies, winners only, the 24 h per-opponent rule (and its setting), the daily cap (global, per-faction
override, 0), the hostile penalty, rank-up through kill points, journal / notice texts (victims never named),
payload validation. Admin enemies (validation, names, permissions) and the FEAT-207 settings.

Duplicate battle / pvp_training / secret victim / fallen winner happy paths are in ``test_faction_stage3_sanity.py``.
"""

from datetime import datetime, timedelta

import pytest

import faction_core as fc
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, INTERNAL, MERCHANT, MOB_BEAR_T, MOB_WOLF_T, R_OST, USER_ALPHA, WOLF, add_rank, as_admin,
    as_moderator, as_user, enemy, exec_, fapi, fw, hostile, join, log_types, make_faction, member, notice_texts,
    outlaw, q, rep_world, rows, settings, tw,
)

I = "/characters/internal"
A = "/characters/admin/factions"


def passive(fapi, cid):
    r = fapi.get(f"{I}/factions/{cid}/passive-modifiers", headers=INTERNAL)
    assert r.status_code == 200, r.text
    return r.json()["modifiers"]


def battle(fapi, battle_id, winners, losers, battle_type="pve", fallen=()):
    """winners: team 0 ids; losers: team 1 as ids or (id, mob_template_id)."""
    parts = [{"character_id": c, "team": 0, "alive": c not in fallen} for c in winners]
    for x in losers:
        cid, template = (x if isinstance(x, tuple) else (x, None))
        parts.append({"character_id": cid, "team": 1, "alive": False, "mob_template_id": template})
    r = fapi.post(f"{I}/factions/battle-result", headers=INTERNAL,
                  json={"battle_id": battle_id, "battle_type": battle_type, "winner_team": 0, "participants": parts})
    assert r.status_code == 200, r.text
    return r.json()


def gains(out):
    return {(a["character_id"], a["faction_id"]): a["points_delta"] for a in out["applied"]}


def ladder(f, name="Орден", **kw):
    """Ranks 1 «Послушник» (+2 str), 2 «Рыцарь» (none, min 100), 3 «Магистр» (+1 str, +5 dodge, min 1000)."""
    fid = make_faction(f, name, **kw)
    r1 = add_rank(f, fid, "Послушник", 1, passive_name="Закалка", passive_modifiers={"strength": 2})
    r2 = add_rank(f, fid, "Рыцарь", 2, min_points=100)
    r3 = add_rank(f, fid, "Магистр", 3, min_points=1000, passive_name="Мастерство",
                  passive_description="Опыт веков", passive_modifiers={"strength": 1, "dodge": 5})
    return fid, (r1, r2, r3)


def set_rank(f, cid, fid, rank_id):
    exec_(f, "UPDATE faction_members SET rank_id = :r WHERE character_id = :c AND faction_id = :fid",
          r=rank_id, c=cid, fid=fid)


# ============================================================================================ passives: pure


@pytest.mark.parametrize("modifiers, message", [
    ({"health": 5}, "Пассивка: неизвестный модификатор «health»"),
    ({"stealth": 5}, "Пассивка: неизвестный модификатор «stealth»"),
    ({"strength": 0}, "Пассивка: значение модификатора «strength» — целое число от -100 до 100, не 0"),
    ({"strength": 101}, "Пассивка: значение модификатора «strength» — целое число от -100 до 100, не 0"),
    ({"strength": -101}, "Пассивка: значение модификатора «strength» — целое число от -100 до 100, не 0"),
    ({"strength": True}, "Пассивка: значение модификатора «strength» — целое число от -100 до 100, не 0"),
    ({"strength": 1.5}, "Пассивка: значение модификатора «strength» — целое число от -100 до 100, не 0"),
    ({"strength": "5"}, "Пассивка: значение модификатора «strength» — целое число от -100 до 100, не 0"),
    ({k: 1 for k in fc.FACTION_PASSIVE_KEYS[:11]}, "Пассивка: не больше 10 модификаторов"),
    (["strength"], "Пассивка: не больше 10 модификаторов"),
])
def test_validate_passive_rejects(modifiers, message):
    with pytest.raises(fc.PassiveError) as exc:
        fc.validate_passive("Имя", None, modifiers)
    assert str(exc.value) == message


def test_validate_passive_name_description_and_normalisation():
    assert fc.validate_passive(None, None, None) == (None, None, None)
    assert fc.validate_passive("x", "y", {}) == (None, None, None)              # empty = no passive
    for name in (None, "  ", "x" * 101):
        with pytest.raises(fc.PassiveError, match="укажите название"):
            fc.validate_passive(name, None, {"luck": 1})
    with pytest.raises(fc.PassiveError, match="описание до 500"):
        fc.validate_passive("Имя", "x" * 501, {"luck": 1})
    name, desc, mods = fc.validate_passive("  Имя ", "  ", {"vul_fire": -100, "luck": 100})
    assert (name, desc, mods) == ("Имя", None, {"luck": 100, "vul_fire": -100})


def test_clean_modifiers_is_tolerant_and_sum_drops_zero():
    assert fc.clean_modifiers({"strength": 2, "health": 9, "dodge": "3", "luck": 0, "agility": True}) == {
        "strength": 2}
    assert fc.clean_modifiers("garbage") == {} and fc.clean_modifiers(None) == {}
    assert fc.sum_modifiers([{"strength": 2}, {"strength": -2, "dodge": 1}, None]) == {"dodge": 1}
    assert fc.active_passives([fc.PassiveRank(1, 1, "A", None, None, {"luck": 1})], None) == []
    assert fc.active_passives([fc.PassiveRank(1, 1, "A", None, None, {"luck": 1})], 999) == []


# ============================================================================================ passives: endpoint / views


def test_passive_sum_is_cumulative_multi_faction_and_hidden_still_counts(fapi, fw):
    a, (r1, r2, r3) = ladder(fw)
    b = make_faction(fw, "Гильдия")
    add_rank(fw, b, "Подмастерье", 1, passive_name="Ловкость", passive_modifiers={"dodge": 3, "luck": 1})
    join(fw, ALPHA, a)
    join(fw, ALPHA, b)
    assert passive(fapi, ALPHA) == {"strength": 2, "dodge": 3, "luck": 1}
    set_rank(fw, ALPHA, a, r2)
    assert passive(fapi, ALPHA) == {"strength": 2, "dodge": 3, "luck": 1}           # rank 2 has no passive
    set_rank(fw, ALPHA, a, r3)
    assert passive(fapi, ALPHA) == {"strength": 3, "dodge": 8, "luck": 1}           # 1 + 3 (cumulative)
    exec_(fw, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=b)
    assert passive(fapi, ALPHA)["luck"] == 1                                          # hidden: members keep it
    exec_(fw, "UPDATE faction_members SET status = 'left' WHERE character_id = :c", c=ALPHA)
    assert passive(fapi, ALPHA) == {}
    assert passive(fapi, MERCHANT) == {} and passive(fapi, 99999) == {}


def test_admin_rank_passive_create_update_keep_and_clear(fapi, fw):
    fid = make_faction(fw, "Орден")
    as_admin()
    base = {"name": "Послушник"}
    r = fapi.post(f"{A}/{fid}/ranks", json={**base, "passive_name": "Закалка",
                                            "passive_modifiers": {"health": 5}})
    assert (r.status_code, r.json()["detail"]) == (422, "Пассивка: неизвестный модификатор «health»")
    r = fapi.post(f"{A}/{fid}/ranks", json={**base, "passive_modifiers": {"strength": 2}})
    assert r.json()["detail"] == "Пассивка: укажите название (до 100 символов)"
    r = fapi.post(f"{A}/{fid}/ranks", json={**base, "passive_name": "Закалка", "passive_description": "Сила",
                                            "passive_modifiers": {"strength": 2, "res_fire": 10}})
    assert r.status_code == 200, r.text
    rid = int(q(fw, "SELECT id FROM faction_ranks WHERE faction_id = :fid", fid=fid))
    assert fapi.put(f"{A}/ranks/{rid}", json={"name": "Новичок"}).status_code == 200      # omitted -> kept
    stored = q(fw, "SELECT passive_modifiers FROM faction_ranks WHERE id = :r", r=rid)
    assert "res_fire" in str(stored) and q(fw, "SELECT passive_name FROM faction_ranks WHERE id = :r", r=rid) == \
        "Закалка"
    assert fapi.put(f"{A}/ranks/{rid}", json={"name": "Новичок", "passive_modifiers": {}}).status_code == 200
    assert q(fw, "SELECT passive_modifiers FROM faction_ranks WHERE id = :r", r=rid) in (None, "null")   # JSON null
    assert passive(fapi, ALPHA) == {}
    as_moderator()                                                               # factions:edit
    assert fapi.put(f"{A}/ranks/{rid}", json={"name": "Новичок"}).status_code == 200
    as_user(USER_ALPHA)
    assert fapi.post(f"{A}/{fid}/ranks", json=base).status_code == 403


def test_private_view_and_catalog_show_passives_and_outlaw_regions(fapi, fw):
    fid, (r1, _r2, r3) = ladder(fw)
    outlaw(fw, fid, R_OST, "criminal")
    join(fw, ALPHA, fid)
    as_user(USER_ALPHA)
    view = fapi.get(f"/characters/{ALPHA}/factions").json()
    (m,) = view["memberships"]
    assert [p["name"] for p in m["passives"]] == ["Закалка"] and view["passive_total"] == {"strength": 2}
    assert m["outlaw_regions"] == [{"region_id": R_OST, "region_name": "Ост", "level_name": "Преступник"}]
    set_rank(fw, ALPHA, fid, r3)
    view = fapi.get(f"/characters/{ALPHA}/factions").json()
    assert view["passive_total"] == {"strength": 3, "dodge": 5}
    assert view["memberships"][0]["passives"][1] == {"rank_id": r3, "rank_name": "Магистр", "name": "Мастерство",
                                                     "description": "Опыт веков",
                                                     "modifiers": {"strength": 1, "dodge": 5}}
    catalog = fapi.get("/characters/factions/catalog").json()
    items = catalog if isinstance(catalog, list) else catalog.get("items", catalog.get("factions"))
    (item,) = [i for i in items if i["id"] == fid]
    assert [rk["passive"] and rk["passive"]["name"] for rk in item["ranks"]] == ["Закалка", None, "Мастерство"]
    assert item["outlaw_regions"][0]["region_name"] == "Ост"


# ============================================================================================ kill points


def test_mob_enemy_counts_only_its_template_and_only_winners_get_points(fapi, tw):
    fid, _r = ladder(tw)
    join(tw, ALPHA, fid)
    join(tw, BETA, fid)
    enemy(tw, fid, "mob", MOB_WOLF_T, 7)
    out = battle(fapi, 1, [ALPHA], [(WOLF, MOB_BEAR_T)])
    assert out["applied"] == []                                          # another template
    out = battle(fapi, 2, [ALPHA], [(WOLF, MOB_WOLF_T), BETA])           # BETA lost: a member, no points
    assert gains(out) == {(ALPHA, fid): 7} and member(tw, BETA, fid)["points"] == 0
    out = battle(fapi, 3, [ALPHA], [(WOLF, None)])                        # no template id -> not identifiable
    assert out["applied"] == []
    enemy(tw, fid, "npc", WOLF, 99)                                      # a mob NPC is never an «npc» enemy
    assert battle(fapi, 4, [ALPHA], [(WOLF, None)])["applied"] == []


def test_several_enemies_in_one_battle_sum_up_and_npc_winners_are_ignored(fapi, tw):
    fid, _r = ladder(tw)
    join(tw, ALPHA, fid)
    enemy(tw, fid, "mob", MOB_WOLF_T, 5)
    enemy(tw, fid, "npc", MERCHANT, 11)
    out = battle(fapi, 10, [ALPHA, GAMMA, 52], [(WOLF, MOB_WOLF_T), MERCHANT])
    assert gains(out) == {(ALPHA, fid): 16}                              # Gamma: no membership; guard 52: NPC
    assert log_types(tw, ALPHA, fid).count(fc.EV_KILL) == 1


def test_hostile_pvp_kill_repeat_rule_and_setting(fapi, tw):
    a, _ra = ladder(tw)
    b, _rb = ladder(tw, "Тень")
    hostile(tw, a, b)
    join(tw, ALPHA, a)
    join(tw, BETA, b)
    enemy(tw, a, "hostile", 0, 10)
    assert gains(battle(fapi, 20, [ALPHA], [BETA], "pvp_death")) == {(ALPHA, a): 10}
    assert battle(fapi, 21, [ALPHA], [BETA], "pvp_death")["applied"] == []          # within 24 h
    exec_(tw, "UPDATE faction_pvp_kills SET last_at = :t", t=datetime.utcnow() - timedelta(hours=25))
    assert gains(battle(fapi, 22, [ALPHA], [BETA], "pvp_attack")) == {(ALPHA, a): 10}
    settings(tw, pvp_kill_repeat_hours=0)                                            # 0 = no repeat rule
    assert gains(battle(fapi, 23, [ALPHA], [BETA], "pvp_death")) == {(ALPHA, a): 10}
    assert q(tw, "SELECT COUNT(*) FROM faction_pvp_kills") == 1
    # BETA defeats ALPHA: Тень has no «hostile» enemy row -> nothing
    assert battle(fapi, 24, [BETA], [ALPHA], "pvp_death")["applied"] == []


def test_non_hostile_victims_and_pve_battles_never_count_as_pvp(fapi, tw):
    a, _ra = ladder(tw)
    c, _rc = ladder(tw, "Нейтралы")
    join(tw, ALPHA, a)
    join(tw, BETA, c)                                                   # not hostile to «Орден»
    enemy(tw, a, "hostile", 0, 10)
    assert battle(fapi, 30, [ALPHA], [BETA], "pvp_death")["applied"] == []
    assert battle(fapi, 31, [ALPHA], [GAMMA], "pvp_death")["applied"] == []          # no faction at all
    hostile(tw, a, c)
    assert battle(fapi, 32, [ALPHA], [BETA], "pve")["applied"] == []                 # not a PvP battle type


def test_daily_cap_global_override_and_zero(fapi, tw):
    fid, _r = ladder(tw)
    join(tw, ALPHA, fid)
    enemy(tw, fid, "npc", MERCHANT, 30)
    exec_(tw, "UPDATE factions SET kill_points_daily_cap = 40 WHERE id = :fid", fid=fid)
    assert gains(battle(fapi, 40, [ALPHA], [MERCHANT])) == {(ALPHA, fid): 30}
    assert gains(battle(fapi, 41, [ALPHA], [MERCHANT])) == {(ALPHA, fid): 10}        # override 40
    out = battle(fapi, 42, [ALPHA], [MERCHANT])
    assert gains(out) == {(ALPHA, fid): 0} and member(tw, ALPHA, fid)["points"] == 40
    assert log_types(tw, ALPHA, fid).count(fc.EV_KILL) == 3                          # the capped one is journaled
    assert q(tw, "SELECT kill_points FROM faction_donation_days WHERE character_id = :c", c=ALPHA) == 40
    assert q(tw, "SELECT points FROM faction_donation_days WHERE character_id = :c", c=ALPHA) == 0   # own counter
    assert len(notice_texts(tw)) == 2                                                # no notice for 0
    exec_(tw, "UPDATE factions SET kill_points_daily_cap = NULL")
    settings(tw, kill_points_daily_cap=0)
    exec_(tw, "DELETE FROM faction_donation_days")
    assert gains(battle(fapi, 43, [ALPHA], [MERCHANT])) == {(ALPHA, fid): 0}


def test_hostile_penalty_rank_up_and_texts(fapi, tw):
    a = make_faction(tw, "Орден")
    add_rank(tw, a, "Послушник", 1)
    knight = add_rank(tw, a, "Рыцарь", 2, min_points=20)
    b, _rb = ladder(tw, "Тень", secret=True)
    join(tw, ALPHA, a)
    join(tw, ALPHA, b)
    exec_(tw, "UPDATE faction_members SET points = 100 WHERE faction_id = :fid", fid=b)
    hostile(tw, a, b)
    enemy(tw, a, "npc", MERCHANT, 30)
    battle(fapi, 50, [ALPHA], [MERCHANT])
    assert member(tw, ALPHA, a)["points"] == 30 and member(tw, ALPHA, a)["rank_id"] == knight      # rank-up
    assert member(tw, ALPHA, b)["points"] == 85                                         # -50 % of 30
    assert fc.EV_HOSTILE in log_types(tw, ALPHA, b)
    texts = notice_texts(tw)
    assert "Победа над врагами фракции «Орден»: +30 очков" in texts
    assert all("Лавочник" not in t for t in texts)
    history = rows(tw, "SELECT reason FROM faction_log WHERE event_type = 'kill'")
    assert history == [("battle:50",)]


@pytest.mark.parametrize("body", [
    {"battle_id": 0, "battle_type": "pve", "winner_team": 0, "participants": []},
    {"battle_id": 1, "battle_type": "pve", "winner_team": 0,
     "participants": [{"character_id": 1, "team": 0}] * 51},
    {"battle_id": 1, "battle_type": "x" * 31, "winner_team": 0, "participants": []},
    {"battle_id": 1, "battle_type": "pve", "participants": []},
    {"battle_id": 1, "battle_type": "pve", "winner_team": 0, "participants": [{"character_id": 0, "team": 0}]},
])
def test_battle_result_validation(fapi, fw, body):
    assert fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).status_code == 422


def test_battle_without_winner_members_or_losers_is_a_noop(fapi, tw):
    fid, _r = ladder(tw)
    enemy(tw, fid, "npc", MERCHANT, 30)
    assert battle(fapi, 60, [ALPHA], [MERCHANT]) == {"applied": [], "duplicate": False}   # not a member
    join(tw, ALPHA, fid)
    assert battle(fapi, 61, [ALPHA], []) == {"applied": [], "duplicate": False}
    assert battle(fapi, 62, [99999], [MERCHANT])["applied"] == []                          # unknown winner


# ============================================================================================ admin enemies / settings


@pytest.mark.parametrize("enemies, cap, detail", [
    ([{"kind": "dragon", "points": 5}], None, "Неизвестный тип врага: dragon"),
    ([{"kind": "mob", "ref_id": MOB_WOLF_T, "points": 0}], None, "Очки за победу: от 1 до 10000"),
    ([{"kind": "mob", "ref_id": MOB_WOLF_T, "points": 10001}], None, "Очки за победу: от 1 до 10000"),
    ([{"kind": "mob", "ref_id": MOB_WOLF_T, "points": 5}] * 2, None, "Враг указан дважды"),
    ([{"kind": "hostile", "points": 5}, {"kind": "hostile", "ref_id": 3, "points": 5}], None,
     "Строка «участники враждебных фракций» может быть только одна"),
    ([{"kind": "mob", "ref_id": 12345, "points": 5}], None, "Шаблон моба не найден"),
    ([{"kind": "npc", "ref_id": ALPHA, "points": 5}], None, "NPC не найден (нужен NPC, не моб)"),
    ([{"kind": "npc", "ref_id": WOLF, "points": 5}], None, "NPC не найден (нужен NPC, не моб)"),
    ([], -1, "Лимит очков за победы в день: от 0 до 100000 (или пусто — общий)"),
    ([], 100001, "Лимит очков за победы в день: от 0 до 100000 (или пусто — общий)"),
])
def test_admin_enemies_validation(fapi, tw, enemies, cap, detail):
    fid = make_faction(tw, "Орден")
    as_admin()
    r = fapi.put(f"{A}/{fid}/enemies", json={"enemies": enemies, "kill_points_daily_cap": cap})
    assert (r.status_code, r.json()["detail"]) == (422, detail)
    assert q(tw, "SELECT COUNT(*) FROM faction_enemies") == 0


def test_admin_enemies_replace_names_and_permissions(fapi, tw):
    fid = make_faction(tw, "Орден")
    as_admin()
    body = {"enemies": [{"kind": "mob", "ref_id": MOB_WOLF_T, "points": 5},
                        {"kind": "npc", "ref_id": MERCHANT, "points": 8},
                        {"kind": "hostile", "ref_id": 777, "points": 3}], "kill_points_daily_cap": 20}
    out = fapi.put(f"{A}/{fid}/enemies", json=body).json()
    assert out == {"enemies": [{"kind": "mob", "ref_id": MOB_WOLF_T, "points": 5, "name": "Волк"},
                               {"kind": "npc", "ref_id": MERCHANT, "points": 8, "name": "Лавочник"},
                               {"kind": "hostile", "ref_id": None, "points": 3, "name": None}],
                   "kill_points_daily_cap": 20}
    out = fapi.put(f"{A}/{fid}/enemies", json={"enemies": [], "kill_points_daily_cap": None}).json()
    assert out == {"enemies": [], "kill_points_daily_cap": None}
    assert fapi.get(f"{A}/99999/enemies").status_code == 404
    as_user(2, "moderator", ["factions:read"])
    assert fapi.get(f"{A}/{fid}/enemies").status_code == 200
    assert fapi.put(f"{A}/{fid}/enemies", json=body).status_code == 403
    as_user(USER_ALPHA)
    assert fapi.get(f"{A}/{fid}/enemies").status_code == 403


SETTINGS_BASE = {"warning_days": 3, "rejoin_cooldown_days": 7, "leave_burn_pct": 50, "hostile_penalty_pct": 50,
                 "reapply_cooldown_hours": 24}


@pytest.mark.parametrize("field, bad, good", [
    ("kill_points_daily_cap", 100001, 0), ("pvp_kill_repeat_hours", 721, 0),
    ("outlaw_check_cooldown_hours", 0, 720), ("econ_item_sale_share_pct", 21, 20),
])
def test_settings_bounds(fapi, fw, field, bad, good):
    as_admin()
    assert fapi.put(f"{A}/settings", json={**SETTINGS_BASE, field: bad}).status_code == 422
    out = fapi.put(f"{A}/settings", json={**SETTINGS_BASE, field: good}).json()
    assert out[field] == good and fapi.get(f"{A}/settings").json()[field] == good
    as_moderator()                                                       # no factions:settings
    assert fapi.put(f"{A}/settings", json={**SETTINGS_BASE, field: good}).status_code == 403


def test_settings_defaults():
    s = fc.territory_settings_from_row(None)
    assert (s.kill_points_daily_cap, s.pvp_kill_repeat_hours, s.outlaw_check_cooldown_hours) == (50, 24, 24)
    assert fc.kill_cap(None, s) == 50 and fc.kill_cap(0, s) == 0 and fc.kill_cap(7, s) == 7
    assert fc.kill_gain([30, 30], 50, 60) == (0, 60)                     # already over the cap (lowered setting)
