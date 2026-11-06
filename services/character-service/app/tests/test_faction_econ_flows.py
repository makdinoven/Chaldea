"""FEAT-206 QA: rank marks -> debt queue -> payouts, and player donations. features/FEAT-206 §3.5, §3.7, §3.9.

Debt queue: one row per grant (``rank:g<grant>``), FIFO partial payouts in their own transaction (one
``faction_payout`` op, key ``faction_payout:f<fid>:s<seq>``), notices once, no retroactive pay, debts survive leave /
expel / hide, the 5-min sweep and the admin emission hook. Donations: points + daily cap per UTC day, request_id
idempotency, insufficient funds, membership / ownership / validation errors, hostile penalty, rank-up -> marks paid from
the donation itself. Every money flow ends with the world invariant ``sum(characters) + sum(accounts) == 0``.
"""

from datetime import datetime, timedelta

import pytest

import econ_core as core
import econ_ledger
import faction_admin_crud as fa
import faction_crud
import faction_econ_crud as fec
import faction_rewards
import models
from main import app
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, MERCHANT, USER_ALPHA, USER_BETA, add_rank, as_admin, as_user, cash, debts, econ_world, exec_,
    fapi, fund, fw, hostile, join, make_faction, member, notice_texts, ops, q, rep_world, rows, run_flow, set_points,
    settings, treasury, world_sum,
)

P = "/characters"
A = "/characters/admin/factions"


def grant_ids(f, cid):
    return [int(r[0]) for r in rows(f, "SELECT id FROM faction_rank_grants WHERE character_id = :c ORDER BY id",
                                    c=cid)]


def settle(f, fid):
    return fec.settle_after_commit([fid], f)


# ============================================================================================ rank marks -> debt


class TestRankMarksDebt:

    def test_one_debt_row_per_grant_and_notice_mentions_marks(self, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        result = join(fw, ALPHA, fid)
        (g,) = grant_ids(fw, ALPHA)
        (d,) = debts(fw, ALPHA)
        assert (d["source"], d["source_key"], d["amount"], d["paid"], d["status"]) == \
            ("rank", f"rank:g{g}", 100, 0, "open")
        assert any("+100 марок из казны фракции" in n.message for n in result.notices)

    def test_empty_treasury_owes_and_notifies_once(self, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        join(fw, ALPHA, fid)
        faction_rewards.deliver_pending(ALPHA, fw)
        settle(fw, fid)
        fec.sweep_debts(fw, datetime.utcnow())
        (d,) = debts(fw, ALPHA)
        assert (d["status"], d["paid"], d["unpaid_notified"]) == ("open", 0, 1)
        owed = [t for t in notice_texts(fw) if "записаны в долг" in t]
        assert owed == ["Казна фракции «Орден Зари» сейчас пуста: 100 марок за звание записаны в долг. "
                        "Выплатим, когда казна пополнится"]
        assert ops(fw, core.OP_FACTION_PAYOUT) == []
        assert int(q(fw, "SELECT payout_seq FROM faction_economy WHERE faction_id = :fid", fid=fid) or 0) == 0

    def test_partial_then_full_payout_with_sequenced_keys(self, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        join(fw, ALPHA, fid)
        faction_rewards.deliver_pending(ALPHA, fw)
        fund(fw, core.AccountRef.faction(fid), 60)
        assert settle(fw, fid) == 1
        assert [(d["paid"], d["status"]) for d in debts(fw, ALPHA)] == [(60, "open")]
        assert cash(fw, ALPHA) == 60 and treasury(fw, fid) == 0
        assert not any("выплатила долг" in t for t in notice_texts(fw))       # partial payments are silent
        fund(fw, core.AccountRef.faction(fid), 100)
        settle(fw, fid)
        (d,) = debts(fw, ALPHA)
        assert (d["paid"], d["status"]) == (100, "paid")
        assert q(fw, "SELECT paid_at FROM faction_debts") is not None
        assert cash(fw, ALPHA) == 100 and treasury(fw, fid) == 60
        assert [k for _t, k in ops(fw, core.OP_FACTION_PAYOUT)] == [f"faction_payout:f{fid}:s1",
                                                                      f"faction_payout:f{fid}:s2"]
        assert [t for t in notice_texts(fw) if "выплатила" in t] == ["Фракция «Орден Зари» выплатила долг: 100 марок"]
        settle(fw, fid)                                                     # nothing left: no op, no seq bump
        assert len(ops(fw, core.OP_FACTION_PAYOUT)) == 2
        assert int(q(fw, "SELECT payout_seq FROM faction_economy WHERE faction_id = :fid", fid=fid)) == 2
        assert world_sum(fw) == 0

    def test_funded_treasury_pays_at_once_without_notices(self, fapi, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        fund(fw, core.AccountRef.faction(fid), 500)
        as_user(USER_ALPHA)
        assert fapi.post(f"{P}/{ALPHA}/factions/{fid}/join").status_code == 200     # API dispatch -> settle
        assert [(d["paid"], d["status"], d["unpaid_notified"]) for d in debts(fw, ALPHA)] == [(100, "paid", 0)]
        assert cash(fw, ALPHA) == 100 and treasury(fw, fid) == 400
        assert not any("долг" in t for t in notice_texts(fw))
        assert world_sum(fw) == 0

    def test_fifo_across_characters(self, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        join(fw, ALPHA, fid)
        join(fw, BETA, fid)
        fund(fw, core.AccountRef.faction(fid), 150)
        settle(fw, fid)
        assert [(d["character_id"], d["paid"], d["status"]) for d in debts(fw)] == \
            [(ALPHA, 100, "paid"), (BETA, 50, "open")]
        (op_meta,) = rows(fw, "SELECT metadata FROM econ_operations WHERE op_type = 'faction_payout'")
        assert cash(fw, ALPHA) == 100 and cash(fw, BETA) == 50
        assert world_sum(fw) == 0

    def test_each_rank_of_a_climb_gets_its_own_row(self, fapi, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=10)
        add_rank(fw, fid, "Рыцарь", 2, min_points=50, reward_marks=40)
        add_rank(fw, fid, "Магистр", 3, min_points=100)                     # no marks -> no row
        join(fw, ALPHA, fid)
        mid = member(fw, ALPHA, fid)["id"]
        as_user(1, "admin", ["factions:manage"])
        r = fapi.post(f"{A}/members/{mid}/points", json={"delta": 150, "reason": "заслуги"})
        assert r.status_code == 200, r.text
        assert sorted(d["amount"] for d in debts(fw, ALPHA)) == [10, 40]
        # the same grant never creates a second row (re-climb after a points loss / regain)
        set_points(fw, ALPHA, fid, 0)
        run_flow(fw, faction_crud.recheck_ranks, ALPHA, datetime.utcnow())
        set_points(fw, ALPHA, fid, 200)
        run_flow(fw, faction_crud.recheck_ranks, ALPHA, datetime.utcnow())
        assert len(debts(fw, ALPHA)) == 2

    def test_no_retroactive_pay(self, fw):
        fid = make_faction(fw)
        rank = add_rank(fw, fid, "Послушник", 1)
        join(fw, ALPHA, fid)
        exec_(fw, "UPDATE faction_ranks SET reward_marks = 500 WHERE id = :r", r=rank)
        fund(fw, core.AccountRef.faction(fid), 1000)
        run_flow(fw, faction_crud.recheck_ranks, ALPHA, datetime.utcnow())
        faction_rewards.deliver_pending(ALPHA, fw)
        fec.sweep_debts(fw, datetime.utcnow())
        assert debts(fw, ALPHA) == [] and cash(fw, ALPHA) == 0
        join(fw, BETA, fid)                                                 # a NEW grant gets the marks
        assert [d["amount"] for d in debts(fw, BETA)] == [500]

    @pytest.mark.parametrize("how", ["leave", "expel", "hide"])
    def test_debt_survives_leave_expel_hide(self, fapi, fw, how):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        join(fw, ALPHA, fid)
        faction_rewards.deliver_pending(ALPHA, fw)
        if how == "leave":
            run_flow(fw, faction_crud.leave, ALPHA, fid)
        elif how == "expel":
            run_flow(fw, fa.expel, member(fw, ALPHA, fid)["id"], "нарушение", 1)
        else:
            exec_(fw, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=fid)
        assert [d["status"] for d in debts(fw, ALPHA)] == ["open"]
        as_user(USER_ALPHA)
        view = fapi.get(f"{P}/{ALPHA}/factions").json()["memberships"]
        (entry,) = [m for m in view if m["faction"]["id"] == fid]
        assert entry["debt"] == 100                                         # shown as a number, any status
        if how != "hide":
            assert entry["donation"] is None and entry["wealth"] is None
        fund(fw, core.AccountRef.faction(fid), 100)
        fec.sweep_debts(fw, datetime.utcnow())                              # the 5-min pass pays it anyway
        assert [d["status"] for d in debts(fw, ALPHA)] == ["paid"] and cash(fw, ALPHA) == 100
        assert world_sum(fw) == 0

    def test_concurrent_settle_is_skipped(self, fw, monkeypatch):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        join(fw, ALPHA, fid)
        fund(fw, core.AccountRef.faction(fid), 100)

        def dup(*_a, **_k):
            raise core.DuplicateOperation("faction_payout:f1:s1")

        monkeypatch.setattr(econ_ledger, "post_operation", dup)
        assert settle(fw, fid) == 0                                          # logged, never raised
        monkeypatch.undo()
        assert [d["paid"] for d in debts(fw, ALPHA)] == [0]
        assert int(q(fw, "SELECT payout_seq FROM faction_economy WHERE faction_id = :fid", fid=fid) or 0) == 0
        assert settle(fw, fid) == 1 and cash(fw, ALPHA) == 100

    def test_settle_of_unknown_faction_is_a_noop(self, fw):
        assert fec.settle_after_commit([999], fw) == 1
        assert fec.settle_after_commit([], fw) == 0

    def test_sweep_settles_every_faction_with_debts(self, fw):
        f1, f2 = make_faction(fw, "Первая"), make_faction(fw, "Вторая")
        for fid in (f1, f2):
            add_rank(fw, fid, "Ранг", 1, reward_marks=30)
            join(fw, ALPHA, fid)
            fund(fw, core.AccountRef.faction(fid), 30)
        assert fec.sweep_debts(fw, datetime.utcnow()) == 2
        assert [d["status"] for d in debts(fw, ALPHA)] == ["paid", "paid"] and cash(fw, ALPHA) == 60
        assert world_sum(fw) == 0

    def test_admin_emission_into_the_treasury_settles(self, fapi, fw):
        import economy_api
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        join(fw, ALPHA, fid)
        fund(fw, core.AccountRef.faction(fid), 1)                            # the account exists now
        settle(fw, fid)
        account = int(q(fw, "SELECT id FROM econ_accounts WHERE kind = 'faction_treasury' AND ref_id = :fid", fid=fid))

        def override_get_db():
            s = fw()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[economy_api.get_db] = override_get_db
        try:
            as_user(1, "admin", ["economy:emit"])
            r = fapi.post(f"{P}/admin/economy/emission", json={"account_id": account, "amount": 200,
                                                               "comment": "стартовая казна"})
            assert r.status_code == 200, r.text
        finally:
            app.dependency_overrides.pop(economy_api.get_db, None)
        assert [(d["paid"], d["status"]) for d in debts(fw, ALPHA)] == [(100, "paid")]
        assert treasury(fw, fid) == 101 and world_sum(fw) == 0

    def test_admin_character_view_lists_debts(self, fapi, fw):
        fid = make_faction(fw)
        add_rank(fw, fid, "Послушник", 1, reward_marks=100)
        join(fw, ALPHA, fid)
        as_admin()
        body = fapi.get(f"{A}/characters/{ALPHA}").json()
        (d,) = body["debts"]
        assert (d["amount"], d["paid"], d["status"], d["source"], d["faction_name"]) == \
            (100, 0, "open", "rank", "Орден Зари")
        assert body["qm_purchases"] == []


# ============================================================================================ donations


def donate(fapi, cid=ALPHA, fid=1, amount=25, rid="req-00001", user=USER_ALPHA):
    as_user(user)
    return fapi.post(f"{P}/{cid}/factions/{fid}/donate", json={"amount": amount, "request_id": rid})


@pytest.fixture
def donor(fw):
    fid = make_faction(fw)
    add_rank(fw, fid, "Послушник", 1)
    join(fw, ALPHA, fid)
    fund(fw, core.AccountRef.character(ALPHA), 1000)
    return fid


class TestDonations:

    def test_happy_path_response_and_ledger(self, fapi, fw, donor):
        r = donate(fapi, fid=donor, amount=25)
        assert r.status_code == 200, r.text
        assert r.json() == {"points_delta": 2, "points_after": 2, "points_today": 2, "daily_cap": 50,
                            "marks_today": 25, "rank_ups": 0, "new_balance": 975}
        assert treasury(fw, donor) == 25 and cash(fw, ALPHA) == 975
        assert ops(fw, core.OP_FACTION_DONATION) == [("faction_donation", "faction_donation:c1:req-00001")]
        # untaxed: exactly one posting character -> faction
        assert int(q(fw, "SELECT COUNT(*) FROM econ_postings p JOIN econ_operations o ON o.id = p.operation_id "
                         "WHERE o.op_type = 'faction_donation'")) == 1
        assert world_sum(fw) == 0

    def test_same_request_id_is_409_and_charged_once(self, fapi, fw, donor):
        assert donate(fapi, fid=donor, amount=25).status_code == 200
        again = donate(fapi, fid=donor, amount=25)
        assert again.status_code == 409 and again.json()["detail"] == "Это пожертвование уже выполнено"
        assert cash(fw, ALPHA) == 975 and member(fw, ALPHA, donor)["points"] == 2
        # the same request id from ANOTHER character is a different key
        join(fw, BETA, donor)
        fund(fw, core.AccountRef.character(BETA), 100)
        assert donate(fapi, cid=BETA, fid=donor, amount=10, user=USER_BETA).status_code == 200
        assert world_sum(fw) == 0

    def test_insufficient_funds_400_nothing_changes(self, fapi, fw, donor):
        r = donate(fapi, fid=donor, amount=1001)
        assert r.status_code == 400 and r.json()["detail"] == "Недостаточно марок"
        assert cash(fw, ALPHA) == 1000 and treasury(fw, donor) == 0
        assert int(q(fw, "SELECT COALESCE(SUM(marks), 0) FROM faction_donation_days")) == 0
        assert member(fw, ALPHA, donor)["points"] == 0
        assert donate(fapi, fid=donor, amount=1000, rid="req-00002").status_code == 200    # retry with a new id

    def test_daily_cap_and_carry(self, fapi, fw, donor):
        assert donate(fapi, fid=donor, amount=25, rid="req-00001").json()["points_delta"] == 2
        assert donate(fapi, fid=donor, amount=5, rid="req-00002").json()["points_delta"] == 1    # 30 -> 3
        r = donate(fapi, fid=donor, amount=900, rid="req-00003").json()
        assert (r["points_delta"], r["points_today"], r["marks_today"]) == (47, 50, 930)
        r = donate(fapi, fid=donor, amount=50, rid="req-00004").json()
        assert (r["points_delta"], r["points_today"], r["new_balance"]) == (0, 50, 20)     # still accepted
        view = fapi.get(f"{P}/{ALPHA}/factions").json()["memberships"][0]["donation"]
        assert (view["points_today"], view["marks_today"], view["daily_cap"], view["marks_per_point"]) == \
            (50, 980, 50, 10)
        assert 0 < view["resets_in_seconds"] <= 86400
        texts = [i["text"] for i in fapi.get(f"{P}/{ALPHA}/factions/history").json()["items"]]
        assert "Пожертвование фракции «Орден Зари»: 50 марок" in texts
        assert "Пожертвование фракции «Орден Зари»: 25 марок, +2 очков" in texts
        assert treasury(fw, donor) == 980 and world_sum(fw) == 0

    def test_cap_resets_per_utc_day(self, fw, donor):
        day1 = datetime(2026, 11, 6, 23, 59, 0)
        day2 = day1 + timedelta(minutes=2)
        r1 = run_flow(fw, fec.donate, ALPHA, donor, 600, "req-day-0001", day1).data
        r2 = run_flow(fw, fec.donate, ALPHA, donor, 100, "req-day-0002", day1).data
        r3 = run_flow(fw, fec.donate, ALPHA, donor, 100, "req-day-0003", day2).data
        assert (r1["points_delta"], r2["points_delta"], r3["points_delta"]) == (50, 0, 10)
        assert rows(fw, "SELECT day, marks, points FROM faction_donation_days ORDER BY day") == \
            [("2026-11-06", 700, 50), ("2026-11-07", 100, 10)]

    def test_settings_rate_and_zero_cap(self, fapi, fw, donor):
        settings(fw, donation_marks_per_point=1, donation_points_daily_cap=0)
        r = donate(fapi, fid=donor, amount=40)
        assert r.status_code == 200 and r.json()["points_delta"] == 0 and r.json()["daily_cap"] == 0
        settings(fw, donation_points_daily_cap=100)
        assert donate(fapi, fid=donor, amount=40, rid="req-00002").json()["points_delta"] == 80
        # marks of the day before the cap change still count toward the total (80 marks -> 80 points, 0 before)

    def test_hostile_penalty_halves(self, fapi, fw, donor):
        other = make_faction(fw, "Тень Зари")
        add_rank(fw, other, "Тень", 1)
        hostile(fw, donor, other)
        join(fw, ALPHA, other)
        set_points(fw, ALPHA, other, 30)
        r = donate(fapi, fid=donor, amount=100)
        assert r.json()["points_delta"] == 10
        assert member(fw, ALPHA, donor)["points"] == 10 and member(fw, ALPHA, other)["points"] == 25
        keys = rows(fw, "SELECT faction_id, event_type, points_delta, event_key FROM faction_log "
                        "WHERE event_type IN ('donation', 'hostile_penalty') ORDER BY id")
        assert keys == [(donor, "donation", 10, "faction:donate:c1:req-00001"),
                        (other, "hostile_penalty", -5, f"faction:donate:c1:req-00001:hostile:{donor}")]

    def test_no_penalty_when_no_points_gained(self, fapi, fw, donor):
        other = make_faction(fw, "Тень Зари")
        add_rank(fw, other, "Тень", 1)
        hostile(fw, donor, other)
        join(fw, ALPHA, other)
        set_points(fw, ALPHA, other, 30)
        donate(fapi, fid=donor, amount=9)
        assert member(fw, ALPHA, other)["points"] == 30

    def test_rank_up_marks_paid_from_the_donation(self, fapi, fw, donor):
        add_rank(fw, donor, "Рыцарь", 2, min_points=10, reward_marks=30)
        r = donate(fapi, fid=donor, amount=100)
        assert r.json()["rank_ups"] == 1
        assert [(d["amount"], d["paid"], d["status"]) for d in debts(fw, ALPHA)] == [(30, 30, "paid")]
        assert cash(fw, ALPHA) == 1000 - 100 + 30 and treasury(fw, donor) == 70
        assert world_sum(fw) == 0

    def test_lock_order_debt_insert_before_ledger_op(self, fapi, fw, donor, monkeypatch):
        """Review #1: rank-up debt row (faction_debts) is written BEFORE post_operation locks characters / accounts."""
        from sqlalchemy import event
        add_rank(fw, donor, "Рыцарь", 2, min_points=10, reward_marks=30)
        seq = []
        real_post = econ_ledger.post_operation

        def spy_post(db, *args, **kwargs):
            seq.append(("post", kwargs.get("op_type")))
            return real_post(db, *args, **kwargs)

        def on_sql(conn, cursor, statement, params, context, executemany):
            s = " ".join(statement.split()).upper()
            for table in ("FACTION_DEBTS", "FACTION_DONATION_DAYS", "FACTION_LOG", "FACTION_RANK_GRANTS"):
                if s.startswith(f"INSERT INTO {table}") or s.startswith(f"UPDATE {table}"):
                    seq.append(("sql", table.lower()))

        def on_commit(conn):
            seq.append(("commit", None))

        monkeypatch.setattr(econ_ledger, "post_operation", spy_post)
        event.listen(fw.engine, "before_cursor_execute", on_sql)
        event.listen(fw.engine, "commit", on_commit)
        try:
            r = donate(fapi, fid=donor, amount=100)
        finally:
            event.remove(fw.engine, "before_cursor_execute", on_sql)
            event.remove(fw.engine, "commit", on_commit)
        assert r.status_code == 200 and r.json()["rank_ups"] == 1
        donation = seq.index(("post", core.OP_FACTION_DONATION))
        before = seq[:donation]
        for table in ("faction_debts", "faction_rank_grants", "faction_log", "faction_donation_days"):
            assert ("sql", table) in before, table
        # nothing of the donation transaction is written after its ledger op: the next event is its commit
        # (the debt payout runs post-commit in its own transaction)
        assert seq[donation + 1] == ("commit", None)
        assert ("post", core.OP_FACTION_PAYOUT) in seq[donation + 1:]
        assert [(d["amount"], d["paid"], d["status"]) for d in debts(fw, ALPHA)] == [(30, 30, "paid")]
        assert world_sum(fw) == 0

    def test_insufficient_funds_after_rank_up_rolls_back_debt_and_points(self, fapi, fw, donor):
        """The ledger op is last now: its failure must still leave no grant / debt / points / day marks behind."""
        add_rank(fw, donor, "Рыцарь", 2, min_points=1, reward_marks=30)
        r = donate(fapi, fid=donor, amount=1001)
        assert r.status_code == 400
        assert debts(fw, ALPHA) == [] and len(grant_ids(fw, ALPHA)) == 1          # only the entry rank
        assert member(fw, ALPHA, donor)["points"] == 0
        assert int(q(fw, "SELECT COALESCE(SUM(marks), 0) FROM faction_donation_days")) == 0
        assert cash(fw, ALPHA) == 1000 and world_sum(fw) == 0

    def test_not_a_member_404(self, fapi, fw, donor):
        other = make_faction(fw, "Чужие")
        r = donate(fapi, fid=other)
        assert r.status_code == 404 and r.json()["detail"] == faction_crud.MSG_NOT_MEMBER
        run_flow(fw, faction_crud.leave, ALPHA, donor)
        assert donate(fapi, fid=donor, rid="req-00009").status_code == 404
        assert cash(fw, ALPHA) == 1000

    def test_hidden_faction_member_can_still_donate(self, fapi, fw, donor):
        exec_(fw, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=donor)
        assert donate(fapi, fid=donor).status_code == 200

    def test_not_owner_403_and_missing_404(self, fapi, fw, donor):
        r = donate(fapi, fid=donor, user=USER_BETA)
        assert r.status_code == 403 and r.json()["detail"] == "Это не ваш персонаж"
        assert donate(fapi, cid=999, fid=donor).status_code == 404
        assert donate(fapi, fid=999).status_code in (403, 404)
        assert cash(fw, ALPHA) == 1000

    def test_npc_cannot_donate(self, fw, donor):
        db = fw()
        try:
            with pytest.raises(faction_crud.FactionError) as err:
                fec.donate(db, MERCHANT, donor, 10, "req-npc-0001")
            assert err.value.status_code == 403
        finally:
            db.rollback()
            db.close()

    @pytest.mark.parametrize("body", [
        {"amount": 0, "request_id": "req-00001"}, {"amount": 1_000_001, "request_id": "req-00001"},
        {"amount": "10", "request_id": "req-00001"}, {"amount": 10.5, "request_id": "req-00001"},
        {"amount": True, "request_id": "req-00001"}, {"amount": 10, "request_id": "short"},
        {"amount": 10, "request_id": "'; DROP TABLE factions; --"}, {"amount": 10, "request_id": "a" * 65},
        {"amount": 10, "request_id": "<script>alert(1)</script>"}, {"amount": 10},
    ])
    def test_validation_422(self, fapi, fw, donor, body):
        as_user(USER_ALPHA)
        r = fapi.post(f"{P}/{ALPHA}/factions/{donor}/donate", json=body)
        assert r.status_code == 422
        assert cash(fw, ALPHA) == 1000 and int(q(fw, "SELECT COUNT(*) FROM factions")) >= 1

    def test_donation_needs_auth(self, fapi, fw, donor):
        from auth_http import get_current_user_via_http
        app.dependency_overrides.pop(get_current_user_via_http, None)
        r = fapi.post(f"{P}/{ALPHA}/factions/{donor}/donate", json={"amount": 10, "request_id": "req-00001"})
        assert r.status_code == 401
