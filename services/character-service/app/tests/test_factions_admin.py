"""FEAT-205 QA (task 10): the faction admin API (``/characters/admin/factions/...``) and migration 045.

* RBAC: every admin route is 403 without its permission; a moderator (read / edit / manage) cannot delete or change
  the settings; player routes never accept an admin-only action;
* validation (422 / 409 with Russian texts): faction fields, ranks (non-repeatable quest, title / items / voucher
  locations exist, bounds), the reorder set, every condition type (unknown keys / types, tier codes, ranges),
  hostility pairs (self, duplicate in any order), members (delta / reason / status), settings bounds;
* delete guards (faction with members / applications / grants, rank held or granted), cascades of a clean delete;
* injection-like strings are stored verbatim and never break a read;
* migration 045: ten tables + seeded settings row, re-run no-op, downgrade, DDL matches the models.
"""

from unittest.mock import MagicMock

import pytest

import models
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, BANDIT, GUARD, ITEM_SHIELD, ITEM_SWORD, L_MARKET, MERCHANT, Q_DAILY, Q_MASTER, Q_TRIAL,
    TITLE_KNIGHT, USER_ALPHA, add_rank, as_admin, as_moderator, as_user, exec_, fapi, fw, hostile, load_migration,
    load_migration_047, make_faction, member, q, rep_world, rows, set_conditions,
)

A = "/characters/admin/factions"


def faction_body(**over):
    body = {"name": "Орден Зари", "description": "Рыцари рассвета", "emblem_url": None, "hq_location_id": None,
            "leader_npc_ids": None, "member_limit": None, "is_invite_only": False, "is_secret": False,
            "is_active": True, "sort_order": 0}
    body.update(over)
    return body


def rank_body(**over):
    body = {"name": "Послушник", "min_points": 0, "min_level": 0, "reward_xp": 0}
    body.update(over)
    return body


def create(api, **over):
    r = api.post(A, json=faction_body(**over))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def join(api, fid, cid=ALPHA, user=USER_ALPHA):
    as_user(user)
    r = api.post(f"/characters/{cid}/factions/{fid}/join")
    as_admin()
    return r


# ============================================================================================ RBAC

ROUTES = [  # (method, path, body, permission)
    ("get", A, None, "factions:read"),
    ("post", A, faction_body(), "factions:edit"),
    ("get", f"{A}/1", None, "factions:read"),
    ("put", f"{A}/1", faction_body(), "factions:edit"),
    ("delete", f"{A}/1", None, "factions:delete"),
    ("post", f"{A}/1/ranks", rank_body(), "factions:edit"),
    ("put", f"{A}/ranks/1", rank_body(), "factions:edit"),
    ("delete", f"{A}/ranks/1", None, "factions:delete"),
    ("put", f"{A}/1/ranks/order", {"rank_ids": []}, "factions:edit"),
    ("put", f"{A}/1/conditions", {"conditions": []}, "factions:edit"),
    ("get", f"{A}/hostilities", None, "factions:read"),
    ("post", f"{A}/hostilities", {"faction_a_id": 1, "faction_b_id": 2}, "factions:edit"),
    ("put", f"{A}/hostilities/1", {"faction_a_id": 1, "faction_b_id": 2}, "factions:edit"),
    ("delete", f"{A}/hostilities/1", None, "factions:edit"),
    ("get", f"{A}/applications", None, "factions:read"),
    ("post", f"{A}/applications/1/approve", None, "factions:manage"),
    ("post", f"{A}/applications/1/reject", {"reason": "нет"}, "factions:manage"),
    ("get", f"{A}/1/members", None, "factions:read"),
    ("get", f"{A}/characters/1", None, "factions:read"),
    ("post", f"{A}/members/1/points", {"delta": 5, "reason": "тест"}, "factions:manage"),
    ("post", f"{A}/members/1/expel", {"reason": "тест"}, "factions:manage"),
    ("post", f"{A}/deliveries/1/retry", None, "factions:manage"),
    ("get", f"{A}/settings", None, "factions:read"),
    ("put", f"{A}/settings", {"warning_days": 3, "rejoin_cooldown_days": 7, "leave_burn_pct": 50,
                             "hostile_penalty_pct": 50, "reapply_cooldown_hours": 24}, "factions:settings"),
]


def call(api, method, path, body):
    if body is None:
        return getattr(api, method)(path)
    return api.request(method.upper(), path, json=body)


class TestRbac:

    @pytest.mark.parametrize("method,path,body,perm", ROUTES)
    def test_player_without_permissions_is_403(self, fapi, fw, method, path, body, perm):
        make_faction(fw)
        as_user(USER_ALPHA)
        r = call(fapi, method, path, body)
        assert r.status_code == 403 and r.json()["detail"] == "Недостаточно прав"

    @pytest.mark.parametrize("method,path,body,perm", ROUTES)
    def test_every_other_permission_is_not_enough(self, fapi, fw, method, path, body, perm):
        make_faction(fw)
        others = [p for p in ("factions:read", "factions:edit", "factions:delete", "factions:manage",
                              "factions:settings") if p != perm]
        as_user(1, "admin", others)
        assert call(fapi, method, path, body).status_code == 403

    def test_moderator_cannot_delete_or_change_settings(self, fapi, fw):
        fid = make_faction(fw)
        as_moderator()
        assert fapi.get(A).status_code == 200
        assert fapi.get(f"{A}/settings").status_code == 200
        assert fapi.delete(f"{A}/{fid}").status_code == 403
        rid = add_rank(fw, fid, "Послушник", 1)
        assert fapi.delete(f"{A}/ranks/{rid}").status_code == 403
        assert fapi.put(f"{A}/settings", json={"warning_days": 1, "rejoin_cooldown_days": 1, "leave_burn_pct": 1,
                                               "hostile_penalty_pct": 1, "reapply_cooldown_hours": 1}).status_code == 403
        assert fapi.post(A, json=faction_body(name="Новая")).status_code == 200

    def test_no_token_is_401(self, fapi, fw):
        from auth_http import get_current_user_via_http
        from main import app
        app.dependency_overrides.pop(get_current_user_via_http, None)
        assert fapi.get(A).status_code == 401


# ============================================================================================ factions

class TestFactionCrud:

    def test_create_read_update(self, fapi, fw):
        as_admin()
        fid = create(fapi, hq_location_id=L_MARKET, leader_npc_ids=[MERCHANT, MERCHANT, GUARD], member_limit=50,
                     emblem_url="https://s3.example/episode_images/x.webp")
        d = fapi.get(f"{A}/{fid}").json()
        assert d["hq_location_name"] == "Рынок" and d["leader_npc_ids"] == [MERCHANT, GUARD]
        assert [l["name"] for l in d["leaders"]] == ["Лавочник", "Стражник"]
        r = fapi.put(f"{A}/{fid}", json=faction_body(name="  Орден Рассвета  ", is_secret=True))
        assert r.status_code == 200 and r.json()["name"] == "Орден Рассвета" and r.json()["is_secret"] is True
        assert fapi.get(f"{A}/999").status_code == 404
        assert fapi.put(f"{A}/999", json=faction_body()).status_code == 404

    @pytest.mark.parametrize("over,detail", [
        ({"name": "   "}, "Название: от 1 до 100 символов"),
        ({"name": "x" * 101}, "Название: от 1 до 100 символов"),
        ({"description": "x" * 5001}, "Описание слишком длинное (до 5000 символов)"),
        ({"emblem_url": "http://evil.example/x.png"}, "Герб: нужна ссылка https:// (до 512 символов)"),
        ({"emblem_url": "javascript:alert(1)"}, "Герб: нужна ссылка https:// (до 512 символов)"),
        ({"hq_location_id": 999}, "Локация штаба не найдена"),
        ({"leader_npc_ids": [ALPHA]}, "Руководителем может быть только существующий NPC"),
        ({"leader_npc_ids": [9999]}, "Руководителем может быть только существующий NPC"),
        ({"leader_npc_ids": [50, 51, 52, 53, 54, 56]}, "Руководителей может быть не больше 5"),
        ({"member_limit": 0}, "Лимит участников: от 1 до 100000 (или пусто — без лимита)"),
        ({"member_limit": 100001}, "Лимит участников: от 1 до 100000 (или пусто — без лимита)"),
        ({"sort_order": 100001}, "Порядок: от -100000 до 100000"),
    ])
    def test_validation(self, fapi, fw, over, detail):
        as_admin()
        r = fapi.post(A, json=faction_body(**over))
        assert r.status_code == 422 and r.json()["detail"] == detail
        assert q(fw, "SELECT COUNT(*) FROM factions") == 0

    def test_schema_level_422(self, fapi, fw):
        as_admin()
        assert fapi.post(A, json={"description": "без названия"}).status_code == 422
        assert fapi.post(A, json=faction_body(name="x" * 201)).status_code == 422
        assert fapi.post(A, json=faction_body(member_limit="много")).status_code == 422

    def test_duplicate_name_is_409(self, fapi, fw):
        as_admin()
        create(fapi)
        r = fapi.post(A, json=faction_body())
        assert r.status_code == 409 and r.json()["detail"] == "Фракция с таким названием уже есть"
        other = create(fapi, name="Братство")
        assert fapi.put(f"{A}/{other}", json=faction_body()).status_code == 409

    @pytest.mark.parametrize("name", ["'; DROP TABLE factions; --", "\" OR 1=1 --", "<script>alert(1)</script>",
                                      "Robert'); DELETE FROM faction_members;--"])
    def test_injection_like_names_are_stored_verbatim(self, fapi, fw, name):
        as_admin()
        fid = create(fapi, name=name)
        assert fapi.get(f"{A}/{fid}").json()["name"] == name
        assert [f["name"] for f in fapi.get(A).json()] == [name]
        as_user(USER_ALPHA)
        assert fapi.get("/characters/factions/catalog").json()[0]["name"] == name
        assert q(fw, "SELECT COUNT(*) FROM factions") == 1

    def test_member_search_with_injection_like_text(self, fapi, fw):
        fid = make_faction(fw)
        join(fapi, fid)
        as_admin()
        for needle in ("' OR '1'='1", "%", "Аль"):
            r = fapi.get(f"{A}/{fid}/members", params={"q": needle, "status": "all"})
            assert r.status_code == 200
        assert [m["character"]["name"] for m in fapi.get(f"{A}/{fid}/members", params={"q": "Аль"}).json()["items"]] \
            == ["Альфа"]
        assert fapi.get(f"{A}/{fid}/members", params={"q": "' OR '1'='1"}).json()["total"] == 0

    def test_list_counts(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        add_rank(fw, fid, "Послушник", 1)
        set_conditions(fw, fid, [("level", {"min_level": 1})])
        as_user(USER_ALPHA)
        fapi.post(f"/characters/{ALPHA}/factions/{fid}/apply", json={})
        as_admin()
        (item,) = fapi.get(A).json()
        assert (item["member_count"], item["pending_applications"], item["rank_count"], item["condition_count"]) \
            == (0, 1, 1, 1)

    def test_delete_guard_and_clean_delete(self, fapi, fw):
        as_admin()
        used = create(fapi)
        join(fapi, used)
        r = fapi.delete(f"{A}/{used}")
        assert r.status_code == 409 and r.json()["detail"] == "Фракцию, в которой были участники, можно только скрыть"
        applied = create(fapi, name="Тайный круг", is_invite_only=True)
        as_user(USER_ALPHA)
        fapi.post(f"/characters/{ALPHA}/factions/{applied}/apply", json={})
        as_admin()
        assert fapi.delete(f"{A}/{applied}").status_code == 409
        clean = create(fapi, name="Черновик")
        add_rank(fw, clean, "Послушник", 1)
        set_conditions(fw, clean, [("level", {"min_level": 1})])
        hostile(fw, clean, used)
        assert fapi.delete(f"{A}/{clean}").json() == {"ok": True}
        for table in ("faction_ranks", "faction_conditions"):
            assert q(fw, f"SELECT COUNT(*) FROM {table} WHERE faction_id = :x", x=clean) == 0
        assert q(fw, "SELECT COUNT(*) FROM faction_hostilities WHERE faction_a_id = :x OR faction_b_id = :x",
                 x=clean) == 0
        assert fapi.delete(f"{A}/{clean}").status_code == 404

    def test_hidden_faction_keeps_its_members(self, fapi, fw):
        as_admin()
        fid = create(fapi)
        join(fapi, fid)
        fapi.put(f"{A}/{fid}", json=faction_body(is_active=False))
        assert member(fw, ALPHA, fid)["status"] == "active"
        as_user(USER_ALPHA)
        assert fapi.get("/characters/factions/catalog").json() == []
        assert fapi.get(f"/characters/{ALPHA}/factions").json()["memberships"][0]["status"] == "active"


# ============================================================================================ ranks

class TestRanks:

    def test_create_appends_to_the_ladder(self, fapi, fw):
        fid = make_faction(fw)
        as_admin()
        r1 = fapi.post(f"{A}/{fid}/ranks", json=rank_body()).json()
        r2 = fapi.post(f"{A}/{fid}/ranks", json=rank_body(
            name="Рыцарь", min_points=20, min_level=5, required_quest_id=Q_MASTER, reward_xp=500,
            reward_title_id=TITLE_KNIGHT, reward_items=[{"item_id": ITEM_SWORD, "quantity": 2}],
            reward_house_location_id=L_MARKET, reward_plot_location_id=110)).json()
        assert (r1["sort_order"], r2["sort_order"]) == (1, 2)
        assert r2["reward_items"] == [{"item_id": ITEM_SWORD, "quantity": 2}]
        assert r2["required_quest_id"] == Q_MASTER
        assert fapi.post(f"{A}/999/ranks", json=rank_body()).status_code == 404

    @pytest.mark.parametrize("over,detail", [
        ({"name": ""}, "Название: от 1 до 100 символов"),
        ({"min_points": -1}, "Очки для звания: от 0 до 10000000"),
        ({"min_points": 10_000_001}, "Очки для звания: от 0 до 10000000"),
        ({"min_level": 1001}, "Уровень для звания: от 0 до 1000"),
        ({"reward_xp": -5}, "Опыт за звание: от 0 до 10000000"),
        ({"required_quest_id": Q_DAILY}, "Условием может быть только неповторяемое задание"),
        ({"required_quest_id": 999}, "Задание не найдено"),
        ({"reward_title_id": 999}, "Титул не найден"),
        ({"reward_items": [{"item_id": 999, "quantity": 1}]}, "Предмет не найден: #999"),
        ({"reward_items": [{"item_id": ITEM_SWORD, "quantity": 1}, {"item_id": ITEM_SWORD, "quantity": 2}]},
         "Предмет указан дважды: #501"),
        ({"reward_items": [{"item_id": ITEM_SWORD, "quantity": 0}]}, "Количество предмета: от 1 до 999"),
        ({"reward_items": [{"item_id": ITEM_SWORD, "quantity": 1000}]}, "Количество предмета: от 1 до 999"),
        ({"reward_items": [{"item_id": 600 + i, "quantity": 1} for i in range(11)]},
         "Предметов в награде может быть не больше 10"),
        ({"reward_house_location_id": 999}, "Локация для права на дом / участок не найдена"),
        ({"reward_plot_location_id": 999}, "Локация для права на дом / участок не найдена"),
    ])
    def test_validation(self, fapi, fw, over, detail):
        fid = make_faction(fw)
        as_admin()
        r = fapi.post(f"{A}/{fid}/ranks", json=rank_body(**over))
        assert r.status_code == 422 and r.json()["detail"] == detail
        assert q(fw, "SELECT COUNT(*) FROM faction_ranks") == 0

    def test_update_and_delete_guards(self, fapi, fw):
        fid = make_faction(fw)
        r1 = add_rank(fw, fid, "Послушник", 1)
        r2 = add_rank(fw, fid, "Брат", 2, min_points=10)
        free = add_rank(fw, fid, "Пустое", 3, min_points=99)
        as_admin()
        assert fapi.put(f"{A}/ranks/{r2}", json=rank_body(name="Собрат", min_points=12)).json()["min_points"] == 12
        assert fapi.put(f"{A}/ranks/999", json=rank_body()).status_code == 404
        join(fapi, fid)                                                       # holds r1, grant r1
        r = fapi.delete(f"{A}/ranks/{r1}")
        assert r.status_code == 409 and r.json()["detail"] == "Звание уже получено участниками — его нельзя удалить"
        exec_(fw, "UPDATE faction_members SET rank_id = :r", r=r2)              # no holder of r1, but a grant
        assert fapi.delete(f"{A}/ranks/{r1}").status_code == 409
        assert fapi.delete(f"{A}/ranks/{free}").json() == {"ok": True}
        assert fapi.delete(f"{A}/ranks/{free}").status_code == 404

    def test_reorder(self, fapi, fw):
        fid = make_faction(fw)
        r1 = add_rank(fw, fid, "Первый", 1)
        r2 = add_rank(fw, fid, "Второй", 2)
        other = add_rank(fw, make_faction(fw, "Другая"), "Чужое", 1)
        as_admin()
        for bad in ([r1], [r1, r2, other], [r1, r1, r2], []):
            r = fapi.put(f"{A}/{fid}/ranks/order", json={"rank_ids": bad})
            assert r.status_code == 422 and r.json()["detail"] == "Нужно перечислить все звания фракции ровно по " \
                                                                  "одному разу"
        r = fapi.put(f"{A}/{fid}/ranks/order", json={"rank_ids": [r2, r1]})
        assert [(x["id"], x["sort_order"]) for x in r.json()] == [(r2, 1), (r1, 2)]


# ============================================================================================ conditions

def put_conditions(api, fid, conditions):
    return api.put(f"{A}/{fid}/conditions", json={"conditions": [{"type": t, "params": p} for t, p in conditions]})


class TestConditions:

    def test_every_type_valid(self, fapi, fw):
        fid = make_faction(fw)
        secret = make_faction(fw, "Тени", secret=True)
        as_admin()
        conds = [("region_reputation", {"region_id": 10, "min_tier": "trusted"}),
                 ("fame", {"min_tier": "familiar", "max_tier": "known"}), ("infamy", {"max_tier": "whispers"}),
                 ("level", {"min_level": 5}), ("class", {"class_ids": [1, 3, 1]}),
                 ("subclass", {"subclass_keys": ["paladin", "berserker_2"]}),
                 ("race", {"race_ids": [2], "subrace_ids": [4]}), ("quest", {"quest_id": Q_TRIAL}),
                 ("not_in_faction", {"faction_id": secret})]
        r = put_conditions(fapi, fid, conds)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out[4]["params"] == {"class_ids": [1, 3]}                        # deduplicated
        assert out[-1]["text"] == "Не состоит во фракции «Тени»"                  # staff sees the secret name
        assert [c["type"] for c in fapi.get(f"{A}/{fid}").json()["conditions"]] == [t for t, _p in conds]
        assert put_conditions(fapi, fid, []).json() == []                         # replace = clear
        assert q(fw, "SELECT COUNT(*) FROM faction_conditions") == 0

    @pytest.mark.parametrize("cond,detail", [
        (("bogus", {}), "Неизвестный тип условия: bogus"),
        (("level", {"min_level": 3, "sql": "1; DROP TABLE x"}), "Лишние параметры условия «level»: sql"),
        (("level", {}), "Условие «level»: не заполнено — min_level"),
        (("level", {"min_level": 0}), "Уровень: от 1 до 1000"),
        (("level", {"min_level": "пять"}), "Уровень: от 1 до 1000"),
        (("region_reputation", {"region_id": 999, "min_tier": "trusted"}), "Край не найден"),
        (("region_reputation", {"region_id": 10, "min_tier": "boss"}), "Репутация: неизвестная ступень «boss»"),
        (("fame", {}), "Слава: укажите ступень «не ниже» и/или «не выше»"),
        (("fame", {"min_tier": "god"}), "Слава: неизвестная ступень «god»"),
        (("fame", {"min_tier": "known", "max_tier": "familiar"}), "Слава: «не ниже» должна быть не выше «не выше»"),
        (("infamy", {"max_tier": "known"}), "Слухи: неизвестная ступень «known»"),
        (("class", {"class_ids": [99]}), "Класс не найден"),
        (("class", {"class_ids": []}), "Классы: от 1 до 20"),
        (("class", {"class_ids": "1"}), "Классы: от 1 до 20"),
        (("subclass", {"subclass_keys": ["Paladin'--"]}), "Подкласс: неверный ключ"),
        (("race", {"race_ids": [99]}), "Раса не найдена"),
        (("race", {"race_ids": [2], "subrace_ids": [99]}), "Подраса не найдена"),
        (("quest", {"quest_id": Q_DAILY}), "Условием может быть только неповторяемое задание"),
        (("quest", {"quest_id": 999}), "Задание не найдено"),
        (("not_in_faction", {"faction_id": 999}), "Фракция не найдена"),
    ])
    def test_validation(self, fapi, fw, cond, detail):
        fid = make_faction(fw)
        as_admin()
        r = put_conditions(fapi, fid, [cond])
        assert r.status_code == 422 and r.json()["detail"] == detail

    def test_not_in_itself_and_too_many(self, fapi, fw):
        fid = make_faction(fw)
        as_admin()
        r = put_conditions(fapi, fid, [("not_in_faction", {"faction_id": fid})])
        assert r.status_code == 422 and r.json()["detail"] == "Условие не может ссылаться на саму фракцию"
        r = put_conditions(fapi, fid, [("level", {"min_level": 1})] * 21)
        assert r.status_code == 422 and r.json()["detail"] == "Условий вступления может быть не больше 20"
        assert put_conditions(fapi, 999, []).status_code == 404

    def test_failed_replace_keeps_the_old_list(self, fapi, fw):
        fid = make_faction(fw)
        set_conditions(fw, fid, [("level", {"min_level": 2})])
        as_admin()
        put_conditions(fapi, fid, [("level", {"min_level": 9}), ("bogus", {})])
        assert rows(fw, "SELECT cond_type FROM faction_conditions") == [("level",)]


# ============================================================================================ hostilities

class TestHostilities:

    def test_crud_and_normalisation(self, fapi, fw):
        a, b, c = make_faction(fw, "А"), make_faction(fw, "Б"), make_faction(fw, "В")
        as_admin()
        r = fapi.post(f"{A}/hostilities", json={"faction_a_id": b, "faction_b_id": a, "irreconcilable": True})
        assert r.status_code == 200
        h = r.json()
        assert (h["faction_a_id"], h["faction_b_id"], h["irreconcilable"]) == (a, b, True)
        for pair in ((a, b), (b, a)):
            r = fapi.post(f"{A}/hostilities", json={"faction_a_id": pair[0], "faction_b_id": pair[1]})
            assert r.status_code == 409 and r.json()["detail"] == "Такая пара враждебных фракций уже есть"
        r = fapi.post(f"{A}/hostilities", json={"faction_a_id": a, "faction_b_id": a})
        assert r.status_code == 422 and r.json()["detail"] == "Фракция не может враждовать сама с собой"
        assert fapi.post(f"{A}/hostilities", json={"faction_a_id": a, "faction_b_id": 999}).status_code == 422
        r = fapi.put(f"{A}/hostilities/{h['id']}", json={"faction_a_id": c, "faction_b_id": a})
        assert r.status_code == 200 and (r.json()["faction_a_id"], r.json()["irreconcilable"]) == (a, False)
        assert [x["faction_b_name"] for x in fapi.get(f"{A}/hostilities").json()] == ["В"]
        assert fapi.put(f"{A}/hostilities/999", json={"faction_a_id": a, "faction_b_id": b}).status_code == 404
        assert fapi.delete(f"{A}/hostilities/{h['id']}").json() == {"ok": True}
        assert fapi.delete(f"{A}/hostilities/{h['id']}").status_code == 404


# ============================================================================================ applications / members

class TestApplicationsAndMembers:

    def test_application_list_filters(self, fapi, fw):
        fid = make_faction(fw, invite=True)
        set_conditions(fw, fid, [("level", {"min_level": 2})])
        as_user(USER_ALPHA)
        fapi.post(f"/characters/{ALPHA}/factions/{fid}/apply", json={"message": "Возьмите"})
        as_admin()
        page = fapi.get(f"{A}/applications").json()
        assert page["total"] == 1
        item = page["items"][0]
        assert item["character"]["name"] == "Альфа" and item["message"] == "Возьмите"
        assert item["conditions"] == [{"type": "level", "text": "Уровень от 2", "met": True}]
        assert fapi.get(f"{A}/applications", params={"status": "rejected"}).json()["total"] == 0
        assert fapi.get(f"{A}/applications", params={"status": "all"}).json()["total"] == 1
        r = fapi.get(f"{A}/applications", params={"status": "bogus"})
        assert r.status_code == 422 and r.json()["detail"] == "Неизвестный статус"
        assert fapi.get(f"{A}/applications", params={"page_size": 51}).status_code == 422
        assert fapi.post(f"{A}/applications/999/approve").status_code == 404
        assert fapi.post(f"{A}/applications/999/reject", json={}).status_code == 404
        assert fapi.post(f"{A}/applications/{item['id']}/reject",
                         json={"reason": "x" * 1001}).status_code == 422

    @pytest.mark.parametrize("body,status,detail", [
        ({"delta": 0, "reason": "Награда"}, 422, "Изменение очков: от -100000 до 100000, не 0"),
        ({"delta": 100001, "reason": "Награда"}, 422, "Изменение очков: от -100000 до 100000, не 0"),
        ({"delta": 5, "reason": "ok"}, 422, "Причина: от 3 до 500 символов"),
        ({"delta": 5, "reason": "   "}, 422, "Причина: от 3 до 500 символов"),
    ])
    def test_points_validation(self, fapi, fw, body, status, detail):
        fid = make_faction(fw)
        join(fapi, fid)
        mid = member(fw, ALPHA, fid)["id"]
        r = fapi.post(f"{A}/members/{mid}/points", json=body)
        assert r.status_code == status and r.json()["detail"] == detail
        assert member(fw, ALPHA, fid)["points"] == 0

    def test_points_and_expel_need_an_active_member(self, fapi, fw):
        fid = make_faction(fw)
        join(fapi, fid)
        mid = member(fw, ALPHA, fid)["id"]
        assert fapi.post(f"{A}/members/999/points", json={"delta": 5, "reason": "Награда"}).status_code == 404
        assert fapi.post(f"{A}/members/{mid}/expel", json={"reason": "no"}).status_code == 422
        assert fapi.post(f"{A}/members/{mid}/expel", json={"reason": "Измена"}).status_code == 200
        r = fapi.post(f"{A}/members/{mid}/points", json={"delta": 5, "reason": "Награда"})
        assert r.status_code == 409 and r.json()["detail"] == "Персонаж не состоит во фракции"
        r = fapi.post(f"{A}/members/{mid}/points", json={"delta": -5, "reason": "Штраф"})
        assert r.status_code == 409

    def test_negative_admin_points_clamp(self, fapi, fw):
        fid = make_faction(fw)
        join(fapi, fid)
        mid = member(fw, ALPHA, fid)["id"]
        exec_(fw, "UPDATE faction_members SET points = 7")
        r = fapi.post(f"{A}/members/{mid}/points", json={"delta": -100, "reason": "Штраф"})
        assert r.json()["points_delta"] == -7 and r.json()["points_after"] == 0

    def test_member_list_status_filter(self, fapi, fw):
        fid = make_faction(fw)
        join(fapi, fid)
        join(fapi, fid, cid=BETA, user=8)
        as_user(8)
        fapi.post(f"/characters/{BETA}/factions/{fid}/leave")
        as_admin()
        assert fapi.get(f"{A}/{fid}/members").json()["total"] == 1
        assert fapi.get(f"{A}/{fid}/members", params={"status": "left"}).json()["items"][0]["character"]["id"] == BETA
        assert fapi.get(f"{A}/{fid}/members", params={"status": "nope"}).status_code == 422
        assert fapi.get(f"{A}/999/members").status_code == 404

    def test_admin_character_card(self, fapi, fw):
        fid = make_faction(fw, secret=True)
        add_rank(fw, fid, "Послушник", 1, reward_xp=10)
        join(fapi, fid)
        card = fapi.get(f"{A}/characters/{ALPHA}").json()
        assert card["memberships"][0]["faction"]["is_secret"] is True
        assert [g["rank_name"] for g in card["grants"]] == ["Послушник"]
        assert [(d["kind"], d["status"]) for d in card["deliveries"]] == [("xp", "done")]
        assert fapi.get(f"{A}/characters/999").status_code == 404


# ============================================================================================ settings

SETTINGS_OK = {"warning_days": 3, "rejoin_cooldown_days": 7, "leave_burn_pct": 50, "hostile_penalty_pct": 50,
               "reapply_cooldown_hours": 24}
# FEAT-206: the economy settings ride in the same row / endpoint (optional on PUT -> kept when omitted)
ECON_SETTINGS_OK = {"donation_marks_per_point": 10, "donation_points_daily_cap": 50, "econ_purse_share_pct": 2,
                    "econ_treasury_share_pct": 1, "members_leave_pct": 5, "members_grow_pct": 1,
                    "qm_take_share_pct": 5, "econ_enabled": True,
                    # FEAT-207 settings (additive fields of the same GET / PUT)
                    "econ_item_sale_share_pct": 2, "kill_points_daily_cap": 50, "pvp_kill_repeat_hours": 24,
                    "outlaw_check_cooldown_hours": 24}


class TestSettings:

    def test_get_and_put(self, fapi, fw):
        as_admin()
        assert fapi.get(f"{A}/settings").json() == {**SETTINGS_OK, **ECON_SETTINGS_OK}
        new = {"warning_days": 0, "rejoin_cooldown_days": 365, "leave_burn_pct": 100, "hostile_penalty_pct": 0,
               "reapply_cooldown_hours": 720}
        assert fapi.put(f"{A}/settings", json=new).json() == {**new, **ECON_SETTINGS_OK}
        assert fapi.get(f"{A}/settings").json() == {**new, **ECON_SETTINGS_OK}

    @pytest.mark.parametrize("field,value,detail", [
        ("warning_days", 61, "Дней до исключения после предупреждения: от 0 до 60"),
        ("warning_days", -1, "Дней до исключения после предупреждения: от 0 до 60"),
        ("rejoin_cooldown_days", 366, "Дней до повторного вступления: от 0 до 365"),
        ("leave_burn_pct", 101, "Сгорает очков при выходе, %: от 0 до 100"),
        ("hostile_penalty_pct", -1, "Штраф враждебной фракции, %: от 0 до 100"),
        ("reapply_cooldown_hours", 721, "Часов до повторной заявки: от 0 до 720"),
    ])
    def test_bounds(self, fapi, fw, field, value, detail):
        as_admin()
        r = fapi.put(f"{A}/settings", json={**SETTINGS_OK, field: value})
        assert r.status_code == 422 and r.json()["detail"] == detail
        assert fapi.get(f"{A}/settings").json() == {**SETTINGS_OK, **ECON_SETTINGS_OK}

    def test_missing_field_is_422(self, fapi, fw):
        as_admin()
        body = dict(SETTINGS_OK)
        body.pop("warning_days")
        assert fapi.put(f"{A}/settings", json=body).status_code == 422


# ============================================================================================ migration 045

def load_migration_046():
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "046_faction_economy.py")
    spec = importlib.util.spec_from_file_location("migration_046_faction_economy_qa", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeMySQL:
    """information_schema.tables + the seed SELECT, emulated; DDL recorded."""

    def __init__(self, tables=("characters",)):
        self.tables = set(tables)
        self.settings_rows = 0
        self.statements = []

    def execute(self, clause, params=None):
        sql = str(clause)
        result = MagicMock()
        if "information_schema.tables" in sql:
            result.scalar.return_value = int(params["t"] in self.tables)
        elif "FROM faction_settings" in sql:
            result.scalar.return_value = self.settings_rows
        else:
            raise AssertionError(f"unexpected bind SQL: {sql}")
        return result

    def op_execute(self, sql):
        sql = str(sql)
        self.statements.append(sql)
        words = sql.split()
        if sql.startswith("CREATE TABLE"):
            assert words[2] not in self.tables, f"duplicate table {words[2]}"
            self.tables.add(words[2])
        elif sql.startswith("DROP TABLE"):
            self.tables.remove(words[2])
            if words[2] == "faction_settings":
                self.settings_rows = 0
        elif sql.startswith("INSERT INTO faction_settings"):
            self.settings_rows += 1
        else:
            raise AssertionError(f"unexpected DDL: {sql}")


@pytest.fixture
def fake_mysql(monkeypatch):
    mig = load_migration()
    db = FakeMySQL()
    monkeypatch.setattr(mig.op, "get_bind", lambda: db, raising=False)
    monkeypatch.setattr(mig.op, "execute", db.op_execute, raising=False)
    return mig, db


FACTION_TABLES = {"factions", "faction_ranks", "faction_conditions", "faction_hostilities", "faction_members",
                  "faction_applications", "faction_rank_grants", "faction_reward_deliveries", "faction_log",
                  "faction_settings"}


class TestMigration045:

    def test_revision(self):
        mig = load_migration()
        assert mig.revision == "045_factions_core" and len(mig.revision) <= 32
        assert mig.down_revision == "044_guard_patrols"

    def test_upgrade_creates_tables_and_seeds_settings(self, fake_mysql):
        mig, db = fake_mysql
        mig.upgrade()
        assert db.tables == FACTION_TABLES | {"characters"}
        assert db.settings_rows == 1
        seed = [s for s in db.statements if s.startswith("INSERT")]
        assert seed == ["INSERT INTO faction_settings (id, warning_days, rejoin_cooldown_days, leave_burn_pct, "
                        "hostile_penalty_pct, reapply_cooldown_hours) VALUES (1, 3, 7, 50, 50, 24)"]

    def test_rerun_is_a_noop(self, fake_mysql):
        mig, db = fake_mysql
        mig.upgrade()
        before = len(db.statements)
        mig.upgrade()
        assert len(db.statements) == before and db.settings_rows == 1

    def test_partial_state_creates_only_the_missing(self, fake_mysql):
        mig, db = fake_mysql
        db.tables |= {"factions", "faction_ranks"}
        mig.upgrade()
        assert db.tables == FACTION_TABLES | {"characters"}
        assert not any(s.startswith("CREATE TABLE factions ") for s in db.statements)

    def test_downgrade_then_upgrade(self, fake_mysql):
        mig, db = fake_mysql
        mig.upgrade()
        mig.downgrade()
        assert db.tables == {"characters"}
        drops = [s.split()[2] for s in db.statements if s.startswith("DROP")]
        assert drops == [name for name, _ddl in reversed(mig._TABLES)]
        before = len(db.statements)
        mig.downgrade()
        assert len(db.statements) == before
        mig.upgrade()
        assert db.tables == FACTION_TABLES | {"characters"} and db.settings_rows == 1

    def test_ddl_matches_the_models(self):
        mig = load_migration()
        ddl = dict(mig._TABLES)
        assert set(ddl) == FACTION_TABLES
        by_table = {m.__tablename__: m for m in (
            models.Faction, models.FactionRank, models.FactionCondition, models.FactionHostility,
            models.FactionMember, models.FactionApplication, models.FactionRankGrant, models.FactionRewardDelivery,
            models.FactionLog, models.FactionSettings)}
        later = {(t, c) for t, c, _ddl in load_migration_046()._COLUMNS}       # FEAT-206 adds these columns
        later |= {(t, c) for t, c, _ddl in load_migration_047()._COLUMNS}      # FEAT-207 adds these columns
        for name, model in by_table.items():
            assert "ENUM" not in ddl[name].upper().replace("INNODB", "")
            for column in model.__table__.columns.keys():
                if (name, column) in later:
                    continue
                assert f" {column} " in ddl[name], (name, column)
        assert "ON DELETE CASCADE" in ddl["faction_members"] and "REFERENCES characters" in ddl["faction_members"]
        assert "ON DELETE RESTRICT" in ddl["faction_rank_grants"]
        assert "UNIQUE KEY uq_faction_log_key (event_key, faction_id)" in ddl["faction_log"]
        assert "UNIQUE KEY uq_faction_grant (character_id, rank_id)" in ddl["faction_rank_grants"]
        assert "UNIQUE KEY uq_faction_app_pending (pending_key)" in ddl["faction_applications"]
        # FK columns carry their own index (MySQL gotcha)
        for name, column in (("faction_members", "rank_id"), ("faction_applications", "character_id"),
                             ("faction_rank_grants", "rank_id"), ("faction_reward_deliveries", "grant_id"),
                             ("faction_log", "faction_id"), ("faction_conditions", "faction_id")):
            assert f"({column})" in ddl[name] or f"({column}," in ddl[name], (name, column)
