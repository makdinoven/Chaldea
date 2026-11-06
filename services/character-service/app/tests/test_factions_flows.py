"""FEAT-205 QA (task 10): faction player flows, the internal quest hook, rank rewards, the level-up hook and the
periodic pass (character-service, SQLite world of :mod:`tests.faction_world`).

* entry conditions through ``POST /{cid}/factions/{fid}/join`` — every block type incl. fame / infamy TIERS (the
  hidden numbers never leave the service), not_in_faction, quest; NPC / hidden faction / ownership;
* member limit, invite-only apply -> approve (re-check, stays pending on failure) / reject -> 24 h re-apply cooldown,
  duplicate pending, cancel; irreconcilable pairs;
* secrecy: catalog counts, public faction / public memberships, condition texts / params, private tab + journal
  (owner / staff only);
* points: quest hook ``POST /internal/factions/quest-completed`` (idempotent by ``faction:quest:cq:{id}``, non-member
  skipped, negative points), hostility −50 % (floor 0, not for admin points / losses, setting), rank auto-climb
  (several at once, quest / level conditions), the level-up hook without recursion;
* rewards exactly once (incl. leave / rejoin), the outbox: xp once, title, item ok / retry / ambiguous timeout,
  voucher idempotent retry, stale ``sending`` rows, admin retry;
* leave / expel (7 d cooldown, 50 % burn, rank recomputed on rejoin), the pass: warning -> cleared / expelled after
  3 days, throttle; character deletion cascade.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import crud
import faction_core as fc
import faction_crud
import faction_hooks
import faction_pass
import faction_rewards
import econ_scheduler
import models
from auth_http import get_current_user_via_http
from main import app
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, INTERNAL, ITEM_SHIELD, ITEM_SWORD, L_MARKET, L_NIVA, MERCHANT, Q_DAILY, Q_MASTER, Q_TRIAL,
    R_OST, TITLE_KNIGHT, USER_ALPHA, USER_BETA, USER_GAMMA, add_rank, as_admin, as_moderator, as_user,
    complete_quest, connect_error, deliveries, exec_, fapi, fw, grants, hostile, join, level, log_types,
    make_faction, member, notices, now, passive_xp, q, read_timeout, rep_world, rows, run_flow, set_conditions,
    set_level, set_points, set_renown, set_value, settings,
)

BASE = "/characters"


def post_join(api, cid=ALPHA, fid=1, user=USER_ALPHA):
    as_user(user)
    return api.post(f"{BASE}/{cid}/factions/{fid}/join")


def quest_done(api, cid=ALPHA, cq=1, rewards=(), quest_id=Q_TRIAL):
    return api.post(f"{BASE}/internal/factions/quest-completed", headers=INTERNAL,
                    json={"character_id": cid, "quest_id": quest_id, "cq_id": cq,
                          "rewards": [{"faction_id": fid, "points": p} for fid, p in rewards]})


def points(f, cid, fid):
    return member(f, cid, fid)["points"]


# ============================================================================================ entry conditions

class TestEntryConditions:

    def test_level(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("level", {"min_level": 3})])
        r = post_join(fapi, fid=fid)
        assert r.status_code == 403 and r.json()["detail"] == "Условия вступления не выполнены: Уровень от 3"
        assert member(fw, ALPHA, fid) is None
        set_level(fw, ALPHA, 3)
        assert post_join(fapi, fid=fid).status_code == 200
        assert member(fw, ALPHA, fid)["status"] == "active"

    def test_region_reputation_tier(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("region_reputation", {"region_id": R_OST, "min_tier": "familiar"})])
        r = post_join(fapi, fid=fid)
        assert r.status_code == 403
        assert "Репутация в крае «Ост»: не ниже «Знакомое лицо»" in r.json()["detail"]
        set_value(fw, ALPHA, R_OST, 100)
        assert post_join(fapi, fid=fid).status_code == 200

    @pytest.mark.parametrize("fame,ok", [(0, False), (199, False), (200, True), (5000, True)])
    def test_fame_min_tier(self, fapi, fw, fame, ok):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("fame", {"min_tier": "known"})])
        set_renown(fw, ALPHA, fame=fame)
        r = post_join(fapi, fid=fid)
        assert (r.status_code == 200) is ok, r.text
        if not ok:
            assert r.json()["detail"].endswith("Слава: не ниже «Известный»")

    @pytest.mark.parametrize("infamy,ok", [(0, True), (399, True), (400, False), (2500, False)])
    def test_infamy_max_tier_never_reveals_the_number(self, fapi, fw, infamy, ok):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("infamy", {"max_tier": "whispers"})])
        set_renown(fw, ALPHA, infamy=infamy)
        r = post_join(fapi, fid=fid)
        assert (r.status_code == 200) is ok, r.text
        if not ok:
            assert r.json()["detail"] == "Условия вступления не выполнены: Слухи: не выше «Шёпот в тавернах»"
            assert str(infamy) not in r.text

    def test_class(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("class", {"class_ids": [3]})])
        r = post_join(fapi, fid=fid)
        assert r.status_code == 403 and r.json()["detail"].endswith("Класс: Маг")
        exec_(fw, "UPDATE characters SET id_class = 3 WHERE id = :c", c=ALPHA)
        assert post_join(fapi, fid=fid).status_code == 200

    def test_subclass(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("subclass", {"subclass_keys": ["paladin"]})])
        assert post_join(fapi, fid=fid).status_code == 403
        exec_(fw, "INSERT INTO tree_nodes (id, node_type, subclass_key) VALUES (1, 'subclass_choice', 'paladin')")
        exec_(fw, "INSERT INTO character_tree_progress (character_id, node_id) VALUES (:c, 1)", c=ALPHA)
        assert post_join(fapi, fid=fid).status_code == 200

    def test_subclass_text_uses_names(self, fapi, fw):
        # review #1: the text (also stored in warning_reasons / journal / notifications) shows names, not keys
        fid = make_faction(fw)
        set_conditions(fw, fid, [("subclass", {"subclass_keys": ["paladin", "berserker"]})])
        exec_(fw, "INSERT INTO tree_nodes (id, node_type, subclass_key, name) VALUES "
                  "(5, 'subclass_choice', 'paladin', 'Паладин'), (6, 'subclass_choice', 'paladin', 'Дубль'), "
                  "(7, 'regular', 'berserker', 'Не подкласс')")
        r = post_join(fapi, fid=fid)
        assert r.status_code == 403
        assert r.json()["detail"].endswith("Подкласс: Паладин или berserker")

    def test_subclass_names_lookup(self, fw):
        exec_(fw, "INSERT INTO tree_nodes (id, node_type, subclass_key, name) VALUES "
                  "(5, 'subclass_choice', 'paladin', 'Паладин'), (6, 'subclass_choice', 'paladin', 'Дубль')")
        db = fw()
        try:
            assert faction_crud.subclass_names(db, []) == {}
            assert faction_crud.subclass_names(db, ["paladin", "nope", "x'); DROP TABLE tree_nodes; --"]) \
                == {"paladin": "Паладин"}
            refs = faction_crud.load_refs(db, [("subclass", {"subclass_keys": ["paladin", "nope"]})])
            assert refs.subclasses == {"paladin": "Паладин"}
            assert fc.condition_text("subclass", {"subclass_keys": ["paladin", "nope"]}, refs) \
                == "Подкласс: Паладин или nope"
        finally:
            db.close()
        exec_(fw, "DROP TABLE tree_nodes")
        db = fw()
        try:
            assert faction_crud.subclass_names(db, ["paladin"]) == {}      # DB error -> key fallback
        finally:
            db.close()

    def test_race_and_subrace(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("race", {"race_ids": [2], "subrace_ids": [4]})])
        r = post_join(fapi, fid=fid)
        assert r.status_code == 403 and r.json()["detail"].endswith("Раса: Эльф (подраса: Лесной)")
        exec_(fw, "UPDATE characters SET id_race = 2, id_subrace = 1 WHERE id = :c", c=ALPHA)
        assert post_join(fapi, fid=fid).status_code == 403
        exec_(fw, "UPDATE characters SET id_subrace = 4 WHERE id = :c", c=ALPHA)
        assert post_join(fapi, fid=fid).status_code == 200

    def test_quest(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("quest", {"quest_id": Q_TRIAL})])
        r = post_join(fapi, fid=fid)
        assert r.status_code == 403 and r.json()["detail"].endswith("Выполнено задание «Испытание»")
        complete_quest(fw, ALPHA, Q_TRIAL, status="active")
        assert post_join(fapi, fid=fid).status_code == 403
        complete_quest(fw, ALPHA, Q_TRIAL)
        assert post_join(fapi, fid=fid).status_code == 200

    def test_not_in_faction(self, fapi, fw):
        a = make_faction(fw, "Орден Зари")
        b = make_faction(fw, "Братство Ночи")
        set_conditions(fw, a, [("not_in_faction", {"faction_id": b})])
        assert post_join(fapi, fid=b).status_code == 200
        r = post_join(fapi, fid=a)
        assert r.status_code == 403 and r.json()["detail"].endswith("Не состоит во фракции «Братство Ночи»")
        as_user(USER_ALPHA)
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{b}/leave").status_code == 200
        assert post_join(fapi, fid=a).status_code == 200

    def test_all_conditions_are_and_ed_and_every_unmet_is_listed(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("level", {"min_level": 9}), ("class", {"class_ids": [1]}),
                                 ("quest", {"quest_id": Q_TRIAL})])
        r = post_join(fapi, fid=fid)
        assert r.json()["detail"] == ("Условия вступления не выполнены: Уровень от 9; "
                                      "Выполнено задание «Испытание»")

    def test_npc_cannot_join(self, fw):
        fid = make_faction(fw)
        with pytest.raises(faction_crud.FactionError) as exc:
            join(fw, MERCHANT, fid)
        assert (exc.value.status_code, exc.value.detail) == (403, "NPC не может вступать во фракции")

    def test_hidden_or_missing_faction_is_404(self, fapi, fw):
        hidden = make_faction(fw, active=False)
        r = post_join(fapi, fid=hidden)
        assert r.status_code == 404 and r.json()["detail"] == "Фракция не найдена"
        assert post_join(fapi, fid=999).status_code == 404

    def test_only_the_owner_acts_for_a_character(self, fapi, fw):
        fid = make_faction(fw)
        r = post_join(fapi, cid=ALPHA, fid=fid, user=USER_BETA)
        assert r.status_code == 403 and r.json()["detail"] == "Это не ваш персонаж"
        as_user(USER_BETA)
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave").status_code == 403
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).status_code == 403
        assert fapi.post(f"{BASE}/999/factions/{fid}/join").status_code == 404
        assert member(fw, ALPHA, fid) is None

    def test_already_member(self, fapi, fw):
        fid = make_faction(fw)
        assert post_join(fapi, fid=fid).status_code == 200
        r = post_join(fapi, fid=fid)
        assert r.status_code == 409 and r.json()["detail"] == "Вы уже состоите в этой фракции"


# ============================================================================================ limit / invite-only

class TestLimitAndApplications:

    def test_member_limit(self, fapi, fw):
        fid = make_faction(fw, limit=1)
        assert post_join(fapi, cid=ALPHA, fid=fid).status_code == 200
        r = post_join(fapi, cid=BETA, fid=fid, user=USER_BETA)
        assert r.status_code == 409 and r.json()["detail"] == "Во фракции нет мест"
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave")
        assert post_join(fapi, cid=BETA, fid=fid, user=USER_BETA).status_code == 200

    def test_invite_only_needs_an_application(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        r = post_join(fapi, fid=fid)
        assert r.status_code == 409 and r.json()["detail"] == "Вступление только по заявке"
        as_user(USER_ALPHA)
        r = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={"message": "Прошу принять"})
        assert r.status_code == 200, r.text
        app_id = r.json()["application_id"]
        r = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={})
        assert r.status_code == 409 and r.json()["detail"] == "Заявка уже подана"
        cat = {c["id"]: c for c in fapi.get(f"{BASE}/factions/catalog?character_id={ALPHA}").json()}
        assert cat[fid]["my"]["status"] == "pending" and cat[fid]["my"]["application_id"] == app_id
        assert cat[fid]["can_join"] is False and cat[fid]["join_block_reason"] == "Заявка на рассмотрении"
        as_admin()
        r = fapi.post(f"{BASE}/admin/factions/applications/{app_id}/approve")
        assert r.status_code == 200, r.text
        assert member(fw, ALPHA, fid)["status"] == "active"
        assert log_types(fw, ALPHA, fid) == ["applied", "application_approved", "joined"]
        assert any("одобрена" in n["message"] for n in notices(fw))
        assert fapi.post(f"{BASE}/admin/factions/applications/{app_id}/approve").status_code == 409

    def test_apply_to_an_open_faction_is_refused(self, fapi, fw):
        fid = make_faction(fw)
        as_user(USER_ALPHA)
        r = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={})
        assert r.status_code == 409 and r.json()["detail"] == "Во фракцию можно вступить без заявки"

    def test_hopeless_application_is_refused(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        set_conditions(fw, fid, [("level", {"min_level": 10})])
        as_user(USER_ALPHA)
        r = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={})
        assert r.status_code == 403

    def test_message_too_long_is_422(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        as_user(USER_ALPHA)
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={"message": "x" * 501}).status_code == 422

    def test_approve_rechecks_and_keeps_the_application_pending(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        as_user(USER_ALPHA)
        app_id = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).json()["application_id"]
        set_conditions(fw, fid, [("level", {"min_level": 5})])
        as_admin()
        r = fapi.post(f"{BASE}/admin/factions/applications/{app_id}/approve")
        assert r.status_code == 409 and r.json()["detail"].endswith("Уровень от 5")
        assert q(fw, "SELECT status FROM faction_applications WHERE id = :a", a=app_id) == "pending"
        assert member(fw, ALPHA, fid) is None
        set_level(fw, ALPHA, 5)
        assert fapi.post(f"{BASE}/admin/factions/applications/{app_id}/approve").status_code == 200

    def test_approve_works_for_a_hidden_faction(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        as_user(USER_ALPHA)
        app_id = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).json()["application_id"]
        exec_(fw, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=fid)
        as_admin()
        assert fapi.post(f"{BASE}/admin/factions/applications/{app_id}/approve").status_code == 200

    def test_reject_then_24h_reapply_cooldown(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        as_user(USER_ALPHA)
        app_id = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).json()["application_id"]
        as_admin()
        r = fapi.post(f"{BASE}/admin/factions/applications/{app_id}/reject", json={"reason": "Не сейчас"})
        assert r.status_code == 200, r.text
        assert any(n["message"] == "Ваша заявка во фракцию «Орден Зари» отклонена: Не сейчас" for n in notices(fw))
        as_user(USER_ALPHA)
        r = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={})
        assert r.status_code == 409 and r.json()["detail"].startswith("Повторная заявка возможна через 1 д")
        cat = {c["id"]: c for c in fapi.get(f"{BASE}/factions/catalog?character_id={ALPHA}").json()}
        assert 0 < cat[fid]["my"]["reapply_in_seconds"] <= 24 * 3600
        exec_(fw, "UPDATE faction_applications SET decided_at = :d WHERE id = :a",
              d=now() - timedelta(hours=25), a=app_id)
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).status_code == 200
        as_admin()
        assert fapi.post(f"{BASE}/admin/factions/applications/{app_id}/reject", json={}).status_code == 409

    def test_reapply_cooldown_setting_zero(self, fapi, fw):
        settings(fw, reapply_cooldown_hours=0)
        fid = make_faction(fw, invite=True)
        as_user(USER_ALPHA)
        app_id = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).json()["application_id"]
        as_admin()
        fapi.post(f"{BASE}/admin/factions/applications/{app_id}/reject", json={})
        as_user(USER_ALPHA)
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).status_code == 200

    def test_cancel_application(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        as_user(USER_ALPHA)
        app_id = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).json()["application_id"]
        as_user(USER_BETA)
        assert fapi.delete(f"{BASE}/{BETA}/factions/applications/{app_id}").status_code == 404   # not BETA's
        assert fapi.delete(f"{BASE}/{ALPHA}/factions/applications/{app_id}").status_code == 403
        as_user(USER_ALPHA)
        assert fapi.delete(f"{BASE}/{ALPHA}/factions/applications/{app_id}").json() == {"ok": True}
        assert fapi.delete(f"{BASE}/{ALPHA}/factions/applications/{app_id}").status_code == 409
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/apply", json={}).status_code == 200   # no cooldown


# ============================================================================================ hostility

class TestHostility:

    def test_irreconcilable_pair_blocks_the_second(self, fapi, fw):
        a = make_faction(fw, "Орден Зари")
        b = make_faction(fw, "Братство Ночи")
        hostile(fw, a, b, irreconcilable=True)
        assert post_join(fapi, fid=b).status_code == 200
        r = post_join(fapi, fid=a)
        assert r.status_code == 409
        assert r.json()["detail"] == "Нельзя состоять одновременно в этой фракции и во фракции «Братство Ночи»"
        cat = {c["id"]: c for c in fapi.get(f"{BASE}/factions/catalog?character_id={ALPHA}").json()}
        assert {"type": "not_in_faction", "text": "Не состоит во фракции «Братство Ночи»", "met": False,
                "params": {"faction_id": b}} in cat[a]["conditions"]
        assert cat[a]["can_join"] is False

    def test_plain_hostility_does_not_block(self, fapi, fw):
        a = make_faction(fw, "Орден Зари")
        b = make_faction(fw, "Братство Ночи")
        hostile(fw, a, b)
        assert post_join(fapi, fid=b).status_code == 200
        assert post_join(fapi, fid=a).status_code == 200

    def _two(self, fapi, fw, pct=None):
        a = make_faction(fw, "Орден Зари")
        b = make_faction(fw, "Братство Ночи")
        hostile(fw, a, b)
        if pct is not None:
            settings(fw, hostile_penalty_pct=pct)
        post_join(fapi, fid=a)
        post_join(fapi, fid=b)
        return a, b

    def test_quest_gain_takes_half_from_the_hostile_faction(self, fapi, fw):
        a, b = self._two(fapi, fw)
        set_points(fw, ALPHA, b, 30)
        r = quest_done(fapi, cq=11, rewards=[(a, 21)])
        assert r.status_code == 200, r.text
        assert r.json()["applied"] == [{"faction_id": a, "points_delta": 21, "points_after": 21}]
        assert (points(fw, ALPHA, a), points(fw, ALPHA, b)) == (21, 20)                    # floor(21 * 50 %) = 10
        assert rows(fw, "SELECT points_delta, event_key, reason FROM faction_log WHERE faction_id = :b "
                        "AND event_type = 'hostile_penalty'", b=b) == [(-10, f"faction:quest:cq:11:hostile:{a}",
                                                                        f"faction:{a}")]

    def test_penalty_floor_is_zero(self, fapi, fw):
        a, b = self._two(fapi, fw)
        set_points(fw, ALPHA, b, 3)
        quest_done(fapi, cq=12, rewards=[(a, 40)])
        assert points(fw, ALPHA, b) == 0
        assert q(fw, "SELECT points_delta FROM faction_log WHERE faction_id = :b AND event_type = 'hostile_penalty'",
                 b=b) == -3

    def test_negative_quest_points_no_penalty(self, fapi, fw):
        a, b = self._two(fapi, fw)
        set_points(fw, ALPHA, a, 10)
        set_points(fw, ALPHA, b, 30)
        quest_done(fapi, cq=13, rewards=[(a, -25)])
        assert (points(fw, ALPHA, a), points(fw, ALPHA, b)) == (0, 30)                      # clamped at 0

    def test_admin_points_no_penalty(self, fapi, fw):
        a, b = self._two(fapi, fw)
        set_points(fw, ALPHA, b, 30)
        as_admin()
        mid = member(fw, ALPHA, a)["id"]
        r = fapi.post(f"{BASE}/admin/factions/members/{mid}/points", json={"delta": 40, "reason": "За заслуги"})
        assert r.status_code == 200, r.text
        assert (points(fw, ALPHA, a), points(fw, ALPHA, b)) == (40, 30)

    def test_penalty_only_for_active_memberships_in_the_hostile_faction(self, fapi, fw):
        a, b = self._two(fapi, fw)
        set_points(fw, ALPHA, b, 30)
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{b}/leave")                                    # 30 -> 15
        quest_done(fapi, cq=14, rewards=[(a, 20)])
        assert points(fw, ALPHA, b) == 15

    def test_penalty_setting(self, fapi, fw):
        a, b = self._two(fapi, fw, pct=0)
        set_points(fw, ALPHA, b, 30)
        quest_done(fapi, cq=15, rewards=[(a, 20)])
        assert points(fw, ALPHA, b) == 30


# ============================================================================================ quest hook

class TestQuestHook:

    def test_idempotent_per_cq(self, fapi, fw):
        fid = make_faction(fw)
        post_join(fapi, fid=fid)
        first = quest_done(fapi, cq=21, rewards=[(fid, 15)])
        assert first.json()["duplicate"] is False
        again = quest_done(fapi, cq=21, rewards=[(fid, 15)])
        assert again.status_code == 200 and again.json()["duplicate"] is True and again.json()["applied"] == []
        assert points(fw, ALPHA, fid) == 15
        assert q(fw, "SELECT COUNT(*) FROM faction_log WHERE event_key = 'faction:quest:cq:21'") == 1
        quest_done(fapi, cq=22, rewards=[(fid, 15)])
        assert points(fw, ALPHA, fid) == 30

    def test_non_member_rewards_are_skipped(self, fapi, fw):
        a = make_faction(fw, "Орден Зари")
        b = make_faction(fw, "Братство Ночи")
        post_join(fapi, fid=a)
        r = quest_done(fapi, cq=23, rewards=[(a, 5), (b, 50), (999, 7)])
        assert r.json()["applied"] == [{"faction_id": a, "points_delta": 5, "points_after": 5}]
        assert member(fw, ALPHA, b) is None

    def test_points_accrue_only_while_active(self, fapi, fw):
        fid = make_faction(fw)
        post_join(fapi, fid=fid)
        set_points(fw, ALPHA, fid, 10)
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave")
        quest_done(fapi, cq=24, rewards=[(fid, 100)])
        assert points(fw, ALPHA, fid) == 5

    def test_auth_and_validation(self, fapi, fw):
        body = {"character_id": ALPHA, "quest_id": 1, "cq_id": 1, "rewards": []}
        assert fapi.post(f"{BASE}/internal/factions/quest-completed", json=body).status_code == 401
        assert fapi.post(f"{BASE}/internal/factions/quest-completed", json=body,
                         headers={"X-Internal-Token": "wrong"}).status_code == 401
        assert quest_done(fapi, cid=999).status_code == 404
        for bad in ({**body, "rewards": [{"faction_id": 1, "points": 10001}]},
                    {**body, "rewards": [{"faction_id": i, "points": 1} for i in range(1, 7)]},
                    {**body, "cq_id": 0}):
            assert fapi.post(f"{BASE}/internal/factions/quest-completed", json=bad,
                             headers=INTERNAL).status_code == 422

    def test_no_membership_no_change(self, fapi, fw):
        r = quest_done(fapi, cq=25, rewards=[])
        assert r.status_code == 200 and r.json() == {"applied": [], "duplicate": False, "rank_ups": 0}


# ============================================================================================ ranks

def ladder(f, fid):
    """Послушник (entry) < Брат (10 pts) < Рыцарь (20 pts) < Капитан (level 5) < Магистр (quest 701)."""
    return [add_rank(f, fid, "Послушник", 1), add_rank(f, fid, "Брат", 2, min_points=10),
            add_rank(f, fid, "Рыцарь", 3, min_points=20), add_rank(f, fid, "Капитан", 4, min_level=5),
            add_rank(f, fid, "Магистр", 5, required_quest_id=Q_MASTER)]


class TestRanks:

    def test_join_gets_the_entry_rank(self, fapi, fw):
        fid = make_faction(fw)
        r1, *_ = ladder(fw, fid)
        r = post_join(fapi, fid=fid)
        assert r.json()["rank_name"] == "Послушник"
        assert member(fw, ALPHA, fid)["rank_id"] == r1 and grants(fw, ALPHA) == [r1]
        assert log_types(fw, ALPHA, fid) == ["joined"]
        assert notices(fw)[0]["message"] == "Вы вступили во фракцию «Орден Зари». Звание: «Послушник»"
        assert notices(fw)[0]["target_value"] == USER_ALPHA and notices(fw)[0]["ws_type"] == "faction"

    def test_faction_without_ranks(self, fapi, fw):
        fid = make_faction(fw)
        r = post_join(fapi, fid=fid)
        assert r.status_code == 200 and r.json()["rank_name"] is None
        assert member(fw, ALPHA, fid)["rank_id"] is None

    def test_several_ranks_at_once(self, fapi, fw):
        fid = make_faction(fw)
        r1, r2, r3, _r4, _r5 = ladder(fw, fid)
        post_join(fapi, fid=fid)
        r = quest_done(fapi, cq=31, rewards=[(fid, 25)])
        assert r.json()["rank_ups"] == 2
        assert member(fw, ALPHA, fid)["rank_id"] == r3
        assert grants(fw, ALPHA) == [r1, r2, r3]
        assert log_types(fw, ALPHA, fid) == ["joined", "points", "rank_up", "rank_up"]

    def test_join_with_points_from_before_climbs_on_join(self, fapi, fw):
        fid = make_faction(fw)
        r1, r2, r3, _r4, _r5 = ladder(fw, fid)
        post_join(fapi, fid=fid)
        quest_done(fapi, cq=32, rewards=[(fid, 40)])                                     # Рыцарь
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave")                               # 40 -> 20
        exec_(fw, "UPDATE faction_members SET rejoin_after = :d", d=now() - timedelta(seconds=5))
        r = post_join(fapi, fid=fid)
        assert r.status_code == 200 and r.json()["rank_name"] == "Рыцарь"

    def test_quest_condition_rank_without_points(self, fapi, fw):
        fid = make_faction(fw)
        r1 = add_rank(fw, fid, "Послушник", 1)
        r2 = add_rank(fw, fid, "Посвящённый", 2, required_quest_id=Q_MASTER)
        post_join(fapi, fid=fid)
        assert quest_done(fapi, cq=33).json()["rank_ups"] == 0
        complete_quest(fw, ALPHA, Q_MASTER)
        r = quest_done(fapi, cq=34, quest_id=Q_MASTER)
        assert r.json()["rank_ups"] == 1
        assert member(fw, ALPHA, fid)["rank_id"] == r2 and grants(fw, ALPHA) == [r1, r2]

    def test_level_condition_via_the_quest_hook_level_check(self, fapi, fw):
        """Quest XP from locations-service is not levelled immediately: the hook levels first."""
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1)
        r2 = add_rank(fw, fid, "Ветеран", 2, min_level=3)
        post_join(fapi, fid=fid)
        exec_(fw, "UPDATE character_attributes SET passive_experience = 150 WHERE character_id = :c", c=ALPHA)
        r = quest_done(fapi, cq=35)
        assert r.status_code == 200
        assert level(fw, ALPHA) == 3 and member(fw, ALPHA, fid)["rank_id"] == r2

    def test_no_demotion_while_a_member(self, fapi, fw):
        fid = make_faction(fw)
        _r1, _r2, r3, _r4, _r5 = ladder(fw, fid)
        post_join(fapi, fid=fid)
        quest_done(fapi, cq=36, rewards=[(fid, 25)])
        quest_done(fapi, cq=37, rewards=[(fid, -25)])
        assert points(fw, ALPHA, fid) == 0 and member(fw, ALPHA, fid)["rank_id"] == r3

    def test_admin_points_recheck_ranks(self, fapi, fw):
        fid = make_faction(fw)
        _r1, r2, *_ = ladder(fw, fid)
        post_join(fapi, fid=fid)
        as_admin()
        mid = member(fw, ALPHA, fid)["id"]
        r = fapi.post(f"{BASE}/admin/factions/members/{mid}/points", json={"delta": 12, "reason": "Награда"})
        assert r.json()["rank_id"] == r2
        assert log_types(fw, ALPHA, fid) == ["joined", "admin_points", "rank_up"]
        assert q(fw, "SELECT actor_user_id FROM faction_log WHERE event_type = 'admin_points'") == 1


class TestLevelUpHook:

    def test_level_up_climbs_and_reward_xp_chain_does_not_recurse(self, fw):
        fid = make_faction(fw)
        r1 = add_rank(fw, fid, "Послушник", 1)
        r2 = add_rank(fw, fid, "Ветеран", 2, min_level=3, reward_xp=1000)       # its XP -> level 5
        r3 = add_rank(fw, fid, "Капитан", 3, min_level=5, reward_xp=10)
        join(fw, ALPHA, fid)
        exec_(fw, "UPDATE character_attributes SET passive_experience = 100 WHERE character_id = :c", c=ALPHA)
        db = fw()
        try:
            crud.check_and_update_level(db, ALPHA, 100)
        finally:
            db.close()
        assert level(fw, ALPHA) == 5
        assert member(fw, ALPHA, fid)["rank_id"] == r3
        assert grants(fw, ALPHA) == [r1, r2, r3]
        assert [(k, s) for _i, k, s, *_r in deliveries(fw, ALPHA)] == [("xp", "done"), ("xp", "done")]
        assert passive_xp(fw, ALPHA) == 1110                                             # every XP exactly once
        messages = [n["message"] for n in notices(fw)]
        assert sum("«Ветеран»" in m for m in messages) == 1 and sum("«Капитан»" in m for m in messages) == 1

    def test_hook_is_cheap_without_memberships(self, fw, monkeypatch):
        called = []
        monkeypatch.setattr(faction_crud, "recheck_ranks", lambda *a, **k: called.append(a))
        db = fw()
        try:
            faction_hooks.after_level_up(db, ALPHA)
        finally:
            db.close()
        assert called == []

    def test_hook_failure_never_breaks_the_level_up(self, fw, monkeypatch):
        fid = make_faction(fw)
        join(fw, ALPHA, fid)

        def boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(faction_hooks, "after_level_up", boom)
        db = fw()
        try:
            character = crud.check_and_update_level(db, ALPHA, 300)
        finally:
            db.close()
        assert character is not None and level(fw, ALPHA) == 4

    def test_collecting_records_instead_of_dispatching(self, fw, monkeypatch):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1)
        add_rank(fw, fid, "Ветеран", 2, min_level=3, reward_xp=5)
        join(fw, ALPHA, fid)
        dispatched = []
        monkeypatch.setattr(faction_hooks, "dispatch_result", lambda r: dispatched.append(r))
        db = fw()
        try:
            with faction_hooks.collecting() as bucket:
                crud.check_and_update_level(db, ALPHA, 100)
        finally:
            db.close()
        assert dispatched == [] and bucket.deliver == {ALPHA} and len(bucket.notices) == 1
        assert [s for _i, _k, s, *_r in deliveries(fw, ALPHA)] == ["pending"]


# ============================================================================================ rewards / outbox

def rewarded_rank(f, fid, **rewards):
    return add_rank(f, fid, "Послушник", 1, **rewards)


class TestRewards:

    def test_rewards_granted_once_even_after_leave_and_rejoin(self, fapi, fw):
        fid = make_faction(fw)
        r1 = rewarded_rank(fw, fid, reward_xp=50, reward_title_id=TITLE_KNIGHT,
                           reward_items=[{"item_id": ITEM_SWORD, "quantity": 2}])
        post_join(fapi, fid=fid)
        assert [(k, s) for _i, k, s, *_r in deliveries(fw, ALPHA)] == [("xp", "done"), ("title", "done"),
                                                                     ("item", "done")]
        assert passive_xp(fw, ALPHA) == 50
        assert q(fw, "SELECT COUNT(*) FROM character_titles WHERE character_id = :c AND title_id = :t",
                 c=ALPHA, t=TITLE_KNIGHT) == 1
        assert fw.http.calls == [(faction_rewards.inventory_url(ALPHA), {"item_id": ITEM_SWORD, "quantity": 2})]
        join_notice = [n["message"] for n in notices(fw) if "Награда за звание" in n["message"]]
        assert join_notice == ["Награда за звание «Послушник» во фракции «Орден Зари»: +50 опыта, "
                               "титул «Рыцарь Зари», предметы ×2"]
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave")
        exec_(fw, "UPDATE faction_members SET rejoin_after = :d", d=now() - timedelta(seconds=5))
        fw.fsent.reset_mock()
        assert post_join(fapi, fid=fid).status_code == 200
        assert grants(fw, ALPHA) == [r1] and len(deliveries(fw, ALPHA)) == 3
        assert passive_xp(fw, ALPHA) == 50 and len(fw.http.calls) == 1
        assert not any("Награда" in n["message"] for n in notices(fw))

    def test_xp_delivered_exactly_once(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_xp=30)
        join(fw, ALPHA, fid)
        faction_rewards.deliver_pending(ALPHA, fw)
        faction_rewards.deliver_pending(ALPHA, fw)
        did = deliveries(fw, ALPHA)[0][0]
        assert faction_rewards.deliver_one(fw, did) is None                              # not pending -> no claim
        assert passive_xp(fw, ALPHA) == 30

    def test_missing_title_fails_without_retry(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_title_id=TITLE_KNIGHT)
        join(fw, ALPHA, fid)
        exec_(fw, "DELETE FROM titles")
        faction_rewards.deliver_pending(ALPHA, fw)
        (_id, kind, status, attempts, err, _p), = deliveries(fw, ALPHA)
        assert (kind, status, attempts, err) == ("title", "failed", 1, "title_not_found")
        assert "reward_failed" in log_types(fw, ALPHA, fid)

    def test_item_ambiguous_timeout_is_never_auto_retried(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_items=[{"item_id": ITEM_SWORD, "quantity": 1}])
        join(fw, ALPHA, fid)
        fw.http.push(read_timeout())
        stats = faction_rewards.deliver_pending(ALPHA, fw)
        assert stats == {"done": 0, "pending": 0, "failed": 1}
        (_id, _k, status, attempts, err, _p), = deliveries(fw, ALPHA)
        assert (status, attempts, err) == ("failed", 1, "uncertain: ReadTimeout")
        faction_rewards.deliver_pending(ALPHA, fw, now=now() + timedelta(days=1))
        faction_rewards.retry_due(fw, now() + timedelta(days=1))
        assert len(fw.http.calls) == 1
        assert "reward_failed" in log_types(fw, ALPHA, fid)

    def test_item_connect_error_retries_with_backoff_then_fails(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_items=[{"item_id": ITEM_SWORD, "quantity": 1}])
        t = now()
        join(fw, ALPHA, fid, at=t)                       # one clock read: the row is due exactly at t
        fw.http.push(connect_error())
        faction_rewards.deliver_pending(ALPHA, fw, now=t)
        (_id, _k, status, attempts, err, _p), = deliveries(fw, ALPHA)
        assert (status, attempts, err) == ("pending", 1, "connect: ConnectError")
        faction_rewards.deliver_pending(ALPHA, fw, now=t + timedelta(seconds=30))       # not due (2 min backoff)
        assert len(fw.http.calls) == 1
        fw.http.push(500, 502, 503, 504)
        when = t
        for minutes in (3, 10, 30, 70):
            when = t + timedelta(minutes=minutes)
            faction_rewards.deliver_pending(ALPHA, fw, now=when)
        (_id, _k, status, attempts, err, _p), = deliveries(fw, ALPHA)
        assert (status, attempts, err) == ("failed", faction_rewards.MAX_ITEM_ATTEMPTS, "http 504")
        assert len(fw.http.calls) == 5

    def test_item_4xx_is_retried_then_succeeds(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_items=[{"item_id": ITEM_SWORD, "quantity": 3}])
        join(fw, ALPHA, fid)
        t = now()
        fw.http.push(404)
        faction_rewards.deliver_pending(ALPHA, fw, now=t)
        faction_rewards.retry_due(fw, t + timedelta(minutes=5))
        assert [s for _i, _k, s, *_r in deliveries(fw, ALPHA)] == ["done"]
        assert len(fw.http.calls) == 2

    def test_admin_retry_of_a_failed_item(self, fapi, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_items=[{"item_id": ITEM_SHIELD, "quantity": 1}])
        join(fw, ALPHA, fid)
        fw.http.push(read_timeout())
        faction_rewards.deliver_pending(ALPHA, fw)
        did = deliveries(fw, ALPHA)[0][0]
        as_admin()
        card = fapi.get(f"{BASE}/admin/factions/characters/{ALPHA}").json()
        assert card["deliveries"][0]["last_error"] == "uncertain: ReadTimeout"
        assert any(h["event_type"] == "reward_failed" for h in card["history"])
        r = fapi.post(f"{BASE}/admin/factions/deliveries/{did}/retry")
        assert r.status_code == 200, r.text
        assert r.json()["deliveries"][0]["status"] == "done"
        assert len(fw.http.calls) == 2
        assert fapi.post(f"{BASE}/admin/factions/deliveries/{did}/retry").status_code == 409
        assert fapi.post(f"{BASE}/admin/factions/deliveries/9999/retry").status_code == 404
        as_moderator()
        assert fapi.post(f"{BASE}/admin/factions/deliveries/{did}/retry").status_code == 409   # manage: allowed
        as_user(USER_ALPHA)
        assert fapi.post(f"{BASE}/admin/factions/deliveries/{did}/retry").status_code == 403

    def test_reward_failed_is_hidden_from_the_player_journal(self, fapi, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_items=[{"item_id": ITEM_SWORD, "quantity": 1}])
        join(fw, ALPHA, fid)
        fw.http.push(read_timeout())
        faction_rewards.deliver_pending(ALPHA, fw)
        as_user(USER_ALPHA)
        hist = fapi.get(f"{BASE}/{ALPHA}/factions/history").json()
        assert [i["event_type"] for i in hist["items"]] == ["joined"] and hist["total"] == 1

    def test_vouchers_idempotent_key_and_retry_on_any_error(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_house_location_id=L_MARKET, reward_plot_location_id=L_NIVA)
        join(fw, ALPHA, fid)
        gid = int(q(fw, "SELECT id FROM faction_rank_grants WHERE character_id = :c", c=ALPHA))
        t = now()
        fw.http.push(read_timeout(), 200)
        faction_rewards.deliver_pending(ALPHA, fw, now=t)
        assert [s for _i, _k, s, *_r in deliveries(fw, ALPHA)] == ["pending", "done"]   # timeout = retry
        faction_rewards.retry_due(fw, t + timedelta(minutes=5))
        assert [s for _i, _k, s, *_r in deliveries(fw, ALPHA)] == ["done", "done"]
        urls = set(fw.http.urls())
        assert urls == {faction_rewards.voucher_url()}
        assert faction_rewards.voucher_url().endswith("/locations/houses/internal/vouchers")
        payloads = [p for _u, p in fw.http.calls]
        assert payloads[0] == payloads[2]                                               # the retry = same key
        assert {(p["kind"], p["location_id"], p["source_key"]) for p in payloads} == {
            ("ready", L_MARKET, f"faction:grant:{gid}:voucher:ready"),
            ("empty", L_NIVA, f"faction:grant:{gid}:voucher:empty")}
        assert all(p["character_id"] == ALPHA and "Послушник" in p["source_text"] for p in payloads)

    @pytest.mark.parametrize("kind", ["item", "voucher"])
    def test_no_transaction_is_open_during_the_http_call(self, fw, monkeypatch, kind):
        """§3.6: «no HTTP inside a transaction». The item path re-reads the expired ``delivery.character_id`` after
        its ``db.rollback()`` would lazy-load and hold a read transaction + connection during the inventory call
        (FEAT-205 QA bug #1, fixed: the URL is built before the rollback)."""
        fid = make_faction(fw)
        reward = ({"reward_items": [{"item_id": ITEM_SWORD, "quantity": 1}]} if kind == "item"
                  else {"reward_house_location_id": L_MARKET})
        rewarded_rank(fw, fid, **reward)
        t = now()
        join(fw, ALPHA, fid, at=t)
        state = {"open": 0}
        for name, step in (("begin", 1), ("commit", -1), ("rollback", -1)):
            event.listen(fw.engine, name, lambda conn, step=step: state.__setitem__("open", state["open"] + step))
        seen = []

        def http(url, payload):
            seen.append(state["open"])
            return type("R", (), {"status_code": 200})()

        monkeypatch.setattr(faction_rewards, "http_post", http)
        faction_rewards.deliver_pending(ALPHA, fw, now=t)
        assert seen == [0]

    def test_xp_without_an_attributes_row_is_retried(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_xp=5)
        join(fw, ALPHA, fid)
        exec_(fw, "DELETE FROM character_attributes WHERE character_id = :c", c=ALPHA)
        faction_rewards.deliver_pending(ALPHA, fw)
        (_id, _k, status, attempts, err, _p), = deliveries(fw, ALPHA)
        assert (status, attempts, err) == ("pending", 1, "no_attributes")

    def test_stale_sending_rows(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_xp=5, reward_items=[{"item_id": ITEM_SWORD, "quantity": 1}])
        join(fw, ALPHA, fid)
        old = now() - timedelta(minutes=30)
        exec_(fw, "UPDATE faction_reward_deliveries SET status = 'sending', updated_at = :u", u=old)
        assert faction_rewards.recover_stale(fw, now()) == 2
        got = {k: (s, e) for _i, k, s, _a, e, _p in deliveries(fw, ALPHA)}
        assert got == {"xp": ("pending", None), "item": ("failed", "uncertain: stale")}

    def test_rank_up_notice_lists_the_rewards(self, fapi, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1)
        add_rank(fw, fid, "Рыцарь", 2, min_points=5, reward_xp=500, reward_title_id=TITLE_KNIGHT,
                 reward_items=[{"item_id": ITEM_SWORD, "quantity": 1}, {"item_id": ITEM_SHIELD, "quantity": 2}],
                 reward_house_location_id=L_MARKET)
        post_join(fapi, fid=fid)
        quest_done(fapi, cq=41, rewards=[(fid, 5)])
        msgs = [n["message"] for n in notices(fw) if n["message"].startswith("Новое звание")]
        assert msgs == ["Новое звание «Рыцарь» во фракции «Орден Зари»: +500 опыта, титул «Рыцарь Зари», "
                        "предметы ×3, право на дом в «Рынок»"]


# ============================================================================================ leave / expel

class TestLeaveExpel:

    def test_leave_burns_half_and_sets_a_7_day_cooldown(self, fapi, fw):
        fid = make_faction(fw)
        post_join(fapi, fid=fid)
        set_points(fw, ALPHA, fid, 31)
        as_user(USER_ALPHA)
        r = fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave")
        assert r.status_code == 200
        assert r.json()["points_after"] == 15
        assert 7 * 86400 - 5 <= r.json()["rejoin_in_seconds"] <= 7 * 86400
        m = member(fw, ALPHA, fid)
        assert (m["status"], m["points"]) == ("left", 15)
        r = post_join(fapi, fid=fid)
        assert r.status_code == 409 and r.json()["detail"] == "Повторное вступление возможно через 7 д"
        as_user(USER_ALPHA)
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave").status_code == 409

    def test_rejoin_recomputes_the_rank_from_the_remaining_points(self, fapi, fw):
        fid = make_faction(fw)
        _r1, r2, r3, *_ = ladder(fw, fid)
        post_join(fapi, fid=fid)
        quest_done(fapi, cq=51, rewards=[(fid, 30)])
        assert member(fw, ALPHA, fid)["rank_id"] == r3
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave")                                # 30 -> 15
        exec_(fw, "UPDATE faction_members SET rejoin_after = :d", d=now() - timedelta(seconds=5))
        assert post_join(fapi, fid=fid).json()["rank_name"] == "Брат"
        assert member(fw, ALPHA, fid)["rank_id"] == r2 and member(fw, ALPHA, fid)["points"] == 15

    def test_settings_change_burn_and_cooldown(self, fapi, fw):
        settings(fw, leave_burn_pct=0, rejoin_cooldown_days=0)
        fid = make_faction(fw)
        post_join(fapi, fid=fid)
        set_points(fw, ALPHA, fid, 40)
        as_user(USER_ALPHA)
        assert fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave").json()["points_after"] == 40
        assert post_join(fapi, fid=fid).status_code == 200

    def test_admin_expel(self, fapi, fw):
        fid = make_faction(fw)
        post_join(fapi, fid=fid)
        set_points(fw, ALPHA, fid, 10)
        mid = member(fw, ALPHA, fid)["id"]
        as_admin()
        r = fapi.post(f"{BASE}/admin/factions/members/{mid}/expel", json={"reason": "Предательство"})
        assert r.status_code == 200 and r.json()["points_after"] == 5
        m = member(fw, ALPHA, fid)
        assert m["status"] == "expelled" and m["rejoin_after"] is not None
        assert notices(fw)[-1]["message"] == "Вас исключили из фракции «Орден Зари»: Предательство"
        assert fapi.post(f"{BASE}/admin/factions/members/{mid}/expel",
                         json={"reason": "Ещё раз"}).status_code == 409
        r = post_join(fapi, fid=fid)
        assert r.status_code == 409 and r.json()["detail"].startswith("Повторное вступление возможно через")


# ============================================================================================ secrecy

class TestSecrecy:

    def test_catalog_hides_counts_and_limits_of_secret_factions(self, fapi, fw):
        open_ = make_faction(fw, "Орден Зари", limit=10)
        secret = make_faction(fw, "Тени", secret=True, limit=10)
        hidden = make_faction(fw, "Черновик", active=False)
        post_join(fapi, fid=open_)
        post_join(fapi, fid=secret)
        as_user(USER_BETA)
        cat = {c["id"]: c for c in fapi.get(f"{BASE}/factions/catalog").json()}
        assert hidden not in cat
        assert (cat[open_]["member_count"], cat[open_]["member_limit"]) == (1, 10)
        assert (cat[secret]["member_count"], cat[secret]["member_limit"]) == (None, None)
        assert cat[secret]["is_secret"] is True
        assert cat[open_]["my"] is None and cat[open_]["can_join"] is False

    def test_catalog_condition_naming_a_secret_faction_is_masked(self, fapi, fw):
        secret = make_faction(fw, "Тени", secret=True)
        open_ = make_faction(fw, "Орден Зари")
        set_conditions(fw, open_, [("not_in_faction", {"faction_id": secret})])
        as_user(USER_BETA)
        cat = {c["id"]: c for c in fapi.get(f"{BASE}/factions/catalog?character_id={BETA}").json()}
        assert cat[open_]["conditions"] == [{"type": "not_in_faction", "text": "Не состоит в некоторых тайных "
                                                                              "организациях", "met": True,
                                             "params": None}]
        assert "Тени" not in fapi.get(f"{BASE}/factions/{open_}/public").text

    def test_irreconcilable_secret_partner_is_masked_in_the_catalog(self, fapi, fw):
        secret = make_faction(fw, "Тени", secret=True)
        open_ = make_faction(fw, "Орден Зари")
        hostile(fw, open_, secret, irreconcilable=True)
        as_user(USER_BETA)
        body = fapi.get(f"{BASE}/factions/catalog?character_id={BETA}").text
        cat = {c["id"]: c for c in fapi.get(f"{BASE}/factions/catalog?character_id={BETA}").json()}
        assert cat[open_]["conditions"][0]["text"] == fc.SECRET_FACTION_TEXT
        assert cat[open_]["conditions"][0]["params"] is None
        assert f'"faction_id":{secret}' not in body.replace(" ", "")

    def test_catalog_with_another_players_character_is_403(self, fapi, fw):
        make_faction(fw)
        as_user(USER_BETA)
        assert fapi.get(f"{BASE}/factions/catalog?character_id={ALPHA}").status_code == 403
        app.dependency_overrides.pop(get_current_user_via_http, None)
        assert fapi.get(f"{BASE}/factions/catalog").status_code == 401

    def test_public_faction_endpoint(self, fapi, fw):
        secret = make_faction(fw, "Тени", secret=True)
        hidden = make_faction(fw, "Черновик", active=False)
        set_conditions(fw, secret, [("level", {"min_level": 3})])
        r = fapi.get(f"{BASE}/factions/{secret}/public")
        assert r.status_code == 200 and r.json()["member_count"] is None
        assert "met" not in r.json()["conditions"][0]
        assert fapi.get(f"{BASE}/factions/{hidden}/public").status_code == 404
        assert fapi.get(f"{BASE}/factions/999/public").status_code == 404

    def test_public_memberships_skip_secret_and_inactive(self, fapi, fw):
        open_ = make_faction(fw, "Орден Зари")
        secret = make_faction(fw, "Тени", secret=True)
        gone = make_faction(fw, "Гильдия")
        add_rank(fw, open_, "Послушник", 1)
        for fid in (open_, secret, gone):
            post_join(fapi, fid=fid)
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{gone}/leave")
        r = fapi.get(f"{BASE}/{ALPHA}/factions/public")
        assert r.json() == [{"faction_id": open_, "name": "Орден Зари", "emblem_url": None,
                             "rank_name": "Послушник"}]
        assert fapi.get(f"{BASE}/999/factions/public").status_code == 404

    def test_private_tab_and_journal_owner_or_staff_only(self, fapi, fw):
        secret = make_faction(fw, "Тени", secret=True)
        post_join(fapi, fid=secret)
        as_user(USER_BETA)
        assert fapi.get(f"{BASE}/{ALPHA}/factions").status_code == 403
        assert fapi.get(f"{BASE}/{ALPHA}/factions/history").status_code == 403
        as_user(USER_BETA, "editor", ["characters:read"])
        assert fapi.get(f"{BASE}/{ALPHA}/factions").status_code == 403
        as_moderator()
        assert fapi.get(f"{BASE}/{ALPHA}/factions").status_code == 200
        as_user(USER_ALPHA)
        view = fapi.get(f"{BASE}/{ALPHA}/factions").json()
        assert [m["faction"]["name"] for m in view["memberships"]] == ["Тени"]
        assert view["memberships"][0]["faction"]["is_secret"] is True
        assert view["settings"] == {"rejoin_cooldown_days": 7, "leave_burn_pct": 50, "warning_days": 3}

    def test_notices_go_only_to_the_owner(self, fapi, fw):
        fid = make_faction(fw, "Тени", secret=True)
        post_join(fapi, fid=fid)
        assert {n["target_value"] for n in notices(fw)} == {USER_ALPHA}


# ============================================================================================ private view / journal

class TestPrivateView:

    def test_next_rank_progress_and_history_texts(self, fapi, fw):
        fid = make_faction(fw)
        ladder(fw, fid)
        post_join(fapi, fid=fid)
        quest_done(fapi, cq=61, rewards=[(fid, 12)])
        as_user(USER_ALPHA)
        view = fapi.get(f"{BASE}/{ALPHA}/factions").json()["memberships"][0]
        assert view["rank"]["name"] == "Брат" and view["points"] == 12
        assert view["next_rank"] == {"id": view["next_rank"]["id"], "name": "Рыцарь", "conditions": [
            {"type": "points", "text": "Очки фракции: 12 / 20", "met": False}]}
        hist = fapi.get(f"{BASE}/{ALPHA}/factions/history?page=1&page_size=2").json()
        assert hist["total"] == 3 and len(hist["items"]) == 2
        assert [i["text"] for i in hist["items"]] == ["Новое звание во фракции «Орден Зари»: «Брат»",
                                                      "Очки фракции «Орден Зари»: +12 за задание"]
        assert fapi.get(f"{BASE}/{ALPHA}/factions/history?page_size=51").status_code == 422

    def test_former_memberships_show_the_rejoin_countdown(self, fapi, fw):
        fid = make_faction(fw)
        post_join(fapi, fid=fid)
        as_user(USER_ALPHA)
        fapi.post(f"{BASE}/{ALPHA}/factions/{fid}/leave")
        m = fapi.get(f"{BASE}/{ALPHA}/factions").json()["memberships"][0]
        assert m["status"] == "left" and m["next_rank"] is None and m["rejoin_in_seconds"] > 6 * 86400


# ============================================================================================ periodic pass

class TestPass:

    def _member(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("level", {"min_level": 2})])
        post_join(fapi, fid=fid)
        fw.fsent.reset_mock()
        return fid

    def test_warning_then_clear(self, fapi, fw):
        fid = self._member(fapi, fw)
        t = now()
        set_level(fw, ALPHA, 1)
        stats = faction_pass.run_pass(fw, t, force=True)
        assert (stats["warned"], stats["cleared"], stats["expelled"]) == (1, 0, 0)
        m = member(fw, ALPHA, fid)
        assert m["status"] == "active" and m["warning_reasons"] == ["Уровень от 2"]
        assert notices(fw)[0]["message"] == ("Вы перестали соответствовать условиям фракции «Орден Зари»: "
                                             "Уровень от 2. Исправьте в течение 3 д, иначе вас исключат")
        as_user(USER_ALPHA)
        warning = fapi.get(f"{BASE}/{ALPHA}/factions").json()["memberships"][0]["warning"]
        assert warning["reasons"] == ["Уровень от 2"] and 0 < warning["remaining_seconds"] <= 3 * 86400
        stats = faction_pass.run_pass(fw, t + timedelta(days=1), force=True)
        assert (stats["warned"], stats["expelled"]) == (0, 0)                              # still in the window
        set_level(fw, ALPHA, 2)
        stats = faction_pass.run_pass(fw, t + timedelta(days=2), force=True)
        assert stats["cleared"] == 1
        assert member(fw, ALPHA, fid)["warning_at"] is None
        assert log_types(fw, ALPHA, fid) == ["joined", "warning", "warning_cleared"]
        assert "угроза исключения снята" in notices(fw)[-1]["message"]

    def test_expelled_after_three_days(self, fapi, fw):
        fid = self._member(fapi, fw)
        set_points(fw, ALPHA, fid, 20)
        t = now()
        set_level(fw, ALPHA, 1)
        faction_pass.run_pass(fw, t, force=True)
        stats = faction_pass.run_pass(fw, t + timedelta(days=3) - timedelta(minutes=1), force=True)
        assert stats["expelled"] == 0
        stats = faction_pass.run_pass(fw, t + timedelta(days=3), force=True)
        assert stats["expelled"] == 1
        m = member(fw, ALPHA, fid)
        assert (m["status"], m["points"]) == ("expelled", 10)
        assert m["rejoin_after"] is not None and m["warning_at"] is None
        assert log_types(fw, ALPHA, fid)[-1] == "expelled"
        assert notices(fw)[-1]["message"] == ("Вас исключили из фракции «Орден Зари»: "
                                              "Не соответствует условиям вступления")

    def test_irreconcilable_pair_created_later_warns_double_members(self, fapi, fw):
        a = make_faction(fw, "Орден Зари")
        b = make_faction(fw, "Братство Ночи")
        post_join(fapi, fid=a)
        post_join(fapi, fid=b)
        hostile(fw, a, b, irreconcilable=True)
        stats = faction_pass.run_pass(fw, now(), force=True)
        assert stats["warned"] == 2
        assert member(fw, ALPHA, a)["warning_reasons"] == ["Не состоит во фракции «Братство Ночи»"]

    def test_hidden_faction_members_are_still_watched(self, fapi, fw):
        fid = self._member(fapi, fw)
        exec_(fw, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=fid)
        set_level(fw, ALPHA, 1)
        assert faction_pass.run_pass(fw, now(), force=True)["warned"] == 1

    def test_throttle(self, fapi, fw):
        self._member(fapi, fw)
        t = now()
        assert faction_pass.run_pass(fw, t) is not None
        assert faction_pass.run_pass(fw, t + timedelta(seconds=60)) is None
        assert faction_pass.run_pass(fw, t + timedelta(seconds=faction_pass.RUN_INTERVAL_SECONDS)) is not None

    def test_no_settings_row_no_run(self, fw):
        exec_(fw, "DELETE FROM faction_settings")
        assert faction_pass.run_pass(fw, now()) is None

    def test_pass_retries_due_deliveries(self, fw):
        fid = make_faction(fw)
        rewarded_rank(fw, fid, reward_items=[{"item_id": ITEM_SWORD, "quantity": 1}])
        join(fw, ALPHA, fid)
        stats = faction_pass.run_pass(fw, now(), force=True)
        assert stats["deliveries"]["done"] == 1
        assert len(fw.http.calls) == 1

    def test_one_broken_member_does_not_stop_the_pass(self, fapi, fw, monkeypatch):
        fid = self._member(fapi, fw)
        post_join(fapi, cid=BETA, fid=fid, user=USER_BETA)
        set_level(fw, ALPHA, 1)
        set_level(fw, BETA, 1)
        real = faction_pass.check_member
        alpha_mid = member(fw, ALPHA, fid)["id"]

        def flaky(db, member_id, *args, **kwargs):
            if member_id == alpha_mid:
                raise RuntimeError("boom")
            return real(db, member_id, *args, **kwargs)

        monkeypatch.setattr(faction_pass, "check_member", flaky)
        assert faction_pass.run_pass(fw, now(), force=True)["warned"] == 1
        assert member(fw, BETA, fid)["warning_at"] is not None

    def test_scheduler_runs_the_faction_pass_and_swallows_errors(self, monkeypatch):
        calls = []
        monkeypatch.setattr(faction_pass, "run_pass", lambda factory: calls.append(factory))
        econ_scheduler.run_faction_pass("factory")
        assert calls == ["factory"]

        def boom(factory):
            raise RuntimeError("down")

        monkeypatch.setattr(faction_pass, "run_pass", boom)
        econ_scheduler.run_faction_pass("factory")                                     # no raise


# ============================================================================================ deletion cascade

def test_character_deletion_cascades_faction_rows():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    models.Base.metadata.create_all(bind=eng)
    factory = sessionmaker(bind=eng)
    t = now()
    with factory() as db:
        db.execute(text("INSERT INTO races (id_race, name) VALUES (1, 'Человек')"))
        db.execute(text("INSERT INTO subraces (id_subrace, id_race, name) VALUES (1, 1, 'Норд')"))
        db.execute(text("INSERT INTO classes (id_class, name) VALUES (1, 'Воин')"))
        db.commit()
        import econ_ledger
        with econ_ledger.allow_direct_balance_write(db):
            db.add(models.Character(id=1, name="Альфа", user_id=7, id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", level=2, currency_balance=0))
            db.flush()
        f = models.Faction(name="Орден", is_active=True, created_at=t, updated_at=t)
        db.add(f)
        db.flush()
        rank = models.FactionRank(faction_id=f.id, name="Послушник", sort_order=1, created_at=t)
        db.add(rank)
        db.flush()
        db.add(models.FactionMember(character_id=1, faction_id=f.id, status="active", points=0, rank_id=rank.id,
                                    joined_at=t))
        db.add(models.FactionApplication(character_id=1, faction_id=f.id, status="rejected", created_at=t))
        grant = models.FactionRankGrant(character_id=1, faction_id=f.id, rank_id=rank.id, granted_at=t)
        db.add(grant)
        db.flush()
        db.add(models.FactionRewardDelivery(grant_id=grant.id, character_id=1, kind="xp", payload={"xp": 1},
                                            status="pending", attempts=0, next_attempt_at=t, updated_at=t))
        db.add(models.FactionLog(character_id=1, faction_id=f.id, event_type="joined", created_at=t))
        db.commit()
        db.execute(text("DELETE FROM characters WHERE id = 1"))
        db.commit()
        for table in ("faction_members", "faction_applications", "faction_rank_grants", "faction_reward_deliveries",
                      "faction_log"):
            assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0, table
        assert db.execute(text("SELECT COUNT(*) FROM factions")).scalar() == 1
    eng.dispose()
