"""
Precise coastline outlines for clickable map zones.

The admin draws a rough polygon per country/region (ClickableZones.zone_data,
percent coordinates) and clicks a few "not land" colours on the map (sea,
shallows, clouds). Land = pixels far enough from all sampled colours. Each zone's
outline is its rough polygon intersected with the land, traced into an SVG path in
the same 0..100 space as zone_data, one sub-path per island.
"""
import base64
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

# Maps larger than this are processed downscaled; the path is in percent anyway
MAX_PROCESSING_SIDE = 3000
# Half-size of the square averaged around a sampled point, in processing pixels
SAMPLE_RADIUS = 4
# Land specks smaller than this share of the image are noise (ships, foam, rocks)
MIN_ISLAND_FRACTION = 0.00015
# Water pockets smaller than this share, enclosed by land, are lakes/shadows -> land
MAX_LAKE_FRACTION = 0.0005
# Contour simplification tolerance, in processing pixels
SIMPLIFY_EPSILON = 1.0
PREVIEW_MAX_SIDE = 1024
PREVIEW_WATER_RGBA = (10, 25, 60, 150)
PATH_DECIMALS = 2

Point = Tuple[float, float]


def decode_image(data: bytes) -> np.ndarray:
    """Bytes -> BGR image, downscaled to MAX_PROCESSING_SIDE."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Не удалось прочитать изображение карты")
    h, w = img.shape[:2]
    scale = MAX_PROCESSING_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _to_lab(img: np.ndarray) -> np.ndarray:
    # Float Lab: L in 0..100, a/b roughly -127..127, so distances read as delta-E
    return cv2.cvtColor(img.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)


def sample_colors(lab: np.ndarray, samples: Sequence[Point]) -> np.ndarray:
    """Median Lab colour around each sampled point (x, y in percent)."""
    h, w = lab.shape[:2]
    colors = []
    for x_pct, y_pct in samples:
        cx = min(max(int(round(x_pct / 100 * (w - 1))), 0), w - 1)
        cy = min(max(int(round(y_pct / 100 * (h - 1))), 0), h - 1)
        patch = lab[
            max(cy - SAMPLE_RADIUS, 0):cy + SAMPLE_RADIUS + 1,
            max(cx - SAMPLE_RADIUS, 0):cx + SAMPLE_RADIUS + 1,
        ].reshape(-1, 3)
        colors.append(np.median(patch, axis=0))
    return np.array(colors, dtype=np.float32)


def land_mask(img: np.ndarray, samples: Sequence[Point], tolerance: float) -> np.ndarray:
    """uint8 mask, 255 = land."""
    if not samples:
        raise ValueError("Нужна хотя бы одна точка воды")
    lab = _to_lab(img)
    colors = sample_colors(lab, samples)

    not_land = np.zeros(lab.shape[:2], dtype=bool)
    for color in colors:
        distance = np.linalg.norm(lab - color, axis=2)
        not_land |= distance <= tolerance
    land = (~not_land).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    land = cv2.morphologyEx(land, cv2.MORPH_OPEN, kernel)
    land = cv2.morphologyEx(land, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    area = land.shape[0] * land.shape[1]
    land = _drop_small_components(land, int(area * MIN_ISLAND_FRACTION))
    water = _drop_small_components(255 - land, int(area * MAX_LAKE_FRACTION))
    return 255 - water


def _drop_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(count, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= max(min_area, 1)
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def _zone_raster(shape, zone_points: Sequence[Point]) -> np.ndarray:
    h, w = shape[:2]
    polygon = np.array(
        [[x / 100 * w, y / 100 * h] for x, y in zone_points], dtype=np.float32,
    ).round().astype(np.int32)
    zone = np.zeros(shape[:2], dtype=np.uint8)
    if len(zone_points) >= 3:
        cv2.fillPoly(zone, [polygon], 255)
    return zone


def restrict_to_zone(land: np.ndarray, zone_points: Sequence[Point]) -> np.ndarray:
    """Land only inside a rough zone polygon (for per-zone previews)."""
    return cv2.bitwise_and(land, _zone_raster(land.shape, zone_points))


def zone_path(land: np.ndarray, zone_points: Sequence[Point]) -> Optional[str]:
    """SVG path (0..100 space) of the land inside a rough zone polygon, or None."""
    if len(zone_points) < 3:
        return None
    h, w = land.shape[:2]
    inside = restrict_to_zone(land, zone_points)

    min_area = land.shape[0] * land.shape[1] * MIN_ISLAND_FRACTION
    contours, _ = cv2.findContours(inside, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    parts: List[str] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) < min_area:
            continue
        simplified = cv2.approxPolyDP(contour, SIMPLIFY_EPSILON, True).reshape(-1, 2)
        if len(simplified) < 3:
            continue
        coords = [
            f"{round(px / w * 100, PATH_DECIMALS):g} {round(py / h * 100, PATH_DECIMALS):g}"
            for px, py in simplified
        ]
        parts.append("M" + " L".join(coords) + " Z")
    return " ".join(parts) if parts else None


def preview_png(land: np.ndarray) -> Tuple[str, float]:
    """Semi-transparent tint over everything that is not land, as a data URI, plus land share."""
    h, w = land.shape[:2]
    scale = min(1.0, PREVIEW_MAX_SIDE / max(h, w))
    small = cv2.resize(land, (max(int(w * scale), 1), max(int(h * scale), 1)), interpolation=cv2.INTER_NEAREST)
    rgba = np.zeros((*small.shape, 4), dtype=np.uint8)
    r, g, b, a = PREVIEW_WATER_RGBA
    rgba[small == 0] = (b, g, r, a)  # OpenCV writes BGRA
    ok, encoded = cv2.imencode(".png", rgba)
    if not ok:
        raise ValueError("Не удалось построить превью маски")
    land_ratio = float((land > 0).mean())
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode(), land_ratio
