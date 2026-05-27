from __future__ import annotations

from typing import Any

import cv2
import numpy as np

COURT_WIDTH_M = 6.1
COURT_LENGTH_M = 13.4
COURT_BOUNDS_TOLERANCE_M = 0.35


def normalized_to_pixels(points: list[dict[str, float]], width: int, height: int) -> list[list[float]]:
    return [[point["x"] * width, point["y"] * height] for point in points]


def build_court_transform(court_points: list[dict[str, float]] | None, width: int, height: int) -> dict[str, Any] | None:
    if not court_points or len(court_points) != 4:
        return None
    source = np.array(normalized_to_pixels(court_points, width, height), dtype=np.float32)
    destination = np.array(
        [
            [0.0, 0.0],
            [COURT_WIDTH_M, 0.0],
            [COURT_WIDTH_M, COURT_LENGTH_M],
            [0.0, COURT_LENGTH_M],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    return {
        "points": court_points,
        "court_width_m": COURT_WIDTH_M,
        "court_length_m": COURT_LENGTH_M,
        "homography": matrix.tolist(),
    }


def map_point_to_court(point: list[float] | None, transform: dict[str, Any] | None) -> list[float] | None:
    if not point or not transform:
        return None
    matrix = np.array(transform["homography"], dtype=np.float32)
    source = np.array([[[point[0], point[1]]]], dtype=np.float32)
    mapped = cv2.perspectiveTransform(source, matrix)[0][0]
    x = float(mapped[0])
    y = float(mapped[1])
    if not np.isfinite(x) or not np.isfinite(y):
        return None
    return [round(x, 3), round(y, 3)]


def point_in_court_polygon(point: list[float] | None, court_points: list[dict[str, float]] | None, width: int, height: int) -> bool:
    if not point or not court_points or len(court_points) != 4:
        return False
    polygon = np.array(normalized_to_pixels(court_points, width, height), dtype=np.float32)
    return cv2.pointPolygonTest(polygon, (float(point[0]), float(point[1])), False) >= 0


def point_in_court_bounds(point: list[float] | None, tolerance_m: float = COURT_BOUNDS_TOLERANCE_M) -> bool:
    if not point:
        return False
    return (
        -tolerance_m <= point[0] <= COURT_WIDTH_M + tolerance_m
        and -tolerance_m <= point[1] <= COURT_LENGTH_M + tolerance_m
    )


def add_court_points_to_frames(frames: list[dict[str, Any]], transform: dict[str, Any] | None) -> None:
    if not transform:
        return
    for frame in frames:
        for person in frame.get("persons", []):
            court_point = map_point_to_court(person.get("foot_midpoint"), transform)
            person["court_point"] = court_point
            person["in_court"] = point_in_court_bounds(court_point)
        frame_court_point = map_point_to_court(frame.get("foot_midpoint"), transform)
        frame["court_point"] = frame_court_point
        frame["in_court"] = point_in_court_bounds(frame_court_point)
