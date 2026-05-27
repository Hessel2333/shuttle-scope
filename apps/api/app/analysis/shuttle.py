from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .court import build_court_transform, map_point_to_court, normalized_to_pixels
from .yolo_pose import video_metadata


def detect_shuttle_candidates(
    *,
    video_id: str,
    video_path: str,
    fps_sampled: int,
    pose: dict[str, Any],
    court_points: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    duration_sec, width, height, source_fps = video_metadata(video_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    stride = max(1, round((source_fps or fps_sampled) / fps_sampled))
    play_mask, play_polygon = build_play_volume_mask(court_points, width, height)
    court_transform = build_court_transform(court_points, width, height)
    pose_frames = sorted(pose.get("frames", []), key=lambda item: float(item.get("timestamp", 0)))
    frames: list[dict[str, Any]] = []
    source_index = 0
    sampled_index = 0
    previous_sample_gray: np.ndarray | None = None
    previous_point: list[float] | None = None

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if source_index % stride != 0:
            source_index += 1
            continue

        timestamp = source_index / source_fps if source_fps > 0 else sampled_index / fps_sampled
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff = None
        if previous_sample_gray is not None:
            diff = cv2.absdiff(gray, previous_sample_gray)
        pose_frame = nearest_pose_frame(pose_frames, timestamp)
        candidate, candidates = best_candidate(frame, diff, play_mask, court_transform, pose_frame, previous_point)
        output: dict[str, Any] = {
            "frame_index": sampled_index,
            "timestamp": round(timestamp, 3),
            "position": None,
            "court_point": None,
            "confidence": 0.0,
            "candidates": candidates,
        }
        if candidate:
            point, confidence = candidate
            court_point = map_point_to_court(point, court_transform)
            output.update(
                {
                    "position": [round(point[0], 2), round(point[1], 2)],
                    "court_point": court_point,
                    "confidence": round(confidence, 3),
                }
            )
            previous_point = point
        elif previous_point is not None:
            previous_point = None
        frames.append(output)
        previous_sample_gray = gray
        sampled_index += 1
        source_index += 1

    cap.release()
    detected = [frame for frame in frames if frame["position"]]
    return {
        "video_id": video_id,
        "fps_sampled": fps_sampled,
        "duration_sec": round(duration_sec, 2),
        "source_width": width,
        "source_height": height,
        "method": "opencv_airborne_candidate_v2",
        "play_polygon": play_polygon,
        "detected_frames": len(detected),
        "frames": frames,
    }


def build_play_volume_mask(court_points: list[dict[str, float]] | None, width: int, height: int) -> tuple[np.ndarray | None, list[list[int]] | None]:
    if not court_points or len(court_points) != 4:
        return None, None
    mask = np.zeros((height, width), dtype=np.uint8)
    court = np.array(normalized_to_pixels(court_points, width, height), dtype=np.float32)
    min_x = float(np.min(court[:, 0]))
    max_x = float(np.max(court[:, 0]))
    min_y = float(np.min(court[:, 1]))
    max_y = float(np.max(court[:, 1]))
    court_width = max_x - min_x
    court_height = max_y - min_y

    # The shuttle is airborne: its image projection can sit above or outside the
    # calibrated court quadrilateral. Use the court only to define a loose play
    # volume and keep distant seats/walls/other courts out.
    left = max(0, min_x - court_width * 0.22)
    right = min(width - 1, max_x + court_width * 0.22)
    top = max(0, min_y - court_height * 0.75)
    bottom = min(height - 1, max_y + court_height * 0.08)
    polygon = np.array([[left, top], [right, top], [right, bottom], [left, bottom]], dtype=np.int32)
    cv2.fillConvexPoly(mask, polygon, 255)
    return mask, polygon.tolist()


def best_candidate(
    frame: np.ndarray,
    diff: np.ndarray | None,
    play_mask: np.ndarray | None,
    court_transform: dict[str, Any] | None,
    pose_frame: dict[str, Any] | None,
    previous_point: list[float] | None,
) -> tuple[tuple[list[float], float] | None, list[dict[str, Any]]]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    bright = cv2.inRange(hsv, np.array([0, 0, 155]), np.array([179, 92, 255]))
    if diff is not None:
        moving_mask = cv2.threshold(diff, 34, 255, cv2.THRESH_BINARY)[1]
    else:
        moving_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    kernel = np.ones((2, 2), np.uint8)
    moving_mask = cv2.morphologyEx(moving_mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.bitwise_and(moving_mask, cv2.dilate(bright, kernel, iterations=1))
    if play_mask is not None:
        mask = cv2.bitwise_and(mask, play_mask)
    mask = cv2.medianBlur(mask, 3)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blocked_boxes = [person.get("bbox") for person in (pose_frame or {}).get("persons", []) if person.get("bbox")]
    blocked_points = blocked_keypoint_zones(pose_frame, frame.shape[1], frame.shape[0])
    best: tuple[list[float], float] | None = None
    ranked: list[dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 3 or area > 65:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < 2 or h < 2 or w > 20 or h > 20:
            continue
        center = [x + w / 2, y + h / 2]
        if point_in_boxes(center, blocked_boxes, padding=4) or point_in_keypoint_zones(center, blocked_points):
            continue
        projected = map_point_to_court(center, court_transform)
        if not plausible_airborne_projection(projected, court_transform):
            continue
        patch = frame[max(0, y - 3) : min(frame.shape[0], y + h + 3), max(0, x - 3) : min(frame.shape[1], x + w + 3)]
        object_patch = frame[y : y + h, x : x + w]
        brightness = float(np.mean(object_patch)) / 255.0
        contrast = max(0.0, (float(np.mean(object_patch)) - float(np.mean(patch))) / 255.0)
        compactness = min(w, h) / max(w, h, 1)
        motion_strength = float(np.mean(moving_mask[y : y + h, x : x + w])) / 255.0
        if contrast < 0.018 or motion_strength < 0.45:
            continue
        continuity = continuity_score(center, previous_point)
        size_score = 1.0 - min(max(area - 10.0, 0.0) / 65.0, 1.0)
        confidence = min(
            1.0,
            brightness * 0.14
            + contrast * 0.34
            + compactness * 0.14
            + motion_strength * 0.22
            + size_score * 0.09
            + continuity * 0.07,
        )
        ranked.append(
            {
                "position": [round(center[0], 2), round(center[1], 2)],
                "confidence": round(confidence, 3),
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
                "court_point": projected,
            }
        )
        if best is None or confidence > best[1]:
            best = (center, confidence)
    ranked.sort(key=lambda item: item["confidence"], reverse=True)
    accepted = best if best and best[1] >= 0.6 else None
    return accepted, ranked[:5]


def nearest_pose_frame(frames: list[dict[str, Any]], timestamp: float) -> dict[str, Any] | None:
    if not frames:
        return None
    best = min(frames, key=lambda frame: abs(float(frame.get("timestamp", 0)) - timestamp))
    return best if abs(float(best.get("timestamp", 0)) - timestamp) <= 0.18 else None


def point_in_boxes(point: list[float], boxes: list[list[float]], padding: float) -> bool:
    for box in boxes:
        if box[0] - padding <= point[0] <= box[2] + padding and box[1] - padding <= point[1] <= box[3] + padding:
            return True
    return False


def blocked_keypoint_zones(pose_frame: dict[str, Any] | None, width: int, height: int) -> list[tuple[float, float, float]]:
    zones: list[tuple[float, float, float]] = []
    persons = (pose_frame or {}).get("persons", [])
    base = max(10.0, min(width, height) * 0.018)
    for person in persons:
        keypoints = person.get("keypoints") or []
        for index, point in enumerate(keypoints):
            if len(point) < 3 or point[2] < 0.25:
                continue
            radius = base
            if index in {7, 8, 9, 10}:
                radius = base * 2.4
            zones.append((float(point[0]), float(point[1]), radius))
    return zones


def point_in_keypoint_zones(point: list[float], zones: list[tuple[float, float, float]]) -> bool:
    return any(np.hypot(point[0] - x, point[1] - y) <= radius for x, y, radius in zones)


def continuity_score(point: list[float], previous_point: list[float] | None) -> float:
    if previous_point is None:
        return 0.5
    distance = float(np.hypot(point[0] - previous_point[0], point[1] - previous_point[1]))
    if distance < 3:
        return 0.05
    if distance <= 260:
        return 1.0
    if distance <= 460:
        return 0.45
    return 0.1


def plausible_airborne_projection(point: list[float] | None, transform: dict[str, Any] | None) -> bool:
    if not transform or not point:
        return True
    width = float(transform["court_width_m"])
    length = float(transform["court_length_m"])
    return -4.0 <= point[0] <= width + 4.0 and -8.0 <= point[1] <= length + 8.0
