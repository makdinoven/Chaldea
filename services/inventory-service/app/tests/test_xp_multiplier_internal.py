"""
FEAT-168 §3.3.4 / §3.9-bis C — the internal XP-multiplier endpoints.

    GET /inventory/internal/characters/{cid}/xp-multiplier?buff_type=…
    GET /inventory/internal/characters/{cid}/xp-multipliers?buff_types=a,b,c

character-service and locations-service call these before writing character XP.
They are internal-only: guarded by `X-Internal-Token`, and **fail closed** when
the token is not configured at all (503, never "open").
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

import auth_http
import crud
import models
import schemas


_TOKEN = "test-internal-token"
_HEADERS = {"X-Internal-Token": _TOKEN}

QUEST = schemas.XP_BUFF_CHARACTER_QUEST
ALL_CHAR = schemas.XP_BUFF_CHARACTER_ALL
BATTLE = schemas.XP_BUFF_CHARACTER_BATTLE
PROFESSION = schemas.XP_BUFF_PROFESSION


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _TOKEN)


@pytest.fixture()
def characters(db_session):
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER)"))
    db_session.execute(text("INSERT INTO characters (id, user_id) VALUES (7, 1)"))
    db_session.commit()
    yield
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


def _single(client, cid=7, **params):
    return client.get(f"/inventory/internal/characters/{cid}/xp-multiplier",
                      params=params, headers=_HEADERS)


def _batch(client, cid=7, **params):
    return client.get(f"/inventory/internal/characters/{cid}/xp-multipliers",
                      params=params, headers=_HEADERS)


def _buff(db, buff_type, value, cid=7, minutes=60):
    crud.apply_buff(db, character_id=cid, buff_type=buff_type, value=value,
                    duration_minutes=minutes, source_name="Книга")
    db.commit()


# ===========================================================================
# 1. Single endpoint
# ===========================================================================

class TestXpMultiplierEndpoint:

    def test_no_buff_returns_one(self, client, db_session, characters):
        resp = _single(client, buff_type=QUEST)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"character_id": 7, "buff_type": QUEST, "multiplier": 1.0}

    def test_default_buff_type_is_profession(self, client, db_session, characters):
        _buff(db_session, PROFESSION, 0.5)
        resp = _single(client)
        assert resp.status_code == 200, resp.text
        assert resp.json()["buff_type"] == PROFESSION
        assert resp.json()["multiplier"] == 1.5

    def test_active_buff_is_reflected(self, client, db_session, characters):
        _buff(db_session, QUEST, 0.25)
        assert _single(client, buff_type=QUEST).json()["multiplier"] == pytest.approx(1.25)

    def test_umbrella_is_folded_in(self, client, db_session, characters):
        _buff(db_session, QUEST, 0.25)
        _buff(db_session, ALL_CHAR, 0.10)
        assert _single(client, buff_type=QUEST).json()["multiplier"] == pytest.approx(1.35)
        assert _single(client, buff_type=BATTLE).json()["multiplier"] == pytest.approx(1.10)

    def test_expired_buff_is_cleaned_up_and_committed(self, client, db_session, characters):
        db_session.add(models.ActiveBuff(
            character_id=7, buff_type=QUEST, value=0.5,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            source_item_name="Просрочка",
        ))
        db_session.commit()

        assert _single(client, buff_type=QUEST).json()["multiplier"] == 1.0
        db_session.expire_all()
        assert db_session.query(models.ActiveBuff).filter_by(character_id=7).count() == 0

    def test_unknown_buff_type_is_400(self, client, db_session, characters):
        resp = _single(client, buff_type="xp_hacks")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Недопустимый тип баффа"

    def test_unknown_character_is_404(self, client, db_session, characters):
        resp = _single(client, cid=999, buff_type=QUEST)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Персонаж не найден"

    def test_missing_token_is_401(self, client, db_session, characters):
        resp = client.get("/inventory/internal/characters/7/xp-multiplier")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Недействительный internal token"

    @pytest.mark.parametrize("token", ["", "wrong-token", _TOKEN.upper()])
    def test_bad_token_is_401(self, client, db_session, characters, token):
        resp = client.get("/inventory/internal/characters/7/xp-multiplier",
                          headers={"X-Internal-Token": token})
        assert resp.status_code == 401

    def test_fails_closed_when_token_not_configured(self, client, db_session,
                                                    characters, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        for headers in ({}, {"X-Internal-Token": "anything"}, _HEADERS):
            resp = client.get("/inventory/internal/characters/7/xp-multiplier",
                              headers=headers)
            assert resp.status_code == 503, resp.text
            assert resp.json()["detail"] == "Internal service token не настроен"

    def test_sql_injection_in_buff_type(self, client, db_session, characters):
        resp = _single(client, buff_type="xp_bonus'; DROP TABLE items; --")
        assert resp.status_code == 400
        # the table is still there
        assert db_session.execute(text("SELECT COUNT(*) FROM items")).scalar() == 0


# ===========================================================================
# 2. Batch endpoint
# ===========================================================================

class TestXpMultipliersBatchEndpoint:

    def test_happy_path(self, client, db_session, characters):
        _buff(db_session, QUEST, 0.25)
        _buff(db_session, ALL_CHAR, 0.10)

        resp = _batch(client, buff_types=f"{QUEST},{BATTLE},{PROFESSION}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["character_id"] == 7
        assert data["multipliers"][QUEST] == pytest.approx(1.35)
        assert data["multipliers"][BATTLE] == pytest.approx(1.10)
        assert data["multipliers"][PROFESSION] == 1.0

    def test_whitespace_is_tolerated(self, client, db_session, characters):
        resp = _batch(client, buff_types=f" {QUEST} , {PROFESSION} ")
        assert resp.status_code == 200, resp.text
        assert set(resp.json()["multipliers"]) == {QUEST, PROFESSION}

    def test_every_allowed_type_at_once(self, client, db_session, characters):
        resp = _batch(client, buff_types=",".join(sorted(schemas.ALLOWED_BUFF_TYPES)))
        assert resp.status_code == 200, resp.text
        assert set(resp.json()["multipliers"]) == set(schemas.ALLOWED_BUFF_TYPES)

    @pytest.mark.parametrize("raw", ["", " ", ",,,"])
    def test_empty_list_is_400(self, client, db_session, characters, raw):
        resp = _batch(client, buff_types=raw)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Параметр buff_types не должен быть пустым"

    def test_missing_parameter_is_422(self, client, db_session, characters):
        resp = client.get("/inventory/internal/characters/7/xp-multipliers",
                          headers=_HEADERS)
        assert resp.status_code == 422

    def test_unknown_type_is_400(self, client, db_session, characters):
        resp = _batch(client, buff_types=f"{QUEST},xp_hacks")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Недопустимый тип баффа"

    def test_too_many_types_is_400(self, client, db_session, characters):
        raw = ",".join(sorted(schemas.ALLOWED_BUFF_TYPES) + [PROFESSION])
        resp = _batch(client, buff_types=raw)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Слишком много типов баффов в запросе"

    def test_unknown_character_is_404(self, client, db_session, characters):
        resp = _batch(client, cid=999, buff_types=QUEST)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Персонаж не найден"

    def test_missing_token_is_401(self, client, db_session, characters):
        resp = client.get("/inventory/internal/characters/7/xp-multipliers",
                          params={"buff_types": QUEST})
        assert resp.status_code == 401

    @pytest.mark.parametrize("token", ["", "wrong-token"])
    def test_bad_token_is_401(self, client, db_session, characters, token):
        resp = client.get("/inventory/internal/characters/7/xp-multipliers",
                          params={"buff_types": QUEST},
                          headers={"X-Internal-Token": token})
        assert resp.status_code == 401

    def test_fails_closed_when_token_not_configured(self, client, db_session,
                                                    characters, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        resp = client.get("/inventory/internal/characters/7/xp-multipliers",
                          params={"buff_types": QUEST}, headers=_HEADERS)
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Internal service token не настроен"

    def test_auth_is_checked_before_the_character_lookup(self, client, db_session,
                                                         characters):
        """Отсутствие токена не должно выдавать существование персонажа."""
        resp = client.get("/inventory/internal/characters/999/xp-multipliers",
                          params={"buff_types": QUEST})
        assert resp.status_code == 401
