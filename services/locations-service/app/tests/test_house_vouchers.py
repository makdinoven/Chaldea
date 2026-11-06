"""FEAT-205 (task 11): house vouchers — a faction rank reward «право на дом / участок».

Runs on the house world of ``test_houses`` (file-backed SQLite, TestClient, sync):

* ``POST /locations/houses/internal/vouchers``: internal token, idempotent by ``source_key`` (same id, duplicate
  flag), unknown location 404, kind / length validation;
* ``GET /locations/houses/vouchers``: own character only;
* ``POST /locations/houses/plots/{id}/claim``: a free house of the voucher's kind in its location, NO gold charged,
  the voucher flips to claimed with the house id; mismatched kind / location, already used, plot taken, not on the
  spot, someone else's voucher / character -> refused and nothing changes;
* character deletion drops the vouchers.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import main  # noqa: E402
from test_houses import (  # noqa: E402,F401  (api is a fixture)
    ADMIN, FAR, FRIEND, OWNER, STRANGER, TOWN, _gold, _layout, _plot, api,
)

TOKEN = "t"
HEAD = {"X-Internal-Token": TOKEN}


@pytest.fixture()
def vapi(api, monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return api


def grant(api, character_id=10, location_id=TOWN, kind="ready", key="faction:grant:1:voucher:ready",
          text="Награда за звание «Рыцарь» (Орден Зари): дом"):
    return api.c.post("/locations/houses/internal/vouchers", headers=HEAD, json={
        "character_id": character_id, "location_id": location_id, "kind": kind, "source_key": key,
        "source_text": text})


def voucher_id(api, **kw):
    r = grant(api, **kw)
    assert r.status_code == 200, r.text
    return r.json()["voucher_id"]


def empty_plot(api, location_id=TOWN, price=50):
    r = api.as_(ADMIN).post("/admin/plots", {"location_id": location_id, "name": "Пустырь", "price": price,
                                             **_layout(2), "kind": "empty"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def claim(api, plot_id, vid, character_id=10, uid=OWNER):
    return api.as_(uid).post(f"/plots/{plot_id}/claim", {"character_id": character_id, "voucher_id": vid})


def voucher_row(api, vid):
    return api.sql("SELECT status, claimed_house_id, claimed_at FROM house_vouchers WHERE id = :v", v=vid)[0]


# --- internal grant -----------------------------------------------------------

def test_grant_is_idempotent_by_source_key(vapi):
    first = grant(vapi)
    assert first.status_code == 200 and first.json()["duplicate"] is False
    again = grant(vapi, location_id=FAR, kind="empty")                       # same key: the first one wins
    assert again.json() == {"voucher_id": first.json()["voucher_id"], "duplicate": True}
    assert vapi.sql("SELECT COUNT(*), MIN(location_id), MIN(kind) FROM house_vouchers")[0] == (1, TOWN, "ready")
    other = grant(vapi, key="faction:grant:1:voucher:empty", kind="empty")
    assert other.json()["duplicate"] is False and other.json()["voucher_id"] != first.json()["voucher_id"]


def test_grant_needs_the_internal_token(vapi):
    body = {"character_id": 10, "location_id": TOWN, "kind": "ready", "source_key": "k"}
    assert vapi.c.post("/locations/houses/internal/vouchers", json=body).status_code == 401
    assert vapi.c.post("/locations/houses/internal/vouchers", json=body,
                       headers={"X-Internal-Token": "wrong"}).status_code == 401
    assert vapi.sql("SELECT COUNT(*) FROM house_vouchers")[0][0] == 0


@pytest.mark.parametrize("over,status", [
    ({"location_id": 999}, 404),
    ({"kind": "castle"}, 422),
    ({"kind": "ready'; DROP TABLE house_vouchers;--"}, 422),
    ({"source_key": "k" * 121}, 422),
    ({"source_key": ""}, 422),
    ({"character_id": 0}, 422),
    ({"source_text": "x" * 256}, 422),
])
def test_grant_validation(vapi, over, status):
    body = {"character_id": 10, "location_id": TOWN, "kind": "ready", "source_key": "k", **over}
    assert vapi.c.post("/locations/houses/internal/vouchers", json=body, headers=HEAD).status_code == status
    assert vapi.sql("SELECT COUNT(*) FROM house_vouchers")[0][0] == 0


# --- list -----------------------------------------------------------------------

def test_list_is_own_only(vapi):
    vid = voucher_id(vapi)
    voucher_id(vapi, character_id=20, key="other")
    mine = vapi.as_(OWNER).get("/vouchers?character_id=10")
    assert mine.status_code == 200
    assert mine.json() == [{"id": vid, "location": {"id": TOWN, "name": f"Улица {TOWN}"}, "kind": "ready",
                            "source_text": "Награда за звание «Рыцарь» (Орден Зари): дом", "status": "unclaimed",
                            "claimed_house_id": None}]
    assert vapi.as_(FRIEND).get("/vouchers?character_id=10").status_code == 403
    assert vapi.as_(OWNER).get("/vouchers?character_id=999").status_code == 404


# --- claim ----------------------------------------------------------------------

def test_claim_takes_a_free_house_without_gold(vapi):
    vid = voucher_id(vapi)
    pid = _plot(vapi, price=300)
    r = claim(vapi, pid, vid)
    assert r.status_code == 200, r.text
    hid = r.json()["house_id"]
    assert _gold(vapi, 10) == 1000                                                 # the price is waived
    status, claimed_house, claimed_at = voucher_row(vapi, vid)
    assert (status, claimed_house) == ("claimed", hid) and claimed_at is not None
    house = vapi.as_(OWNER).get(f"/{hid}").json()
    assert house["owner"]["id"] == 10 and len(house["rooms"]) == 3                 # template rooms copied
    assert vapi.as_(OWNER).get("/vouchers?character_id=10").json()[0]["status"] == "claimed"


def test_used_voucher_cannot_be_claimed_twice(vapi):
    vid = voucher_id(vapi)
    first, second = _plot(vapi), _plot(vapi, name="Второй дом")
    assert claim(vapi, first, vid).status_code == 200
    r = claim(vapi, second, vid)
    assert r.status_code == 409 and r.json()["detail"] == "Это право уже использовано"
    assert vapi.as_(None).get(f"/by-location/{TOWN}").json()[1]["house"] is None


def test_empty_plot_voucher(vapi):
    vid = voucher_id(vapi, kind="empty", key="faction:grant:1:voucher:empty")
    ready = _plot(vapi)
    r = claim(vapi, ready, vid)
    assert r.status_code == 409 and r.json()["detail"] == "Право не подходит к этому участку"
    empty = empty_plot(vapi)
    assert claim(vapi, empty, vid).status_code == 200
    assert _gold(vapi, 10) == 1000


def test_location_must_match(vapi):
    vid = voucher_id(vapi, location_id=FAR)
    pid = _plot(vapi)
    r = claim(vapi, pid, vid)
    assert r.status_code == 409 and r.json()["detail"] == "Право не подходит к этому участку"
    assert voucher_row(vapi, vid)[0] == "unclaimed"


def test_taken_plot_keeps_the_voucher(vapi):
    vid = voucher_id(vapi)
    pid = _plot(vapi)
    assert vapi.as_(STRANGER).post(f"/plots/{pid}/buy", {"character_id": 30}).status_code == 200
    r = claim(vapi, pid, vid)
    assert r.status_code == 409
    assert voucher_row(vapi, vid)[0] == "unclaimed"
    assert vapi.sql("SELECT COUNT(*) FROM houses")[0][0] == 1


def test_must_stand_in_the_location(vapi):
    vid = voucher_id(vapi, character_id=11)
    pid = _plot(vapi)
    r = claim(vapi, pid, vid, character_id=11)                                     # character 11 is in FAR
    assert r.status_code == 400
    assert voucher_row(vapi, vid)[0] == "unclaimed"


def test_someone_elses_voucher_or_character(vapi):
    vid = voucher_id(vapi)
    pid = _plot(vapi)
    r = claim(vapi, pid, vid, character_id=20, uid=FRIEND)
    assert r.status_code == 404 and r.json()["detail"] == "Право на дом не найдено"
    assert claim(vapi, pid, vid, character_id=10, uid=FRIEND).status_code == 403
    assert claim(vapi, pid, 9999).status_code == 404
    assert voucher_row(vapi, vid)[0] == "unclaimed"
    assert vapi.sql("SELECT COUNT(*) FROM houses")[0][0] == 0


def test_claim_body_validation(vapi):
    pid = _plot(vapi)
    assert vapi.as_(OWNER).post(f"/plots/{pid}/claim", {"character_id": 10}).status_code == 422
    assert vapi.as_(OWNER).post(f"/plots/{pid}/claim", {"character_id": 10, "voucher_id": 0}).status_code == 422
    assert claim(vapi, 9999, voucher_id(vapi)).status_code == 404


def test_buying_is_unchanged(vapi):
    voucher_id(vapi)
    pid = _plot(vapi, price=300)
    assert vapi.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 200
    assert _gold(vapi, 10) == 700
    assert vapi.sql("SELECT status FROM house_vouchers")[0][0] == "unclaimed"


def test_character_deletion_drops_the_vouchers(vapi):
    voucher_id(vapi)
    voucher_id(vapi, character_id=20, key="other")
    r = vapi.c.post("/locations/houses/internal/character-deleted/10", headers=HEAD)
    assert r.status_code == 200
    assert vapi.sql("SELECT character_id FROM house_vouchers") == [(20,)]
