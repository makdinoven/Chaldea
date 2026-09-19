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
    the gated character-attributes paths must pass the token helper.
    Adding a new XP (or settle-regen) call without the header breaks this test.

    FEAT-169 note: `main.py` calls `_internal_token_headers()` (a thin alias
    kept for the existing call sites) while `crud.py` calls
    `internal_token_headers()` from the new `internal_auth` leaf module, so the
    needle is the un-prefixed name — it matches both spellings."""

    GATED_PATHS = ("active_experience", "passive_experience",
                   "internal/settle-regen")

    def test_source_sweep(self):
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        offenders = []
        for filename in ("main.py", "crud.py"):
            path = os.path.join(app_dir, filename)
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            for gated in self.GATED_PATHS:
                idx = 0
                while True:
                    idx = source.find(gated, idx)
                    if idx == -1:
                        break
                    window = source[max(0, idx - 400): idx + 400]
                    if "internal_token_headers()" not in window:
                        line = source.count("\n", 0, idx) + 1
                        offenders.append(f"{filename}:{line} ({gated})")
                    idx += len(gated)
        assert not offenders, (
            "gated call(s) without the internal header: " + "; ".join(offenders)
        )


# ---------------------------------------------------------------------------
# FEAT-169 — `POST /attributes/internal/settle-regen`
# ---------------------------------------------------------------------------
# `crud.settle_regen` runs before every read of squad member resources
# (`get_attributes_map`). It is **best effort**: a non-200 or an exception is
# logged at WARNING and the read continues with whatever is stored. So a
# dropped header would not raise anywhere — the squad panel would just start
# showing stale health/mana, forever, with nothing but a log line.
#
# `crud.py` could not import the helper from `main.py` (circular), which is why
# FEAT-169 M1/M2 put both directions in the leaf module `internal_auth`. These
# assertions run against the **real** `crud.settle_regen` with `httpx` patched.


class TestSettleRegenHeader:

    def _captured(self, monkeypatch):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return _Resp()

        monkeypatch.setattr(main.crud.httpx, "post", fake_post)
        return calls

    def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = self._captured(monkeypatch)
        main.crud.settle_regen([1, 2])

        assert len(calls) == 1, "settle-regen never reached attributes-service"
        url, kwargs = calls[0]
        assert url.endswith("/internal/settle-regen"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "party-service dropped X-Internal-Token on settle-regen — the call "
            "would 401 and squad member resources would silently go stale"
        )
        assert kwargs["json"] == {"character_ids": [1, 2]}
        assert kwargs["timeout"] == main.crud.SETTLE_REGEN_TIMEOUT_SECONDS

    def test_token_is_read_at_call_time(self, monkeypatch):
        """`internal_auth.internal_token_headers()` reads the env on every
        call. A module constant captured at import would freeze an empty value
        in a container that received the variable later."""
        calls = self._captured(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        main.crud.settle_regen([1])
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        main.crud.settle_regen([2])

        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    def test_every_chunk_carries_the_header(self, monkeypatch, token_env):
        """Long member lists are chunked — the header must be on each POST, not
        only the first."""
        calls = self._captured(monkeypatch)
        main.crud.settle_regen(list(range(1, 121)))

        assert len(calls) == 3
        assert all(c[1]["headers"]["X-Internal-Token"] == TOKEN for c in calls)

    def test_a_401_is_logged_not_swallowed(self, monkeypatch, token_env, caplog):
        class _Fail:
            status_code = 401
            text = '{"detail": "Недействительный internal token"}'

        monkeypatch.setattr(main.crud.httpx, "post", lambda url, **kw: _Fail())
        with caplog.at_level("WARNING", logger="crud"):
            main.crud.settle_regen([1])
        assert any("401" in record.getMessage() for record in caplog.records)
