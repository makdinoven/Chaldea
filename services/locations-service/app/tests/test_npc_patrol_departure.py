"""FEAT-204 QA (task 8): ``NpcInLocation.patrol_departure`` is passed through untouched.

character-service adds ``patrol_departure`` ('soon' | 'short' | 'long' | null) to ``GET /characters/npcs/by_location``;
locations-service only has to keep it in ``LocationClientDetails.npcs`` (a typed schema would otherwise drop it) and
stay compatible with an older character-service that does not send the field.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import crud
from schemas import LocationClientDetails, NpcInLocation


def _details(npcs):
    return {
        "id": 72, "name": "Деревня", "type": "location", "parent_id": None, "description": "",
        "image_url": None, "recommended_level": 1, "quick_travel_marker": False, "marker_type": "safe",
        "district_id": 1, "region_id": 1, "is_favorited": False, "neighbors": [], "players": [], "npcs": npcs,
        "posts": [], "loot": [],
    }


GUARD = {"id": 90, "name": "Патрульный Ивар", "avatar": None, "level": 5, "class_name": "Воин",
         "race_name": "Человек", "npc_role": "guard"}


@pytest.mark.parametrize("bucket", ["soon", "short", "long", None])
def test_schema_keeps_the_bucket(bucket):
    assert NpcInLocation(**GUARD, patrol_departure=bucket).patrol_departure == bucket


def test_schema_without_the_field_defaults_to_none():
    npc = NpcInLocation(**GUARD)
    assert npc.patrol_departure is None
    assert "patrol_departure" in npc.dict()


def test_client_details_schema_keeps_the_bucket():
    model = LocationClientDetails(**_details([dict(GUARD, patrol_departure="short"), dict(GUARD, id=91)]))
    assert [n.patrol_departure for n in model.npcs] == ["short", None]


@patch("main.get_optional_user", return_value=None)
@patch("crud.get_client_location_details", new_callable=AsyncMock)
def test_client_details_endpoint_passes_the_bucket(mock_crud, mock_user, client):
    mock_crud.return_value = _details([
        dict(GUARD, patrol_departure="soon"),
        dict(GUARD, id=91, name="Стражник у ворот", patrol_departure=None),
        {"id": 92, "name": "Торговка", "level": 3, "npc_role": "merchant"},           # older character-service
    ])
    resp = client.get("/locations/72/client/details")
    assert resp.status_code == 200, resp.text
    npcs = {n["id"]: n for n in resp.json()["npcs"]}
    assert npcs[90]["patrol_departure"] == "soon"
    assert npcs[91]["patrol_departure"] is None
    assert npcs[92]["patrol_departure"] is None


async def test_get_npcs_in_location_returns_the_field_as_is():
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = [dict(GUARD, patrol_departure="long")]
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("crud.httpx.AsyncClient", return_value=client):
        npcs = await crud.get_npcs_in_location(72)
    assert npcs == [dict(GUARD, patrol_departure="long")]
    assert "location_id=72" in client.get.await_args.args[0]
