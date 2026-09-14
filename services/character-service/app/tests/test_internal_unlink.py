"""
Tests for POST /characters/internal/unlink endpoint in character-service.

The endpoint performs **three** writes, and for a long time only one of them
worked. The other two were raw SQL against user-service's tables and used names
that do not exist — column `current_character_id` (real: `current_character`) and
table `user_characters` (real: `users_character`). Both failures were swallowed
by `except Exception` + `logger.warning`, so battle-service was told the death
duel had "killed" the character while the user still had it selected and still
had the link row.

Two things let that survive: the swallow, and this file's fixture, which created
only `models.Base` tables — so SQLite had no `users_character` for the raw SQL to
miss. The mirror DDL below closes the second hole and is checked column-for-column
against user-service's own models (`services/user-service/models.py`):

    users            -> id INT PK, current_character INT NULL
    users_character  -> user_id INT, character_id INT, PRIMARY KEY (both)

Covers:
- Unlink performs all three writes (character.user_id, users_character,
  users.current_character)
- Character not found -> 404
- Already unlinked character -> 200 (idempotent), nothing else touched
- A failing write raises 500 and rolls back instead of reporting success
"""

import pytest
from unittest.mock import patch
from sqlalchemy import text
from fastapi.testclient import TestClient

import models
import database
import auth_http
from main import app, get_db

# FEAT-162 §3.4: /characters/internal/unlink now requires the X-Internal-Token
# header. Pin the module constant so the suite does not depend on
# INTERNAL_SERVICE_TOKEN being set in the environment.
auth_http.INTERNAL_SERVICE_TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# `users` and `users_character` belong to user-service, so they are absent from
# character-service's metadata — but /internal/unlink writes to both with raw
# SQL. Without them the SQLite schema silently diverged from production and the
# endpoint's `current_character_id` / `user_characters` typos went unnoticed
# (the errors were swallowed). Create them here so the raw SQL is exercised.
# Shapes verified against services/user-service/models.py (User, UserCharacter)
# and against the live MySQL schema of `mydatabase`.
_FOREIGN_TABLES_DDL = (
    "CREATE TABLE IF NOT EXISTS users ("
    " id INTEGER PRIMARY KEY, current_character INTEGER)",
    "CREATE TABLE IF NOT EXISTS users_character ("
    " user_id INTEGER NOT NULL, character_id INTEGER NOT NULL,"
    " PRIMARY KEY (user_id, character_id))",
)


@pytest.fixture(autouse=True)
def setup_tables(test_engine):
    """Create all tables before each test, drop after."""
    models.Base.metadata.create_all(bind=test_engine)
    with test_engine.begin() as conn:
        for ddl in _FOREIGN_TABLES_DDL:
            conn.execute(text(ddl))
    yield
    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS users_character"))
        conn.execute(text("DROP TABLE IF EXISTS users"))
    models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session(test_session_factory):
    """Provide a clean DB session for each test."""
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()


def _seed_reference_data(session):
    """Insert minimal FK reference data required by characters table."""
    for rid, name in [(1, "Человек")]:
        if not session.query(models.Race).filter_by(id_race=rid).first():
            session.add(models.Race(id_race=rid, name=name))
    session.flush()
    for sid, rid, name in [(1, 1, "Норд")]:
        if not session.query(models.Subrace).filter_by(id_subrace=sid).first():
            session.add(models.Subrace(id_subrace=sid, id_race=rid, name=name))
    session.flush()
    for cid, name in [(1, "Воин")]:
        if not session.query(models.Class).filter_by(id_class=cid).first():
            session.add(models.Class(id_class=cid, name=name))
    session.commit()


def _create_character(session, char_id=1, user_id=10, name="TestChar"):
    """Create a test character with minimal required fields.

    When `user_id` is given, the user-service side of the link is created too —
    the `users` row with `current_character` pointing at this character and the
    `users_character` join row. That is the real production state a death duel
    unlinks from, and without it two of the endpoint's three writes would be
    no-ops that any assertion would happily pass.
    """
    _seed_reference_data(session)
    char = models.Character(
        id=char_id,
        name=name,
        id_subrace=1,
        id_class=1,
        id_race=1,
        user_id=user_id,
        appearance="Test appearance",
        avatar="test.png",
    )
    session.add(char)
    session.commit()
    session.refresh(char)
    if user_id is not None:
        _link_user(session, user_id, char_id)
    return char


def _link_user(session, user_id, char_id):
    """Create the user-service half of the link (users + users_character)."""
    session.execute(
        text("INSERT INTO users (id, current_character) VALUES (:uid, :cid)"),
        {"uid": user_id, "cid": char_id},
    )
    session.execute(
        text(
            "INSERT INTO users_character (user_id, character_id) "
            "VALUES (:uid, :cid)"
        ),
        {"uid": user_id, "cid": char_id},
    )
    session.commit()


def _link_rows(session, user_id=None, char_id=None):
    sql = "SELECT user_id, character_id FROM users_character WHERE 1=1"
    params = {}
    if user_id is not None:
        sql += " AND user_id = :uid"
        params["uid"] = user_id
    if char_id is not None:
        sql += " AND character_id = :cid"
        params["cid"] = char_id
    return session.execute(text(sql), params).fetchall()


def _current_character(session, user_id):
    return session.execute(
        text("SELECT current_character FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).scalar()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with real SQLite DB session."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Fixture guard — the mirrors must model the real database
# ═══════════════════════════════════════════════════════════════════════════


class TestForeignTableMirrors:
    """A fixture that models a different database than production tests nothing.

    These assertions are deliberately about *names*, because names are what
    broke. They are pinned to user-service's models, which are the source of
    truth for both tables.
    """

    def test_mirrors_use_the_real_table_and_column_names(self, db_session):
        # `users_character`, not `user_characters`
        cols = {
            row[1]
            for row in db_session.execute(
                text("PRAGMA table_info(users_character)")
            ).fetchall()
        }
        assert cols == {"user_id", "character_id"}

        # `current_character`, not `current_character_id`
        user_cols = {
            row[1]
            for row in db_session.execute(
                text("PRAGMA table_info(users)")
            ).fetchall()
        }
        assert "current_character" in user_cols
        assert "current_character_id" not in user_cols

    def test_the_wrong_names_really_are_absent(self, db_session):
        """If either of these ever resolves, this file stops proving anything."""
        from sqlalchemy.exc import OperationalError

        with pytest.raises(OperationalError):
            db_session.execute(text("SELECT 1 FROM user_characters"))
        db_session.rollback()
        with pytest.raises(OperationalError):
            db_session.execute(text("SELECT current_character_id FROM users"))
        db_session.rollback()


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /characters/internal/unlink
# ═══════════════════════════════════════════════════════════════════════════


class TestInternalUnlink:
    """Tests for the internal unlink endpoint."""

    def test_unlink_character_success(self, client, db_session):
        """All three writes land: user_id, users_character, current_character."""
        char = _create_character(db_session, char_id=1, user_id=10)
        assert char.user_id == 10
        assert _link_rows(db_session, 10, 1)
        assert _current_character(db_session, 10) == 1

        response = client.post(
            "/characters/internal/unlink",
            json={"character_id": 1}, headers=INTERNAL_HEADERS,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["detail"] == "Character unlinked from user"
        assert data["character_id"] == 1
        assert data["previous_user_id"] == 10

        # Verify in DB — write 1 of 3
        db_session.expire_all()
        updated_char = db_session.query(models.Character).filter_by(id=1).first()
        assert updated_char.user_id is None

        # Write 2 of 3: the join row is gone, or the user keeps the dead
        # character in their character list.
        assert _link_rows(db_session, 10, 1) == []

        # Write 3 of 3: the user is no longer "playing as" the dead character.
        assert _current_character(db_session, 10) is None

    def test_unlink_leaves_other_characters_of_the_same_user_alone(
        self, client, db_session
    ):
        """The DELETE is scoped by both columns — a sibling must survive."""
        _create_character(db_session, char_id=1, user_id=10)
        # Second character of the same user: only the join row, `users` already exists.
        _seed_reference_data(db_session)
        db_session.add(models.Character(
            id=2, name="Second", id_subrace=1, id_class=1, id_race=1,
            user_id=10, appearance="a", avatar="b.png",
        ))
        db_session.commit()
        db_session.execute(
            text("INSERT INTO users_character (user_id, character_id) "
                 "VALUES (10, 2)")
        )
        db_session.commit()

        response = client.post(
            "/characters/internal/unlink", json={"character_id": 1}, headers=INTERNAL_HEADERS,
        )

        assert response.status_code == 200, response.text
        db_session.expire_all()
        assert _link_rows(db_session, 10, 1) == []
        assert len(_link_rows(db_session, 10, 2)) == 1
        assert db_session.query(models.Character).filter_by(id=2).first().user_id == 10

    def test_unlink_leaves_current_character_of_another_user_alone(
        self, client, db_session
    ):
        """The UPDATE is scoped by user id — other players are untouched."""
        _create_character(db_session, char_id=1, user_id=10)
        db_session.execute(
            text("INSERT INTO users (id, current_character) VALUES (11, 99)")
        )
        db_session.commit()

        response = client.post(
            "/characters/internal/unlink", json={"character_id": 1}, headers=INTERNAL_HEADERS,
        )

        assert response.status_code == 200, response.text
        assert _current_character(db_session, 11) == 99

    def test_current_character_pointing_elsewhere_is_not_cleared(
        self, client, db_session
    ):
        """The owner is mid-swap: `current_character` is some other character."""
        _create_character(db_session, char_id=1, user_id=10)
        db_session.execute(
            text("UPDATE users SET current_character = 42 WHERE id = 10")
        )
        db_session.commit()

        response = client.post(
            "/characters/internal/unlink", json={"character_id": 1}, headers=INTERNAL_HEADERS,
        )

        assert response.status_code == 200, response.text
        assert _current_character(db_session, 10) == 42
        assert _link_rows(db_session, 10, 1) == []

    def test_character_not_found_returns_404(self, client):
        """Non-existent character -> 404."""
        response = client.post(
            "/characters/internal/unlink",
            json={"character_id": 9999}, headers=INTERNAL_HEADERS,
        )

        assert response.status_code == 404
        assert "не найден" in response.json()["detail"]

    def test_already_unlinked_returns_200_idempotent(self, client, db_session):
        """Already unlinked character -> 200 with idempotent message."""
        char = _create_character(db_session, char_id=2, user_id=None)
        assert char.user_id is None

        response = client.post(
            "/characters/internal/unlink",
            json={"character_id": 2}, headers=INTERNAL_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["detail"] == "Character already unlinked"
        assert data["character_id"] == 2

    def test_already_unlinked_touches_nothing_else(self, client, db_session):
        """A stale join row for a different user must not be collateral damage."""
        _create_character(db_session, char_id=2, user_id=None)
        db_session.execute(
            text("INSERT INTO users (id, current_character) VALUES (10, 2)")
        )
        db_session.execute(
            text("INSERT INTO users_character (user_id, character_id) "
                 "VALUES (10, 2)")
        )
        db_session.commit()

        response = client.post(
            "/characters/internal/unlink", json={"character_id": 2}, headers=INTERNAL_HEADERS,
        )

        assert response.status_code == 200
        # The early return leaves them alone — documenting, not endorsing.
        assert len(_link_rows(db_session, 10, 2)) == 1
        assert _current_character(db_session, 10) == 2


# ═══════════════════════════════════════════════════════════════════════════
# A failing write must be reported, never swallowed
# ═══════════════════════════════════════════════════════════════════════════


class TestUnlinkFailuresAreNotSwallowed:
    """battle-service acts on the response; a lying 200 loses a character.

    Before the fix every one of the three writes sat in its own
    `try/except Exception: logger.warning(...)`, so two of them could fail
    permanently — as they did — and the caller still saw
    `{"detail": "Character unlinked from user"}`.
    """

    def test_failing_write_returns_500_not_success(self, client, db_session):
        _create_character(db_session, char_id=1, user_id=10)

        with patch.object(
            db_session, "commit", side_effect=RuntimeError("unknown column")
        ):
            response = client.post(
                "/characters/internal/unlink", json={"character_id": 1}, headers=INTERNAL_HEADERS,
            )

        assert response.status_code == 500, response.text
        body = response.json()
        assert body["detail"] == "Не удалось отвязать персонажа"
        assert "unlinked" not in str(body).lower()

    def test_failing_write_rolls_everything_back(self, client, db_session):
        """Partial application is the other way to lose a character."""
        _create_character(db_session, char_id=1, user_id=10)

        with patch.object(
            db_session, "commit", side_effect=RuntimeError("unknown column")
        ):
            response = client.post(
                "/characters/internal/unlink", json={"character_id": 1}, headers=INTERNAL_HEADERS,
            )
        assert response.status_code == 500

        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(id=1).first().user_id == 10
        assert len(_link_rows(db_session, 10, 1)) == 1
        assert _current_character(db_session, 10) == 1

    def test_failing_raw_sql_is_reported(self, client, db_session):
        """The original failure mode: the raw SQL itself blows up."""
        _create_character(db_session, char_id=1, user_id=10)
        real_execute = db_session.execute

        def _boom(statement, *args, **kwargs):
            if "users_character" in str(statement):
                raise RuntimeError("no such table: users_character")
            return real_execute(statement, *args, **kwargs)

        with patch.object(db_session, "execute", side_effect=_boom):
            response = client.post(
                "/characters/internal/unlink", json={"character_id": 1}, headers=INTERNAL_HEADERS,
            )

        assert response.status_code == 500, response.text
        assert response.json()["detail"] == "Не удалось отвязать персонажа"
        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(id=1).first().user_id == 10

    def test_failure_is_logged_with_a_traceback(self, client, db_session):
        _create_character(db_session, char_id=1, user_id=10)

        with patch("main.logger.error") as err, patch.object(
            db_session, "commit", side_effect=RuntimeError("unknown column")
        ):
            response = client.post(
                "/characters/internal/unlink", json={"character_id": 1}, headers=INTERNAL_HEADERS,
            )

        assert response.status_code == 500
        assert err.called
        assert any(call.kwargs.get("exc_info") for call in err.call_args_list)
