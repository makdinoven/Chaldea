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
    _attrs(session)  # attributes-service's table: saving the level table writes to it
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
    assert [(t["level_number"], t["required_experience"]) for t in resp.json()["thresholds"]] == [(2, 100), (3, 250), (4, 450)]
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


# ---------- the profile's experience bar ----------

def test_bar_shows_earned_of_the_whole_step():
    from main import level_progress
    p = level_progress(300, 200, 420, 3)  # level 2 at 200, level 3 at 420
    assert (p.current_exp_in_level, p.exp_for_level, p.exp_to_next_level) == (100, 220, 120)
    assert p.progress_fraction == round(100 / 220, 4) and p.next_level == 3 and not p.max_level


def test_bar_never_goes_below_zero_for_a_level_set_by_hand():
    from main import level_progress
    p = level_progress(1622, 29726, 32918, 31)
    assert p.current_exp_in_level == 0 and p.progress_fraction == 0
    assert p.exp_to_next_level == 32918 - 1622


def test_past_the_last_level_of_the_table():
    from main import level_progress
    p = level_progress(5000, 0, None, 151)
    assert p.max_level and p.next_level is None and p.progress_fraction == 1.0


# ---------- saving the table raises players to their level's threshold ----------

def _attrs(db):
    from sqlalchemy import text
    db.execute(text("DROP TABLE IF EXISTS character_attributes"))
    db.execute(text("CREATE TABLE character_attributes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "character_id INTEGER, passive_experience INTEGER DEFAULT 0)"))
    db.commit()


def _xp(db, cid):
    from sqlalchemy import text
    return db.execute(text("SELECT passive_experience FROM character_attributes WHERE character_id = :c"),
                      {"c": cid}).scalar()


def test_save_raises_experience_below_the_held_level(client, db_session):
    from sqlalchemy import text
    _attrs(db_session)
    low = _character(db_session, level=3)        # holds 3, has 50: raised to 250
    ahead = _character(db_session, level=2)      # holds 2, has 400: untouched
    beyond = _character(db_session, level=9)     # no row for 9 in the table: untouched
    npc = _character(db_session, level=3)
    npc.is_npc = True
    db_session.commit()
    for cid, xp in ((low.id, 50), (ahead.id, 400), (beyond.id, 10), (npc.id, 0)):
        db_session.execute(text("INSERT INTO character_attributes (character_id, passive_experience) VALUES (:c, :x)"),
                           {"c": cid, "x": xp})
    db_session.commit()
    resp = client.put(URL, json=_table((2, 100), (3, 250), (4, 450)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["raised"] == 1
    assert (_xp(db_session, low.id), _xp(db_session, ahead.id), _xp(db_session, beyond.id), _xp(db_session, npc.id))         == (250, 400, 10, 0)
