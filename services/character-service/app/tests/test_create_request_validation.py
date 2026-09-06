"""
FEAT-154 (task #24) — tests for POST /characters/requests/ and its domain validation.

Covers:
(a) ownership (403) is checked BEFORE any domain validation — the load-bearing
    check order of §3.1 / §3.3
(b) the happy path: 200 AND the row really lands in the database (the set had no
    such test at all before this file)
(c) every rule of §3.2 returns 400 with a Russian message, including the N20 fix
    (a too-long name is a 400, never a 422) and the N21 write-back of the
    stripped name
(d) subrace-belongs-to-race consistency (rule 34)
(e) the character limit at submit time (rule 31 / D13) — off by default,
    and enforced as before once settings.MAX_CHARACTERS_PER_USER is set
(f) locations-service being unreachable never blocks a submission (graceful)
(g) N16 — GET /characters/races exposes the new subrace fields without losing
    the old ones
(h) security: SQL injection in free-text fields, unauthenticated access

The whole file keeps the locations-service client stubbed (see the autouse
fixture in test_approval_flow.py): unpatched, every probe burns the 5 s client
timeout before falling through gracefully.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

import crud
import database
from database import Base
import models
from auth_http import get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


USER_A = UserRead(id=42, username="playerA", role="user", permissions=[])
USER_B = UserRead(id=77, username="playerB", role="user", permissions=[])

# The in-game year is NEVER hardcoded in production code (§3.5) — it is read from
# locations-service at runtime. This is only the value the *stubbed* service
# reports; every year used below is derived from it, so moving the real clock
# cannot break these tests.
STUB_CURRENT_GAME_YEAR = 1787

# The character limit is a setting (settings.MAX_CHARACTERS_PER_USER) and it is
# DISABLED by default (0 = no limit). The limit tests below switch it on
# explicitly through the ``character_limit`` fixture; this is the value they use.
TEST_CHARACTER_LIMIT = 5


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def character_limit(monkeypatch):
    """Turn the character limit on for one test (restored afterwards)."""
    def _set(value=TEST_CHARACTER_LIMIT):
        monkeypatch.setattr(crud.settings, "MAX_CHARACTERS_PER_USER", value)
    return _set


@pytest.fixture(autouse=True)
def stub_locations_client():
    """Keep the domain validator off the network.

    ``crud.validate_character_request_payload`` probes locations-service for the
    starting point and for the current in-game year. Default here: the service
    answers, the point is a curated one. Individual tests override the mocks.
    """
    with patch("crud.locations_client") as mock_client:
        mock_client.probe_starting_point = AsyncMock(return_value=True)
        mock_client.get_current_game_year = AsyncMock(return_value=STUB_CURRENT_GAME_YEAR)
        yield mock_client


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def make_client(db_session):
    """Build a TestClient authenticated as an arbitrary user (None = anonymous)."""

    def _factory(user=None):
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        if user is not None:
            app.dependency_overrides[get_current_user_via_http] = lambda: user
            app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
        else:
            app.dependency_overrides.pop(get_current_user_via_http, None)
            app.dependency_overrides.pop(OAUTH2_SCHEME, None)
        return TestClient(app)

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def client_a(make_client):
    return make_client(USER_A)


@pytest.fixture
def anon_client(make_client):
    return make_client(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload(**overrides):
    """A valid POST body for USER_A (race 2 = Эльф, subrace 4 = Лесной, class 1)."""
    body = {
        "name": "Аэлис",
        "id_race": 2,
        "id_subrace": 4,
        "id_class": 1,
        "biography": "Био",
        "personality": "Характер",
        "appearance": "Высокая эльфийка",
        "background": "Предыстория",
        "sex": "female",
        "age": 120,
        "weight": "52",
        "height": "168",
        "user_id": USER_A.id,
        "avatar": "https://example.com/a.webp",
        "origin_id": 7,
        "start_location_id": None,
        "skitaltsy_since_year": None,
        "skitaltsy_since_segment": None,
    }
    body.update(overrides)
    return body


def _seed_request(db, user_id=USER_A.id, status="pending", request_type="creation", **overrides):
    fields = dict(
        user_id=user_id,
        name="Прошлая",
        id_race=2,
        id_subrace=4,
        id_class=1,
        biography="Био",
        personality="Характер",
        appearance="Внешность",
        background="Предыстория",
        sex="female",
        age=120,
        weight="52",
        height="168",
        avatar="https://example.com/a.webp",
        status=status,
        request_type=request_type,
    )
    fields.update(overrides)
    req = models.CharacterRequest(**fields)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _count(db):
    return db.query(models.CharacterRequest).count()


# ===========================================================================
# (a) Ownership is checked FIRST
# ===========================================================================

class TestOwnershipComesFirst:
    def test_user_id_mismatch_returns_403(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(user_id=USER_B.id))
        assert response.status_code == 403
        assert _count(db_session) == 0

    def test_403_wins_over_domain_violations_in_the_same_body(self, db_session, client_a):
        """The explicit acceptance criterion: ownership beats §3.2, never the other way."""
        response = client_a.post(
            "/characters/requests/",
            json=_payload(
                user_id=USER_B.id,      # ownership violation
                name="",                # would be 400
                appearance="   ",       # would be 400
                id_race=9999,           # would be 400
                id_subrace=9999,        # would be 400
                id_class=9999,          # would be 400
                age=0,                  # would be 400
                sex="attack helicopter",  # would be 400
                origin_id=-1,           # would be 400
                skitaltsy_since_segment=99,  # would be 400
            ),
        )
        assert response.status_code == 403
        assert response.status_code not in (400, 422)
        assert _count(db_session) == 0

    def test_403_wins_even_when_the_limit_is_already_reached(self, db_session, client_a,
                                                             character_limit):
        character_limit()
        for _ in range(TEST_CHARACTER_LIMIT):
            _seed_request(db_session, user_id=USER_B.id)

        response = client_a.post("/characters/requests/", json=_payload(user_id=USER_B.id))
        assert response.status_code == 403

    def test_unauthenticated_returns_401(self, db_session, anon_client):
        response = anon_client.post("/characters/requests/", json=_payload())
        assert response.status_code == 401
        assert _count(db_session) == 0


# ===========================================================================
# (b) Happy path — 200 AND a row in the database
# ===========================================================================

class TestHappyPath:
    def test_valid_request_returns_200_and_is_persisted(self, db_session, client_a):
        assert _count(db_session) == 0

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["name"] == "Аэлис"
        assert body["status"] == "pending"

        # The row really exists — not just a 200.
        assert _count(db_session) == 1
        row = db_session.query(models.CharacterRequest).one()
        assert row.id == body["id"]
        assert row.user_id == USER_A.id
        assert row.name == "Аэлис"
        assert row.status == "pending"
        assert row.request_type == "creation"
        assert row.appearance == "Высокая эльфийка"

    def test_owner_comes_from_the_token_and_is_stored(self, db_session, client_a):
        client_a.post("/characters/requests/", json=_payload())
        assert db_session.query(models.CharacterRequest).one().user_id == USER_A.id

    def test_new_feat154_fields_are_persisted(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(
                origin_id=7,
                start_location_id=1183,
                skitaltsy_since_year=STUB_CURRENT_GAME_YEAR - 4,
                skitaltsy_since_segment=2,
            ),
        )
        assert response.status_code == 200, response.text

        row = db_session.query(models.CharacterRequest).one()
        assert row.origin_id == 7
        assert row.start_location_id == 1183
        assert row.skitaltsy_since_year == STUB_CURRENT_GAME_YEAR - 4
        assert row.skitaltsy_since_segment == 2

        body = response.json()
        assert body["origin_id"] == 7
        assert body["start_location_id"] == 1183
        assert body["skitaltsy_since_year"] == STUB_CURRENT_GAME_YEAR - 4
        assert body["skitaltsy_since_segment"] == 2

    def test_response_carries_the_fields_the_old_model_omitted(self, db_session, client_a):
        body = client_a.post("/characters/requests/", json=_payload()).json()
        assert body["created_at"] is not None
        assert body["request_type"] == "creation"
        assert body["character_id"] is None
        assert body["rejection_reason"] is None

    def test_avatar_is_optional(self, db_session, client_a):
        """D5 — a failed upload must never block a submission."""
        payload = _payload()
        payload.pop("avatar")

        response = client_a.post("/characters/requests/", json=payload)
        assert response.status_code == 200, response.text
        assert db_session.query(models.CharacterRequest).one().avatar is None

    def test_optional_new_fields_may_be_omitted_entirely(self, db_session, client_a):
        payload = _payload()
        for key in ("origin_id", "start_location_id",
                    "skitaltsy_since_year", "skitaltsy_since_segment"):
            payload.pop(key)

        response = client_a.post("/characters/requests/", json=payload)
        assert response.status_code == 200, response.text
        row = db_session.query(models.CharacterRequest).one()
        assert row.origin_id is None
        assert row.start_location_id is None
        assert row.skitaltsy_since_year is None
        assert row.skitaltsy_since_segment is None


# ===========================================================================
# (c) §3.2 domain validation — 400 with a Russian message
# ===========================================================================

class TestNameValidation:
    NAME_MESSAGE = "Имя обязательно и не длиннее 20 символов."

    def test_empty_name_returns_400(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(name=""))
        assert response.status_code == 400
        assert response.json()["detail"] == self.NAME_MESSAGE
        assert _count(db_session) == 0

    def test_blank_name_returns_400(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(name="    "))
        assert response.status_code == 400
        assert response.json()["detail"] == self.NAME_MESSAGE

    def test_name_over_20_chars_returns_400_not_422(self, db_session, client_a):
        """N20 / task #36 — Pydantic's English 422 was replaced by a Russian 400."""
        response = client_a.post("/characters/requests/", json=_payload(name="А" * 21))
        assert response.status_code == 400
        assert response.json()["detail"] == self.NAME_MESSAGE
        assert _count(db_session) == 0

    def test_name_of_exactly_20_chars_is_accepted(self, db_session, client_a):
        name = "А" * 20
        response = client_a.post("/characters/requests/", json=_payload(name=name))
        assert response.status_code == 200, response.text
        assert db_session.query(models.CharacterRequest).one().name == name

    def test_padded_20_char_name_is_stored_stripped(self, db_session, client_a):
        """N21 — the validator writes the cleaned value back, so String(20) is safe.

        Without the write-back this reaches MySQL as 23 characters and raises 1406.
        """
        name = "А" * 20
        response = client_a.post("/characters/requests/", json=_payload(name="   " + name))
        assert response.status_code == 200, response.text

        row = db_session.query(models.CharacterRequest).one()
        assert row.name == name
        assert len(row.name) == 20
        assert response.json()["name"] == name


class TestDomainValidation:
    def test_blank_appearance_returns_400(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(appearance="   "))
        assert response.status_code == 400
        assert response.json()["detail"] == "Опишите внешность персонажа."
        assert _count(db_session) == 0

    def test_unknown_race_returns_400(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(id_race=9999))
        assert response.status_code == 400
        assert response.json()["detail"] == "Указанная раса не найдена."

    def test_unknown_subrace_returns_400(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(id_subrace=9999))
        assert response.status_code == 400
        assert response.json()["detail"] == "Подраса не принадлежит выбранной расе."

    def test_subrace_of_another_race_returns_400(self, db_session, client_a):
        """Rule 34 — subrace 4 (Лесной) belongs to race 2, not race 1."""
        response = client_a.post(
            "/characters/requests/", json=_payload(id_race=1, id_subrace=4)
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Подраса не принадлежит выбранной расе."
        assert _count(db_session) == 0

    def test_matching_race_and_subrace_are_accepted(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/", json=_payload(id_race=1, id_subrace=2)
        )
        assert response.status_code == 200, response.text

    def test_unknown_class_returns_400(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(id_class=9999))
        assert response.status_code == 400
        assert response.json()["detail"] == "Указанный класс не найден."

    @pytest.mark.parametrize("age", [0, -5, crud.MAX_CHARACTER_AGE + 1])
    def test_age_out_of_range_returns_400(self, db_session, client_a, age):
        response = client_a.post("/characters/requests/", json=_payload(age=age))
        assert response.status_code == 400
        assert response.json()["detail"] == "Возраст указан некорректно."

    @pytest.mark.parametrize("age", [crud.MIN_CHARACTER_AGE, crud.MAX_CHARACTER_AGE])
    def test_age_at_the_bounds_is_accepted(self, db_session, client_a, age):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(age=age, skitaltsy_since_year=STUB_CURRENT_GAME_YEAR),
        )
        assert response.status_code == 200, response.text

    def test_age_may_be_omitted(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(age=None))
        assert response.status_code == 200, response.text

    def test_invalid_sex_returns_400(self, db_session, client_a):
        response = client_a.post("/characters/requests/", json=_payload(sex="dragon"))
        assert response.status_code == 400
        assert response.json()["detail"] == "Некорректное значение пола."

    @pytest.mark.parametrize("sex", ["male", "female", "genderless"])
    def test_allowed_sex_values_are_accepted(self, db_session, client_a, sex):
        response = client_a.post("/characters/requests/", json=_payload(sex=sex))
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("origin_id", [0, -3])
    def test_non_positive_origin_returns_400(self, db_session, client_a, origin_id):
        response = client_a.post("/characters/requests/", json=_payload(origin_id=origin_id))
        assert response.status_code == 400
        assert response.json()["detail"] == "Указано некорректное происхождение."

    def test_origin_existence_is_not_checked_cross_service(self, db_session, client_a):
        """§3.2 — a positive origin_id is accepted as-is; the moderator resolves it."""
        response = client_a.post("/characters/requests/", json=_payload(origin_id=987654))
        assert response.status_code == 200, response.text
        assert db_session.query(models.CharacterRequest).one().origin_id == 987654

    @pytest.mark.parametrize("segment", [-1, crud.GAME_YEAR_SEGMENT_COUNT])
    def test_segment_out_of_range_returns_400(self, db_session, client_a, segment):
        response = client_a.post(
            "/characters/requests/", json=_payload(skitaltsy_since_segment=segment)
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Некорректный сезон."

    @pytest.mark.parametrize("segment", [0, crud.GAME_YEAR_SEGMENT_COUNT - 1])
    def test_segment_at_the_bounds_is_accepted(self, db_session, client_a, segment):
        response = client_a.post(
            "/characters/requests/", json=_payload(skitaltsy_since_segment=segment)
        )
        assert response.status_code == 200, response.text

    def test_non_curated_start_location_returns_400(self, db_session, client_a,
                                                    stub_locations_client):
        stub_locations_client.probe_starting_point = AsyncMock(return_value=False)

        response = client_a.post("/characters/requests/", json=_payload(start_location_id=99))
        assert response.status_code == 400
        assert response.json()["detail"] == "Выбранная точка не входит в список стартовых."
        assert _count(db_session) == 0

    def test_tenure_later_than_the_current_game_year_returns_400(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(skitaltsy_since_year=STUB_CURRENT_GAME_YEAR + 1),
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Нельзя вступить в Скитальцы позже текущей игровой даты."

    def test_tenure_equal_to_the_current_game_year_is_accepted(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(skitaltsy_since_year=STUB_CURRENT_GAME_YEAR),
        )
        assert response.status_code == 200, response.text

    def test_tenure_longer_than_the_age_returns_400(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(age=10, skitaltsy_since_year=STUB_CURRENT_GAME_YEAR - 11),
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Указанный стаж больше возраста персонажа."

    def test_tenure_exactly_matching_the_age_is_accepted(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(age=10, skitaltsy_since_year=STUB_CURRENT_GAME_YEAR - 10),
        )
        assert response.status_code == 200, response.text

    def test_missing_required_field_is_a_422(self, db_session, client_a):
        """Schema errors stay 422 (§3.2 ordering: 403 -> 422 -> 400)."""
        payload = _payload()
        payload.pop("id_class")
        assert client_a.post("/characters/requests/", json=payload).status_code == 422


# ===========================================================================
# (e) Character limit at submit time — rule 31 / D13
# ===========================================================================

class TestCharacterLimitDisabledByDefault:
    """Out of the box there is no limit — settings.MAX_CHARACTERS_PER_USER == 0."""

    def test_get_character_limit_is_none_by_default(self):
        assert crud.get_character_limit() is None

    def test_submitting_far_above_the_old_limit_is_accepted(self, db_session, client_a):
        for _ in range(TEST_CHARACTER_LIMIT * 2):
            _seed_request(db_session, user_id=USER_A.id)

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 200, response.text
        assert _count(db_session) == TEST_CHARACTER_LIMIT * 2 + 1

    @pytest.mark.parametrize("value", [0, -1])
    def test_zero_and_negative_settings_mean_unlimited(self, db_session, client_a,
                                                       character_limit, value):
        character_limit(value)
        for _ in range(TEST_CHARACTER_LIMIT):
            _seed_request(db_session, user_id=USER_A.id)

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 200, response.text


class TestCharacterLimit:
    """With the setting switched on, the limit behaves exactly as it used to."""

    def test_submitting_below_the_limit_is_accepted(self, db_session, client_a, character_limit):
        character_limit()
        for _ in range(TEST_CHARACTER_LIMIT - 1):
            _seed_request(db_session, user_id=USER_A.id)

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 200, response.text
        assert _count(db_session) == TEST_CHARACTER_LIMIT

    def test_limit_is_enforced_on_submit(self, db_session, client_a, character_limit):
        character_limit()
        for _ in range(TEST_CHARACTER_LIMIT):
            _seed_request(db_session, user_id=USER_A.id)

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 400
        assert response.json()["detail"] == (
            f"Достигнут лимит персонажей (максимум {TEST_CHARACTER_LIMIT})."
        )
        assert _count(db_session) == TEST_CHARACTER_LIMIT

    def test_the_configured_value_is_the_one_enforced(self, db_session, client_a,
                                                      character_limit):
        """A different setting value moves the threshold and the message."""
        character_limit(2)
        for _ in range(2):
            _seed_request(db_session, user_id=USER_A.id)

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 400
        assert response.json()["detail"] == "Достигнут лимит персонажей (максимум 2)."

    def test_rejected_and_approved_requests_do_not_count(self, db_session, client_a,
                                                         character_limit):
        character_limit()
        for _ in range(TEST_CHARACTER_LIMIT):
            _seed_request(db_session, user_id=USER_A.id, status="rejected")
        for _ in range(TEST_CHARACTER_LIMIT):
            _seed_request(db_session, user_id=USER_A.id, status="approved")

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 200, response.text

    def test_claim_requests_do_not_count(self, db_session, client_a, character_limit):
        character_limit()
        for _ in range(TEST_CHARACTER_LIMIT):
            _seed_request(db_session, user_id=USER_A.id, request_type="claim")

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 200, response.text

    def test_another_users_requests_do_not_count(self, db_session, client_a, character_limit):
        character_limit()
        for _ in range(TEST_CHARACTER_LIMIT):
            _seed_request(db_session, user_id=USER_B.id)

        response = client_a.post("/characters/requests/", json=_payload())
        assert response.status_code == 200, response.text


# ===========================================================================
# (f) locations-service is graceful — an outage never blocks a submission
# ===========================================================================

class TestLocationsServiceIsGraceful:
    def test_unreachable_service_does_not_block_the_start_location(
        self, db_session, client_a, stub_locations_client
    ):
        stub_locations_client.probe_starting_point = AsyncMock(return_value=None)

        response = client_a.post("/characters/requests/", json=_payload(start_location_id=1183))
        assert response.status_code == 200, response.text
        assert db_session.query(models.CharacterRequest).one().start_location_id == 1183

    def test_unknown_game_year_skips_both_tenure_bounds(
        self, db_session, client_a, stub_locations_client
    ):
        stub_locations_client.get_current_game_year = AsyncMock(return_value=None)

        response = client_a.post(
            "/characters/requests/",
            json=_payload(age=10, skitaltsy_since_year=STUB_CURRENT_GAME_YEAR + 500),
        )
        assert response.status_code == 200, response.text
        row = db_session.query(models.CharacterRequest).one()
        assert row.skitaltsy_since_year == STUB_CURRENT_GAME_YEAR + 500

    def test_the_segment_check_still_applies_while_the_service_is_down(
        self, db_session, client_a, stub_locations_client
    ):
        """The segment bound is self-contained — an outage must not relax it."""
        stub_locations_client.get_current_game_year = AsyncMock(return_value=None)
        stub_locations_client.probe_starting_point = AsyncMock(return_value=None)

        response = client_a.post(
            "/characters/requests/",
            json=_payload(skitaltsy_since_segment=crud.GAME_YEAR_SEGMENT_COUNT),
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Некорректный сезон."

    def test_the_year_is_never_hardcoded_in_the_service(self, db_session, client_a,
                                                        stub_locations_client):
        """Move the stubbed clock and the bound moves with it (§3.5 hard constraint)."""
        moved_year = STUB_CURRENT_GAME_YEAR + 100
        stub_locations_client.get_current_game_year = AsyncMock(return_value=moved_year)

        ok = client_a.post(
            "/characters/requests/", json=_payload(skitaltsy_since_year=moved_year)
        )
        assert ok.status_code == 200, ok.text

        too_late = client_a.post(
            "/characters/requests/", json=_payload(skitaltsy_since_year=moved_year + 1)
        )
        assert too_late.status_code == 400


# ===========================================================================
# (g) N16 — GET /characters/races exposes the new subrace fields
# ===========================================================================

class TestRacesEndpointSubraceFields:
    def _forest_elf(self, anon_client):
        races = anon_client.get("/characters/races").json()
        race = next(r for r in races if r["id_race"] == 2)
        return next(s for s in race["subraces"] if s["id_subrace"] == 4)

    def test_new_fields_are_returned(self, db_session, anon_client):
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.distinctive_features = "Заострённые уши, зелёные глаза."
        subrace.height_min = 165
        subrace.height_max = 195
        subrace.typical_origin_ids = [3, 7]
        db_session.commit()

        sub = self._forest_elf(anon_client)
        assert sub["distinctive_features"] == "Заострённые уши, зелёные глаза."
        assert sub["height_min"] == 165
        assert sub["height_max"] == 195
        assert sub["typical_origin_ids"] == [3, 7]

    def test_old_keys_did_not_disappear(self, db_session, anon_client):
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.description = "Лесные эльфы"
        subrace.stat_preset = {"strength": 10}
        subrace.image = "https://example.com/elf.webp"
        db_session.commit()

        sub = self._forest_elf(anon_client)
        assert sub["id_subrace"] == 4
        assert sub["name"] == "Лесной"
        assert sub["id_race"] == 2  # родитель, а не undefined
        assert sub["description"] == "Лесные эльфы"
        assert sub["stat_preset"] == {"strength": 10}
        assert sub["image"] == "https://example.com/elf.webp"

    def test_new_fields_are_null_when_unset(self, db_session, anon_client):
        sub = self._forest_elf(anon_client)
        assert sub["distinctive_features"] is None
        assert sub["height_min"] is None
        assert sub["height_max"] is None
        assert sub["typical_origin_ids"] is None

    def test_id_race_points_at_the_parent_race(self, db_session, anon_client):
        """Публичный ответ обязан называть настоящего родителя подрасы."""
        races = anon_client.get("/characters/races").json()
        for race in races:
            for sub in race["subraces"]:
                assert sub["id_race"] == race["id_race"]

    def test_key_set_is_exactly_the_contract(self, db_session, anon_client):
        """Аддитивность: новый ключ появился, ни один старый не пропал."""
        sub = self._forest_elf(anon_client)
        assert set(sub.keys()) == {
            "id_subrace",
            "id_race",
            "name",
            "description",
            "stat_preset",
            "image",
            "distinctive_features",
            "height_min",
            "height_max",
            "typical_origin_ids",
        }

    def test_endpoint_stays_public(self, db_session, anon_client):
        assert anon_client.get("/characters/races").status_code == 200


# ===========================================================================
# (h) Security
# ===========================================================================

class TestSecurity:
    def test_sql_injection_in_text_fields_is_stored_literally(self, db_session, client_a):
        injected_name = "'; DROP TABLE t; --"  # 19 chars, fits the name limit

        response = client_a.post(
            "/characters/requests/",
            json=_payload(
                name=injected_name,
                biography='" OR 1=1 --',
                personality="1; DELETE FROM characters",
                appearance="'); DROP TABLE character_requests; --",
                background="admin'--",
            ),
        )
        assert response.status_code == 200, response.text
        assert response.json()["name"] == injected_name

        # The tables survived and the payload was stored, not executed.
        assert _count(db_session) == 1
        assert db_session.query(models.Race).count() > 0
        row = db_session.query(models.CharacterRequest).one()
        assert row.name == injected_name
        assert row.appearance == "'); DROP TABLE character_requests; --"

    def test_injection_in_the_weight_and_height_fields_is_harmless(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(weight="1 OR 1=1", height="'--"),
        )
        assert response.status_code == 200, response.text
        assert _count(db_session) == 1

    def test_injection_attempt_does_not_produce_a_500(self, db_session, client_a):
        response = client_a.post(
            "/characters/requests/",
            json=_payload(name="' UNION SELECT 1--", id_race=1, id_subrace=1),
        )
        assert response.status_code != 500

    def test_unauthenticated_submission_is_refused(self, db_session, anon_client):
        assert anon_client.post("/characters/requests/", json=_payload()).status_code == 401
        assert _count(db_session) == 0
