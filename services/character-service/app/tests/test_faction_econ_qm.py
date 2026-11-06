"""FEAT-206 QA: the faction quartermaster («Интендант»). features/FEAT-206 §3.8, §3.9.

Probe ``none`` / ``silent`` / ``open`` (secret faction secrecy, NPC role label), the view gate (ownership, NPC /
binding, dead, location, secret non-member 403 with the exact text and no faction data), the buy (rank gate, discount,
stock, idempotency, insufficient funds, dialogue gate, activity lock, validation), the delivery outbox (success, definite
failure -> backoff -> retry -> auto-refund after 5 attempts, refund-as-debt when the treasury cannot pay, uncertain
never retried, stale claims, no transaction open during the HTTP call) and the admin retry / refund. World invariant
after every money flow.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

import econ_core as core
import faction_crud
import faction_econ_crud as fec
import faction_qm_crud as fqm
import faction_rewards
import locations_client
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, GUARD, ITEM_SCROLL, ITEM_SHIELD, ITEM_SWORD, MERCHANT, QM_NPC, QM_NPC_2, USER_ALPHA, USER_BETA,
    USER_GAMMA, add_rank, as_user, bind_qm, cash, connect_error, debts, econ_world, exec_, fapi, fund, fw, gate_open,
    join, make_faction, notice_texts, ops, q, qm_item, read_timeout, rep_world, rows, run_flow, treasury, world_sum,
)

P = "/characters/factions/quartermaster/npc"
A = "/characters/admin/factions"


def probe(fapi, npc=QM_NPC, cid=ALPHA, user=USER_ALPHA):
    as_user(user)
    return fapi.get(f"{P}/{npc}/probe?character_id={cid}")


def view(fapi, npc=QM_NPC, cid=ALPHA, user=USER_ALPHA):
    as_user(user)
    return fapi.get(f"{P}/{npc}?character_id={cid}")


def buy(fapi, qid, qty=1, rid="buy-00001", npc=QM_NPC, cid=ALPHA, user=USER_ALPHA):
    as_user(user)
    return fapi.post(f"{P}/{npc}/buy", json={"character_id": cid, "qm_item_id": qid, "quantity": qty,
                                             "request_id": rid})


def purchases(f):
    keys = ("id", "character_id", "status", "attempts", "last_error", "quantity", "price_total", "qm_item_id")
    return [dict(zip(keys, r)) for r in rows(f, f"SELECT {', '.join(keys)} FROM faction_qm_purchases ORDER BY id")]


def qm_stock(f, qid):
    return int(q(f, "SELECT stock FROM faction_qm_items WHERE id = :i", i=qid))


@pytest.fixture
def shop(econ_world, gate_open):
    """Public faction «Орден Зари» (ranks I / II with discounts 0 / 10), quartermaster NPC 53 @100, sword row
    (price 50, stock 3, no min rank) and shield row (price 40, min rank II); Alpha is a member with 1000 marks."""
    f = econ_world
    fid = make_faction(f)
    r1 = add_rank(f, fid, "Послушник", 1)
    r2 = add_rank(f, fid, "Рыцарь", 2, min_points=100, qm_discount_pct=10)
    bind_qm(f, fid)
    sword = qm_item(f, fid, ITEM_SWORD, price=50, stock=3, sort=1)
    shield = qm_item(f, fid, ITEM_SHIELD, price=40, stock=5, min_rank=r2, sort=2)
    join(f, ALPHA, fid)
    fund(f, core.AccountRef.character(ALPHA), 1000)
    f.ids = {"fid": fid, "r1": r1, "r2": r2, "sword": sword, "shield": shield}
    return f


@pytest.fixture
def secret(econ_world, gate_open):
    f = econ_world
    fid = make_faction(f, "Тень", secret=True)
    add_rank(f, fid, "Тень I", 1)
    bind_qm(f, fid)
    qid = qm_item(f, fid, ITEM_SWORD, price=50, stock=3)
    fund(f, core.AccountRef.character(ALPHA), 1000)
    f.ids = {"fid": fid, "sword": qid}
    return f


def promote(f, fid, cid=ALPHA, points=100):
    exec_(f, "UPDATE faction_members SET points = :p WHERE character_id = :c AND faction_id = :fid",
          p=points, c=cid, fid=fid)
    run_flow(f, faction_crud.recheck_ranks, cid, datetime.utcnow())


# ============================================================================================ probe


class TestProbe:

    def test_unbound_npc_is_none(self, fapi, shop):
        assert probe(fapi, npc=MERCHANT).json() == {"state": "none"}
        assert probe(fapi, npc=999).json() == {"state": "none"}

    def test_public_faction_open_for_everybody(self, fapi, shop):
        assert probe(fapi).json() == {"state": "open"}
        assert probe(fapi, cid=GAMMA, user=USER_GAMMA).json() == {"state": "open"}    # no location check

    def test_secret_states(self, fapi, secret):
        assert probe(fapi).json() == {"state": "silent"}
        exec_(secret, "UPDATE characters SET npc_role = 'scribe' WHERE id = :n", n=QM_NPC)
        assert probe(fapi).json() == {"state": "none"}                    # neutral role: no button at all
        join(secret, ALPHA, secret.ids["fid"])
        assert probe(fapi).json() == {"state": "open"}
        run_flow(secret, faction_crud.leave, ALPHA, secret.ids["fid"])
        exec_(secret, "UPDATE characters SET npc_role = 'quartermaster' WHERE id = :n", n=QM_NPC)
        assert probe(fapi).json() == {"state": "silent"}                  # former member = non-member

    def test_not_own_character(self, fapi, shop):
        r = probe(fapi, cid=BETA)
        assert r.status_code == 403 and r.json()["detail"] == "Это не ваш персонаж"
        assert probe(fapi, cid=MERCHANT).status_code == 403
        assert probe(fapi, cid=999).status_code == 404


# ============================================================================================ view


class TestView:

    def test_member_view(self, fapi, shop):
        r = view(fapi)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["npc"] == {"id": QM_NPC, "name": "Безымянный"}
        assert body["faction"] == {"id": shop.ids["fid"], "name": "Орден Зари", "emblem_url": None}
        assert body["member"] is True and body["balance"] == 1000
        assert body["rank"] == {"id": shop.ids["r1"], "name": "Послушник", "discount_pct": 0}
        sword, shield = body["items"]
        assert (sword["qm_item_id"], sword["item"]["name"], sword["price"], sword["final_price"], sword["stock"],
                sword["min_rank"], sword["locked_reason"]) == (shop.ids["sword"], "Меч Зари", 50, 50, 3, None, None)
        assert shield["locked_reason"] == "Нужно звание «Рыцарь»"
        assert shield["min_rank"] == {"id": shop.ids["r2"], "name": "Рыцарь"}

    def test_discount_by_rank(self, fapi, shop):
        promote(shop, shop.ids["fid"])
        body = view(fapi).json()
        assert body["rank"]["discount_pct"] == 10
        assert [(i["price"], i["final_price"], i["locked_reason"]) for i in body["items"]] == \
            [(50, 45, None), (40, 36, None)]

    def test_public_non_member_sees_locked_items(self, fapi, shop):
        body = view(fapi, cid=BETA, user=USER_BETA).json()
        assert body["member"] is False and body["rank"] is None
        assert {i["locked_reason"] for i in body["items"]} == {"Только для членов фракции «Орден Зари»"}

    def test_secret_non_member_gets_silence_and_nothing_else(self, fapi, secret):
        r = view(fapi)
        assert r.status_code == 403 and r.json() == {"detail": "Этот человек с вами не разговаривает"}
        assert "Тень" not in r.text

    def test_secret_silence_comes_before_dead_and_location(self, fapi, secret):
        exec_(secret, "UPDATE characters SET npc_status = 'dead' WHERE id = :n", n=QM_NPC)
        for r in (view(fapi), view(fapi, cid=GAMMA, user=USER_GAMMA)):           # dead; Гамма @200 elsewhere
            assert r.status_code == 403 and r.json() == {"detail": "Этот человек с вами не разговаривает"}

    def test_secret_neutral_role_answers_exactly_like_a_plain_npc(self, fapi, secret):
        exec_(secret, "UPDATE characters SET npc_role = 'scribe' WHERE id = :n", n=QM_NPC)
        plain = view(fapi, npc=MERCHANT)
        assert (plain.status_code, plain.json()) == (404, {"detail": "Интендант не найден"})
        for r in (view(fapi), view(fapi, cid=GAMMA, user=USER_GAMMA)):           # same place / elsewhere
            assert (r.status_code, r.json()) == (plain.status_code, plain.json())
        exec_(secret, "UPDATE characters SET npc_status = 'dead' WHERE id = :n", n=QM_NPC)
        assert (view(fapi).status_code, view(fapi).json()) == (plain.status_code, plain.json())
        exec_(secret, "UPDATE characters SET npc_status = 'alive' WHERE id = :n", n=QM_NPC)
        join(secret, ALPHA, secret.ids["fid"])
        assert view(fapi).status_code == 200                                     # a member still sees the shop

    def test_secret_refusal_mirrors_the_probe(self):
        from types import SimpleNamespace
        silent = fqm.secret_refusal(SimpleNamespace(npc_role="quartermaster"))
        plain = fqm.secret_refusal(SimpleNamespace(npc_role=None))
        assert (silent.status_code, silent.detail) == (403, "Этот человек с вами не разговаривает")
        assert (plain.status_code, plain.detail) == (404, "Интендант не найден")

    def test_inactive_hidden_zero_stock_shown(self, fapi, shop):
        exec_(shop, "UPDATE faction_qm_items SET is_active = 0 WHERE id = :i", i=shop.ids["shield"])
        exec_(shop, "UPDATE faction_qm_items SET stock = 0 WHERE id = :i", i=shop.ids["sword"])
        assert [(i["qm_item_id"], i["stock"]) for i in view(fapi).json()["items"]] == [(shop.ids["sword"], 0)]

    def test_gate_errors(self, fapi, shop):
        r = view(fapi, cid=GAMMA, user=USER_GAMMA)                            # Гамма @200
        assert r.status_code == 400 and r.json()["detail"] == "Вы не рядом с интендантом"
        assert view(fapi, npc=MERCHANT).status_code == 404                    # NPC, not bound
        assert view(fapi, npc=BETA).status_code == 404                        # a player, not an NPC
        assert view(fapi, npc=999).json()["detail"] == "Интендант не найден"
        exec_(shop, "UPDATE characters SET npc_status = 'dead' WHERE id = :n", n=QM_NPC)
        r = view(fapi)
        assert r.status_code == 409 and r.json()["detail"] == "Интендант мёртв"
        assert view(fapi, cid=BETA).status_code == 403                        # not own

    def test_view_needs_auth(self, fapi, shop):
        from auth_http import get_current_user_via_http
        from main import app
        app.dependency_overrides.pop(get_current_user_via_http, None)
        assert fapi.get(f"{P}/{QM_NPC}?character_id={ALPHA}").status_code == 401


# ============================================================================================ buy


class TestBuy:

    def test_happy_path(self, fapi, shop, gate_open):
        promote(shop, shop.ids["fid"])
        r = buy(fapi, shop.ids["sword"], qty=2)
        assert r.status_code == 200, r.text
        assert r.json() == {"purchase_id": 1, "delivered": True, "price_total": 90, "new_balance": 910,
                            "message": "Покупка выполнена — предмет в инвентаре"}
        assert qm_stock(shop, shop.ids["sword"]) == 1
        assert treasury(shop, shop.ids["fid"]) == 90 and cash(shop, ALPHA) == 910
        assert shop.http.calls == [(faction_rewards.inventory_url(ALPHA), {"item_id": ITEM_SWORD, "quantity": 2})]
        assert [(p["status"], p["attempts"]) for p in purchases(shop)] == [("done", 1)]
        (op,) = rows(shop, "SELECT idempotency_key, location_id FROM econ_operations WHERE op_type = 'faction_qm_sale'")
        assert op[0] == "faction_qm:c1:buy-00001" and int(op[1]) == 100
        assert gate_open.calls == [(ALPHA, 100, QM_NPC)]
        assert world_sum(shop) == 0

    def test_same_request_id_409_no_double_charge(self, fapi, shop):
        assert buy(fapi, shop.ids["sword"]).status_code == 200
        again = buy(fapi, shop.ids["sword"])
        assert again.status_code == 409 and again.json()["detail"] == "Покупка уже выполнена"
        assert cash(shop, ALPHA) == 950 and qm_stock(shop, shop.ids["sword"]) == 2 and len(purchases(shop)) == 1
        assert len(shop.http.calls) == 1

    def test_stock_exhausted(self, fapi, shop):
        assert buy(fapi, shop.ids["sword"], qty=2, rid="buy-00001").status_code == 200
        r = buy(fapi, shop.ids["sword"], qty=2, rid="buy-00002")
        assert r.status_code == 409 and r.json()["detail"] == "Недостаточно товара у интенданта"
        assert qm_stock(shop, shop.ids["sword"]) == 1 and cash(shop, ALPHA) == 900
        assert buy(fapi, shop.ids["sword"], qty=1, rid="buy-00003").status_code == 200
        assert qm_stock(shop, shop.ids["sword"]) == 0 and world_sum(shop) == 0

    def test_insufficient_funds_rolls_back_the_stock(self, fapi, shop):
        exec_(shop, "UPDATE faction_qm_items SET price = 600 WHERE id = :i", i=shop.ids["sword"])
        r = buy(fapi, shop.ids["sword"], qty=2)
        assert r.status_code == 400 and r.json()["detail"] == "Недостаточно марок"
        assert qm_stock(shop, shop.ids["sword"]) == 3 and purchases(shop) == [] and cash(shop, ALPHA) == 1000

    def test_rank_gate(self, fapi, shop):
        r = buy(fapi, shop.ids["shield"])
        assert r.status_code == 403 and r.json()["detail"] == "Нужно звание «Рыцарь»"
        promote(shop, shop.ids["fid"])
        r = buy(fapi, shop.ids["shield"], qty=3, rid="buy-00002")
        assert r.status_code == 200 and r.json()["price_total"] == 3 * 36

    def test_non_members(self, fapi, shop):
        fund(shop, core.AccountRef.character(BETA), 500)
        r = buy(fapi, shop.ids["sword"], cid=BETA, user=USER_BETA)
        assert r.status_code == 403 and r.json()["detail"] == "Только для членов фракции «Орден Зари»"
        hidden = make_faction(shop, "Тень", secret=True)
        bind_qm(shop, hidden, npc_id=QM_NPC_2)
        row = qm_item(shop, hidden, ITEM_SWORD, price=1, stock=3)
        r = buy(fapi, row, npc=QM_NPC_2)
        assert r.status_code == 403 and r.json()["detail"] == "Этот человек с вами не разговаривает"
        assert cash(shop, BETA) == 500 and cash(shop, ALPHA) == 1000

    def test_secret_neutral_role_buy_answers_like_a_plain_npc(self, fapi, secret, gate_open):
        exec_(secret, "UPDATE characters SET npc_role = 'scribe' WHERE id = :n", n=QM_NPC)
        plain = buy(fapi, secret.ids["sword"], npc=MERCHANT)
        assert (plain.status_code, plain.json()) == (404, {"detail": "Интендант не найден"})
        r = buy(fapi, secret.ids["sword"], rid="buy-00002")
        assert (r.status_code, r.json()) == (plain.status_code, plain.json())
        exec_(secret, "UPDATE characters SET current_location_id = 200, dungeon_session_id = 7 WHERE id = :c", c=ALPHA)
        r = buy(fapi, secret.ids["sword"], rid="buy-00003")                    # elsewhere + activity lock
        assert (r.status_code, r.json()) == (plain.status_code, plain.json())
        assert gate_open.calls == [] and purchases(secret) == [] and cash(secret, ALPHA) == 1000

    def test_foreign_or_inactive_row(self, fapi, shop):
        other = make_faction(shop, "Чужие")
        foreign = qm_item(shop, other, ITEM_SWORD, price=1, stock=9)
        r = buy(fapi, foreign)
        assert r.status_code == 404 and r.json()["detail"] == "Такого товара у интенданта нет"
        exec_(shop, "UPDATE faction_qm_items SET is_active = 0 WHERE id = :i", i=shop.ids["sword"])
        assert buy(fapi, shop.ids["sword"], rid="buy-00002").status_code == 404
        assert buy(fapi, 99999, rid="buy-00003").status_code == 404
        assert cash(shop, ALPHA) == 1000

    def test_dialogue_gate(self, fapi, shop, gate_open, monkeypatch):
        gate_open.answer = False
        r = buy(fapi, shop.ids["sword"])
        assert r.status_code == 403 and r.json()["detail"] == fqm.MSG_GATE_CLOSED

        async def down(*_a):
            raise locations_client.GateUnavailable("down")

        monkeypatch.setattr(locations_client, "check_npc_gate", down)
        r = buy(fapi, shop.ids["sword"], rid="buy-00002")
        assert r.status_code == 503 and r.json()["detail"] == fqm.MSG_GATE_UNAVAILABLE
        assert cash(shop, ALPHA) == 1000 and purchases(shop) == []

    def test_gate_checked_before_the_dialogue_call(self, fapi, shop, gate_open):
        exec_(shop, "UPDATE characters SET current_location_id = 200 WHERE id = :c", c=ALPHA)
        assert buy(fapi, shop.ids["sword"]).status_code == 400
        exec_(shop, "UPDATE characters SET current_location_id = 100, dungeon_session_id = 7 WHERE id = :c", c=ALPHA)
        assert buy(fapi, shop.ids["sword"]).status_code == 409             # activity lock (buy only)
        assert view(fapi).status_code == 200                               # viewing is fine
        assert gate_open.calls == [] and purchases(shop) == []

    @pytest.mark.parametrize("patch", [
        {"quantity": 0}, {"quantity": 100}, {"quantity": "1"}, {"quantity": True}, {"qm_item_id": 0},
        {"character_id": "1"}, {"request_id": "x"}, {"request_id": "1' OR '1'='1"}, {"request_id": "<b>buy</b>-1"},
    ])
    def test_validation_422(self, fapi, shop, patch):
        body = {"character_id": ALPHA, "qm_item_id": shop.ids["sword"], "quantity": 1, "request_id": "buy-00001"}
        body.update(patch)
        as_user(USER_ALPHA)
        assert fapi.post(f"{P}/{QM_NPC}/buy", json=body).status_code == 422
        assert cash(shop, ALPHA) == 1000

    def test_buy_settles_open_debts_of_the_faction(self, fapi, shop):
        add_rank(shop, shop.ids["fid"], "Рыцарь II", 3, min_points=100, reward_marks=40)
        promote(shop, shop.ids["fid"])                                     # debt 40, treasury empty
        assert [d["status"] for d in debts(shop, ALPHA)] == ["open"]
        r = buy(fapi, shop.ids["sword"])                                  # rank «Рыцарь II»: no discount
        assert r.status_code == 200 and r.json()["price_total"] == 50     # 50 into the treasury -> pays 40
        assert [(d["paid"], d["status"]) for d in debts(shop, ALPHA)] == [(40, "paid")]
        assert treasury(shop, shop.ids["fid"]) == 10 and cash(shop, ALPHA) == 1000 - 50 + 40
        assert world_sum(shop) == 0

    def test_lock_order_purchase_row_before_ledger_op(self, fapi, shop, monkeypatch):
        """Review #1: the purchase row (faction_qm_purchases) is inserted BEFORE post_operation locks characters /
        econ_accounts; nothing of the buy transaction is written after the ledger op."""
        import econ_ledger
        seq = []
        real_post = econ_ledger.post_operation

        def spy_post(db, *args, **kwargs):
            seq.append(("post", kwargs.get("op_type")))
            return real_post(db, *args, **kwargs)

        def on_sql(conn, cursor, statement, params, context, executemany):
            s = " ".join(statement.split()).upper()
            for table in ("FACTION_QM_PURCHASES", "FACTION_QM_ITEMS"):
                if s.startswith(f"INSERT INTO {table}") or s.startswith(f"UPDATE {table}"):
                    seq.append(("sql", table.lower()))

        def on_commit(conn):
            seq.append(("commit", None))

        monkeypatch.setattr(econ_ledger, "post_operation", spy_post)
        event.listen(shop.engine, "before_cursor_execute", on_sql)
        event.listen(shop.engine, "commit", on_commit)
        try:
            r = buy(fapi, shop.ids["sword"])
        finally:
            event.remove(shop.engine, "before_cursor_execute", on_sql)
            event.remove(shop.engine, "commit", on_commit)
        assert r.status_code == 200, r.text
        sale = seq.index(("post", core.OP_FACTION_QM_SALE))
        assert [e for e in seq[:sale] if e[0] == "sql"] == [("sql", "faction_qm_items"), ("sql", "faction_qm_purchases")]
        assert seq[sale + 1] == ("commit", None)            # the delivery claim etc. run after the buy committed
        assert world_sum(shop) == 0

    def test_insufficient_funds_leaves_no_purchase_row(self, fapi, shop):
        exec_(shop, "UPDATE faction_qm_items SET price = 5000 WHERE id = :i", i=shop.ids["sword"])
        r = buy(fapi, shop.ids["sword"])
        assert r.status_code == 400
        assert purchases(shop) == [] and qm_stock(shop, shop.ids["sword"]) == 3 and cash(shop, ALPHA) == 1000

    def test_same_request_id_twice_is_409_once(self, fapi, shop):
        assert buy(fapi, shop.ids["sword"]).status_code == 200
        again = buy(fapi, shop.ids["sword"])
        assert again.status_code == 409
        assert len(purchases(shop)) == 1 and cash(shop, ALPHA) == 950 and world_sum(shop) == 0


# ============================================================================================ delivery outbox


class TestDelivery:

    def test_definite_failure_backs_off_then_retries(self, fapi, shop):
        shop.http.push(500)
        r = buy(fapi, shop.ids["sword"])
        assert r.json()["delivered"] is False
        assert r.json()["message"] == "Предмет будет доставлен в инвентарь в ближайшее время"
        (p,) = purchases(shop)
        assert (p["status"], p["attempts"], p["last_error"]) == ("pending", 1, "http 500")
        nxt = q(shop, "SELECT next_attempt_at FROM faction_qm_purchases")
        assert str(nxt) > str(datetime.utcnow() + timedelta(seconds=90))[:19]      # 2^1 min backoff
        assert fqm.retry_due(shop, datetime.utcnow())["done"] == 0               # not due yet
        stats = fqm.retry_due(shop, datetime.utcnow() + timedelta(minutes=3))
        assert stats["done"] == 1 and purchases(shop)[0]["status"] == "done"
        assert len(shop.http.calls) == 2 and world_sum(shop) == 0

    def test_five_definite_failures_auto_refund(self, fapi, shop):
        shop.http.push(*[connect_error() for _ in range(5)])
        buy(fapi, shop.ids["sword"], qty=2)
        at = datetime.utcnow()
        for _ in range(4):
            at += timedelta(days=2)
            fqm.retry_due(shop, at)
        (p,) = purchases(shop)
        assert (p["status"], p["attempts"]) == ("refunded", 5)
        assert cash(shop, ALPHA) == 1000 and treasury(shop, shop.ids["fid"]) == 0
        assert qm_stock(shop, shop.ids["sword"]) == 3                             # stock back
        assert [k for _t, k in ops(shop, core.OP_FACTION_QM_REFUND)] == [f"faction_qm_refund:p{p['id']}"]
        assert "Интендант не смог выдать «Меч Зари» — марки возвращены" in notice_texts(shop)
        fqm.retry_due(shop, at + timedelta(days=5))
        assert len(shop.http.calls) == 5 and world_sum(shop) == 0

    def test_refund_becomes_a_debt_when_the_treasury_is_empty(self, fapi, shop):
        from tests.faction_world import drain
        shop.http.push(500)
        buy(fapi, shop.ids["sword"], qty=2)                                       # 100 into the treasury
        drain(shop, core.AccountRef.faction(shop.ids["fid"]), 70)                 # admin drained it to 30
        as_user(1, "admin", ["factions:read", "factions:economy"])
        r = fapi.post(f"{A}/qm-purchases/{purchases(shop)[0]['id']}/refund")
        assert r.status_code == 200 and r.json()["status"] == "refunded"
        (d,) = debts(shop, ALPHA)
        assert (d["source"], d["source_key"], d["amount"], d["paid"], d["unpaid_notified"]) == \
            ("refund", f"refund:p{purchases(shop)[0]['id']}", 100, 0, 1)
        assert ops(shop, core.OP_FACTION_QM_REFUND) == []
        assert "Интендант не смог выдать «Меч Зари» — марки вернут из казны фракции позже" in notice_texts(shop)
        fund(shop, core.AccountRef.faction(shop.ids["fid"]), 70)
        fec.sweep_debts(shop, datetime.utcnow())
        assert [(x["paid"], x["status"]) for x in debts(shop, ALPHA)] == [(100, "paid")]
        assert cash(shop, ALPHA) == 1000 and world_sum(shop) == 0

    def test_uncertain_is_never_retried(self, fapi, shop):
        shop.http.push(read_timeout())
        r = buy(fapi, shop.ids["sword"])
        assert r.status_code == 200 and r.json()["delivered"] is False
        (p,) = purchases(shop)
        assert (p["status"], p["last_error"]) == ("failed", "uncertain: ReadTimeout")
        fqm.retry_due(shop, datetime.utcnow() + timedelta(days=3))
        assert len(shop.http.calls) == 1 and purchases(shop)[0]["status"] == "failed"
        assert cash(shop, ALPHA) == 950                                           # no automatic refund

    def test_unexpected_exception_is_uncertain(self, fapi, shop, monkeypatch):
        def crash(url, payload):
            shop.http.calls.append((url, payload))
            raise ValueError("bad json")

        monkeypatch.setattr(faction_rewards, "http_post", crash)
        buy(fapi, shop.ids["sword"])
        assert purchases(shop)[0]["status"] == "failed"
        assert purchases(shop)[0]["last_error"] == "uncertain: ValueError"

    def test_stale_sending_becomes_uncertain(self, fapi, shop):
        shop.http.push(500)
        buy(fapi, shop.ids["sword"])
        exec_(shop, "UPDATE faction_qm_purchases SET status = 'sending', updated_at = :u",
              u=datetime.utcnow() - timedelta(minutes=30))
        assert fqm.recover_stale(shop, datetime.utcnow()) == 1
        assert (purchases(shop)[0]["status"], purchases(shop)[0]["last_error"]) == ("failed", "uncertain: stale")

    def test_claim_is_exclusive(self, fapi, shop):
        shop.http.push(500)
        buy(fapi, shop.ids["sword"])
        pid = purchases(shop)[0]["id"]
        exec_(shop, "UPDATE faction_qm_purchases SET status = 'sending'")
        assert fqm.deliver(shop, pid) is None                                      # somebody else holds it
        assert len(shop.http.calls) == 1

    def test_no_transaction_is_open_during_the_http_call(self, fapi, shop, monkeypatch):
        state = {"open": 0}
        for name, step in (("begin", 1), ("commit", -1), ("rollback", -1)):
            event.listen(shop.engine, name, lambda conn, step=step: state.__setitem__("open", state["open"] + step))
        seen = []

        def http(url, payload):
            seen.append(state["open"])
            return type("R", (), {"status_code": 200})()

        monkeypatch.setattr(faction_rewards, "http_post", http)
        exec_(shop, "INSERT INTO faction_qm_purchases (character_id, faction_id, qm_item_id, npc_id, item_id, "
                    "quantity, price_total, op_key, status, attempts, next_attempt_at, created_at, updated_at) "
                    "VALUES (1, :fid, :q, 53, 501, 1, 0, 'k-1', 'pending', 0, :t, :t, :t)",
              fid=shop.ids["fid"], q=shop.ids["sword"], t=datetime.utcnow())
        state["open"] = 0
        assert fqm.deliver(shop, 1) == "done"
        assert seen == [0]


# ============================================================================================ admin retry / refund


class TestAdminPurchases:

    def test_retry_failed_then_409_on_done(self, fapi, shop):
        shop.http.push(read_timeout())
        buy(fapi, shop.ids["sword"])
        pid = purchases(shop)[0]["id"]
        as_user(1, "admin", ["factions:read", "factions:economy"])
        r = fapi.post(f"{A}/qm-purchases/{pid}/retry")
        assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["attempts"] == 1
        r = fapi.post(f"{A}/qm-purchases/{pid}/retry")
        assert r.status_code == 409 and r.json()["detail"] == "Повторить можно только неудавшуюся выдачу"
        assert len(shop.http.calls) == 2 and cash(shop, ALPHA) == 950

    def test_refund_states(self, fapi, shop):
        shop.http.push(read_timeout())
        buy(fapi, shop.ids["sword"], qty=3)
        pid = purchases(shop)[0]["id"]
        as_user(1, "admin", ["factions:read", "factions:economy"])
        r = fapi.post(f"{A}/qm-purchases/{pid}/refund")
        assert r.status_code == 200 and r.json()["status"] == "refunded"
        assert cash(shop, ALPHA) == 1000 and qm_stock(shop, shop.ids["sword"]) == 3
        again = fapi.post(f"{A}/qm-purchases/{pid}/refund")
        assert again.status_code == 409 and again.json()["detail"] == "Вернуть деньги можно только за невыданную покупку"
        assert fapi.post(f"{A}/qm-purchases/{pid}/retry").status_code == 409
        assert fapi.post(f"{A}/qm-purchases/9999/refund").status_code == 404
        buy(fapi, shop.ids["sword"], rid="buy-00002")                              # delivered -> done
        done = purchases(shop)[-1]["id"]
        as_user(1, "admin", ["factions:read", "factions:economy"])
        assert fapi.post(f"{A}/qm-purchases/{done}/refund").status_code == 409
        assert len(ops(shop, core.OP_FACTION_QM_REFUND)) == 1 and world_sum(shop) == 0

    def test_refund_after_the_row_was_deleted(self, fapi, shop):
        shop.http.push(read_timeout())
        buy(fapi, shop.ids["sword"])
        pid = purchases(shop)[0]["id"]
        as_user(1, "admin", ["factions:read", "factions:economy"])
        assert fapi.delete(f"{A}/qm-items/{shop.ids['sword']}").status_code == 200
        # (MySQL sets qm_item_id NULL via the FK; the SQLite world has no FK enforcement — the refund must cope
        # with a dangling id either way)
        assert fapi.post(f"{A}/qm-purchases/{pid}/refund").status_code == 200
        assert cash(shop, ALPHA) == 1000 and world_sum(shop) == 0

    def test_permissions(self, fapi, shop):
        shop.http.push(read_timeout())
        buy(fapi, shop.ids["sword"])
        pid = purchases(shop)[0]["id"]
        for perms in ([], ["factions:read", "factions:manage", "factions:edit"]):
            as_user(2, "moderator", perms)
            assert fapi.post(f"{A}/qm-purchases/{pid}/retry").status_code == 403
            assert fapi.post(f"{A}/qm-purchases/{pid}/refund").status_code == 403
        as_user(USER_ALPHA)
        assert fapi.get(f"{A}/{shop.ids['fid']}/qm-purchases").status_code == 403
        as_user(1, "admin", ["factions:read"])
        listing = fapi.get(f"{A}/{shop.ids['fid']}/qm-purchases?status=failed").json()
        assert [(i["id"], i["status"], i["character"]["name"], i["item"]["name"]) for i in listing["items"]] == \
            [(pid, "failed", "Альфа", "Меч Зари")]
        assert fapi.get(f"{A}/{shop.ids['fid']}/qm-purchases?status=bogus").status_code == 422
        assert purchases(shop)[0]["status"] == "failed"
