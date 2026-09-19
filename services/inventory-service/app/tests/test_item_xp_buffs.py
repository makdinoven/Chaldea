"""
FEAT-168 §3.9 / §3.9-bis — flexible XP books.

An item can now accelerate several XP sources at once (`item_xp_buffs`), the
legacy `buff_type/buff_value/buff_duration_minutes` triple stays as a fallback,
and `crud.get_xp_multiplier` folds the umbrella type «ко всему опыту персонажа»
into every granular character source.

Pinned here:
  * `get_xp_multiplier` per buff type, including the umbrella folding rule
    (quest 0.25 + character_xp_bonus 0.10 → exactly ×1.35);
  * profession XP is NOT touched by character books, and character sources are
    not touched by the profession book;
  * `item_xp_buffs` round-trip (rows read back from the DB with the real column
    names), replace-all semantics and the clearing of the legacy columns;
  * every Russian validation message of §3.9-bis C;
  * `use-buff-item` applies EVERY row — asserted by reading `active_buffs` back
    from the DB — and its message lists all of them with the right label;
  * the legacy fallback for items written before this feature.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

import crud
import auth_http
import models

# FEAT-171 I3: `GET /inventory/items/{id}` is now the thin public card; the fat
# item template moved to the internal twin, which requires `X-Internal-Token`.
_INTERNAL_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _INTERNAL_TOKEN}


@pytest.fixture(autouse=True)
def _pin_internal_token(monkeypatch):
    """`verify_internal_token` reads a module-level constant — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _INTERNAL_TOKEN)

import schemas
from auth_http import UserRead, get_current_user_via_http

from tests.feat165_helpers import (
    assign_profession, ensure_characters, seed_professions,
)


HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update", "items:delete"]}

QUEST = schemas.XP_BUFF_CHARACTER_QUEST
ALL_CHAR = schemas.XP_BUFF_CHARACTER_ALL
BATTLE = schemas.XP_BUFF_CHARACTER_BATTLE
PROFESSION = schemas.XP_BUFF_PROFESSION
GATHERING = schemas.XP_BUFF_GATHERING


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _body(**overrides):
    body = {
        "name": "Книга опыта",
        "item_level": 1,
        "item_type": "consumable",
        "item_rarity": "common",
        "max_stack_size": 10,
        "is_unique": False,
    }
    body.update(overrides)
    return body


def _post(client, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.post("/inventory/items", json=body, headers=HEADERS)


def _put(client, item_id, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.put(f"/inventory/items/{item_id}", json=body, headers=HEADERS)


def _messages(resp):
    detail = resp.json()["detail"]
    if isinstance(detail, str):
        return detail
    return " | ".join(str(err.get("msg", "")) for err in detail)


_XP_COLUMNS = ("buff_type", "value", "duration_minutes")


def _read_xp_buffs(db, item_id):
    """Raw-SQL readback with the real column names."""
    cols = ", ".join(_XP_COLUMNS)
    rows = db.execute(
        text(f"SELECT {cols} FROM item_xp_buffs WHERE item_id = :iid ORDER BY id"),
        {"iid": item_id},
    ).fetchall()
    return [dict(zip(_XP_COLUMNS, row)) for row in rows]


def _read_active_buffs(db, character_id):
    db.expire_all()
    rows = db.execute(
        text("SELECT buff_type, value, source_item_name FROM active_buffs "
             "WHERE character_id = :cid ORDER BY buff_type"),
        {"cid": character_id},
    ).fetchall()
    return [{"buff_type": r[0], "value": r[1], "source_item_name": r[2]} for r in rows]


# ===========================================================================
# 1. crud.get_xp_multiplier
# ===========================================================================

class TestXpMultiplier:

    def test_no_buffs_is_one(self, db_session):
        for buff_type in schemas.ALLOWED_BUFF_TYPES:
            assert crud.get_xp_multiplier(db_session, 1, buff_type) == 1.0

    def test_default_argument_is_profession_xp(self, db_session):
        crud.apply_buff(db_session, character_id=1, buff_type=PROFESSION,
                        value=0.5, duration_minutes=60, source_name="Книга")
        db_session.commit()
        assert crud.get_xp_multiplier(db_session, 1) == 1.5
        assert crud.get_xp_multiplier(db_session, 1, PROFESSION) == 1.5

    @pytest.mark.parametrize("buff_type", sorted(schemas.ALLOWED_BUFF_TYPES))
    def test_each_type_multiplies_only_itself(self, db_session, buff_type):
        crud.apply_buff(db_session, character_id=1, buff_type=buff_type,
                        value=0.5, duration_minutes=60, source_name="Книга")
        db_session.commit()

        assert crud.get_xp_multiplier(db_session, 1, buff_type) == 1.5
        for other in sorted(schemas.ALLOWED_BUFF_TYPES):
            if other == buff_type:
                continue
            expected = 1.5 if buff_type == ALL_CHAR and other in schemas.XP_BUFF_PARENTS \
                else 1.0
            assert crud.get_xp_multiplier(db_session, 1, other) == expected, (
                f"{buff_type} не должен влиять на {other}"
            )

    def test_umbrella_folds_into_every_character_source(self, db_session):
        crud.apply_buff(db_session, character_id=1, buff_type=ALL_CHAR,
                        value=0.10, duration_minutes=60, source_name="Общая книга")
        db_session.commit()
        for source in schemas.XP_BUFF_PARENTS:
            assert crud.get_xp_multiplier(db_session, 1, source) == pytest.approx(1.10)

    def test_umbrella_does_not_touch_profession_or_gathering(self, db_session):
        crud.apply_buff(db_session, character_id=1, buff_type=ALL_CHAR,
                        value=0.10, duration_minutes=60, source_name="Общая книга")
        db_session.commit()
        assert crud.get_xp_multiplier(db_session, 1, PROFESSION) == 1.0
        assert crud.get_xp_multiplier(db_session, 1, GATHERING) == 1.0

    def test_quest_book_plus_umbrella_is_exactly_1_35(self, db_session):
        """§3.9-bis A: +25 % за задания и +10 % на весь опыт дают ×1.35."""
        crud.apply_buff(db_session, character_id=1, buff_type=QUEST,
                        value=0.25, duration_minutes=60, source_name="Книга заданий")
        crud.apply_buff(db_session, character_id=1, buff_type=ALL_CHAR,
                        value=0.10, duration_minutes=60, source_name="Общая книга")
        db_session.commit()

        assert crud.get_xp_multiplier(db_session, 1, QUEST) == pytest.approx(1.35)
        # другие источники получают только зонтик
        assert crud.get_xp_multiplier(db_session, 1, BATTLE) == pytest.approx(1.10)

    def test_buff_is_per_character(self, db_session):
        crud.apply_buff(db_session, character_id=1, buff_type=QUEST,
                        value=0.25, duration_minutes=60, source_name="Книга")
        db_session.commit()
        assert crud.get_xp_multiplier(db_session, 2, QUEST) == 1.0

    def test_expired_buff_is_ignored_and_removed(self, db_session):
        buff = models.ActiveBuff(
            character_id=1, buff_type=QUEST, value=0.5,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            source_item_name="Просроченная книга",
        )
        db_session.add(buff)
        db_session.commit()

        assert crud.get_xp_multiplier(db_session, 1, QUEST) == 1.0
        db_session.commit()
        assert _read_active_buffs(db_session, 1) == []

    def test_batch_multipliers(self, db_session):
        crud.apply_buff(db_session, character_id=1, buff_type=QUEST,
                        value=0.25, duration_minutes=60, source_name="Книга")
        crud.apply_buff(db_session, character_id=1, buff_type=ALL_CHAR,
                        value=0.10, duration_minutes=60, source_name="Общая")
        db_session.commit()

        result = crud.get_xp_multipliers(db_session, 1, [QUEST, BATTLE, PROFESSION])
        assert result[QUEST] == pytest.approx(1.35)
        assert result[BATTLE] == pytest.approx(1.10)
        assert result[PROFESSION] == 1.0


class TestProfessionXpIsNotTouchedByCharacterBooks:

    @pytest.fixture()
    def prof_env(self, db_session):
        ensure_characters(db_session)
        seed_professions(db_session)
        assign_profession(db_session, 1, "blacksmith", rank=1)
        return crud.get_character_profession(db_session, 1)

    def test_character_books_do_not_boost_profession_xp(self, db_session, prof_env):
        for buff_type in (ALL_CHAR, QUEST, BATTLE, GATHERING):
            crud.apply_buff(db_session, character_id=1, buff_type=buff_type,
                            value=1.0, duration_minutes=60, source_name="Книга")
        db_session.commit()

        result = crud.award_profession_xp(db_session, prof_env, 10)
        db_session.commit()

        assert result["xp_earned"] == 10
        db_session.expire_all()
        assert crud.get_character_profession(db_session, 1).experience == 10

    def test_profession_book_still_boosts_profession_xp(self, db_session, prof_env):
        crud.apply_buff(db_session, character_id=1, buff_type=PROFESSION,
                        value=0.5, duration_minutes=60, source_name="Книга кузнеца")
        db_session.commit()

        result = crud.award_profession_xp(db_session, prof_env, 10)
        db_session.commit()

        assert result["xp_earned"] == 15
        db_session.expire_all()
        assert crud.get_character_profession(db_session, 1).experience == 15


# ===========================================================================
# 2. item_xp_buffs round-trip + validation
# ===========================================================================

_ROW_QUEST = {"buff_type": QUEST, "value": 0.25, "duration_minutes": 60}
_ROW_PROF = {"buff_type": PROFESSION, "value": 0.10, "duration_minutes": 30}


class TestXpBuffRoundTrip:

    def test_create_with_three_rows(self, client, db_session):
        rows = [_ROW_QUEST, _ROW_PROF,
                {"buff_type": GATHERING, "value": 0.5, "duration_minutes": 120}]
        resp = _post(client, _body(xp_buffs=rows))
        assert resp.status_code == 201, resp.text
        item_id = resp.json()["id"]

        assert len(resp.json()["xp_buffs"]) == 3
        assert _read_xp_buffs(db_session, item_id) == rows

        got = client.get(f"/inventory/internal/items/{item_id}", headers=_INTERNAL_HEADERS)
        assert [r["buff_type"] for r in got.json()["xp_buffs"]] == \
            [QUEST, PROFESSION, GATHERING]

    def test_item_without_rows_returns_empty_list(self, client, db_session):
        item_id = _post(client, _body(name="Просто зелье")).json()["id"]
        assert client.get(f"/inventory/internal/items/{item_id}", headers=_INTERNAL_HEADERS).json()["xp_buffs"] == []
        assert _read_xp_buffs(db_session, item_id) == []

    def test_saving_rows_clears_the_legacy_columns(self, client, db_session):
        """§3.9-bis B: ровно один источник правды."""
        item_id = _post(client, _body(
            buff_type=PROFESSION, buff_value=0.2, buff_duration_minutes=45,
        )).json()["id"]
        db_session.expire_all()
        assert db_session.query(models.Items).get(item_id).buff_type == PROFESSION

        resp = _put(client, item_id, _body(
            buff_type=PROFESSION, buff_value=0.2, buff_duration_minutes=45,
            xp_buffs=[_ROW_QUEST],
        ))
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        stored = db_session.query(models.Items).get(item_id)
        assert stored.buff_type is None
        assert stored.buff_value is None
        assert stored.buff_duration_minutes is None
        assert _read_xp_buffs(db_session, item_id) == [_ROW_QUEST]

    def test_empty_list_clears_the_legacy_columns(self, client, db_session):
        """Присланный пустой список — это «ускорения опыта нет».

        Ревью #1 §5: если чистить тройку только при непустом списке, админ,
        удаливший последнюю строку, получит воскресший старый бафф из
        `get_item_xp_buffs`. Присланный список авторитетен, даже пустой.
        """
        item_id = _post(client, _body(
            buff_type=PROFESSION, buff_value=0.2, buff_duration_minutes=45,
        )).json()["id"]

        resp = _put(client, item_id, _body(
            buff_type=PROFESSION, buff_value=0.2, buff_duration_minutes=45,
            xp_buffs=[],
        ))
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        stored = db_session.query(models.Items).get(item_id)
        assert stored.buff_type is None
        assert stored.buff_value is None
        assert stored.buff_duration_minutes is None
        assert _read_xp_buffs(db_session, item_id) == []
        assert crud.get_item_xp_buffs(db_session, stored) == []

    def test_legacy_only_payload_keeps_the_triple(self, client, db_session):
        """Клиент, ничего не знающий про xp_buffs, работает как раньше.

        Ключ `xp_buffs` не прислан вообще — ни на создании, ни на обновлении,
        поэтому старая тройка не трогается и `get_item_xp_buffs` отдаёт её.
        """
        item_id = _post(client, _body(
            buff_type=PROFESSION, buff_value=0.2, buff_duration_minutes=45,
        )).json()["id"]

        db_session.expire_all()
        stored = db_session.query(models.Items).get(item_id)
        assert stored.buff_type == PROFESSION
        assert crud.get_item_xp_buffs(db_session, stored) == [
            {"buff_type": PROFESSION, "value": 0.2, "duration_minutes": 45}
        ]

        resp = _put(client, item_id, _body(
            buff_type=PROFESSION, buff_value=0.2, buff_duration_minutes=45,
            description="только описание",
        ))
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        assert db_session.query(models.Items).get(item_id).buff_type == PROFESSION

    def test_put_replaces_rows(self, client, db_session):
        item_id = _post(client, _body(xp_buffs=[_ROW_QUEST, _ROW_PROF])).json()["id"]
        _put(client, item_id, _body(xp_buffs=[_ROW_PROF]))
        assert _read_xp_buffs(db_session, item_id) == [_ROW_PROF]

    def test_put_omitting_the_key_leaves_rows(self, client, db_session):
        item_id = _post(client, _body(xp_buffs=[_ROW_QUEST])).json()["id"]
        _put(client, item_id, _body(description="только описание"))
        assert _read_xp_buffs(db_session, item_id) == [_ROW_QUEST]

    def test_delete_item_cascades_to_xp_rows(self, client, db_session):
        item_id = _post(client, _body(xp_buffs=[_ROW_QUEST])).json()["id"]
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.delete(f"/inventory/items/{item_id}",
                                 headers=HEADERS)
        assert resp.status_code == 204, resp.text
        db_session.expire_all()
        assert _read_xp_buffs(db_session, item_id) == []


class TestXpBuffValidation:

    def test_unknown_buff_type(self, client):
        resp = _post(client, _body(xp_buffs=[dict(_ROW_QUEST, buff_type="xp_hacks")]))
        assert resp.status_code == 422
        assert "Недопустимый тип опыта" in _messages(resp)

    @pytest.mark.parametrize("buff_type", sorted(schemas.ALLOWED_BUFF_TYPES))
    def test_every_whitelisted_type_is_accepted(self, client, buff_type):
        resp = _post(client, _body(name=f"Книга {buff_type}",
                                   xp_buffs=[dict(_ROW_QUEST, buff_type=buff_type)]))
        assert resp.status_code == 201, resp.text

    @pytest.mark.parametrize("value", [0, -0.5, 10.5])
    def test_value_out_of_range(self, client, value):
        resp = _post(client, _body(xp_buffs=[dict(_ROW_QUEST, value=value)]))
        assert resp.status_code == 422
        assert "Прибавка к опыту должна быть больше 0 и не больше 1000 %" in _messages(resp)

    def test_value_boundary_accepted(self, client, db_session):
        resp = _post(client, _body(xp_buffs=[dict(_ROW_QUEST, value=10.0)]))
        assert resp.status_code == 201, resp.text
        assert _read_xp_buffs(db_session, resp.json()["id"])[0]["value"] == 10.0

    @pytest.mark.parametrize("minutes", [0, -1, 10081])
    def test_duration_out_of_range(self, client, minutes):
        resp = _post(client, _body(xp_buffs=[dict(_ROW_QUEST, duration_minutes=minutes)]))
        assert resp.status_code == 422
        assert "Длительность баффа опыта должна быть от 1 до 10080 минут" in _messages(resp)

    @pytest.mark.parametrize("minutes", [1, 10080])
    def test_duration_boundaries_accepted(self, client, minutes):
        resp = _post(client, _body(name=f"Книга {minutes}",
                                   xp_buffs=[dict(_ROW_QUEST, duration_minutes=minutes)]))
        assert resp.status_code == 201, resp.text

    def test_duplicate_buff_type(self, client):
        resp = _post(client, _body(xp_buffs=[_ROW_QUEST, dict(_ROW_QUEST, value=0.5)]))
        assert resp.status_code == 422
        assert "Один тип опыта можно указать у предмета только один раз" in _messages(resp)

    @pytest.mark.parametrize("item_type", ["weapon", "misc", "resource", "body"])
    def test_only_consumable_and_scroll(self, client, item_type):
        resp = _post(client, _body(item_type=item_type, xp_buffs=[_ROW_QUEST]))
        assert resp.status_code == 422
        assert "Ускорение опыта доступно только для расходников и свитков" in _messages(resp)

    @pytest.mark.parametrize("item_type", ["consumable", "scroll"])
    def test_consumable_and_scroll_pass(self, client, item_type):
        resp = _post(client, _body(name=f"Книга {item_type}", item_type=item_type,
                                   xp_buffs=[_ROW_QUEST]))
        assert resp.status_code == 201, resp.text

    def test_food_cannot_accelerate_xp(self, client):
        resp = _post(client, _body(is_food=True, xp_buffs=[_ROW_QUEST]))
        assert resp.status_code == 422
        assert "Еда не может ускорять опыт" in _messages(resp)

    def test_more_than_8_rows(self, client):
        rows = [{"buff_type": bt, "value": 0.1, "duration_minutes": 60}
                for bt in sorted(schemas.ALLOWED_BUFF_TYPES)]
        rows.append({"buff_type": "xp_hacks", "value": 0.1, "duration_minutes": 60})
        resp = _post(client, _body(xp_buffs=rows))
        assert resp.status_code == 422
        # 9 строк: ловится либо лимитом, либо белым списком типа
        assert ("Не больше 8 строк опыта у предмета" in _messages(resp)
                or "Недопустимый тип опыта" in _messages(resp))

    def test_exactly_8_rows_pass(self, client, db_session):
        rows = [{"buff_type": bt, "value": 0.1, "duration_minutes": 60}
                for bt in sorted(schemas.ALLOWED_BUFF_TYPES)]
        resp = _post(client, _body(xp_buffs=rows))
        assert resp.status_code == 201, resp.text
        assert len(_read_xp_buffs(db_session, resp.json()["id"])) == 8

    def test_legacy_buff_type_is_whitelisted(self, client):
        resp = _post(client, _body(buff_type="free_text_buff", buff_value=0.2,
                                   buff_duration_minutes=60))
        assert resp.status_code == 422
        assert "Недопустимый тип баффа" in _messages(resp)


class TestGetItemXpBuffs:
    """`crud.get_item_xp_buffs` — rows win, legacy triple is the fallback."""

    def _item(self, db_session, **kwargs):
        item = models.Items(name=kwargs.pop("name", "Книга"), item_level=1,
                            item_type="consumable", item_rarity="common",
                            max_stack_size=10, is_unique=False, **kwargs)
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)
        return item

    def test_legacy_columns_are_the_fallback(self, db_session):
        item = self._item(db_session, buff_type=PROFESSION, buff_value=0.2,
                          buff_duration_minutes=45)
        assert crud.get_item_xp_buffs(db_session, item) == [
            {"buff_type": PROFESSION, "value": 0.2, "duration_minutes": 45},
        ]

    def test_rows_win_over_legacy_columns(self, db_session):
        item = self._item(db_session, name="Смешанная", buff_type=PROFESSION,
                          buff_value=0.2, buff_duration_minutes=45)
        db_session.add(models.ItemXpBuff(item_id=item.id, buff_type=QUEST,
                                         value=0.25, duration_minutes=60))
        db_session.commit()

        assert crud.get_item_xp_buffs(db_session, item) == [
            {"buff_type": QUEST, "value": 0.25, "duration_minutes": 60},
        ]

    def test_incomplete_legacy_triple_yields_nothing(self, db_session):
        item = self._item(db_session, name="Недокнига", buff_type=PROFESSION)
        assert crud.get_item_xp_buffs(db_session, item) == []

    def test_plain_item_yields_nothing(self, db_session):
        assert crud.get_item_xp_buffs(db_session, self._item(db_session, name="Зелье")) == []


# ===========================================================================
# 3. POST /{cid}/use-buff-item
# ===========================================================================

@pytest.fixture()
def authed_client(client, db_session):
    from main import app

    ensure_characters(db_session)
    user = UserRead(id=1, username="owner", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _book(db_session, rows=(), legacy=None, name="Книга", is_food=False,
          item_type="consumable"):
    kwargs = {}
    if legacy:
        kwargs.update(buff_type=legacy[0], buff_value=legacy[1],
                      buff_duration_minutes=legacy[2])
    item = models.Items(name=name, item_level=1, item_type=item_type,
                        item_rarity="common", max_stack_size=10, is_unique=False,
                        is_food=is_food, **kwargs)
    db_session.add(item)
    db_session.flush()
    for row in rows:
        db_session.add(models.ItemXpBuff(item_id=item.id, **row))
    inv = models.CharacterInventory(character_id=1, item_id=item.id, quantity=2)
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return item, inv


class TestUseBuffItem:

    def test_three_rows_create_three_active_buffs(self, authed_client, db_session):
        rows = [
            {"buff_type": QUEST, "value": 0.25, "duration_minutes": 60},
            {"buff_type": PROFESSION, "value": 0.10, "duration_minutes": 30},
            {"buff_type": GATHERING, "value": 0.5, "duration_minutes": 120},
        ]
        item, inv = _book(db_session, rows, name="Большая книга")

        resp = authed_client.post("/inventory/1/use-buff-item",
                                  json={"inventory_item_id": inv.id})
        assert resp.status_code == 200, resp.text

        # --- DB state, not just the response
        stored = _read_active_buffs(db_session, 1)
        assert {b["buff_type"] for b in stored} == {QUEST, PROFESSION, GATHERING}
        assert all(b["source_item_name"] == "Большая книга" for b in stored)
        assert crud.get_xp_multiplier(db_session, 1, QUEST) == pytest.approx(1.25)
        assert crud.get_xp_multiplier(db_session, 1, PROFESSION) == pytest.approx(1.10)
        assert crud.get_xp_multiplier(db_session, 1, GATHERING) == pytest.approx(1.5)

        # --- response lists every buff
        data = resp.json()
        assert len(data["buffs"]) == 3
        assert data["buff_type"] == QUEST  # первый — ради совместимости
        assert "к опыту персонажа за задания" in data["message"]
        assert "к опыту профессии" in data["message"]
        assert "к опыту сбора" in data["message"]
        assert "+25%" in data["message"] and "на 60 мин" in data["message"]

    def test_one_item_is_consumed(self, authed_client, db_session):
        item, inv = _book(db_session, [{"buff_type": QUEST, "value": 0.25,
                                        "duration_minutes": 60}])
        authed_client.post("/inventory/1/use-buff-item",
                           json={"inventory_item_id": inv.id})
        db_session.expire_all()
        assert db_session.query(models.CharacterInventory).get(inv.id).quantity == 1

    @pytest.mark.parametrize("buff_type,label", [
        (PROFESSION, "к опыту профессии"),
        (GATHERING, "к опыту сбора"),
        (ALL_CHAR, "ко всему опыту персонажа"),
        (BATTLE, "к опыту персонажа за бои"),
        (schemas.XP_BUFF_CHARACTER_POST, "к опыту персонажа за отыгрыш"),
        (QUEST, "к опыту персонажа за задания"),
        (schemas.XP_BUFF_CHARACTER_TITLE, "к опыту персонажа за титулы"),
        (schemas.XP_BUFF_CHARACTER_PASS, "к опыту персонажа за боевой пропуск"),
    ])
    def test_message_is_type_aware(self, authed_client, db_session, buff_type, label):
        """ISSUES #5: раньше в сообщении всегда стояло «XP»."""
        item, inv = _book(db_session, [{"buff_type": buff_type, "value": 0.25,
                                        "duration_minutes": 60}])
        resp = authed_client.post("/inventory/1/use-buff-item",
                                  json={"inventory_item_id": inv.id})
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == f"Бафф активирован: +25% {label} на 60 мин"
        assert "XP" not in resp.json()["message"]

    def test_legacy_item_still_works(self, authed_client, db_session):
        item, inv = _book(db_session, legacy=(PROFESSION, 0.2, 45),
                          name="Старая книга")
        resp = authed_client.post("/inventory/1/use-buff-item",
                                  json={"inventory_item_id": inv.id})
        assert resp.status_code == 200, resp.text

        stored = _read_active_buffs(db_session, 1)
        assert len(stored) == 1
        assert stored[0]["buff_type"] == PROFESSION
        assert stored[0]["value"] == pytest.approx(0.2)
        assert resp.json()["message"] == "Бафф активирован: +20% к опыту профессии на 45 мин"

    def test_non_buff_item_rejected(self, authed_client, db_session):
        item, inv = _book(db_session, name="Обычное зелье")
        resp = authed_client.post("/inventory/1/use-buff-item",
                                  json={"inventory_item_id": inv.id})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Этот предмет не является баффовым"
        assert _read_active_buffs(db_session, 1) == []
        db_session.expire_all()
        assert db_session.query(models.CharacterInventory).get(inv.id).quantity == 2

    def test_reuse_refreshes_instead_of_stacking(self, authed_client, db_session):
        rows = [{"buff_type": QUEST, "value": 0.25, "duration_minutes": 60}]
        item, inv = _book(db_session, rows)
        for _ in range(2):
            resp = authed_client.post("/inventory/1/use-buff-item",
                                      json={"inventory_item_id": inv.id})
            assert resp.status_code == 200, resp.text

        assert len(_read_active_buffs(db_session, 1)) == 1
        assert crud.get_xp_multiplier(db_session, 1, QUEST) == pytest.approx(1.25)

    def test_foreign_character_is_refused(self, authed_client, db_session):
        rows = [{"buff_type": QUEST, "value": 0.25, "duration_minutes": 60}]
        item = models.Items(name="Чужая книга", item_level=1, item_type="consumable",
                            item_rarity="common", max_stack_size=10, is_unique=False)
        db_session.add(item)
        db_session.flush()
        for row in rows:
            db_session.add(models.ItemXpBuff(item_id=item.id, **row))
        inv = models.CharacterInventory(character_id=2, item_id=item.id, quantity=1)
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        resp = authed_client.post("/inventory/2/use-buff-item",
                                  json={"inventory_item_id": inv.id})
        assert resp.status_code in (403, 404)
        assert _read_active_buffs(db_session, 2) == []
