"""party-service FEAT-164 — settle passive regen before reading member resources.

* get_attributes_map calls character-attributes-service
  POST /attributes/internal/settle-regen BEFORE the raw SELECT, so the values
  it returns are the ones persisted by the settle (the fake HTTP call below
  really updates the table — if the order were reversed the test would see
  stale numbers);
* ids are de-duplicated and sent in chunks of <= 50, timeout 2 s;
* connection errors / timeouts / non-200 responses are logged at WARNING and
  the read still returns the stored values.
"""
import logging
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import crud

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_Session = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

SETTLE_URL = f"{crud.settings.ATTRIBUTES_SERVICE_URL}internal/settle-regen"


@pytest.fixture(autouse=True)
def _tables():
    with _engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE character_attributes (character_id INTEGER PRIMARY KEY,"
            " current_health INTEGER, max_health INTEGER,"
            " current_mana INTEGER, max_mana INTEGER)"
        ))
        conn.execute(text(
            "INSERT INTO character_attributes VALUES (1, 10, 100, 5, 50), (2, 20, 100, 6, 50)"
        ))
    yield
    with _engine.begin() as conn:
        conn.execute(text("DROP TABLE character_attributes"))


def _ok():
    r = MagicMock()
    r.status_code = 200
    r.text = '{"settled": [], "missing": []}'
    return r


def test_settle_runs_before_select_and_its_result_is_read(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        # the attributes service persists regen into the shared table
        with _engine.begin() as conn:
            conn.execute(text("UPDATE character_attributes SET current_health = current_health + 30"))
        return _ok()

    monkeypatch.setattr(crud.httpx, "post", fake_post)
    db = _Session()
    m = crud.get_attributes_map(db, [1, 2])
    db.close()

    assert calls == [(SETTLE_URL, {"character_ids": [1, 2]}, crud.SETTLE_REGEN_TIMEOUT_SECONDS)]
    assert crud.SETTLE_REGEN_TIMEOUT_SECONDS == 2.0
    assert m[1]["current_health"] == 40
    assert m[2]["current_health"] == 50


def test_ids_deduplicated_and_chunked(monkeypatch):
    sent = []
    monkeypatch.setattr(crud.httpx, "post",
                        lambda url, json=None, timeout=None: sent.append(json["character_ids"]) or _ok())
    ids = list(range(1, 121)) + [5, 7]
    crud.settle_regen(ids)
    assert [len(c) for c in sent] == [50, 50, 20]
    flat = [i for c in sent for i in c]
    assert flat == list(range(1, 121))
    assert all(len(c) <= crud.SETTLE_REGEN_MAX_IDS for c in sent)


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("refused"),
    httpx.ReadTimeout("slow"),
    RuntimeError("anything else"),
])
def test_http_failure_is_tolerated_and_logged(monkeypatch, caplog, exc):
    def boom(*a, **kw):
        raise exc

    monkeypatch.setattr(crud.httpx, "post", boom)
    db = _Session()
    with caplog.at_level(logging.WARNING, logger="crud"):
        m = crud.get_attributes_map(db, [1, 2])
    db.close()
    assert m[1]["current_health"] == 10
    assert m[2]["current_mana"] == 6
    assert any(r.levelno == logging.WARNING and "settle-regen" in r.getMessage()
               for r in caplog.records)


@pytest.mark.parametrize("status", [404, 422, 500, 503])
def test_non_200_is_tolerated_and_logged(monkeypatch, caplog, status):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "error"
    monkeypatch.setattr(crud.httpx, "post", lambda *a, **kw: resp)
    db = _Session()
    with caplog.at_level(logging.WARNING, logger="crud"):
        m = crud.get_attributes_map(db, [1])
    db.close()
    assert m == {1: {"current_health": 10, "max_health": 100, "current_mana": 5, "max_mana": 50}}
    assert any(str(status) in r.getMessage() for r in caplog.records)


def test_empty_ids_do_not_call_attributes(monkeypatch):
    post = MagicMock()
    monkeypatch.setattr(crud.httpx, "post", post)
    db = _Session()
    assert crud.get_attributes_map(db, []) == {}
    db.close()
    post.assert_not_called()


def test_settle_url_is_internal_path():
    # /attributes/internal/ is blocked at the gateway; party-service must use it
    # through the service network only.
    assert crud.settings.ATTRIBUTES_SERVICE_URL.rstrip("/").endswith("/attributes")
