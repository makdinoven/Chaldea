"""FEAT-200 QA (task 3): the reputation / law / shadow tails in character-service.

* fix 1: reviving an NPC (internal ``npc-status`` -> alive, admin ``PUT /admin/npcs/{id}`` dead -> alive) restores
  every ``current_*`` resource to its ``max_*`` in ``character_attributes``; a failing heal never blocks the revival;
* fix 4: the reputation journal of a knocked-out guard says «Повержен стражник «…» (#id)», other NPCs unchanged;
* fix 5: the law auto-resolution skips an encounter that turned «fighting» meanwhile (no jail, no fine);
* fix 6: clearing wanted in a region without wanted answers «Розыска нет» and writes no journal row;
* fix 7: ``killer_character_ids`` above 50 (and duplicates) are accepted — deduped, first 200 kept, the NPC dies;
* fix 8: ``fame_rep_key`` keeps short keys, hashes long ones (sha1, <= 191) so distinct long keys never collide.
"""

import asyncio
import hashlib

import pytest
from sqlalchemy.exc import OperationalError

import law_crud
import law_flows
import reputation_crud
import schemas
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GUARD, GUARD_POST, INTERNAL, L_FARM, L_JAIL, MERCHANT, NO_ROLE, R_OST, R_PASHNI, USER_ALPHA, api,
    as_admin, as_user, char_row, encounter, exec_, gold, law_world, make_encounter, q, rep_world, rid, rows,
    set_gold, set_wanted, wanted,
)
from tests.reputation_world import force_witnessed, log_rows, value  # noqa: F401  (force_witnessed: fixture)
from tests.shadow_world import renown, renown_log


# =============================================================================================== helpers

RESOURCES = ("health", "mana", "energy", "stamina")


def _drain(f, npc_id, current=0):
    """Give the NPC an attributes row (if missing) with every current resource at ``current`` (max stays 100/50)."""
    if q(f, "SELECT COUNT(*) FROM character_attributes WHERE character_id = :c", c=npc_id) == 0:
        exec_(f, "INSERT INTO character_attributes (character_id) VALUES (:c)", c=npc_id)
    exec_(f, "UPDATE character_attributes SET current_health = :v, current_mana = :v, current_energy = :v, "
             "current_stamina = :v WHERE character_id = :c", v=current, c=npc_id)


def _resources(f, npc_id):
    cols = ", ".join(f"current_{r}, max_{r}" for r in RESOURCES)
    (row,) = rows(f, f"SELECT {cols} FROM character_attributes WHERE character_id = :c", c=npc_id)
    return {r: (row[2 * i], row[2 * i + 1]) for i, r in enumerate(RESOURCES)}


def _full(f, npc_id):
    return all(cur == mx for cur, mx in _resources(f, npc_id).values())


def _status(api, npc_id, status, **extra):
    return api.put(f"/characters/internal/npc-status/{npc_id}", json={"status": status, **extra}, headers=INTERNAL)


def _admin_update(api, npc_id, body):
    as_user(1, "admin", ["npcs:update"])
    return api.put(f"/characters/admin/npcs/{npc_id}", json=body, headers={"Authorization": "Bearer t"})


def _dead(f, npc_id):
    exec_(f, "UPDATE characters SET npc_status = 'dead' WHERE id = :n", n=npc_id)


# =============================================================================================== fix 1: revival heals

class TestRevivalRestoresResources:

    @pytest.mark.parametrize("npc_id", [MERCHANT, NO_ROLE])
    def test_internal_revival_restores_every_resource(self, api, law_world, npc_id):
        _dead(law_world, npc_id)
        _drain(law_world, npc_id)
        resp = _status(api, npc_id, "alive")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "alive"
        assert _resources(law_world, npc_id) == {"health": (100, 100), "mana": (50, 50), "energy": (50, 50),
                                                 "stamina": (50, 50)}

    def test_internal_revival_of_a_knocked_out_guard_heals_it(self, api, law_world):
        _drain(law_world, GUARD_POST, current=-7)
        exec_(law_world, "UPDATE characters SET unconscious_until = '2999-01-01 00:00:00' WHERE id = :g", g=GUARD_POST)
        assert _status(api, GUARD_POST, "alive").status_code == 200
        assert _full(law_world, GUARD_POST)
        assert q(law_world, "SELECT unconscious_until FROM characters WHERE id = :g", g=GUARD_POST) is None

    def test_revival_never_touches_another_npc(self, api, law_world):
        _dead(law_world, MERCHANT)
        _drain(law_world, MERCHANT)
        _drain(law_world, NO_ROLE)
        _status(api, MERCHANT, "alive")
        assert _resources(law_world, NO_ROLE)["health"] == (0, 100)

    def test_revival_without_an_attributes_row_still_succeeds(self, api, law_world):
        _dead(law_world, NO_ROLE)
        assert q(law_world, "SELECT COUNT(*) FROM character_attributes WHERE character_id = :c", c=NO_ROLE) == 0
        resp = _status(api, NO_ROLE, "alive")
        assert resp.status_code == 200 and resp.json()["status"] == "alive"

    def test_failing_heal_does_not_block_the_internal_revival(self, api, law_world, monkeypatch):
        def boom(db, npc_id):
            raise OperationalError("UPDATE character_attributes", {}, Exception("table is locked"))

        monkeypatch.setattr(law_crud, "heal_guard", boom)
        _dead(law_world, MERCHANT)
        _drain(law_world, MERCHANT)
        resp = _status(api, MERCHANT, "alive")
        assert resp.status_code == 200, resp.text
        assert q(law_world, "SELECT npc_status FROM characters WHERE id = :n", n=MERCHANT) == "alive"
        assert _resources(law_world, MERCHANT)["health"] == (0, 100)          # heal failed, revival kept

    def test_admin_dead_to_alive_restores_every_resource(self, api, law_world):
        _dead(law_world, MERCHANT)
        _drain(law_world, MERCHANT)
        resp = _admin_update(api, MERCHANT, {"npc_status": "alive"})
        assert resp.status_code == 200, resp.text
        assert q(law_world, "SELECT npc_status FROM characters WHERE id = :n", n=MERCHANT) == "alive"
        assert _full(law_world, MERCHANT)

    def test_admin_update_of_a_living_npc_does_not_heal(self, api, law_world):
        """Only the dead -> alive transition is a revival; editing a living NPC leaves its resources alone."""
        _drain(law_world, MERCHANT, current=10)
        assert _admin_update(api, MERCHANT, {"npc_status": "alive"}).status_code == 200
        assert _resources(law_world, MERCHANT)["health"] == (10, 100)

    def test_admin_kill_does_not_heal(self, api, law_world):
        _drain(law_world, MERCHANT, current=10)
        assert _admin_update(api, MERCHANT, {"npc_status": "dead"}).status_code == 200
        assert _resources(law_world, MERCHANT)["health"] == (10, 100)

    def test_failing_heal_does_not_block_the_admin_revival(self, api, law_world, monkeypatch):
        def boom(db, npc_id):
            raise OperationalError("UPDATE character_attributes", {}, Exception("deadlock"))

        monkeypatch.setattr(law_crud, "heal_guard", boom)
        _dead(law_world, MERCHANT)
        _drain(law_world, MERCHANT)
        resp = _admin_update(api, MERCHANT, {"npc_status": "alive"})
        assert resp.status_code == 200, resp.text
        assert q(law_world, "SELECT npc_status FROM characters WHERE id = :n", n=MERCHANT) == "alive"

    def test_admin_revival_requires_the_permission(self, api, law_world):
        _dead(law_world, MERCHANT)
        _drain(law_world, MERCHANT)
        as_user(USER_ALPHA, "user", [])
        resp = api.put(f"/characters/admin/npcs/{MERCHANT}", json={"npc_status": "alive"},
                       headers={"Authorization": "Bearer t"})
        assert resp.status_code == 403
        assert q(law_world, "SELECT npc_status FROM characters WHERE id = :n", n=MERCHANT) == "dead"
        assert _resources(law_world, MERCHANT)["health"] == (0, 100)


# =============================================================================================== fix 4: journal reason

@pytest.mark.usefixtures("force_witnessed")
class TestKillJournalReason:

    def test_knocked_out_guard_is_journalled_as_defeated(self, api, law_world):
        resp = _status(api, GUARD, "dead", killer_character_ids=[ALPHA], battle_id=77)
        assert resp.status_code == 200, resp.text
        assert resp.json()["knocked_out_until"] is not None and resp.json()["status"] == "alive"
        origin = [r for r in log_rows(law_world, ALPHA) if not r[4]]
        assert origin and origin[0][11] == f"Повержен стражник «Стражник» (#{GUARD}) в бою #77"
        assert not any("Убит" in (r[11] or "") for r in log_rows(law_world, ALPHA))

    def test_non_guard_kill_reason_is_unchanged(self, api, law_world):
        _status(api, MERCHANT, "dead", killer_character_ids=[ALPHA], battle_id=77)
        origin = [r for r in log_rows(law_world, ALPHA) if not r[4]]
        assert origin[0][11] == f"Убит NPC «Лавочник» (#{MERCHANT}) в бою #77"

    def test_reason_helper(self, law_world):
        db = law_world()
        try:
            from models import Character
            guard = db.get(Character, GUARD)
            merchant = db.get(Character, MERCHANT)
            no_role = db.get(Character, NO_ROLE)
            assert reputation_crud.npc_kill_reason(guard, None) == f"Повержен стражник «Стражник» (#{GUARD})"
            assert reputation_crud.npc_kill_reason(merchant, 5) == f"Убит NPC «Лавочник» (#{MERCHANT}) в бою #5"
            assert reputation_crud.npc_kill_reason(no_role, None) == f"Убит NPC «Безымянный» (#{NO_ROLE})"
        finally:
            db.close()


# =============================================================================================== fix 5: auto-resolve

def _expire(f, enc_id):
    exec_(f, "UPDATE law_encounters SET expires_at = '2000-01-01 00:00:00' WHERE id = :e", e=enc_id)


def _auto_resolve(f, enc_id):
    db = f()
    try:
        return asyncio.run(law_flows.auto_resolve(db, enc_id))
    finally:
        db.close()


class TestAutoResolveSkipsAFight:

    def test_fight_chosen_during_the_move_is_never_auto_jailed(self, law_world):
        set_wanted(law_world, ALPHA, R_OST, 150)
        enc_id = make_encounter(law_world)
        _expire(law_world, enc_id)

        async def fight_chosen_meanwhile(*_a, **_k):
            exec_(law_world, "UPDATE law_encounters SET status = 'fighting' WHERE id = :e", e=enc_id)
            return False

        law_world.prepare_move.side_effect = fight_chosen_meanwhile
        assert _auto_resolve(law_world, enc_id) == []
        assert encounter(law_world, enc_id).status == "fighting"
        row = char_row(law_world, ALPHA)
        assert row.jailed_until is None and row.current_location_id != L_JAIL
        assert row.law_encounter_id == enc_id
        assert q(law_world, "SELECT COUNT(*) FROM law_jail_terms") == 0
        assert q(law_world, "SELECT COUNT(*) FROM law_log WHERE event_key = :k", k=f"law:auto:{enc_id}") == 0

    def test_fight_chosen_before_the_lock_is_never_auto_fined(self, law_world, monkeypatch):
        set_wanted(law_world, ALPHA, R_PASHNI, 150)
        set_gold(law_world, ALPHA, 1000)
        enc_id = make_encounter(law_world, location_id=L_FARM)          # region 11: no jail -> forced fine
        _expire(law_world, enc_id)
        real_lock = law_crud.lock_character

        def lock_after_fight(db, character_id):
            # another request (the player's «драться») commits the fight just before the row lock
            db.execute(law_crud.text("UPDATE law_encounters SET status = 'fighting' WHERE id = :e"), {"e": enc_id})
            db.commit()
            return real_lock(db, character_id)

        monkeypatch.setattr(law_crud, "lock_character", lock_after_fight)
        assert _auto_resolve(law_world, enc_id) == []
        assert encounter(law_world, enc_id).status == "fighting"
        assert gold(law_world, ALPHA) == 1000 and wanted(law_world, ALPHA, R_PASHNI) == 150
        assert q(law_world, "SELECT COUNT(*) FROM law_log WHERE event_key = :k", k=f"law:auto:{enc_id}") == 0

    def test_already_fighting_encounter_is_skipped(self, law_world):
        set_wanted(law_world, ALPHA, R_OST, 150)
        enc_id = make_encounter(law_world)
        _expire(law_world, enc_id)
        exec_(law_world, "UPDATE law_encounters SET status = 'fighting' WHERE id = :e", e=enc_id)
        assert _auto_resolve(law_world, enc_id) == []
        assert encounter(law_world, enc_id).status == "fighting"
        law_world.prepare_move.assert_not_called()

    def test_pending_encounter_is_still_auto_jailed(self, law_world):
        set_wanted(law_world, ALPHA, R_OST, 150)
        enc_id = make_encounter(law_world)
        _expire(law_world, enc_id)
        notices = _auto_resolve(law_world, enc_id)
        assert len(notices) == 1
        assert encounter(law_world, enc_id).status == "jailed"
        assert char_row(law_world, ALPHA).current_location_id == L_JAIL

    def test_pending_encounter_is_still_auto_fined(self, law_world):
        set_wanted(law_world, ALPHA, R_PASHNI, 150)
        set_gold(law_world, ALPHA, 1000)
        enc_id = make_encounter(law_world, location_id=L_FARM)
        _expire(law_world, enc_id)
        assert len(_auto_resolve(law_world, enc_id)) == 1
        assert encounter(law_world, enc_id).status == "auto_fined"
        assert gold(law_world, ALPHA) == 850

    def test_player_choice_send_to_jail_still_accepts_open_statuses(self, law_world):
        """The default ``statuses`` (every open status) is unchanged for the non-automatic callers."""
        import law_core as lc
        assert lc.ENC_PENDING in lc.ENC_OPEN and lc.ENC_FIGHTING in lc.ENC_OPEN
        import inspect
        assert inspect.signature(law_flows.send_to_jail).parameters["statuses"].default == lc.ENC_OPEN


# =============================================================================================== fix 6: «Розыска нет»

ADMIN_BASE = "/characters/admin/law"


def _clear(api, region_id=None, request_id=None):
    return api.post(f"{ADMIN_BASE}/characters/{ALPHA}/clear-wanted",
                    json={"region_id": region_id, "reason": "Дело закрыто", "request_id": request_id or rid()})


class TestClearWithoutWanted:

    def test_region_without_a_wanted_row(self, api, law_world):
        set_wanted(law_world, ALPHA, R_OST, 300)                       # wanted elsewhere only
        as_admin()
        resp = _clear(api, region_id=R_PASHNI)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"message": "Розыска нет", "cleared_region_ids": [], "duplicate": False}
        assert q(law_world, "SELECT COUNT(*) FROM law_log") == 0
        assert wanted(law_world, ALPHA, R_OST) == 300

    def test_region_with_a_zero_wanted_row(self, api, law_world):
        set_wanted(law_world, ALPHA, R_OST, 0)
        as_admin()
        resp = _clear(api, region_id=R_OST)
        assert resp.json()["message"] == "Розыска нет" and resp.json()["cleared_region_ids"] == []
        assert q(law_world, "SELECT COUNT(*) FROM law_log") == 0

    def test_all_regions_without_wanted_writes_nothing(self, api, law_world):
        as_admin()
        resp = _clear(api)
        assert resp.json() == {"message": "Розыска нет", "cleared_region_ids": [], "duplicate": False}
        assert q(law_world, "SELECT COUNT(*) FROM law_log") == 0

    def test_replay_of_an_empty_clear_answers_the_same(self, api, law_world):
        as_admin()
        request_id = rid()
        assert _clear(api, region_id=R_OST, request_id=request_id).json()["message"] == "Розыска нет"
        again = _clear(api, region_id=R_OST, request_id=request_id)
        assert again.status_code == 200 and again.json()["cleared_region_ids"] == []
        assert q(law_world, "SELECT COUNT(*) FROM law_log") == 0

    def test_region_with_wanted_is_still_cleared_and_logged(self, api, law_world):
        set_wanted(law_world, ALPHA, R_OST, 300)
        as_admin()
        resp = _clear(api, region_id=R_OST)
        assert resp.json()["cleared_region_ids"] == [R_OST]
        assert wanted(law_world, ALPHA, R_OST) == 0
        assert q(law_world, "SELECT COUNT(*) FROM law_log WHERE action = 'staff_clear'") == 1


# =============================================================================================== fix 7: killer list

class TestKillerListCap:

    def test_schema_dedupes_and_keeps_the_first_200(self):
        ids = [5, 5, 3, 5, 3] + list(range(1000, 1300))
        req = schemas.UpdateNpcStatusRequest(status="dead", killer_character_ids=ids)
        assert len(req.killer_character_ids) == schemas.NPC_KILLER_IDS_MAX == 200
        assert req.killer_character_ids[:3] == [5, 3, 1000]                 # order of first appearance
        assert req.killer_character_ids[-1] == 1197
        assert len(set(req.killer_character_ids)) == 200

    @pytest.mark.parametrize("ids,expected", [(None, None), ([], []), ([7, 7, 7], [7])])
    def test_schema_small_lists(self, ids, expected):
        assert schemas.UpdateNpcStatusRequest(status="dead", killer_character_ids=ids).killer_character_ids == expected

    @pytest.mark.usefixtures("force_witnessed")
    def test_big_winning_team_kills_the_npc_and_rewards_once(self, api, law_world):
        killers = [ALPHA, ALPHA, BETA] + list(range(5000, 5080)) + [ALPHA]        # 84 ids, > 50, duplicates
        resp = _status(api, MERCHANT, "dead", killer_character_ids=killers, battle_id=91)
        assert resp.status_code == 200, resp.text
        assert resp.json()["killed"] is True
        assert q(law_world, "SELECT npc_status FROM characters WHERE id = :n", n=MERCHANT) == "dead"
        origin = [r for r in log_rows(law_world, ALPHA) if not r[4]]
        assert len(origin) == 1                                               # deduped: one kill event
        assert value(law_world, ALPHA, R_OST) is not None and value(law_world, BETA, R_OST) is not None

    def test_more_than_200_ids_is_not_a_422(self, api, law_world):
        resp = _status(api, MERCHANT, "dead", killer_character_ids=list(range(6000, 6400)), battle_id=92)
        assert resp.status_code == 200, resp.text
        assert q(law_world, "SELECT npc_status FROM characters WHERE id = :n", n=MERCHANT) == "dead"

    def test_bad_id_type_is_still_a_422(self, api, law_world):
        resp = _status(api, MERCHANT, "dead", killer_character_ids=["1; DROP TABLE characters"])
        assert resp.status_code == 422
        assert q(law_world, "SELECT npc_status FROM characters WHERE id = :n", n=MERCHANT) == "alive"


# =============================================================================================== fix 8: fame key

class TestFameRepKey:

    @pytest.mark.parametrize("idem", ["ev:1", "x" * (191 - len("fame:rep:"))])
    def test_short_keys_are_unchanged(self, idem):
        assert reputation_crud.fame_rep_key(idem) == f"fame:rep:{idem}"

    def test_long_key_is_hashed(self):
        idem = "x" * (191 - len("fame:rep:") + 1)
        key = reputation_crud.fame_rep_key(idem)
        assert key == "fame:rep:sha1:" + hashlib.sha1(idem.encode("utf-8")).hexdigest()
        assert len(key) <= 191

    def test_longest_allowed_reputation_key_fits(self):
        key = reputation_crud.fame_rep_key("я" * 191)
        assert len(key) <= 191 and key.startswith("fame:rep:sha1:")

    def test_distinct_long_keys_with_a_common_head_do_not_collide(self):
        head = "region_event:" + "a" * 180
        a, b = head + ":1", head + ":2"
        assert reputation_crud.fame_rep_key(a) != reputation_crud.fame_rep_key(b)
        assert reputation_crud.fame_rep_key(a) == reputation_crud.fame_rep_key(a)   # deterministic

    def test_two_long_reputation_events_give_two_fame_events(self, law_world):
        from tests.reputation_world import apply
        head = "ev:" + "z" * 180
        for tail in ("1", "2"):
            apply(law_world, character_id=ALPHA, region_id=R_OST, action="region_event_help",
                  idem_key=f"{head}:{tail}", delta=100)
        log = renown_log(law_world, ALPHA)
        assert len(log) == 2 and log[0][0] != log[1][0]
        assert all(k.startswith("fame:rep:sha1:") and len(k) <= 191 for k, *_ in log)
        assert renown(law_world, ALPHA) == (100, 0)
        # a replay of the same long reputation event adds no second fame
        apply(law_world, character_id=ALPHA, region_id=R_OST, action="region_event_help", idem_key=f"{head}:1",
              delta=100)
        assert renown(law_world, ALPHA) == (100, 0)
