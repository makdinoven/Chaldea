"""Admin level table (2026-10-25): total experience per level, edited as a whole;
and level-up reading it as TOTAL experience (several levels at once when earned)."""

import pytest
from fastapi.testclient import TestClient

import crud
import database
import models
from auth_http import UserRead, get_admin_user, get_current_user_via_http, OAUTH2_SCHEME
from main import app, get_db

_ADMIN = UserRead(id=1, username="admin", role="admin", permissions=["characters:read", "characters:update"])
URL = "/characters/admin/levels/thresholds"


@pytest.fixture
def db_session(test_engine):
    models.Base.metadata.create_all(bind=test_engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = lambda: _ADMIN
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN
    app.dependency_overrides[OAUTH2_SCHEME] = lambda: "token"
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _table(*pairs):
    return {"thresholds": [{"level_number": lv, "required_experience": xp} for lv, xp in pairs]}


def test_save_replaces_the_table_and_reads_back_in_order(client, db_session):
    db_session.add(models.LevelThreshold(level_number=2, required_experience=999))
    db_session.commit()
    resp = client.put(URL, json=_table((3, 250), (2, 100), (4, 450)))
    assert resp.status_code == 200, resp.text
    assert [(t["level_number"], t["required_experience"]) for t in resp.json()] == [(2, 100), (3, 250), (4, 450)]
    assert [(t["level_number"], t["required_experience"]) for t in client.get(URL).json()] == [(2, 100), (3, 250), (4, 450)]


@pytest.mark.parametrize("body", [
    _table((3, 100)),                      # does not start at level 2
    _table((2, 100), (4, 300)),            # a gap
    _table((2, 100), (2, 200)),            # a repeat
    _table((2, 100), (3, 100)),            # not rising
    _table((2, 0)),                        # nothing to earn
    {"thresholds": "много"},
])
def test_bad_tables_are_refused(client, body):
    assert client.put(URL, json=body).status_code == 422


def test_an_empty_table_is_allowed(client):
    assert client.put(URL, json={"thresholds": []}).status_code == 200
    assert client.get(URL).json() == []


def test_needs_admin_rights(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        c = TestClient(app)
        assert c.get(URL).status_code in (401, 403)
        assert c.put(URL, json=_table((2, 100))).status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()


def _character(db, level=1):
    ch = models.Character(name="Тест", id_subrace=1, id_class=1, id_race=1, level=level, stat_points=0,
                          appearance="", avatar="", currency_balance=0)
    db.add(ch)
    db.commit()
    return ch


def test_level_up_reads_total_experience_several_levels_at_once(db_session):
    for lv, xp in ((2, 100), (3, 250), (4, 450), (5, 700)):
        db_session.add(models.LevelThreshold(level_number=lv, required_experience=xp))
    db_session.commit()
    ch = _character(db_session)
    crud.check_and_update_level(db_session, ch.id, 600)  # past 2, 3 and 4 in one go
    db_session.refresh(ch)
    assert ch.level == 4 and ch.stat_points == 30
    crud.check_and_update_level(db_session, ch.id, 650)  # not yet 700
    db_session.refresh(ch)
    assert ch.level == 4


def test_no_threshold_means_no_level_up(db_session):
    db_session.add(models.LevelThreshold(level_number=2, required_experience=100))
    db_session.commit()
    ch = _character(db_session, level=2)
    crud.check_and_update_level(db_session, ch.id, 10_000)
    db_session.refresh(ch)
    assert ch.level == 2
