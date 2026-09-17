"""
FEAT-167 — party-service must send `X-Internal-Token` on its XP calls.

`PUT /attributes/{id}/active_experience` and `/passive_experience` are
internal-only now. Both party call sites are fire-and-forget (they log and
continue), so a missing header would not raise anywhere — squad XP would simply
stop arriving, silently. party-service also had **no** test touching these
functions and **no** `INTERNAL_SERVICE_TOKEN` in either compose file before this
feature, which is exactly the combination that hides such a regression.

The assertions run against the real `main._charge_active_xp` /
`main._award_passive_xp` (no re-implemented client), with `httpx` patched.
"""

import os

import pytest

import main


TOKEN = "test-internal-token"


@pytest.fixture()
def token_env(monkeypatch):
    """The helper reads the env at call time, so the env is what we pin."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    status_code = 200
    text = "{}"


def _captured(monkeypatch, verb):
    calls = []

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        return _Resp()

    monkeypatch.setattr(main.httpx, verb, fake)
    return calls


class TestChargeActiveXp:

    def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _captured(monkeypatch, "put")
        main._charge_active_xp(42, 15)

        assert len(calls) == 1, "the XP charge did not reach attributes-service"
        url, kwargs = calls[0]
        assert url.endswith("/42/active_experience"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "party-service dropped X-Internal-Token — the call would 401 and "
            "the squad XP charge would be lost silently"
        )
        assert kwargs["json"] == {"amount": -15}

    def test_zero_amount_makes_no_call(self, monkeypatch, token_env):
        calls = _captured(monkeypatch, "put")
        main._charge_active_xp(42, 0)
        assert calls == []

    def test_token_is_read_at_call_time(self, monkeypatch):
        """A module-level constant would freeze the value at import and send an
        empty header in a container that got the var later."""
        calls = _captured(monkeypatch, "put")
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        main._charge_active_xp(1, 5)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        main._charge_active_xp(1, 5)

        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    def test_non_200_is_logged_not_swallowed(self, monkeypatch, token_env, caplog):
        """A future 401 must be visible in the logs (the call is best-effort)."""
        class _Fail:
            status_code = 401
            text = '{"detail": "Недействительный internal token"}'

        monkeypatch.setattr(main.httpx, "put", lambda url, **kw: _Fail())
        with caplog.at_level("WARNING"):
            main._charge_active_xp(42, 15)
        assert any("401" in record.getMessage() for record in caplog.records)


class TestAwardPassiveXp:

    def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _captured(monkeypatch, "put")
        main._award_passive_xp(43, 7)

        assert len(calls) == 1
        url, kwargs = calls[0]
        assert url.endswith("/43/passive_experience"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "party-service dropped X-Internal-Token — the squad XP trickle "
            "would be lost silently"
        )
        assert kwargs["json"] == {"amount": 7}

    def test_zero_amount_makes_no_call(self, monkeypatch, token_env):
        calls = _captured(monkeypatch, "put")
        main._award_passive_xp(43, 0)
        assert calls == []

    def test_non_200_is_logged_not_swallowed(self, monkeypatch, token_env, caplog):
        class _Fail:
            status_code = 401
            text = '{"detail": "Недействительный internal token"}'

        monkeypatch.setattr(main.httpx, "put", lambda url, **kw: _Fail())
        with caplog.at_level("WARNING"):
            main._award_passive_xp(43, 7)
        assert any("401" in record.getMessage() for record in caplog.records)


class TestEveryAttributesCallCarriesTheHeader:
    """A sweep over the source: every call in party-service that targets one of
    the gated `/attributes/{id}/...` paths must pass `_internal_token_headers()`.
    Adding a new XP call without the header breaks this test."""

    def test_source_sweep(self):
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        offenders = []
        for filename in ("main.py", "crud.py"):
            path = os.path.join(app_dir, filename)
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            for gated in ("active_experience", "passive_experience"):
                idx = 0
                while True:
                    idx = source.find(gated, idx)
                    if idx == -1:
                        break
                    window = source[max(0, idx - 400): idx + 400]
                    if "_internal_token_headers()" not in window:
                        offenders.append(f"{filename}: {gated} near offset {idx}")
                    idx += len(gated)
        assert not offenders, (
            "gated attributes call(s) without the internal header: "
            + "; ".join(offenders)
        )
