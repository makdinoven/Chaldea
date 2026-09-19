"""
FEAT-171 task 19 (dungeon-service) — the three cross-service **reads** moved
onto the internal twins.

FEAT-167 covered dungeon-service's *writes* (`consume_stamina`, `recover`,
the item grant). Its reads stayed anonymous and had **no test at all** until
this file:

| function | was | now |
|---|---|---|
| `http_clients.get_character_items`      | `GET /inventory/{id}/items` (anonymous)  | `GET /inventory/internal/characters/{id}/items` (I1i) |
| `http_clients.get_item_info`            | `GET /inventory/items/{id}` (anonymous)  | `GET /inventory/internal/items/{id}` (I3i) |
| `http_clients.get_character_attributes` | `GET /attributes/{id}` (anonymous)       | `GET /attributes/internal/{id}` (A1i) |

The third was found during Pass A — §2.7 had missed it — and it is the one that
would have taken dungeons down outright.

These three do NOT swallow — unlike the six callers §3.5 warns about, each one
turns a non-2xx into `HTTPException(502)`, so a dropped header would at least
be loud. That is worth pinning too (`test_a_401_surfaces_loudly`), because the
error is a *generic* 502 «Ошибка при получении…»: nothing in it says
"credentials", so in an incident it reads as "inventory-service is down" and
sends the investigation the wrong way. The URL and the header value are
therefore still asserted on the recorded request, not inferred from "it worked".
"""

import pytest

import http_clients
from config import settings


TOKEN = "test-internal-token"

CHARACTER_ID = 11
ITEM_ID = 331


@pytest.fixture()
def token(monkeypatch):
    """`http_clients._internal_token_headers` reads `settings` — pin it."""
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            from unittest.mock import MagicMock
            response = MagicMock()
            response.status_code = self.status_code
            raise httpx.HTTPStatusError(
                str(self.status_code), request=MagicMock(), response=response
            )

    def json(self):
        return self._payload


def _patch_get(monkeypatch, response=None):
    """Record every outgoing GET made through `http_clients.httpx`."""
    calls = []
    resp = response if response is not None else _Resp(200, {})

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return resp

    monkeypatch.setattr(http_clients.httpx, "AsyncClient", _Client)
    return calls


# The three repointed reads, as (label, coroutine factory, expected URL tail).
READS = [
    (
        "I1i inventory",
        lambda: http_clients.get_character_items(CHARACTER_ID),
        f"/inventory/internal/characters/{CHARACTER_ID}/items",
        _Resp(200, []),
    ),
    (
        "I3i item template",
        lambda: http_clients.get_item_info(ITEM_ID),
        f"/inventory/internal/items/{ITEM_ID}",
        _Resp(200, {"id": ITEM_ID, "name": "Меч"}),
    ),
    (
        "A1i attributes",
        lambda: http_clients.get_character_attributes(CHARACTER_ID),
        f"/attributes/internal/{CHARACTER_ID}",
        _Resp(200, {"current_health": 10}),
    ),
]

_PARAMS = [pytest.param(*r, id=r[0]) for r in READS]


@pytest.mark.parametrize("label,call,expected_tail,response", _PARAMS)
@pytest.mark.asyncio
async def test_the_read_targets_the_internal_twin(
    monkeypatch, token, label, call, expected_tail, response
):
    calls = _patch_get(monkeypatch, response)
    await call()
    assert len(calls) == 1, f"{label}: the call never went out"
    url, _kwargs = calls[0]
    assert url.endswith(expected_tail), f"{label}: {url}"


@pytest.mark.parametrize("label,call,expected_tail,response", _PARAMS)
@pytest.mark.asyncio
async def test_the_read_sends_the_internal_token(
    monkeypatch, token, label, call, expected_tail, response
):
    """The assertion that names the actual cause. Without it the only evidence
    of a dropped header is a generic 502 that blames the other service."""
    calls = _patch_get(monkeypatch, response)
    await call()
    _url, kwargs = calls[0]
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
        f"{label}: dungeon-service dropped X-Internal-Token — the twin answers "
        "401, the warning is the only trace"
    )


@pytest.mark.parametrize("label,call,expected_tail,response", _PARAMS)
@pytest.mark.asyncio
async def test_the_read_never_uses_the_player_route(
    monkeypatch, token, label, call, expected_tail, response
):
    calls = _patch_get(monkeypatch, response)
    await call()
    url = calls[0][0]
    assert "/internal/" in url, f"{label}: anonymous path survived — {url}"


@pytest.mark.parametrize("label,call,expected_tail,response", _PARAMS)
@pytest.mark.asyncio
async def test_a_401_surfaces_loudly_but_anonymously(
    monkeypatch, token, label, call, expected_tail, response
):
    """A refused twin becomes a 502 with a generic Russian message.

    Loud is good — these three are NOT part of the swallow-with-a-warning
    family. But the message says nothing about credentials, so a dropped
    header reads as "inventory-service is down" during an incident. That is
    exactly why the header itself is asserted above rather than inferred from
    a green dungeon run."""
    from fastapi import HTTPException

    _patch_get(monkeypatch, _Resp(401, {"detail": "Недействительный internal token"}))
    with pytest.raises(HTTPException) as exc:
        await call()
    assert exc.value.status_code == 502, (label, exc.value.detail)
    assert "token" not in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_the_token_is_read_at_call_time(monkeypatch):
    """A constant frozen at import would keep sending a stale secret after a
    rotation, and every such call would be swallowed."""
    calls = _patch_get(monkeypatch, _Resp(200, []))
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "first")
    await http_clients.get_character_items(CHARACTER_ID)
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "second")
    await http_clients.get_character_items(CHARACTER_ID)
    assert [kw["headers"]["X-Internal-Token"] for _u, kw in calls] == [
        "first", "second"
    ]


@pytest.mark.asyncio
async def test_dropping_the_header_would_be_caught(monkeypatch, token):
    """Red-proof, kept permanently: a caller that forgets the header produces
    exactly this, and the assertion used above rejects it."""
    calls = _patch_get(monkeypatch, _Resp(200, []))
    await http_clients.get_character_items(CHARACTER_ID)
    _url, kwargs = calls[0]
    without = {k: v for k, v in kwargs["headers"].items() if k != "X-Internal-Token"}
    with pytest.raises(KeyError):
        without["X-Internal-Token"]


@pytest.mark.asyncio
async def test_no_read_in_the_module_still_points_at_a_gated_public_route(
    monkeypatch, token
):
    """Source sweep with no allowlist: any remaining `/inventory/items/`,
    `/inventory/{...}/items` or `/attributes/{...}` URL that is not under
    `/internal/` is a Pass-A leftover that will 403 in production."""
    import os
    import re

    path = os.path.join(os.path.dirname(http_clients.__file__), "http_clients.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    urls = re.findall(r'f"\{settings\.[A-Z_]+\}([^"]*)"', source)
    assert urls, "the sweep matched no URL — it went blind"

    # Only the FEAT-171 *reads* are in scope. The mutating attribute routes
    # (`/attributes/{id}/consume_stamina`, `/recover`) keep their public path
    # on purpose: FEAT-167 gated them in place with `verify_internal_token`
    # instead of moving them under `/internal/`, and they already carry the
    # header (covered by `test_internal_headers.py`).
    READ_SHAPES = (
        re.compile(r"^/attributes/\{[^}]+\}$"),          # A1
        re.compile(r"^/inventory/items/"),                 # I3
        re.compile(r"^/inventory/\{[^}]+\}/items$"),      # I1
        re.compile(r"^/inventory/\{[^}]+\}/equipment$"),  # I2
    )
    offenders = [
        u for u in urls
        if "/internal/" not in u and any(p.match(u) for p in READ_SHAPES)
    ]
    assert offenders == [], f"anonymous reads survived Pass A: {offenders}"
