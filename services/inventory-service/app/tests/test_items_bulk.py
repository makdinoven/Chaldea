"""
Tests for GET /inventory/items/bulk (FEAT-154, task #9).

Contract (§3.1):
- ``ids`` is a comma-separated list of ints, deduplicated, capped at 100
- unknown ids are silently omitted
- malformed input and an oversized list are 400
- the endpoint is public — no token required

N2: the response keys are ``image_url`` / ``rarity`` / ``type``, mapped from
the model columns ``image`` / ``item_rarity`` / ``item_type``. That renaming is
deliberate and is pinned here so nobody "fixes" it.
"""

import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_items(db_session):
    db_session.add_all([
        models.Items(
            id=1, name="Ржавый меч", description="Видал лучшие дни.",
            image="https://s3/rusty.webp", item_type="main_weapon",
            item_rarity="common", item_level=1,
        ),
        models.Items(
            id=2, name="Кожаный доспех", description=None,
            image=None, item_type="body", item_rarity="rare", item_level=2,
        ),
        models.Items(
            id=3, name="Зелье лечения", description="Пахнет травами.",
            image="https://s3/potion.webp", item_type="consumable",
            item_rarity="epic", item_level=1,
        ),
    ])
    db_session.commit()


# ===========================================================================
# 1. Happy path
# ===========================================================================

class TestItemsBulkHappyPath:

    def test_returns_requested_items(self, client, db_session):
        _seed_items(db_session)
        resp = client.get("/inventory/items/bulk", params={"ids": "1,3"})
        assert resp.status_code == 200
        body = resp.json()
        assert [row["id"] for row in body] == [1, 3]

    def test_no_auth_required(self, client, db_session):
        _seed_items(db_session)
        assert client.get(
            "/inventory/items/bulk", params={"ids": "1"}
        ).status_code == 200

    def test_response_uses_the_contract_key_names(self, client, db_session):
        """N2 — image_url / rarity / type, not image / item_rarity / item_type."""
        _seed_items(db_session)
        row = client.get("/inventory/items/bulk", params={"ids": "1"}).json()[0]
        assert set(row.keys()) == {
            "id", "name", "description", "image_url", "rarity", "type",
        }
        assert row["image_url"] == "https://s3/rusty.webp"
        assert row["rarity"] == "common"
        assert row["type"] == "main_weapon"

    def test_nullable_fields_come_back_as_null(self, client, db_session):
        _seed_items(db_session)
        row = client.get("/inventory/items/bulk", params={"ids": "2"}).json()[0]
        assert row["description"] is None
        assert row["image_url"] is None

    def test_results_are_ordered_by_id(self, client, db_session):
        _seed_items(db_session)
        body = client.get("/inventory/items/bulk", params={"ids": "3,1,2"}).json()
        assert [row["id"] for row in body] == [1, 2, 3]

    def test_duplicate_ids_are_deduplicated(self, client, db_session):
        _seed_items(db_session)
        body = client.get("/inventory/items/bulk", params={"ids": "1,1,1"}).json()
        assert len(body) == 1

    def test_whitespace_around_ids_is_tolerated(self, client, db_session):
        _seed_items(db_session)
        body = client.get("/inventory/items/bulk", params={"ids": " 1 , 2 "}).json()
        assert [row["id"] for row in body] == [1, 2]

    def test_exactly_100_ids_is_allowed(self, client, db_session):
        _seed_items(db_session)
        ids = ",".join(str(i) for i in range(1, 101))
        resp = client.get("/inventory/items/bulk", params={"ids": ids})
        assert resp.status_code == 200


# ===========================================================================
# 2. Unknown ids are silently omitted
# ===========================================================================

class TestItemsBulkUnknownIds:

    def test_unknown_ids_are_omitted_not_errors(self, client, db_session):
        _seed_items(db_session)
        resp = client.get("/inventory/items/bulk", params={"ids": "1,99999"})
        assert resp.status_code == 200
        assert [row["id"] for row in resp.json()] == [1]

    def test_all_unknown_ids_return_an_empty_list(self, client, db_session):
        _seed_items(db_session)
        resp = client.get("/inventory/items/bulk", params={"ids": "70000,80000"})
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# 3. Malformed input -> 400
# ===========================================================================

class TestItemsBulkValidation:

    def test_missing_ids_param_returns_422(self, client, db_session):
        assert client.get("/inventory/items/bulk").status_code == 422

    def test_empty_ids_returns_400(self, client, db_session):
        resp = client.get("/inventory/items/bulk", params={"ids": ""})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Параметр ids не должен быть пустым"

    def test_only_commas_returns_400(self, client, db_session):
        assert client.get(
            "/inventory/items/bulk", params={"ids": ",,,"}
        ).status_code == 400

    def test_non_numeric_id_returns_400(self, client, db_session):
        resp = client.get("/inventory/items/bulk", params={"ids": "1,abc"})
        assert resp.status_code == 400
        assert "целые числа" in resp.json()["detail"]

    def test_float_id_returns_400(self, client, db_session):
        assert client.get(
            "/inventory/items/bulk", params={"ids": "1.5"}
        ).status_code == 400

    def test_zero_and_negative_ids_return_400(self, client, db_session):
        assert client.get(
            "/inventory/items/bulk", params={"ids": "0"}
        ).status_code == 400
        assert client.get(
            "/inventory/items/bulk", params={"ids": "1,-2"}
        ).status_code == 400

    def test_more_than_100_ids_returns_400(self, client, db_session):
        ids = ",".join(str(i) for i in range(1, 102))
        resp = client.get("/inventory/items/bulk", params={"ids": ids})
        assert resp.status_code == 400
        assert "максимум 100" in resp.json()["detail"]

    def test_the_cap_counts_raw_tokens_not_unique_ids(self, client, db_session):
        """101 raw entries that dedupe to 2 still hit the cap — it guards parsing."""
        ids = ",".join(["1", "2"] * 50 + ["1"])
        resp = client.get("/inventory/items/bulk", params={"ids": ids})
        assert resp.status_code == 400
        assert "максимум 100" in resp.json()["detail"]

    def test_exactly_100_unique_ids_is_allowed(self, client, db_session):
        ids = ",".join(str(i) for i in range(1, 101))
        assert client.get(
            "/inventory/items/bulk", params={"ids": ids}
        ).status_code == 200


# ===========================================================================
# 4. Security — SQL injection
# ===========================================================================

class TestItemsBulkInjection:

    def test_injection_string_is_rejected_with_400(self, client, db_session):
        _seed_items(db_session)
        resp = client.get(
            "/inventory/items/bulk",
            params={"ids": "1; DROP TABLE items; --"},
        )
        assert resp.status_code == 400

    def test_injection_does_not_execute(self, client, db_session):
        """The items table must survive every injection attempt."""
        _seed_items(db_session)
        payloads = [
            "1; DROP TABLE items; --",
            "1) OR 1=1 --",
            "' OR '1'='1",
            "1 UNION SELECT id, name FROM items",
            "1,(SELECT 1)",
        ]
        for payload in payloads:
            resp = client.get("/inventory/items/bulk", params={"ids": payload})
            assert resp.status_code == 400, payload

        assert db_session.query(models.Items).count() == 3
        ok = client.get("/inventory/items/bulk", params={"ids": "1,2,3"})
        assert ok.status_code == 200
        assert len(ok.json()) == 3

    def test_or_1_equals_1_does_not_widen_the_result(self, client, db_session):
        """A tautology must never turn a 1-id request into "everything"."""
        _seed_items(db_session)
        resp = client.get("/inventory/items/bulk", params={"ids": "1 OR 1=1"})
        assert resp.status_code == 400
