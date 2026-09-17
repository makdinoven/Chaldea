"""
FEAT-164 — eating food (POST /inventory/{cid}/eat-food) and food rejection
on every other consumption path.

eat-food:
  * success: exactly one item consumed (row deleted at 0), correct payload
    (modifiers from *_modifier, recovery from *_recovery, rarity, name) sent
    to character-attributes-service internal satiety endpoint
  * 409 «Вы уже наелись» / 400 passthrough — item kept
  * attributes unreachable / 5xx → 502 — item kept
  * in battle → 400 (attributes never called); dropped-out participant,
    active gathering and active dungeon → allowed
  * not food → 400; foreign / missing inventory row → 404
  * security: no token → 401, foreign character → 403, bad ids → 422
Food rejected by: use_item, use-buff-item, equip (fast slots),
internal consume_item (battle).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import text

import models
from auth_http import UserRead, get_current_user_via_http

CID = 1
OTHER_CID = 2
FOOD_ID = 300
PLAIN_ID = 301

SATIETY_OK = {
    "satiety": {
        "item_id": FOOD_ID,
        "source_item_name": "Жаркое из кабана",
        "rarity": "rare",
        "regen_bonus_percent": 100,
        "modifiers": {"strength": 2.0},
        "started_at": "2026-09-17T10:00:00",
        "expires_at": "2026-09-18T10:00:00",
        "remaining_seconds": 86400,
    },
    "stats_changed": True,
}


def _resp(status, body):
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.json.return_value = body
    r.text = str(body)
    return r


@pytest.fixture()
def env(client, db_session):
    from main import app

    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT)"
    ))
    db_session.execute(text("INSERT INTO characters (id, user_id, name) VALUES (1, 1, 'Hero'), (2, 99, 'Other')"))
    db_session.execute(text("DROP TABLE IF EXISTS dungeon_sessions"))
    db_session.execute(text(
        "CREATE TABLE dungeon_sessions (id INTEGER PRIMARY KEY, leader_character_id INTEGER, "
        "status TEXT, started_at TIMESTAMP, finished_at TIMESTAMP)"
    ))

    food = models.Items(
        id=FOOD_ID, name="Жаркое из кабана", item_level=1, item_type="consumable",
        item_rarity="rare", max_stack_size=20, is_unique=False, is_food=True,
        strength_modifier=2, res_fire_modifier=1.5, health_modifier=1,
        health_recovery=30, mana_recovery=0, energy_recovery=-5, stamina_recovery=4,
    )
    plain = models.Items(
        id=PLAIN_ID, name="Зелье", item_level=1, item_type="consumable",
        item_rarity="common", max_stack_size=20, is_unique=False,
        health_recovery=10,
    )
    db_session.add_all([food, plain])
    db_session.flush()
    food_row = models.CharacterInventory(character_id=CID, item_id=FOOD_ID, quantity=3)
    plain_row = models.CharacterInventory(character_id=CID, item_id=PLAIN_ID, quantity=2)
    other_row = models.CharacterInventory(character_id=OTHER_CID, item_id=FOOD_ID, quantity=1)
    db_session.add_all([food_row, plain_row, other_row])
    db_session.commit()

    user = UserRead(id=1, username="hero", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    yield {
        "client": client, "db": db_session,
        "food_row": food_row.id, "plain_row": plain_row.id, "other_row": other_row.id,
    }
    app.dependency_overrides.pop(get_current_user_via_http, None)
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text("DROP TABLE IF EXISTS dungeon_sessions"))
    db_session.commit()


def _qty(db, row_id):
    db.expire_all()
    row = db.query(models.CharacterInventory).get(row_id)
    return row.quantity if row else None


def _eat(env, row_id=None, cid=CID):
    return env["client"].post(
        f"/inventory/{cid}/eat-food",
        json={"inventory_item_id": row_id if row_id is not None else env["food_row"]},
    )


def _in_battle(db, cid=CID, dropped=False):
    db.execute(text("INSERT INTO battles (id, status) VALUES (77, 'in_progress')"))
    db.execute(
        text("INSERT INTO battle_participants (id, battle_id, character_id, dropped_out_at) VALUES (1, 77, :c, :d)"),
        {"c": cid, "d": datetime.utcnow() if dropped else None},
    )
    db.commit()


# ===========================================================================
# eat-food
# ===========================================================================

class TestEatFood:

    def test_success_consumes_one_and_sends_payload(self, env):
        with patch("main.httpx.post", return_value=_resp(201, SATIETY_OK)) as post:
            resp = _eat(env)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "Вы поели: Жаркое из кабана. Сытость на 24 ч"
        assert body["satiety"]["rarity"] == "rare"
        assert body["satiety"]["regen_bonus_percent"] == 100
        assert _qty(env["db"], env["food_row"]) == 2

        post.assert_called_once()
        url = post.call_args.args[0] if post.call_args.args else post.call_args.kwargs["url"]
        assert url.endswith(f"/attributes/internal/{CID}/satiety")
        sent = post.call_args.kwargs["json"]
        assert sent["item_id"] == FOOD_ID
        assert sent["source_item_name"] == "Жаркое из кабана"
        assert sent["rarity"] == "rare"
        assert sent["modifiers"] == {"strength": 2, "res_fire": 1.5, "health": 1}
        assert sent["recovery"] == {
            "health_recovery": 30, "mana_recovery": 0,
            "energy_recovery": 0,  # negative clamped
            "stamina_recovery": 4,
        }
        assert post.call_args.kwargs.get("timeout")

    def test_last_item_row_deleted(self, env):
        db = env["db"]
        db.query(models.CharacterInventory).get(env["food_row"]).quantity = 1
        db.commit()
        with patch("main.httpx.post", return_value=_resp(201, SATIETY_OK)):
            assert _eat(env).status_code == 200
        assert _qty(db, env["food_row"]) is None

    def test_already_satiated_409_item_kept(self, env):
        with patch("main.httpx.post", return_value=_resp(409, {"detail": "Вы уже наелись"})):
            resp = _eat(env)
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Вы уже наелись"
        assert _qty(env["db"], env["food_row"]) == 3

    def test_attributes_validation_400_passthrough_item_kept(self, env):
        with patch("main.httpx.post", return_value=_resp(400, {"detail": "Недопустимая редкость еды"})):
            resp = _eat(env)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Недопустимая редкость еды"
        assert _qty(env["db"], env["food_row"]) == 3

    @pytest.mark.parametrize("exc", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
    def test_attributes_unreachable_502_item_kept(self, env, exc):
        with patch("main.httpx.post", side_effect=exc):
            resp = _eat(env)
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Не удалось применить сытость, попробуйте позже"
        assert _qty(env["db"], env["food_row"]) == 3

    @pytest.mark.parametrize("status", [500, 404, 200, 422])
    def test_attributes_unexpected_status_502_item_kept(self, env, status):
        with patch("main.httpx.post", return_value=_resp(status, {"detail": "boom"})):
            resp = _eat(env)
        assert resp.status_code == 502
        assert _qty(env["db"], env["food_row"]) == 3

    def test_in_battle_rejected_without_calling_attributes(self, env):
        _in_battle(env["db"])
        with patch("main.httpx.post") as post:
            resp = _eat(env)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Нельзя есть во время боя"
        post.assert_not_called()
        assert _qty(env["db"], env["food_row"]) == 3

    def test_dropped_out_of_battle_can_eat(self, env):
        _in_battle(env["db"], dropped=True)
        with patch("main.httpx.post", return_value=_resp(201, SATIETY_OK)):
            assert _eat(env).status_code == 200

    def test_allowed_while_gathering(self, env):
        db = env["db"]
        now = datetime.utcnow()
        db.execute(
            text("INSERT INTO gathering_sessions (character_id, node_id, status, started_at, complete_at) "
                 "VALUES (:c, 1, 'active', :s, :e)"),
            {"c": CID, "s": (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
             "e": (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")},
        )
        db.commit()
        # sanity: the character really counts as gathering for other actions
        import crud
        assert crud.is_character_gathering(db, CID) is True
        with patch("main.httpx.post", return_value=_resp(201, SATIETY_OK)):
            resp = _eat(env)
        assert resp.status_code == 200, resp.text
        assert _qty(db, env["food_row"]) == 2

    def test_allowed_in_dungeon(self, env):
        db = env["db"]
        db.execute(text(
            "INSERT INTO dungeon_sessions (id, leader_character_id, status, started_at) "
            "VALUES (5, 1, 'active', '2026-09-17 10:00:00')"
        ))
        db.commit()
        with patch("main.httpx.post", return_value=_resp(201, SATIETY_OK)):
            assert _eat(env).status_code == 200

    def test_not_food_rejected(self, env):
        with patch("main.httpx.post") as post:
            resp = _eat(env, row_id=env["plain_row"])
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Этот предмет нельзя съесть"
        post.assert_not_called()
        assert _qty(env["db"], env["plain_row"]) == 2

    def test_other_characters_inventory_row_404(self, env):
        with patch("main.httpx.post") as post:
            resp = _eat(env, row_id=env["other_row"])
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Предмет не найден в инвентаре"
        post.assert_not_called()
        assert _qty(env["db"], env["other_row"]) == 1

    def test_missing_row_404(self, env):
        with patch("main.httpx.post") as post:
            assert _eat(env, row_id=424242).status_code == 404
        post.assert_not_called()

    def test_zero_quantity_row_404(self, env):
        db = env["db"]
        db.query(models.CharacterInventory).get(env["food_row"]).quantity = 0
        db.commit()
        with patch("main.httpx.post") as post:
            assert _eat(env).status_code == 404
        post.assert_not_called()


class TestEatFoodSecurity:

    def test_no_token_401(self, client, db_session):
        resp = client.post("/inventory/1/eat-food", json={"inventory_item_id": 1})
        assert resp.status_code == 401

    def test_foreign_character_403(self, env):
        with patch("main.httpx.post") as post:
            resp = _eat(env, row_id=env["other_row"], cid=OTHER_CID)
        assert resp.status_code == 403
        post.assert_not_called()
        assert _qty(env["db"], env["other_row"]) == 1

    def test_unknown_character_404(self, env):
        with patch("main.httpx.post") as post:
            resp = _eat(env, cid=31337)
        assert resp.status_code == 404
        post.assert_not_called()

    @pytest.mark.parametrize("bad", ["1 OR 1=1", "'; DROP TABLE items; --", None])
    def test_injection_in_body_422(self, env, bad):
        resp = env["client"].post(f"/inventory/{CID}/eat-food", json={"inventory_item_id": bad})
        assert resp.status_code == 422
        assert _qty(env["db"], env["food_row"]) == 3

    def test_injection_in_path_422(self, env):
        resp = env["client"].post("/inventory/1%20OR%201=1/eat-food", json={"inventory_item_id": 1})
        assert resp.status_code == 422


# ===========================================================================
# Food rejected on other consumption paths
# ===========================================================================

class TestFoodRejectedElsewhere:

    def test_use_item_rejects_food(self, env):
        with patch("main.httpx.post") as post, patch("main.httpx.AsyncClient") as ac:
            resp = env["client"].post(f"/inventory/{CID}/use_item", json={"item_id": FOOD_ID, "quantity": 1})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Еду нужно съесть"
        post.assert_not_called()
        ac.assert_not_called()
        assert _qty(env["db"], env["food_row"]) == 3

    def test_use_buff_item_rejects_food(self, env):
        resp = env["client"].post(f"/inventory/{CID}/use-buff-item", json={"inventory_item_id": env["food_row"]})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Еду нужно съесть"
        assert _qty(env["db"], env["food_row"]) == 3
        assert env["db"].query(models.ActiveBuff).count() == 0

    def test_equip_rejects_food_fast_slot(self, env):
        resp = env["client"].post(
            f"/inventory/{CID}/equip",
            json={"item_id": FOOD_ID, "inventory_item_id": env["food_row"]},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Еду нельзя положить в быстрый слот"
        assert _qty(env["db"], env["food_row"]) == 3

    def test_internal_consume_item_rejects_food(self, env):
        resp = env["client"].post(
            f"/inventory/internal/characters/{CID}/consume_item", json={"item_id": FOOD_ID},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Еду нельзя использовать в бою"
        assert _qty(env["db"], env["food_row"]) == 3

    def test_internal_consume_item_still_works_for_potions(self, env):
        resp = env["client"].post(
            f"/inventory/internal/characters/{CID}/consume_item", json={"item_id": PLAIN_ID},
        )
        assert resp.status_code == 200, resp.text
        assert _qty(env["db"], env["plain_row"]) == 1
