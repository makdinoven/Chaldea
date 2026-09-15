"""
Precise coastline outlines for clickable map zones.

Synthetic map: blue sea, white cloud bank, two green islands, a tiny "ship" speck.
- land_mask: sea and clouds sampled -> only islands are land; specks dropped; lakes filled
- zone_path: rough polygon ∩ land -> one sub-path per island, in 0..100 space; empty -> None
- endpoints: preview / apply / settings, validation, auth, recompute on map upload
"""

import io
import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

import map_outlines


W, H = 400, 200
SEA = (160, 90, 20)       # BGR blue
CLOUD = (245, 245, 245)
ISLAND = (40, 140, 60)    # BGR green


def _map_image(with_lake=False, with_ship=True) -> np.ndarray:
    img = np.full((H, W, 3), SEA, dtype=np.uint8)
    cv2.rectangle(img, (0, 0), (W, 30), CLOUD, -1)                 # cloud bank on top
    cv2.circle(img, (100, 110), 40, ISLAND, -1)                    # island A (left)
    cv2.ellipse(img, (300, 120), (50, 30), 0, 0, 360, ISLAND, -1)  # island B (right)
    if with_lake:
        cv2.circle(img, (100, 110), 3, SEA, -1)                    # tiny lake inside A
    if with_ship:
        cv2.rectangle(img, (200, 170), (202, 172), (20, 20, 20), -1)
    # Mild noise, like lossy WebP
    noise = np.random.default_rng(1).integers(-4, 5, img.shape)
    return np.clip(img.astype(int) + noise, 0, 255).astype(np.uint8)


def _encoded(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


SEA_PT = (50.0, 90.0)      # percent: bottom middle is sea
CLOUD_PT = (50.0, 5.0)


def _subpaths(path):
    return [p for p in path.split("Z") if p.strip()]


def _coords(path):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", path)]


# ===========================================================================
# 1. Pure image logic
# ===========================================================================

class TestLandMask:

    def test_islands_are_land_sea_and_clouds_are_not(self):
        land = map_outlines.land_mask(_map_image(), [SEA_PT, CLOUD_PT], tolerance=18)
        assert land[110, 100] == 255
        assert land[120, 300] == 255
        assert land[180, 50] == 0
        assert land[10, 200] == 0

    def test_unsampled_clouds_count_as_land(self):
        land = map_outlines.land_mask(_map_image(), [SEA_PT], tolerance=18)
        assert land[10, 200] == 255

    def test_ship_speck_dropped(self):
        land = map_outlines.land_mask(_map_image(), [SEA_PT, CLOUD_PT], tolerance=18)
        assert land[171, 201] == 0

    def test_small_lake_filled(self):
        land = map_outlines.land_mask(_map_image(with_lake=True), [SEA_PT, CLOUD_PT], tolerance=18)
        assert land[110, 100] == 255

    def test_no_samples_rejected(self):
        with pytest.raises(ValueError):
            map_outlines.land_mask(_map_image(), [], tolerance=18)

    def test_large_images_are_downscaled(self):
        big = cv2.resize(_map_image(), (map_outlines.MAX_PROCESSING_SIDE * 2, map_outlines.MAX_PROCESSING_SIDE))
        img = map_outlines.decode_image(_encoded(big))
        assert max(img.shape[:2]) == map_outlines.MAX_PROCESSING_SIDE

    def test_garbage_bytes_rejected(self):
        with pytest.raises(ValueError):
            map_outlines.decode_image(b"not an image")


class TestZonePath:

    def setup_method(self):
        self.land = map_outlines.land_mask(_map_image(), [SEA_PT, CLOUD_PT], tolerance=18)

    def test_rough_zone_around_both_islands_gives_two_subpaths(self):
        zone = [(5, 35), (95, 35), (95, 95), (5, 95)]
        path = map_outlines.zone_path(self.land, zone)
        assert len(_subpaths(path)) == 2
        coords = _coords(path)
        assert all(0 <= v <= 100 for v in coords)

    def test_outline_follows_the_coast_not_the_polygon(self):
        zone = [(5, 35), (45, 35), (45, 95), (5, 95)]   # generous box around island A
        path = map_outlines.zone_path(self.land, zone)
        xs = _coords(path)[0::2]
        ys = _coords(path)[1::2]
        # Island A spans x 60..140 px (15..35 %), y 70..150 px (35..75 %)
        assert 13 <= min(xs) <= 17 and 33 <= max(xs) <= 37
        assert 33 <= min(ys) <= 37 and 73 <= max(ys) <= 77

    def test_border_between_zones_cuts_the_island(self):
        left_half = [(0, 30), (25, 30), (25, 100), (0, 100)]
        path = map_outlines.zone_path(self.land, left_half)
        assert max(_coords(path)[0::2]) <= 25.3

    def test_zone_over_open_sea_is_empty(self):
        assert map_outlines.zone_path(self.land, [(55, 75), (70, 75), (70, 95), (55, 95)]) is None

    def test_degenerate_polygon_is_empty(self):
        assert map_outlines.zone_path(self.land, [(10, 10), (20, 20)]) is None

    def test_preview_png(self):
        uri, ratio = map_outlines.preview_png(self.land)
        assert uri.startswith("data:image/png;base64,")
        assert 0.05 < ratio < 0.3


# ===========================================================================
# 2. Endpoints
# ===========================================================================

HEADERS = {"Authorization": "Bearer t"}
URL = "https://s3.example/bucket/maps/country_map_6.webp"


def _auth(permissions):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": 1, "username": "a", "role": "admin", "permissions": permissions}
    return resp


EDITOR = ["locations:update"]


def _body(**overrides):
    body = {"parent_type": "country", "parent_id": 6,
            "samples": [{"x": SEA_PT[0], "y": SEA_PT[1]}, {"x": CLOUD_PT[0], "y": CLOUD_PT[1]}],
            "tolerance": 18}
    body.update(overrides)
    return body


def _zone(zone_id, points, parent_type="country", parent_id=6, land_settings=None):
    return SimpleNamespace(
        id=zone_id, zone_data=[{"x": x, "y": y} for x, y in points], precise_path=None,
        parent_type=parent_type, parent_id=parent_id, land_settings=land_settings,
    )


class TestEndpoints:

    @patch("main.download_s3_file", return_value=_encoded(_map_image()))
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_preview(self, _auth_mock, get_parent, _download, client):
        get_parent.return_value = SimpleNamespace(map_image_url=URL, map_land_settings=None)
        resp = client.post("/photo/map_outlines/preview", json=_body(), headers=HEADERS)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mask_png"].startswith("data:image/png;base64,")
        assert (data["width"], data["height"]) == (W, H)

    @patch("main.get_clickable_zones")
    @patch("main.download_s3_file", return_value=_encoded(_map_image()))
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_apply_updates_zones_and_saves_settings(self, _auth_mock, get_parent, _download, get_zones, client):
        parent = SimpleNamespace(map_image_url=URL, map_land_settings=None)
        get_parent.return_value = parent
        islands = _zone(1, [(5, 35), (95, 35), (95, 95), (5, 95)])
        open_sea = _zone(2, [(55, 75), (70, 75), (70, 95), (55, 95)])
        get_zones.return_value = [islands, open_sea]

        resp = client.post("/photo/map_outlines/apply", json=_body(), headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"zones_updated": 1, "zones_empty": [2]}
        assert len(_subpaths(islands.precise_path)) == 2
        assert open_sea.precise_path is None
        saved = json.loads(parent.map_land_settings)
        assert saved["tolerance"] == 18 and len(saved["samples"]) == 2

    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_map_without_image_is_404(self, _auth_mock, get_parent, client):
        get_parent.return_value = SimpleNamespace(map_image_url=None, map_land_settings=None)
        resp = client.post("/photo/map_outlines/apply", json=_body(), headers=HEADERS)
        assert resp.status_code == 404

    @patch("main.get_map_parent", return_value=None)
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_unknown_map_is_404(self, _auth_mock, _get_parent, client):
        assert client.post("/photo/map_outlines/preview", json=_body(), headers=HEADERS).status_code == 404

    @pytest.mark.parametrize("override", [
        {"parent_type": "region"},
        {"samples": []},
        {"samples": [{"x": 10, "y": 10}] * 9},
        {"samples": [{"x": 150, "y": 10}]},
        {"tolerance": 0},
        {"tolerance": 99},
        {"parent_id": "6; DROP TABLE Countries"},
    ])
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_validation(self, _auth_mock, override, client):
        resp = client.post("/photo/map_outlines/apply", json=_body(**override), headers=HEADERS)
        assert resp.status_code == 422

    @patch("auth_http.requests.get", return_value=_auth([]))
    def test_requires_permission(self, _auth_mock, client):
        assert client.post("/photo/map_outlines/apply", json=_body(), headers=HEADERS).status_code == 403
        assert client.get("/photo/map_outlines/settings/country/6", headers=HEADERS).status_code == 403

    def test_requires_token(self, client):
        assert client.post("/photo/map_outlines/preview", json=_body()).status_code == 401

    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_settings(self, _auth_mock, get_parent, client):
        get_parent.return_value = SimpleNamespace(map_land_settings=None)
        assert client.get("/photo/map_outlines/settings/country/6", headers=HEADERS).json() is None
        get_parent.return_value = SimpleNamespace(map_land_settings='{"samples": [{"x": 1, "y": 2}], "tolerance": 20}')
        assert client.get("/photo/map_outlines/settings/country/6", headers=HEADERS).json()["tolerance"] == 20


class TestRecomputeOnUpload:

    @patch("main.get_clickable_zones")
    @patch("main.download_s3_file", return_value=_encoded(_map_image()))
    @patch("main.get_map_parent")
    @patch("main.update_country_map_image")
    @patch("main.upload_file_to_s3", return_value=URL)
    @patch("auth_http.requests.get", return_value=_auth(["photos:upload"]))
    def test_new_map_recomputes_with_saved_settings(
        self, _auth_mock, _upload, _update, get_parent, _download, get_zones, client,
    ):
        settings = {"samples": [{"x": SEA_PT[0], "y": SEA_PT[1]}, {"x": CLOUD_PT[0], "y": CLOUD_PT[1]}], "tolerance": 18}
        get_parent.return_value = SimpleNamespace(map_image_url=URL, map_land_settings=json.dumps(settings))
        zone = _zone(1, [(5, 35), (45, 35), (45, 95), (5, 95)])
        get_zones.return_value = [zone]

        resp = client.post(
            "/photo/change_country_map",
            data={"country_id": "6"},
            files=[("file", ("map.png", io.BytesIO(_encoded(_map_image())), "image/png"))],
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        assert "outlines_warning" not in resp.json()
        assert zone.precise_path and len(_subpaths(zone.precise_path)) == 1

    @patch("main.download_s3_file", side_effect=RuntimeError("s3 down"))
    @patch("main.get_map_parent")
    @patch("main.update_country_map_image")
    @patch("main.upload_file_to_s3", return_value=URL)
    @patch("auth_http.requests.get", return_value=_auth(["photos:upload"]))
    def test_recompute_failure_keeps_upload_and_warns(self, _auth_mock, _upload, _update, get_parent, _download, client):
        get_parent.return_value = SimpleNamespace(
            map_image_url=URL, map_land_settings='{"samples": [{"x": 1, "y": 1}], "tolerance": 18}',
        )
        resp = client.post(
            "/photo/change_country_map",
            data={"country_id": "6"},
            files=[("file", ("map.png", io.BytesIO(_encoded(_map_image())), "image/png"))],
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert "контуры" in resp.json()["outlines_warning"]


# ===========================================================================
# 3. Per-zone settings
# ===========================================================================

ONLY_SEA = {"samples": [{"x": SEA_PT[0], "y": SEA_PT[1]}], "tolerance": 18}
BOTH_ISLANDS = [(5, 35), (95, 35), (95, 95), (5, 95)]
CLOUDY_BOX = [(5, 2), (95, 2), (95, 95), (5, 95)]   # reaches into the cloud bank


class TestZoneSettings:

    @patch("main.get_clickable_zones")
    @patch("main.get_clickable_zone")
    @patch("main.download_s3_file", return_value=_encoded(_map_image()))
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_zone_apply_touches_only_that_zone(self, _a, get_parent, _d, get_zone, get_zones, client):
        parent = SimpleNamespace(map_image_url=URL, map_land_settings=None)
        get_parent.return_value = parent
        target = _zone(5, BOTH_ISLANDS)
        other = _zone(6, BOTH_ISLANDS)
        get_zone.return_value = target
        get_zones.return_value = [target, other]

        resp = client.post("/photo/map_outlines/apply", json=_body(zone_id=5), headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"zones_updated": 1, "zones_empty": []}
        assert json.loads(target.land_settings)["tolerance"] == 18
        assert target.precise_path and other.precise_path is None
        assert parent.map_land_settings is None

    @patch("main.get_clickable_zones")
    @patch("main.download_s3_file", return_value=_encoded(_map_image()))
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_map_apply_keeps_zone_own_settings(self, _a, get_parent, _d, get_zones, client):
        get_parent.return_value = SimpleNamespace(map_image_url=URL, map_land_settings=None)
        # Own settings sample only the sea, so the clouds inside this zone count as land
        own = _zone(1, CLOUDY_BOX, land_settings=json.dumps(ONLY_SEA))
        plain = _zone(2, CLOUDY_BOX)
        get_zones.return_value = [own, plain]

        resp = client.post("/photo/map_outlines/apply", json=_body(), headers=HEADERS)
        assert resp.status_code == 200, resp.text
        # Map settings sample sea + clouds -> two islands; own settings -> clouds join as a third part
        assert len(_subpaths(plain.precise_path)) == 2
        assert len(_subpaths(own.precise_path)) == 3
        assert own.land_settings == json.dumps(ONLY_SEA)

    @patch("main.get_clickable_zone")
    @patch("main.download_s3_file", return_value=_encoded(_map_image()))
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_preview_for_zone_is_limited_to_it(self, _a, get_parent, _d, get_zone, client):
        get_parent.return_value = SimpleNamespace(map_image_url=URL, map_land_settings=None)
        get_zone.return_value = _zone(5, [(5, 35), (45, 35), (45, 95), (5, 95)])   # island A only
        whole = client.post("/photo/map_outlines/preview", json=_body(), headers=HEADERS).json()
        zone = client.post("/photo/map_outlines/preview", json=_body(zone_id=5), headers=HEADERS).json()
        assert 0 < zone["land_ratio"] < whole["land_ratio"]

    @patch("main.get_clickable_zone")
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_zone_of_another_map_is_404(self, _a, get_parent, get_zone, client):
        get_parent.return_value = SimpleNamespace(map_image_url=URL, map_land_settings=None)
        get_zone.return_value = _zone(5, BOTH_ISLANDS, parent_type="area", parent_id=1)
        resp = client.post("/photo/map_outlines/apply", json=_body(zone_id=5), headers=HEADERS)
        assert resp.status_code == 404

    @patch("main.get_clickable_zone")
    @patch("main.download_s3_file", return_value=_encoded(_map_image()))
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_reset_returns_zone_to_map_settings(self, _a, get_parent, _d, get_zone, client):
        map_settings = {"samples": [{"x": SEA_PT[0], "y": SEA_PT[1]}, {"x": CLOUD_PT[0], "y": CLOUD_PT[1]}], "tolerance": 18}
        get_parent.return_value = SimpleNamespace(map_image_url=URL, map_land_settings=json.dumps(map_settings))
        zone = _zone(1, CLOUDY_BOX, land_settings=json.dumps(ONLY_SEA))
        zone.precise_path = "M1 1 L2 2 L3 1 Z"
        get_zone.return_value = zone

        resp = client.delete("/photo/map_outlines/zone/1/settings", headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert zone.land_settings is None
        assert len(_subpaths(resp.json()["precise_path"])) == 2

    @patch("main.get_clickable_zone")
    @patch("main.get_map_parent")
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_reset_without_map_settings_keeps_outline(self, _a, get_parent, get_zone, client):
        get_parent.return_value = SimpleNamespace(map_image_url=URL, map_land_settings=None)
        zone = _zone(1, CLOUDY_BOX, land_settings=json.dumps(ONLY_SEA))
        zone.precise_path = "M1 1 L2 2 L3 1 Z"
        get_zone.return_value = zone
        resp = client.delete("/photo/map_outlines/zone/1/settings", headers=HEADERS)
        assert resp.json()["precise_path"] == "M1 1 L2 2 L3 1 Z"

    @patch("main.get_clickable_zone", return_value=None)
    @patch("auth_http.requests.get", return_value=_auth(EDITOR))
    def test_reset_unknown_zone_is_404(self, _a, _z, client):
        assert client.delete("/photo/map_outlines/zone/99/settings", headers=HEADERS).status_code == 404

    @patch("auth_http.requests.get", return_value=_auth([]))
    def test_reset_requires_permission(self, _a, client):
        assert client.delete("/photo/map_outlines/zone/1/settings", headers=HEADERS).status_code == 403
