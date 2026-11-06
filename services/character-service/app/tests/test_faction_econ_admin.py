"""FEAT-206 QA: faction economy admin API, secrecy of the player views, migration 046. features/FEAT-206 §3.3, §3.9,
§3.10, §3.12.

Admin: RBAC (``factions:read`` / ``factions:economy`` / fill = ``factions:economy`` + ``economy:emit``), economy view /
update validation (template, overrides whitelist, member bounds), «Заполнить по шаблону» (409 without a template,
re-click emits 0, a new top-up after spending, settles debts), history / operations / debts pages, templates CRUD
(code regex, duplicates, delete guard), quartermasters (NPC only, taken by another faction, max 10), assortment
(off-market restock 422, duplicate 409, foreign rank 422), rank / faction delete guards, settings / rank fields bounds,
the ledger summary total. Secrecy: wealth words in catalog / public / private views, other players' private data.
Migration 046 on an emulated MySQL (tables, columns, seeds, backfill, idempotent re-run, downgrade, DDL vs models).
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import econ_core as core
import economy_crud
import faction_econ as fe
import faction_econ_crud as fec
import models
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GUARD, ITEM_SCROLL, ITEM_SHIELD, ITEM_SWORD, MERCHANT, QM_NPC, QM_NPC_2, USER_ALPHA, USER_BETA,
    add_rank, as_user, bind_qm, cash, debts, econ_faction, econ_row, econ_world, exec_, fapi, fund, fw, join,
    load_migration_046, load_migration_047, make_faction, ops, q, qm_item, rep_world, rows, treasury, world_sum,
)

A = "/characters/admin/factions"
P = "/characters"
READ = ["factions:read"]
ECON = ["factions:read", "factions:economy"]
FILL = ["factions:read", "factions:economy", "economy:emit"]


def admin(perms=FILL + ["factions:edit", "factions:delete", "factions:settings", "factions:manage"]):
    as_user(1, "admin", perms)


# ============================================================================================ RBAC


class TestPermissions:

    @pytest.mark.parametrize("method,path,body", [
        ("put", "/{fid}/economy", {"members_count": 5}),
        ("post", "/econ-templates", {"code": "zz", "name": "Z", "params": {}}),
        ("put", "/econ-templates/order", {"name": "Z", "params": {}}),
        ("delete", "/econ-templates/academy", None),
        ("put", "/{fid}/quartermasters", {"npc_ids": []}),
        ("post", "/{fid}/qm-items", {"item_id": 501, "price": 5}),
        ("put", "/qm-items/1", {"item_id": 501, "price": 5}),
        ("delete", "/qm-items/1", None),
    ])
    def test_economy_writes_need_factions_economy(self, fapi, econ_world, method, path, body):
        fid = make_faction(econ_world)
        qm_item(econ_world, fid)
        url = A + path.format(fid=fid)
        as_user(2, "moderator", ["factions:read", "factions:edit", "factions:manage", "factions:settings",
                                 "economy:emit"])
        r = getattr(fapi, method)(url, json=body) if body is not None else getattr(fapi, method)(url)
        assert r.status_code == 403
        as_user(USER_ALPHA)
        r = getattr(fapi, method)(url, json=body) if body is not None else getattr(fapi, method)(url)
        assert r.status_code == 403

    @pytest.mark.parametrize("path", ["/{fid}/economy", "/{fid}/economy/history", "/{fid}/economy/operations",
                                      "/{fid}/debts", "/econ-templates", "/{fid}/quartermasters", "/{fid}/qm-items",
                                      "/{fid}/qm-purchases"])
    def test_reads_need_factions_read(self, fapi, econ_world, path):
        fid = make_faction(econ_world)
        as_user(USER_ALPHA, "user", ["factions:economy"])
        assert fapi.get(A + path.format(fid=fid)).status_code == 403
        as_user(2, "moderator", READ)
        assert fapi.get(A + path.format(fid=fid)).status_code == 200

    def test_fill_needs_both(self, fapi, econ_world):
        fid = make_faction(econ_world)
        econ_faction(econ_world, fid, "order", members=0)
        body = {"comment": "старт", "set_members": True}
        for perms in (["factions:economy"], ["economy:emit"], ["factions:read", "factions:manage"]):
            as_user(2, "moderator", perms)
            assert fapi.post(f"{A}/{fid}/economy/fill", json=body).status_code == 403
        assert treasury(econ_world, fid) == 0
        as_user(2, "moderator", ["factions:economy", "economy:emit"])
        assert fapi.post(f"{A}/{fid}/economy/fill", json=body).status_code == 200

    def test_unauthenticated_401(self, fapi, econ_world):
        from auth_http import get_current_user_via_http
        from main import app
        fid = make_faction(econ_world)
        app.dependency_overrides.pop(get_current_user_via_http, None)
        assert fapi.get(f"{A}/{fid}/economy").status_code == 401
        assert fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт"}).status_code == 401


# ============================================================================================ economy view / update


class TestEconomy:

    def test_view_without_economy_row(self, fapi, econ_world):
        fid = make_faction(econ_world)                    # created directly: no row (API create makes one)
        admin()
        body = fapi.get(f"{A}/{fid}/economy").json()
        assert (body["template_code"], body["params"], body["wealth"], body["wealth_label"], body["ticking"],
                body["treasury"], body["members_count"]) == \
            (None, None, None, None, False, {"account_id": None, "balance": 0}, 0)
        assert body["not_ticking_reason"]                 # a row-less faction never ticks (backfill makes rows)
        assert fapi.get(f"{A}/999/economy").status_code == 404

    def test_api_create_makes_the_economy_row(self, fapi, econ_world):
        admin()
        r = fapi.post(A, json={"name": "Новая", "description": "Описание"})
        assert r.status_code == 200, r.text
        fid = int(q(econ_world, "SELECT id FROM factions WHERE name = 'Новая'"))
        assert econ_row(econ_world, fid)["members_count"] == 0

    def test_update_and_effective_params(self, fapi, econ_world):
        fid = make_faction(econ_world)
        admin()
        r = fapi.put(f"{A}/{fid}/economy", json={"template_code": "temple", "overrides": {"wage_per_member": 2},
                                                 "members_count": 50, "members_min": 0, "members_max": 40,
                                                 "econ_enabled": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["template_code"], body["template_name"], body["overrides"], body["members_count"],
                body["members_min"], body["members_max"], body["econ_enabled"]) == \
            ("temple", "Храм", {"wage_per_member": "2"}, 40, 0, 40, False)          # members clamped to max
        assert body["params"]["wage_per_member"] == "2" and body["params"]["profile_per_member"] == "0.75"
        assert body["norm"] == 40 * 30 and body["wealth"] == 0 and body["wealth_label"] == "Бедствует"

    def test_partial_update_keeps_omitted_template_and_overrides(self, fapi, econ_world):
        fid = make_faction(econ_world)
        admin()
        url = f"{A}/{fid}/economy"
        assert fapi.put(url, json={"template_code": "temple", "overrides": {"wage_per_member": 2}}).status_code == 200
        body = fapi.put(url, json={"members_count": 50}).json()                        # omitted -> kept
        assert (body["template_code"], body["overrides"], body["members_count"]) == \
            ("temple", {"wage_per_member": "2"}, 50)
        body = fapi.put(url, json={"econ_enabled": False, "overrides": {"wage_per_member": 3}}).json()
        assert (body["template_code"], body["overrides"], body["econ_enabled"]) == \
            ("temple", {"wage_per_member": "3"}, False)                                 # template kept, overrides set
        body = fapi.put(url, json={"overrides": None}).json()                           # explicit null clears
        assert (body["template_code"], body["overrides"]) == ("temple", {})
        body = fapi.put(url, json={"template_code": None}).json()
        assert (body["template_code"], body["members_count"], body["econ_enabled"]) == (None, 50, False)
        r = fapi.put(url, json={"overrides": {"bogus": 1}})                             # validated even alone
        assert r.status_code == 422 and r.json()["detail"] == "Неизвестный параметр шаблона: bogus"

    @pytest.mark.parametrize("body,status,detail", [
        ({"template_code": "nope"}, 404, "Шаблон не найден"),
        ({"template_code": "order", "overrides": {"bogus": 1}}, 422, "Неизвестный параметр шаблона: bogus"),
        ({"template_code": "order", "overrides": {"profile_rate": "0.5"}}, 422, None),
        ({"template_code": "order", "members_min": 50, "members_max": 10}, 422, None),
        ({"template_code": "order", "members_max": 100001}, 422, None),
        ({"template_code": "order", "members_count": -1}, 422, "Число участников: от 0 до 100000"),
        ({"template_code": "'; DROP TABLE factions; --"}, 404, "Шаблон не найден"),
    ])
    def test_update_validation(self, fapi, econ_world, body, status, detail):
        fid = make_faction(econ_world)
        admin()
        r = fapi.put(f"{A}/{fid}/economy", json=body)
        assert r.status_code == status
        if detail:
            assert r.json()["detail"] == detail
        assert int(q(econ_world, "SELECT COUNT(*) FROM factions")) == 1

    def test_history_operations_and_debt_pages(self, fapi, econ_world):
        fid = make_faction(econ_world)
        add_rank(econ_world, fid, "Послушник", 1, reward_marks=10)
        join(econ_world, ALPHA, fid)
        join(econ_world, BETA, fid)
        fund(econ_world, core.AccountRef.faction(fid), 15)
        fec.settle_after_commit([fid], econ_world)
        admin()
        assert fapi.get(f"{A}/{fid}/debts").json()["total"] == 1                        # default: open
        page = fapi.get(f"{A}/{fid}/debts?status=all").json()
        assert [(i["character"]["name"], i["paid"], i["status"]) for i in page["items"]] == \
            [("Альфа", 10, "paid"), ("Бета", 5, "open")]
        assert fapi.get(f"{A}/{fid}/debts?status=paid").json()["total"] == 1
        assert fapi.get(f"{A}/{fid}/debts?status=bogus").status_code == 422
        operations = fapi.get(f"{A}/{fid}/economy/operations").json()
        assert operations["total"] == 2                                                 # emission + payout
        assert fapi.get(f"{A}/{fid}/economy/history").json() == {"items": [], "total": 0, "page": 1,
                                                                  "page_size": 20}
        assert fapi.get(f"{A}/{fid}/economy/history?page_size=51").status_code == 422
        other = make_faction(econ_world, "Пустая")
        assert fapi.get(f"{A}/{other}/economy/operations").json()["items"] == []
        view = fapi.get(f"{A}/{fid}/economy").json()
        assert view["debts"] == {"open_count": 1, "open_total": 5}


class TestFill:

    def test_need_template_409_and_comment_422(self, fapi, econ_world):
        fid = make_faction(econ_world)
        admin()
        r = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт"})
        assert r.status_code == 409 and r.json()["detail"] == "Сначала выберите шаблон"
        econ_faction(econ_world, fid, "order", members=0)
        r = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "  x "})
        assert r.status_code == 422 and r.json()["detail"] == "Комментарий: от 3 до 500 символов"
        assert treasury(econ_world, fid) == 0

    def test_keeps_members_unless_asked_and_tops_up_the_difference(self, fapi, econ_world):
        fid = make_faction(econ_world)
        econ_faction(econ_world, fid, "order", members=50)
        fund(econ_world, core.AccountRef.faction(fid), 1000)
        admin()
        r = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "добавка", "set_members": False})
        assert r.json() == {"members_count": 50, "emitted": 500, "balance": 1500}         # 50 x 30 - 1000
        (op,) = rows(econ_world, "SELECT comment, actor_user_id FROM econ_operations "
                                 "WHERE idempotency_key LIKE 'faction_fill:%'")
        assert op == ("добавка", 1)

    def test_reclick_zero_then_new_top_up_after_spending(self, fapi, econ_world):
        fid = make_faction(econ_world)
        econ_faction(econ_world, fid, "order", members=0)
        add_rank(econ_world, fid, "Послушник", 1, reward_marks=1000)
        join(econ_world, ALPHA, fid)                                                     # debt 1000
        admin()
        first = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт", "set_members": True}).json()
        assert first == {"members_count": 300, "emitted": 9000, "balance": 9000}
        assert [d["status"] for d in debts(econ_world, ALPHA)] == ["paid"]               # settled post-commit
        assert treasury(econ_world, fid) == 8000
        again = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт", "set_members": True}).json()
        assert again["emitted"] == 1000 and treasury(econ_world, fid) == 9000             # the payout moved the key
        third = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт", "set_members": True}).json()
        assert third["emitted"] == 0
        assert world_sum(econ_world) == 0

    def test_concurrent_double_click_is_emitted_zero_not_an_error(self, fapi, econ_world, monkeypatch):
        """The 2nd of two simultaneous clicks derives the same key from a stale snapshot; if its pre-check misses
        the just-committed row, the ledger's duplicate answer means «already done» -> 200 emitted 0."""
        fid = make_faction(econ_world)
        econ_faction(econ_world, fid, "order", members=10)
        admin()
        first = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт"}).json()
        assert first["emitted"] == 300
        econ_before = int(q(econ_world, "SELECT COUNT(*) FROM econ_operations"))
        monkeypatch.setattr(fec, "_fill_key_taken", lambda db, key: False)             # the stale pre-check
        monkeypatch.setattr(fec, "treasury_account", lambda db, fid_: (None, 0))         # stale balance / posting
        r = fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт"})
        assert r.status_code == 200, r.text
        assert r.json() == {"members_count": 10, "emitted": 0, "balance": 300}
        assert int(q(econ_world, "SELECT COUNT(*) FROM econ_operations")) == econ_before
        assert treasury(econ_world, fid) == 300 and world_sum(econ_world) == 0

    def test_fill_respects_member_bounds(self, fapi, econ_world):
        fid = make_faction(econ_world)
        econ_faction(econ_world, fid, "order", members=0, members_max=100)
        admin()
        assert fapi.post(f"{A}/{fid}/economy/fill", json={"comment": "старт"}).json()["members_count"] == 100


# ============================================================================================ templates


class TestTemplates:

    def test_list_with_used_by(self, fapi, econ_world):
        econ_faction(econ_world, make_faction(econ_world), "order")
        admin()
        body = fapi.get(f"{A}/econ-templates").json()
        assert [t["code"] for t in body] == ["order", "merchants_guild", "dark_guild", "temple", "academy"]
        assert body[0]["used_by"] == 1 and body[1]["used_by"] == 0
        assert body[0]["params"]["profile_kind"] == "treasury_share"

    def test_create_update_delete(self, fapi, econ_world):
        admin()
        r = fapi.post(f"{A}/econ-templates", json={"code": "bandits_1", "name": "Разбойники <b>", "params":
                                                   {"dues_per_member": "0.3", "profile_kind": "members_purse"},
                                                   "sort_order": 9})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Разбойники <b>"                                      # plain text, stored as is
        assert set(r.json()["params"]) == set(fe.PARAM_KEYS)
        r = fapi.put(f"{A}/econ-templates/bandits_1", json={"name": "Разбойники", "params": {"norm_per_member": 5}})
        assert r.status_code == 200 and r.json()["params"]["norm_per_member"] == 5
        assert fapi.put(f"{A}/econ-templates/nope", json={"name": "X", "params": {}}).status_code == 404
        assert fapi.delete(f"{A}/econ-templates/bandits_1").status_code == 200
        assert fapi.delete(f"{A}/econ-templates/bandits_1").status_code == 404

    @pytest.mark.parametrize("body,status,detail", [
        ({"code": "Order", "name": "X"}, 422, "Код шаблона: от 2 до 32 символов — латиница в нижнем регистре, цифры и «_»"),
        ({"code": "x", "name": "X"}, 422, None),
        ({"code": "a-b", "name": "X"}, 422, None),
        ({"code": "'; drop", "name": "X"}, 422, None),
        ({"name": "X"}, 422, None),
        ({"code": "order", "name": "X"}, 409, "Шаблон с таким кодом уже есть"),
        ({"code": "ok_1", "name": "   "}, 422, "Название шаблона: от 1 до 100 символов"),
        ({"code": "ok_1", "name": "X" * 101}, 422, None),
        ({"code": "ok_1", "name": "X", "description": "d" * 501}, 422, None),
        ({"code": "ok_1", "name": "X", "params": {"bogus": 1}}, 422, "Неизвестный параметр шаблона: bogus"),
        ({"code": "ok_1", "name": "X", "params": {"qm_budget_share": 2}}, 422, None),
        ({"code": "ok_1", "name": "X", "sort_order": 100001}, 422, None),
    ])
    def test_create_validation(self, fapi, econ_world, body, status, detail):
        admin()
        r = fapi.post(f"{A}/econ-templates", json=body)
        assert r.status_code == status
        if detail:
            assert r.json()["detail"] == detail
        assert int(q(econ_world, "SELECT COUNT(*) FROM faction_econ_templates")) == 5

    def test_delete_used_template_409(self, fapi, econ_world):
        econ_faction(econ_world, make_faction(econ_world), "academy")
        admin()
        r = fapi.delete(f"{A}/econ-templates/academy")
        assert r.status_code == 409 and r.json()["detail"] == "Шаблон используется"


# ============================================================================================ quartermasters / assortment


class TestQuartermasterAdmin:

    def test_set_replace_and_list(self, fapi, econ_world):
        fid = make_faction(econ_world)
        admin()
        r = fapi.put(f"{A}/{fid}/quartermasters", json={"npc_ids": [QM_NPC, QM_NPC_2, QM_NPC]})
        assert r.status_code == 200, r.text
        assert [(x["npc_id"], x["location_name"]) for x in r.json()] == [(QM_NPC, "Рынок"), (QM_NPC_2, "Рынок")]
        r = fapi.put(f"{A}/{fid}/quartermasters", json={"npc_ids": [QM_NPC_2]})
        assert [x["npc_id"] for x in r.json()] == [QM_NPC_2]
        econ = fapi.get(f"{A}/{fid}/economy").json()
        assert econ["quartermasters"] == [{"npc_id": QM_NPC_2, "name": "Писарь", "npc_role": "scribe"}]

    def test_validation(self, fapi, econ_world):
        f1, f2 = make_faction(econ_world, "Первая"), make_faction(econ_world, "Вторая")
        admin()
        r = fapi.put(f"{A}/{f1}/quartermasters", json={"npc_ids": [ALPHA]})
        assert r.status_code == 422 and r.json()["detail"] == "Интендантом может быть только существующий NPC"
        assert fapi.put(f"{A}/{f1}/quartermasters", json={"npc_ids": [9999]}).status_code == 422
        assert fapi.put(f"{A}/{f1}/quartermasters", json={"npc_ids": list(range(50, 61))}).status_code == 422
        assert fapi.put(f"{A}/{f1}/quartermasters", json={"npc_ids": [QM_NPC]}).status_code == 200
        r = fapi.put(f"{A}/{f2}/quartermasters", json={"npc_ids": [QM_NPC]})
        assert r.status_code == 409 and r.json()["detail"] == "NPC уже интендант фракции «Первая»"
        assert fapi.put(f"{A}/999/quartermasters", json={"npc_ids": []}).status_code == 404


class TestAssortment:

    def test_create_list_update_delete(self, fapi, econ_world):
        fid = make_faction(econ_world)
        rank = add_rank(econ_world, fid, "Послушник", 1)
        admin()
        r = fapi.post(f"{A}/{fid}/qm-items", json={"item_id": ITEM_SWORD, "price": 120, "min_rank_id": rank,
                                                   "stock": 4, "restock_target": 10})
        assert r.status_code == 200, r.text
        row = r.json()
        assert (row["off_market"], row["group"], row["min_rank_name"], row["item"]["name"]) == \
            (False, "arms", "Послушник", "Меч Зари")
        r = fapi.put(f"{A}/qm-items/{row['id']}", json={"item_id": ITEM_SWORD, "price": 99, "stock": 0,
                                                        "is_active": False})
        assert r.status_code == 200 and (r.json()["price"], r.json()["is_active"], r.json()["min_rank_id"]) == \
            (99, False, None)
        assert [x["id"] for x in fapi.get(f"{A}/{fid}/qm-items").json()] == [row["id"]]
        assert fapi.delete(f"{A}/qm-items/{row['id']}").status_code == 200
        assert fapi.delete(f"{A}/qm-items/{row['id']}").status_code == 404

    @pytest.mark.parametrize("body,status,detail", [
        ({"item_id": ITEM_SCROLL, "price": 5, "restock_target": 1}, 422,
         "Этот предмет не продаётся на рынке — запас пополняет только администратор"),
        ({"item_id": 9999, "price": 5}, 422, "Предмет не найден"),
        ({"item_id": ITEM_SWORD, "price": 0}, 422, "Цена: от 1 до 10000000"),
        ({"item_id": ITEM_SWORD, "price": 10_000_001}, 422, None),
        ({"item_id": ITEM_SWORD, "price": 5, "stock": -1}, 422, "Запас: от 0 до 100000"),
        ({"item_id": ITEM_SWORD, "price": 5, "restock_target": 100_001}, 422, None),
        ({"item_id": ITEM_SWORD, "price": 5, "sort_order": 10 ** 6}, 422, None),
        ({"item_id": ITEM_SWORD, "price": "5'; --"}, 422, None),
    ])
    def test_validation(self, fapi, econ_world, body, status, detail):
        fid = make_faction(econ_world)
        admin()
        r = fapi.post(f"{A}/{fid}/qm-items", json=body)
        assert r.status_code == status
        if detail:
            assert r.json()["detail"] == detail

    def test_off_market_with_zero_target_is_fine_and_duplicates_409(self, fapi, econ_world):
        fid = make_faction(econ_world)
        admin()
        r = fapi.post(f"{A}/{fid}/qm-items", json={"item_id": ITEM_SCROLL, "price": 5, "stock": 7})
        assert r.status_code == 200 and r.json()["off_market"] is True
        r = fapi.post(f"{A}/{fid}/qm-items", json={"item_id": ITEM_SCROLL, "price": 6})
        assert r.status_code == 409 and r.json()["detail"] == "Этот предмет уже есть в ассортименте"
        sword = fapi.post(f"{A}/{fid}/qm-items", json={"item_id": ITEM_SWORD, "price": 6}).json()["id"]
        r = fapi.put(f"{A}/qm-items/{sword}", json={"item_id": ITEM_SCROLL, "price": 6})
        assert r.status_code == 409

    def test_foreign_rank_422_and_rank_delete_guard(self, fapi, econ_world):
        f1, f2 = make_faction(econ_world, "Первая"), make_faction(econ_world, "Вторая")
        foreign = add_rank(econ_world, f2, "Чужой", 1)
        own = add_rank(econ_world, f1, "Свой", 1)
        admin()
        r = fapi.post(f"{A}/{f1}/qm-items", json={"item_id": ITEM_SWORD, "price": 5, "min_rank_id": foreign})
        assert r.status_code == 422 and r.json()["detail"] == "Звание не из этой фракции"
        assert fapi.post(f"{A}/{f1}/qm-items", json={"item_id": ITEM_SWORD, "price": 5,
                                                     "min_rank_id": own}).status_code == 200
        r = fapi.delete(f"{A}/ranks/{own}")
        assert r.status_code == 409 and r.json()["detail"] == "Звание используется в ассортименте интенданта"


# ============================================================================================ faction delete guards


class TestDeleteGuards:

    def test_treasury_money_blocks(self, fapi, econ_world):
        fid = make_faction(econ_world)
        fund(econ_world, core.AccountRef.faction(fid), 5)
        admin()
        r = fapi.delete(f"{A}/{fid}")
        assert r.status_code == 409 and r.json()["detail"] == "В казне фракции остались марки — сначала обнулите казну"

    def test_debt_row_blocks(self, fapi, econ_world):
        fid = make_faction(econ_world)
        exec_(econ_world, "INSERT INTO faction_debts (character_id, faction_id, source, source_key, amount, paid, "
                          "status, unpaid_notified, created_at) VALUES (1, :fid, 'refund', 'refund:p77', 5, 5, "
                          "'paid', 0, :t)", fid=fid, t=datetime.utcnow())
        admin()
        r = fapi.delete(f"{A}/{fid}")
        assert r.status_code == 409 and r.json()["detail"] == "У фракции есть долги перед игроками — её можно только скрыть"

    def test_clean_delete_removes_econ_rows_and_deactivates_the_account(self, fapi, econ_world):
        fid = make_faction(econ_world)
        econ_faction(econ_world, fid, "order")
        fund(econ_world, core.AccountRef.faction(fid), 5)
        from tests.faction_world import drain
        drain(econ_world, core.AccountRef.faction(fid), 5)
        bind_qm(econ_world, fid)
        qm_item(econ_world, fid)
        admin()
        assert fapi.delete(f"{A}/{fid}").status_code == 200
        for table in ("faction_economy", "faction_qm_items", "faction_quartermasters"):
            assert int(q(econ_world, f"SELECT COUNT(*) FROM {table}")) == 0, table
        assert int(q(econ_world, "SELECT is_active FROM econ_accounts WHERE kind = 'faction_treasury'")) == 0
        assert world_sum(econ_world) == 0


# ============================================================================================ settings / ranks / summary


class TestSettingsAndRanks:
    BASE = {"warning_days": 3, "rejoin_cooldown_days": 7, "leave_burn_pct": 50, "hostile_penalty_pct": 50,
            "reapply_cooldown_hours": 24}

    def test_settings_defaults_and_update(self, fapi, econ_world):
        admin()
        body = fapi.get(f"{A}/settings").json()
        assert {k: body[k] for k in ("donation_marks_per_point", "donation_points_daily_cap", "econ_enabled",
                                     "econ_purse_share_pct", "econ_treasury_share_pct", "members_leave_pct",
                                     "members_grow_pct", "qm_take_share_pct")} == \
            {"donation_marks_per_point": 10, "donation_points_daily_cap": 50, "econ_enabled": True,
             "econ_purse_share_pct": 2, "econ_treasury_share_pct": 1, "members_leave_pct": 5, "members_grow_pct": 1,
             "qm_take_share_pct": 5}
        r = fapi.put(f"{A}/settings", json={**self.BASE, "donation_marks_per_point": 20, "econ_enabled": False})
        assert r.status_code == 200 and r.json()["donation_marks_per_point"] == 20 and not r.json()["econ_enabled"]
        r = fapi.put(f"{A}/settings", json=self.BASE)                                    # old client: kept
        assert r.json()["donation_marks_per_point"] == 20 and r.json()["econ_enabled"] is False

    @pytest.mark.parametrize("field,value", [
        ("donation_marks_per_point", 0), ("donation_marks_per_point", 10001), ("donation_points_daily_cap", -1),
        ("econ_purse_share_pct", 21), ("econ_treasury_share_pct", 21), ("members_leave_pct", 51),
        ("members_grow_pct", 11), ("qm_take_share_pct", 51),
    ])
    def test_settings_bounds(self, fapi, econ_world, field, value):
        admin()
        r = fapi.put(f"{A}/settings", json={**self.BASE, field: value})
        assert r.status_code == 422 and "от" in r.json()["detail"]

    def test_settings_need_permission(self, fapi, econ_world):
        as_user(2, "moderator", ECON)
        assert fapi.put(f"{A}/settings", json={**self.BASE, "econ_enabled": False}).status_code == 403

    @pytest.mark.parametrize("field,value,ok", [
        ("reward_marks", 0, True), ("reward_marks", 1_000_000, True), ("reward_marks", 1_000_001, False),
        ("reward_marks", -1, False), ("qm_discount_pct", 50, True), ("qm_discount_pct", 51, False),
        ("qm_discount_pct", -1, False),
    ])
    def test_rank_fields(self, fapi, econ_world, field, value, ok):
        fid = make_faction(econ_world)
        admin()
        r = fapi.post(f"{A}/{fid}/ranks", json={"name": "Ранг", field: value})
        assert (r.status_code == 200) is ok, r.text
        if ok:
            assert int(q(econ_world, f"SELECT {field} FROM faction_ranks")) == value

    def test_rank_update_omitting_fields_keeps_them(self, fapi, econ_world):
        fid = make_faction(econ_world)
        rank = add_rank(econ_world, fid, "Ранг", 1, reward_marks=70, qm_discount_pct=5)
        admin()
        assert fapi.put(f"{A}/ranks/{rank}", json={"name": "Ранг 2"}).status_code == 200
        assert rows(econ_world, "SELECT reward_marks, qm_discount_pct FROM faction_ranks") == [(70, 5)]

    def test_ledger_summary_has_factions_total(self, econ_world):
        for ddl in ("CREATE TABLE IF NOT EXISTS auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER, "
                    "status VARCHAR(20), current_bidder_id INTEGER)",
                    "CREATE TABLE IF NOT EXISTS auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER)"):
            exec_(econ_world, ddl)
        for name in ("Первая", "Вторая"):
            fund(econ_world, core.AccountRef.faction(make_faction(econ_world, name)), 40)
        db = econ_world()
        try:
            summary = economy_crud.get_summary(db)
        finally:
            db.close()
        assert summary["totals"]["factions"] == 80
        assert summary["invariant"]["ledger_sum"] == 0
        assert core.KIND_FACTION_TREASURY in economy_crud.EMISSION_TARGET_KINDS


# ============================================================================================ secrecy (§3.9)


class TestSecrecy:

    def _world(self, f):
        public = make_faction(f, "Открытая")
        hidden = make_faction(f, "Тайная", secret=True)
        for fid in (public, hidden):
            add_rank(f, fid, "Ранг", 1)
            econ_faction(f, fid, "order", members=100)
            fund(f, core.AccountRef.faction(fid), 6000)                  # wealth 100 -> «Процветает»
        return public, hidden

    def test_catalog_and_public(self, fapi, econ_world):
        public, hidden = self._world(econ_world)
        thriving = {"state": "thriving", "label": "Процветает"}
        as_user(USER_ALPHA)
        items = {i["id"]: i for i in fapi.get(f"{P}/factions/catalog?character_id={ALPHA}").json()}
        assert items[public]["wealth"] == thriving and items[hidden]["wealth"] is None
        join(econ_world, ALPHA, hidden)
        items = {i["id"]: i for i in fapi.get(f"{P}/factions/catalog?character_id={ALPHA}").json()}
        assert items[hidden]["wealth"] == thriving
        items = {i["id"]: i for i in fapi.get(f"{P}/factions/catalog").json()}            # no character
        assert items[hidden]["wealth"] is None
        assert fapi.get(f"{P}/factions/{public}/public").json()["wealth"] == thriving
        assert fapi.get(f"{P}/factions/{hidden}/public").json()["wealth"] is None
        for body in (items[public], items[hidden]):                                    # words only, never numbers
            assert "balance" not in json.dumps(body) and "members_count" not in body

    def test_private_view_words_for_active_only(self, fapi, econ_world):
        public, hidden = self._world(econ_world)
        join(econ_world, ALPHA, public)
        join(econ_world, ALPHA, hidden)
        from tests.faction_world import run_flow
        import faction_crud
        run_flow(econ_world, faction_crud.leave, ALPHA, hidden)
        as_user(USER_ALPHA)
        view = {m["faction"]["id"]: m for m in fapi.get(f"{P}/{ALPHA}/factions").json()["memberships"]}
        assert view[public]["wealth"]["label"] == "Процветает" and view[hidden]["wealth"] is None
        assert view[public]["donation"]["enabled"] is True and view[hidden]["donation"] is None

    def test_other_players_debts_and_donations_are_not_readable(self, fapi, econ_world):
        public, _hidden = self._world(econ_world)
        add_rank(econ_world, public, "Ранг II", 2, reward_marks=10)
        join(econ_world, BETA, public)
        as_user(USER_ALPHA)
        r = fapi.get(f"{P}/{BETA}/factions")
        assert r.status_code == 403 and "debt" not in r.text
        assert fapi.get(f"{A}/characters/{BETA}").status_code == 403
        assert fapi.get(f"{A}/{public}/debts").status_code == 403
        r = fapi.post(f"{P}/{BETA}/factions/{public}/donate", json={"amount": 1, "request_id": "req-00001"})
        assert r.status_code == 403


# ============================================================================================ migration 046


class FakeMySQL046:
    """information_schema + the template / backfill statements of migration 046, emulated; DDL recorded."""

    def __init__(self, tables=("factions", "faction_ranks", "faction_settings", "characters")):
        self.tables = set(tables)
        self.columns = set()
        self.templates = {}
        self.backfills = 0
        self.statements = []

    def execute(self, clause, params=None):
        sql = " ".join(str(clause).split())
        result = MagicMock()
        if "information_schema.columns" in sql:
            result.scalar.return_value = int((params["t"], params["c"]) in self.columns)
        elif "information_schema.tables" in sql:
            result.scalar.return_value = int(params["t"] in self.tables)
        elif sql.startswith("SELECT COUNT(*) FROM faction_econ_templates"):
            result.scalar.return_value = int(params["c"] in self.templates)
        elif sql.startswith("INSERT INTO faction_econ_templates"):
            self.templates[params["c"]] = dict(params)
        elif sql.startswith("INSERT INTO faction_economy"):
            assert "LEFT JOIN faction_economy" in sql and "IS NULL" in sql          # idempotent backfill
            self.backfills += 1
        else:
            raise AssertionError(f"unexpected bind SQL: {sql}")
        return result

    def op_execute(self, sql):
        sql = str(sql)
        self.statements.append(sql)
        words = sql.split()
        if sql.startswith("CREATE TABLE"):
            assert words[2] not in self.tables
            self.tables.add(words[2])
        elif sql.startswith("DROP TABLE"):
            self.tables.remove(words[2])
            if words[2] == "faction_econ_templates":
                self.templates.clear()
        elif sql.startswith("ALTER TABLE") and words[3:5] == ["ADD", "COLUMN"]:
            assert (words[2], words[5]) not in self.columns
            self.columns.add((words[2], words[5]))
        elif sql.startswith("ALTER TABLE") and words[3:5] == ["DROP", "COLUMN"]:
            self.columns.remove((words[2], words[5]))
        else:
            raise AssertionError(f"unexpected DDL: {sql}")


NEW_TABLES = {"faction_econ_templates", "faction_economy", "faction_econ_history", "faction_debts",
              "faction_donation_days", "faction_quartermasters", "faction_qm_items", "faction_qm_purchases"}


@pytest.fixture
def mig046(monkeypatch):
    mig = load_migration_046()
    db = FakeMySQL046()
    monkeypatch.setattr(mig.op, "get_bind", lambda: db, raising=False)
    monkeypatch.setattr(mig.op, "execute", db.op_execute, raising=False)
    return mig, db


class TestMigration046:

    def test_revision(self):
        mig = load_migration_046()
        assert mig.revision == "046_faction_economy" and len(mig.revision) <= 32
        assert mig.down_revision == "045_factions_core"

    def test_upgrade(self, mig046):
        mig, db = mig046
        mig.upgrade()
        assert NEW_TABLES <= db.tables
        assert db.columns == {(t, c) for t, c, _d in mig._COLUMNS}
        assert {c for _t, c in db.columns} >= {"reward_marks", "qm_discount_pct", "donation_marks_per_point",
                                              "econ_enabled", "qm_take_share_pct"}
        assert set(db.templates) == {"order", "merchants_guild", "dark_guild", "temple", "academy"}
        order = db.templates["order"]
        assert order["n"] == "Орден" and json.loads(order["p"])["profile_kind"] == "treasury_share"
        for _code, row in db.templates.items():                         # the stored JSON passes the validator
            fe.validate_params(json.loads(row["p"]), partial=False)
        assert db.backfills == 1

    def test_rerun_is_a_noop(self, mig046):
        mig, db = mig046
        mig.upgrade()
        before = len(db.statements)
        mig.upgrade()
        assert len(db.statements) == before and len(db.templates) == 5

    def test_downgrade_then_upgrade(self, mig046):
        mig, db = mig046
        mig.upgrade()
        mig.downgrade()
        assert not (NEW_TABLES & db.tables) and db.columns == set()
        drops = [s.split()[2] for s in db.statements if s.startswith("DROP")]
        assert drops == [name for name, _ddl in reversed(mig._TABLES)]
        assert drops.index("faction_qm_purchases") < drops.index("faction_qm_items") < \
            drops.index("faction_econ_templates")
        mig.downgrade()
        mig.upgrade()
        assert NEW_TABLES <= db.tables and len(db.templates) == 5

    def test_ddl_matches_the_models(self):
        mig = load_migration_046()
        ddl = dict(mig._TABLES)
        assert set(ddl) == NEW_TABLES
        by_table = {m.__tablename__: m for m in (
            models.FactionEconTemplate, models.FactionEconomy, models.FactionEconHistory, models.FactionDebt,
            models.FactionDonationDay, models.FactionQuartermaster, models.FactionQmItem, models.FactionQmPurchase)}
        later = {(t, c) for t, c, _ddl in load_migration_047()._COLUMNS}      # FEAT-207 adds these columns
        for name, model in by_table.items():
            assert "ENUM" not in ddl[name].upper().replace("INNODB", "")
            for column in model.__table__.columns.keys():
                if (name, column) in later:
                    continue
                assert f" {column} " in ddl[name], (name, column)
        added = {(t, c) for t, c, _d in mig._COLUMNS}
        for table, model in (("faction_ranks", models.FactionRank), ("faction_settings", models.FactionSettings)):
            for column in ("reward_marks", "qm_discount_pct") if table == "faction_ranks" else (
                    "donation_marks_per_point", "donation_points_daily_cap", "econ_enabled", "econ_purse_share_pct",
                    "econ_treasury_share_pct", "members_leave_pct", "members_grow_pct", "qm_take_share_pct"):
                assert (table, column) in added and column in model.__table__.columns
        # FK columns carry their own index (MySQL gotcha); cascades as designed
        for name, column in (("faction_economy", "template_code"), ("faction_debts", "character_id"),
                             ("faction_donation_days", "faction_id"), ("faction_quartermasters", "faction_id"),
                             ("faction_qm_items", "min_rank_id"), ("faction_qm_purchases", "qm_item_id"),
                             ("faction_qm_purchases", "character_id"), ("faction_econ_history", "faction_id")):
            assert f"({column})" in ddl[name] or f"({column}," in ddl[name], (name, column)
        assert "UNIQUE KEY uq_faction_debt_source (source_key)" in ddl["faction_debts"]
        assert "UNIQUE KEY uq_faction_qm_purchase_key (op_key)" in ddl["faction_qm_purchases"]
        assert "UNIQUE KEY uq_faction_econ_hist_run (run_id, faction_id)" in ddl["faction_econ_history"]
        assert "ON DELETE RESTRICT" in ddl["faction_qm_items"] and "ON DELETE SET NULL" in ddl["faction_qm_purchases"]
        assert "ON DELETE RESTRICT" in ddl["faction_economy"]
        assert ddl["faction_debts"].count("ON DELETE CASCADE") == 2
