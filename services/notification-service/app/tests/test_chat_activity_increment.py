"""
FEAT-169 #17 (QA) — notification-service: the activity-points call after a
chat message.

Step 9 of `chat_routes.send_message` awards the sender an activity point. Two
things changed in FEAT-169:

* the target route moved to `POST /users/internal/{uid}/activity/increment`
  and is now gated, so the call must carry `X-Internal-Token`;
* the `except: pass` around it became a `logger.warning`.

Both matter because the call is deliberately fire-and-forget: it can neither
fail the chat send nor raise. That is precisely the silent-failure shape the
project has been bitten by four times — a dropped header, or a caller left on
the old (now 404) path, would stop activity points forever and **no test that
only asserts "the message was sent" would notice**. So the assertions here are
on the URL and on the header *value* of the real `requests.post` the handler
makes, not on "nothing raised".

The mock itself lives in `conftest.mock_activity_increment` (autouse): before
this feature the call was unmocked in every chat test, which is the documented
cause of the flaky `TestRateLimiting` (docs/ISSUES.md) — each send waited on a
real DNS failure for ~4 s and blew the 2-second rate-limit window.
"""

import logging
from unittest.mock import patch

import pytest
import requests


TOKEN = "test-internal-token"

_PROFILE = {"avatar": None, "avatar_frame": None, "chat_background": None}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    import chat_routes

    chat_routes._last_message_time.clear()
    yield
    chat_routes._last_message_time.clear()


@pytest.fixture()
def token_env(monkeypatch):
    """`internal_token_headers()` reads the env at call time."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


def _send(client, content="Hello!"):
    return client.post("/notifications/chat/messages",
                       json={"channel": "general", "content": content})


# ══════════════════════════════════════════════════════════════════════════════
# 1. The call goes to the new path, with the header
# ══════════════════════════════════════════════════════════════════════════════


class TestActivityIncrementCall:

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_posts_to_the_internal_path_with_the_token(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
        token_env,
    ):
        resp = _send(client, "Точки активности")
        assert resp.status_code == 201, resp.text

        mock_activity_increment.assert_called_once()
        call = mock_activity_increment.call_args

        url = call.args[0] if call.args else call.kwargs["url"]
        assert url.endswith("/users/internal/1/activity/increment"), (
            f"the activity call still targets {url!r} — the old "
            "`/users/{{uid}}/activity/increment` path was removed and now 404s"
        )

        assert call.kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "notification-service dropped X-Internal-Token — user-service "
            "would answer 401 and activity points would silently stop"
        )
        assert call.kwargs["json"] == {"points": 1}
        assert call.kwargs["timeout"] == 3

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_the_old_public_path_is_not_used(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
        token_env,
    ):
        """Guard against a half-revert: `/users/1/activity/increment` without
        the `internal` segment is gone from user-service."""
        assert _send(client).status_code == 201
        url = mock_activity_increment.call_args.args[0]
        assert "/users/internal/" in url, url

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_the_token_is_read_at_call_time(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
        monkeypatch,
    ):
        """The helper must not capture the env into a module constant — the
        container reads its config after import."""
        import chat_routes

        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        assert _send(client, "one").status_code == 201
        chat_routes._last_message_time.clear()
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        assert _send(client, "two").status_code == 201

        sent = [c.kwargs["headers"]["X-Internal-Token"]
                for c in mock_activity_increment.call_args_list]
        assert sent == ["first", "second"], sent

    def test_the_helper_reads_the_env_not_a_constant(self):
        import inspect

        import chat_routes

        source = inspect.getsource(chat_routes.internal_token_headers)
        assert 'os.environ.get("INTERNAL_SERVICE_TOKEN"' in source

    def test_the_helper_returns_the_canonical_header_name(self, token_env):
        import chat_routes

        assert chat_routes.internal_token_headers() == {
            "X-Internal-Token": TOKEN
        }


# ══════════════════════════════════════════════════════════════════════════════
# 2. Failures are logged as warnings and never reach the player
# ══════════════════════════════════════════════════════════════════════════════
# `except: pass` used to hide this completely. A WARNING is the only signal an
# operator would ever get that activity points have stopped.


class TestActivityIncrementFailureIsLoggedNotSwallowed:

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_non_200_response_logs_a_warning_and_still_sends(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
        token_env, caplog,
    ):
        """This is what a dropped header looks like from here: 401 from the
        gate. The message must still go out, and the log must say so."""
        mock_activity_increment.return_value.status_code = 401
        mock_activity_increment.return_value.text = "Недействительный internal token"

        with caplog.at_level(logging.WARNING, logger="chat_routes"):
            resp = _send(client, "Сообщение проходит")

        assert resp.status_code == 201, resp.text
        assert resp.json()["content"] == "Сообщение проходит"

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "a rejected activity increment produced no WARNING"
        assert "401" in warnings[0].getMessage()

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_a_503_from_an_unconfigured_gate_also_warns(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
        token_env, caplog,
    ):
        """Fail-closed on the callee side: user-service answers 503 when its
        own INTERNAL_SERVICE_TOKEN is unset."""
        mock_activity_increment.return_value.status_code = 503
        mock_activity_increment.return_value.text = "Internal service token не настроен"

        with caplog.at_level(logging.WARNING, logger="chat_routes"):
            assert _send(client).status_code == 201

        assert any("503" in r.getMessage() for r in caplog.records
                   if r.levelno == logging.WARNING)

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_an_exception_logs_a_warning_and_still_sends(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
        token_env, caplog,
    ):
        mock_activity_increment.side_effect = requests.exceptions.ConnectionError(
            "user-service unreachable"
        )

        with caplog.at_level(logging.WARNING, logger="chat_routes"):
            resp = _send(client, "Сервис недоступен")

        assert resp.status_code == 201, resp.text
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "an exception in the activity call produced no WARNING"
        assert "unreachable" in warnings[-1].getMessage()

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_a_timeout_does_not_fail_the_chat_send(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
        token_env, caplog,
    ):
        mock_activity_increment.side_effect = requests.exceptions.Timeout("slow")

        with caplog.at_level(logging.WARNING, logger="chat_routes"):
            assert _send(client).status_code == 201

        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_the_call_is_not_swallowed_by_a_bare_except(self):
        """Regression guard on the fix itself: `except: pass` is what made the
        previous breakage invisible."""
        import inspect

        import chat_routes

        source = inspect.getsource(chat_routes.send_message)
        assert "except: pass" not in source.replace("\n", " ")
        assert "logger.warning" in source


# ══════════════════════════════════════════════════════════════════════════════
# 3. The rate limiter no longer depends on a live user-service
# ══════════════════════════════════════════════════════════════════════════════
# docs/ISSUES.md: `TestRateLimiting` was flaky because the unmocked activity
# call took ~4 s per send in an environment with slow DNS, so the 2-second
# window had already expired by the second message. With the autouse mock the
# handler does no network I/O at all.


class TestRateLimitingIsNotTimingDependent:

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_two_sends_stay_inside_the_window(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
    ):
        import time

        started = time.time()
        assert _send(client, "First").status_code == 201
        second = _send(client, "Second")
        elapsed = time.time() - started

        assert second.status_code == 429, (
            f"the second message was accepted after {elapsed:.2f}s — the "
            "rate-limit window expired mid-test, which is the flakiness "
            "docs/ISSUES.md describes"
        )
        assert elapsed < 1.0, (
            f"two chat sends took {elapsed:.2f}s — something in the handler is "
            "still doing real network I/O"
        )

    @patch("chat_routes._fetch_user_profile_data", return_value=_PROFILE)
    @patch("chat_routes.broadcast_to_channel")
    def test_a_failing_activity_call_does_not_slow_the_handler(
        self, mock_broadcast, mock_profile, client, mock_activity_increment,
    ):
        """Even when the increment fails, the send path stays fast — the
        warning must not be followed by a retry or a sleep."""
        import time

        mock_activity_increment.side_effect = requests.exceptions.ConnectionError("x")
        started = time.time()
        assert _send(client).status_code == 201
        assert time.time() - started < 1.0
