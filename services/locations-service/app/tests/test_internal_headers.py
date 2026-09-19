"""
FEAT-167 — locations-service is the biggest caller of the newly gated routes.

Seven calls in total; the three standalone client helpers in `crud.py` are
asserted here on the real functions:

  * `_consume_stamina_via_attributes`  -> POST /attributes/{id}/consume_stamina
  * `_refund_stamina_via_attributes`   -> POST /attributes/{id}/refund_stamina
  * `award_post_xp_and_log`            -> PUT  /attributes/{id}/passive_experience
    (the seventh caller, found only during implementation — it is
    fire-and-forget, so without the header the XP for role-play posts would
    have disappeared without a single error anywhere)

The three item grants in `main.py` (location loot, NPC shop, quest reward) used
to forward the *player's* `Authorization`; they must now use the internal route
with the service token instead. That is covered by a source sweep, because those
calls sit inside large endpoint handlers.
"""

import inspect
import os
import re

import pytest

import crud


TOKEN = "test-internal-token"

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def token(monkeypatch):
    """`crud` reads the token into a module constant at import time."""
    monkeypatch.setattr(crud, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "{}"

    def json(self):
        return {}

    def raise_for_status(self):
        return None


def _patch_client(monkeypatch, response=None):
    """Patch `crud.httpx.AsyncClient`, recording POSTs and PUTs."""
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
            calls.append(("POST", url, kwargs))
            return resp

        async def put(self, url, **kwargs):
            calls.append(("PUT", url, kwargs))
            return resp

        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            return resp

    monkeypatch.setattr(crud.httpx, "AsyncClient", _Client)
    return calls


class TestStaminaCalls:

    @pytest.mark.asyncio
    async def test_consume_stamina_sends_the_token(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)
        assert await crud._consume_stamina_via_attributes(31, 5) is True

        method, url, kwargs = calls[0]
        assert method == "POST"
        assert url.endswith("/attributes/31/consume_stamina"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "locations-service dropped X-Internal-Token on consume_stamina — "
            "gathering and travel would stop working with a 502"
        )
        assert kwargs["json"] == {"amount": 5}

    @pytest.mark.asyncio
    async def test_refund_stamina_sends_the_token(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)
        assert await crud._refund_stamina_via_attributes(31, 5) is True

        method, url, kwargs = calls[0]
        assert method == "POST"
        assert url.endswith("/attributes/31/refund_stamina"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN
        assert kwargs["json"] == {"amount": 5}

    @pytest.mark.asyncio
    async def test_a_401_is_reported_as_failure_not_success(self, monkeypatch, token):
        """Both helpers return False on a non-200 — an auth failure must not be
        mistaken for a paid-for stamina charge."""
        _patch_client(monkeypatch, response=_Resp(status_code=401))
        assert await crud._consume_stamina_via_attributes(31, 5) is False
        assert await crud._refund_stamina_via_attributes(31, 5) is False


class TestPostXpCall:

    @pytest.mark.asyncio
    async def test_award_post_xp_sends_the_token(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)

        await crud.award_post_xp_and_log(
            character_id=31, post_id=1, location_id=2,
            location_name="Цитадель", char_count=400, xp=4,
        )

        xp_calls = [c for c in calls if "passive_experience" in c[1]]
        assert xp_calls, "the post XP never reached character-attributes-service"
        method, url, kwargs = xp_calls[0]
        assert method == "PUT"
        assert url.endswith("/attributes/31/passive_experience"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "the post-XP call dropped X-Internal-Token — this call is "
            "fire-and-forget, so the XP would vanish without any error"
        )
        assert kwargs["json"] == {"amount": 4}

    @pytest.mark.asyncio
    async def test_zero_xp_makes_no_attributes_call(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)
        await crud.award_post_xp_and_log(
            character_id=31, post_id=1, location_id=2,
            location_name="Цитадель", char_count=100, xp=0,
        )
        assert not [c for c in calls if "passive_experience" in c[1]]


class TestSourceSweep:
    """The calls that live inside endpoint handlers are pinned by reading the
    source: a new caller that forgets the header, or one that goes back to the
    admin-gated grant path, fails here."""

    GATED_ATTRIBUTE_PATHS = (
        "/consume_stamina", "/refund_stamina",
        "/apply_modifiers", "/recover",
        "/active_experience", "/passive_experience",
    )

    def _sources(self):
        for filename in ("main.py", "crud.py"):
            path = os.path.join(_APP_DIR, filename)
            with open(path, encoding="utf-8") as fh:
                yield filename, fh.read()

    def test_every_gated_attributes_call_carries_the_header(self):
        offenders = []
        for filename, source in self._sources():
            for gated in self.GATED_ATTRIBUTE_PATHS:
                for match in re.finditer(re.escape(gated), source):
                    idx = match.start()
                    window = source[max(0, idx - 200): idx + 700]
                    if "_internal_token_headers()" not in window:
                        line = source.count("\n", 0, idx) + 1
                        offenders.append(f"{filename}:{line} ({gated})")
        assert not offenders, (
            "gated attributes call(s) without X-Internal-Token: "
            + "; ".join(offenders)
        )

    def test_item_grants_use_the_internal_route(self):
        """Loot pickup, NPC shop purchase and quest reward must POST to
        `/inventory/internal/characters/{cid}/items`."""
        offenders = []
        for filename, source in self._sources():
            for match in re.finditer(r"/inventory/[^\"'\s]*items", source):
                fragment = match.group(0)
                if "internal/characters" in fragment:
                    continue
                # a GET read of the inventory is fine; only grants matter
                window = source[max(0, match.start() - 400): match.start() + 400]
                if ".post(" not in window:
                    continue
                line = source.count("\n", 0, match.start()) + 1
                offenders.append(f"{filename}:{line} ({fragment})")
        assert not offenders, (
            "item grant(s) still using the admin-gated route: " + "; ".join(offenders)
        )

    def test_item_grants_no_longer_forward_the_player_token(self):
        """The player's `Authorization` must not be forwarded on the grants —
        ownership is validated in locations-service before the call, and the
        callee now trusts the service token instead."""
        offenders = []
        for filename, source in self._sources():
            for match in re.finditer(r"/inventory/internal/characters/", source):
                window = source[match.start(): match.start() + 700]
                if "auth_header" in window or "Authorization" in window:
                    line = source.count("\n", 0, match.start()) + 1
                    offenders.append(f"{filename}:{line}")
        assert not offenders, (
            "grant call(s) still forwarding the player's token: "
            + "; ".join(offenders)
        )

    def test_helper_exists_and_reads_the_module_constant(self):
        source = inspect.getsource(crud._internal_token_headers)
        assert "X-Internal-Token" in source


# ---------------------------------------------------------------------------
# FEAT-167 #17 — the cumulative-stats call
# ---------------------------------------------------------------------------
# `POST /attributes/cumulative_stats/increment` is internal-only now.
# `main._track_cumulative_stats` is the eighth call from this service and is
# fire-and-forget: without the header, role-play post counters, travel counters
# and quest completions would stop feeding perks with no error anywhere.
# It sits in `main.py`, which the caller suites already import, so it is
# asserted on the real function rather than swept from source.


class TestCumulativeStatsHeader:

    def _patch_main_client(self, monkeypatch):
        import main

        calls = []

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, **kwargs):
                calls.append((url, kwargs))
                return _Resp()

        monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
        return main, calls

    @pytest.mark.asyncio
    async def test_track_cumulative_stats_sends_the_token(self, monkeypatch):
        main, calls = self._patch_main_client(monkeypatch)
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)

        await main._track_cumulative_stats(5, {"total_posts": 1})

        url, kwargs = calls[0]
        assert url.endswith("/attributes/cumulative_stats/increment"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "locations-service dropped X-Internal-Token — post/travel/quest "
            "counters and the perks behind them would silently stop"
        )
        assert kwargs["json"]["character_id"] == 5

    @pytest.mark.asyncio
    async def test_every_increment_call_site_goes_through_the_helper(self):
        """All seven `_track_cumulative_stats(...)` call sites share the single
        helper, so one header fix covers them all — a site that builds its own
        POST would bypass the token."""
        source = open(
            os.path.join(_APP_DIR, "main.py"), encoding="utf-8"
        ).read()
        direct = [
            source.count("\n", 0, m.start()) + 1
            for m in re.finditer(r"cumulative_stats/increment", source)
        ]
        # exactly one place builds the URL: the helper itself
        assert len(direct) == 1, (
            f"more than one cumulative-stats URL in main.py (lines {direct}) — "
            "each needs its own X-Internal-Token"
        )


# ---------------------------------------------------------------------------
# FEAT-169 — four more locations-service calls into newly gated routes
# ---------------------------------------------------------------------------
# `POST /party/internal/xp-bonus`, `GET /party/internal/active-members`,
# `POST /inventory/internal/.../gathering/award` and `.../free_slots_check` are
# all gated now. Three of the four are best-effort (WARNING + continue) and the
# fourth fails *closed*, so a dropped header would not raise anywhere: squad
# bonuses, squad rosters and gathering rewards would simply stop, and the player
# would be told their bag is full. Asserted on the real `crud` functions.
#
# NOTE for review: `GET /party/internal/active-members` had **no** caller row in
# the design's §3.4 matrix at all — this locations caller (`crud.py:7119`) and
# the battle/dungeon ones were found only during implementation.


class TestPartyCallsCarryTheToken:

    @pytest.mark.asyncio
    async def test_post_xp_bonus_sends_the_token(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)
        await crud.award_post_xp_and_log(
            character_id=31, post_id=1, location_id=2,
            location_name="Цитадель", char_count=400, xp=4,
        )

        bonus = [c for c in calls if "xp-bonus" in c[1]]
        assert bonus, "the party bonus for the post never reached party-service"
        _, url, kwargs = bonus[0]
        assert url.endswith("/party/internal/xp-bonus"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "the post party-bonus call dropped X-Internal-Token — it is "
            "fire-and-forget, so the bonus would vanish without any error"
        )

    @pytest.mark.asyncio
    async def test_active_members_sends_the_token(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)
        await crud._party_active_member_ids(31, 2)

        assert calls, "the squad roster lookup never reached party-service"
        method, url, kwargs = calls[0]
        assert method == "GET"
        assert url.endswith("/party/internal/active-members"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "active-members dropped X-Internal-Token — the lookup swallows "
            "errors and returns an empty set, so co-located squadmates would "
            "silently disappear from party activities"
        )
        assert kwargs["params"] == {"character_id": 31, "location_id": 2}


class TestInventoryGatheringCallsCarryTheToken:

    @pytest.mark.asyncio
    async def test_gathering_award_sends_the_token(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)
        await crud._award_via_inventory(
            character_id=31, skill_slug="mining", result_item_id=7,
            granted_quantity=2, tool_inventory_item_id=None,
        )

        method, url, kwargs = calls[0]
        assert method == "POST"
        assert url.endswith("/gathering/award"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "gathering/award dropped X-Internal-Token — the caller only logs a "
            "WARNING, so the gathered resource and its XP would be lost silently"
        )

    @pytest.mark.asyncio
    async def test_free_slots_check_sends_the_token(self, monkeypatch, token):
        calls = _patch_client(monkeypatch)
        await crud._check_inventory_has_free_slot(31)

        method, url, kwargs = calls[0]
        assert method == "POST"
        assert url.endswith("/free_slots_check"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "free_slots_check dropped X-Internal-Token — this one fails closed, "
            "so every player would be told their bag is full"
        )
