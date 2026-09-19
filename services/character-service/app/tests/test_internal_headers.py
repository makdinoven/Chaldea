"""
FEAT-167 #17/#18 — character-service must send `X-Internal-Token` when it
creates a character's attributes and inventory.

`POST /attributes/` and `POST /inventory/` were reachable anonymously through
the gateway (they answered 422 on the body schema instead of 401, so anyone
could seed attribute rows and equipment slots for arbitrary character ids).
Both are internal-only now, and character-service is their **only** caller:

  * `crud.send_attributes_request`       -> POST /attributes/   (character
    creation — hard-fail, rolls the character back — and admin NPC creation)
  * `crud._sync_send_attributes_request` -> POST /attributes/   (mob spawn)
  * `crud.send_inventory_request`        -> POST /inventory/    (starter kit)

Nothing else in the repo posts to either bare base URL, so if these three drop
the header, character creation breaks outright and mob spawns and starter kits
break silently (they log and continue). The existing `test_http_helpers.py`
mocks the transport but never looked at the headers, which is why this file
asserts on the **real** helper functions.
"""

import asyncio

import pytest

import crud


TOKEN = "test-internal-token"


@pytest.fixture()
def token(monkeypatch):
    """`auth_http` reads the secret into a module constant at import time and
    `crud._internal_token_headers` imports it lazily — pin the constant."""
    import auth_http
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "{}"

    def json(self):
        return {"id": 1}


def _patch_async_client(monkeypatch, response=None):
    calls = []
    resp = response or _Resp()

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return resp

    monkeypatch.setattr(crud.httpx, "AsyncClient", _Client)
    return calls


def _patch_sync_post(monkeypatch, response=None):
    calls = []
    resp = response or _Resp()

    def _post(url, **kwargs):
        calls.append((url, kwargs))
        return resp

    monkeypatch.setattr(crud.httpx, "post", _post)
    return calls


class TestInternalHeaderHelper:

    def test_helper_returns_the_configured_token(self, token):
        assert crud._internal_token_headers() == {"X-Internal-Token": TOKEN}

    def test_helper_reads_the_constant_at_call_time(self, monkeypatch):
        """A frozen copy taken at import time would make the tests above pass
        and production fail whenever the value is rotated."""
        import auth_http
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "first")
        assert crud._internal_token_headers()["X-Internal-Token"] == "first"
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "second")
        assert crud._internal_token_headers()["X-Internal-Token"] == "second"


class TestOutgoingCreationCallsSendTheToken:

    def test_send_attributes_request_sends_the_token(self, monkeypatch, token):
        calls = _patch_async_client(monkeypatch)
        result = asyncio.run(crud.send_attributes_request(7, {"strength": 10}))

        assert result is not None
        url, kwargs = calls[0]
        assert url.rstrip("/").endswith("/attributes"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "character-service dropped X-Internal-Token — character creation "
            "would fail with «Не удалось создать атрибуты»"
        )
        assert kwargs["json"]["character_id"] == 7

    def test_sync_send_attributes_request_sends_the_token(self, monkeypatch, token):
        """The mob-spawn path: fire-and-forget, so a missing header would mean
        mobs quietly spawning without attributes."""
        calls = _patch_sync_post(monkeypatch)
        result = crud._sync_send_attributes_request(9, {"strength": 10})

        assert result is not None
        url, kwargs = calls[0]
        assert url.rstrip("/").endswith("/attributes"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN
        assert kwargs["json"]["character_id"] == 9

    def test_send_inventory_request_sends_the_token(self, monkeypatch, token):
        calls = _patch_async_client(monkeypatch)
        result = asyncio.run(
            crud.send_inventory_request(7, [{"item_id": 1, "quantity": 2}])
        )

        assert result is not None
        url, kwargs = calls[0]
        assert url.rstrip("/").endswith("/inventory"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "character-service dropped X-Internal-Token — the starter kit would "
            "silently never be granted"
        )
        assert kwargs["json"]["character_id"] == 7

    @pytest.mark.parametrize("value", ["first", "second"])
    def test_the_token_is_not_frozen_at_import(self, monkeypatch, value):
        import auth_http
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", value)
        calls = _patch_async_client(monkeypatch)
        asyncio.run(crud.send_attributes_request(1, {}))
        assert calls[0][1]["headers"]["X-Internal-Token"] == value


# ═══════════════════════════════════════════════════════════════════════════
# FEAT-169 #15/#16/#17 — the three calls that now need the token
# ═══════════════════════════════════════════════════════════════════════════
# §3.4 lists these three character-service call sites. All three **swallow the
# error** (they log and return `None`, or log a warning and continue), so a
# dropped header raises nothing anywhere:
#
#   16  crud.send_skills_presets_request  -> POST /skills/internal/assign_multiple
#       The character-approval step that grants the preset skills. Re-pointed
#       from the public `/skills/assign_multiple`, which is now behind
#       `require_permission("skills:create")` — so the OLD url would answer
#       401/403 and a character would be approved **with no skills at all**,
#       silently. The url is therefore asserted as hard as the header is.
#   17  crud.send_skills_request          -> POST /skills/ (legacy)
#   15  main.get_full_profile             -> POST /attributes/internal/{id}/reconcile-perks
#       Fired after a level-up; a warning is the only trace it leaves.
#
# Every assertion below runs the REAL function with `httpx` patched and reads
# `call.kwargs["headers"]["X-Internal-Token"]`. A test that only checked "no
# exception raised" would pass with the header removed — which is exactly the
# regression this feature is about (CLAUDE.md «тихие отказы»).


class TestSkillsPresetsCallIsInternal:
    """FEAT-169 #16 — character approval grants the preset skills."""

    def test_sends_the_internal_token(self, monkeypatch, token):
        calls = _patch_async_client(monkeypatch)

        result = asyncio.run(crud.send_skills_presets_request(11, [3, 4]))

        assert result is not None, "the preset-skills call did not go out"
        assert len(calls) == 1
        url, kwargs = calls[0]
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "character-service dropped X-Internal-Token on assign_multiple — "
            "the character would be approved with no skills and nothing would "
            "be raised"
        )

    def test_targets_the_internal_twin_not_the_public_rbac_route(
        self, monkeypatch, token,
    ):
        """The public `/skills/assign_multiple` is now admin-only
        (`require_permission("skills:create")`, FEAT-169 §3.1 group 4): a
        service call to it would 401/403 and be swallowed."""
        calls = _patch_async_client(monkeypatch)

        asyncio.run(crud.send_skills_presets_request(11, [3, 4]))

        url = calls[0][0]
        assert url.endswith("/skills/internal/assign_multiple"), url
        assert "/skills/assign_multiple" not in url.replace(
            "/skills/internal/assign_multiple", "",
        ), f"still pointing at the public admin route: {url}"

    def test_sends_the_unchanged_body(self, monkeypatch, token):
        """The contract of the internal twin is byte-for-byte the old one."""
        calls = _patch_async_client(monkeypatch)

        asyncio.run(crud.send_skills_presets_request(11, [3, 4]))

        assert calls[0][1]["json"] == {
            "character_id": 11,
            "skills": [{"skill_id": 3}, {"skill_id": 4}],
        }

    def test_the_token_is_read_at_call_time(self, monkeypatch):
        """A value frozen at import would send an empty header in a container
        that received the secret later, or after a rotation."""
        import auth_http
        calls = _patch_async_client(monkeypatch)

        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "first")
        asyncio.run(crud.send_skills_presets_request(1, [1]))
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "second")
        asyncio.run(crud.send_skills_presets_request(1, [1]))

        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    def test_a_401_is_swallowed_which_is_why_the_header_is_tested(
        self, monkeypatch, token,
    ):
        """Pins the silent-failure shape itself: if skills-service rejects the
        call, this function returns `None` and the approval carries on. Nothing
        downstream can notice — only the assertions above can."""
        _patch_async_client(monkeypatch, _Resp(status_code=401))

        assert asyncio.run(crud.send_skills_presets_request(11, [3])) is None


class TestLegacySkillsCallIsInternal:
    """FEAT-169 #17 — the legacy `POST /skills/` ("Basic Attack") helper."""

    def test_sends_the_internal_token(self, monkeypatch, token):
        calls = _patch_async_client(monkeypatch)

        result = asyncio.run(crud.send_skills_request(12))

        assert result is not None
        url, kwargs = calls[0]
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "character-service dropped X-Internal-Token on the legacy "
            "POST /skills/ — the call would 401 and be logged, not raised"
        )
        assert kwargs["json"] == {"character_id": 12}

    def test_still_targets_the_bare_skills_base_url(self, monkeypatch, token):
        """This route was gated, not moved — the path must not have drifted."""
        calls = _patch_async_client(monkeypatch)
        asyncio.run(crud.send_skills_request(12))
        assert calls[0][0].rstrip("/").endswith("/skills"), calls[0][0]

    def test_the_token_is_read_at_call_time(self, monkeypatch):
        import auth_http
        calls = _patch_async_client(monkeypatch)

        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "first")
        asyncio.run(crud.send_skills_request(1))
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "second")
        asyncio.run(crud.send_skills_request(1))

        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]


class TestReconcilePerksCallIsInternal:
    """FEAT-169 #15 — `main.get_full_profile` re-evaluates perks after a
    level-up. `character-attributes-service` gates
    `POST /attributes/internal/{id}/reconcile-perks` now, and this call site is
    wrapped in `try/except` with a warning — so it is invisible when broken."""

    # The live end-to-end assertion (the real `GET /{id}/full_profile` handler,
    # a real level-up, `main.httpx` patched, header read off the captured POST)
    # lives in `test_xp_multiplier_call_shape.py::TestReconcilePerksAfterLevelUp`
    # — that module already owns the full_profile harness. What is pinned here
    # is the source-level invariant, so a *new* reconcile-perks call anywhere in
    # the service cannot be added without the header.

    def test_the_handler_source_passes_the_header_helper(self):
        """The call itself lives inline in `main.get_full_profile`, so it is
        pinned at the source level too: a `reconcile-perks` POST from this
        service without `_internal_token_headers()` next to it fails here.
        Mirrors the source sweep in party-service's `test_internal_headers.py`.
        """
        import pathlib

        import main

        offenders = []
        for module in (main, crud):
            source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
            idx = 0
            while True:
                idx = source.find("reconcile-perks", idx)
                if idx == -1:
                    break
                window = source[max(0, idx - 400): idx + 400]
                if "_internal_token_headers()" not in window:
                    offenders.append(
                        f"{pathlib.Path(module.__file__).name}: offset {idx}"
                    )
                idx += len("reconcile-perks")

        assert not offenders, (
            "reconcile-perks call(s) without the internal header: "
            + "; ".join(offenders)
        )


class TestEverySkillsCallCarriesTheHeader:
    """A source sweep over the whole service: any call targeting one of the
    now-gated skills routes must pass `_internal_token_headers()`. Adding a new
    one without the header breaks this test instead of breaking character
    creation in production."""

    def test_source_sweep(self):
        import pathlib

        import main

        offenders = []
        for module in (main, crud):
            path = pathlib.Path(module.__file__)
            source = path.read_text(encoding="utf-8")
            for gated in ("assign_multiple", "SKILLS_SERVICE_URL"):
                idx = 0
                while True:
                    idx = source.find(gated, idx)
                    if idx == -1:
                        break
                    window = source[max(0, idx - 500): idx + 500]
                    # Only call sites matter — a bare settings reference or a
                    # comment has no `client.post(` near it.
                    if ".post(" in window and "_internal_token_headers()" not in window:
                        offenders.append(f"{path.name}: {gated} at offset {idx}")
                    idx += len(gated)

        assert not offenders, (
            "skills call(s) without the internal header: " + "; ".join(offenders)
        )
