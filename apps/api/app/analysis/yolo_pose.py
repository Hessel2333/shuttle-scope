from __future__ import annotations

import math
from typing import Any

import cv2
from pathlib import Path

from .court import add_court_points_to_frames, build_court_transform, normalized_to_pixels, point_in_court_polygon
from .metrics import build_summary

KEYPOINT_MIN_CONFIDENCE = 0.35
BBOX_PADDING_RATIO = 0.18
TRACK_MAX_DISTANCE_RATIO = 0.16
SMOOTHING_ALPHA = 0.65


def detect_device() -> tuple[str, bool]:
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        return ("cuda:0" if cuda else "cpu", cuda)
    except Exception:
        return "cpu", False


def video_metadata(video_path: str) -> tuple[float, int, int, float]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    cap.release()
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
    return duration, width, height, fps


def run_yolo_pose_analysis(
    *,
    job_id: str,
    video_id: str,
    video_path: str,
    fps_sampled: int,
    model_name: str,
    imgsz: int,
    conf: float,
    iou: float,
    max_det: int,
    device: str,
    auto_download_model: bool,
    court_crop_second_pass: bool = True,
    court_crop_imgsz: int = 1280,
    court_crop_conf: float = 0.06,
    court_crop_padding: float = 0.08,
    roi: dict[str, float] | None = None,
    court_points: list[dict[str, float]] | None = None,
    locale: str = "zh",
    progress_callback: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from ultralytics import YOLO

    duration_sec, width, height, source_fps = video_metadata(video_path)
    if not auto_download_model and not Path(model_name).exists():
        raise RuntimeError(f"Model file not found and AUTO_DOWNLOAD_MODEL=false: {model_name}")
    model = YOLO(model_name)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    stride = max(1, round((source_fps or fps_sampled) / fps_sampled))
    total_source_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    expected_samples = max(1, total_source_frames // stride) if total_source_frames else 1
    frames: list[dict[str, Any]] = []
    source_index = 0
    sampled_index = 0
    crop_bbox = court_crop_bbox(court_points, width, height, court_crop_padding) if court_crop_second_pass else None

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if source_index % stride != 0:
            source_index += 1
            continue

        timestamp = source_index / source_fps if source_fps > 0 else sampled_index / fps_sampled
        result = model.predict(frame, verbose=False, device=device, imgsz=imgsz, conf=conf, iou=iou, max_det=max_det)[0]
        parsed = parse_result(result, sampled_index, timestamp, width, height, detection_pass="full")
        if crop_bbox:
            x1, y1, x2, y2 = crop_bbox
            crop = frame[y1:y2, x1:x2]
            if crop.size:
                crop_result = model.predict(
                    crop,
                    verbose=False,
                    device=device,
                    imgsz=court_crop_imgsz,
                    conf=min(conf, court_crop_conf),
                    iou=iou,
                    max_det=max_det,
                )[0]
                crop_parsed = parse_result(
                    crop_result,
                    sampled_index,
                    timestamp,
                    width,
                    height,
                    x_offset=x1,
                    y_offset=y1,
                    detection_pass="court_crop",
                )
                merge_person_detections(parsed, crop_parsed)
        frames.append(parsed)
        sampled_index += 1
        source_index += 1
        if progress_callback:
            progress_callback(min(95, 5 + (sampled_index / expected_samples) * 90))

    cap.release()
    assign_track_ids(frames, width, height)
    smooth_tracked_keypoints(frames)
    court_transform = build_court_transform(court_points, width, height)
    primary_track_id = select_primary_track(frames, width, height, roi, court_points)
    apply_primary_person(frames, primary_track_id, width, height, roi, court_points)
    add_court_points_to_frames(frames, court_transform)
    pose = {
        "video_id": video_id,
        "fps_sampled": fps_sampled,
        "source_width": width,
        "source_height": height,
        "roi": roi,
        "court": court_transform,
        "primary_track_id": primary_track_id,
        "keypoint_filter": {
            "min_confidence": KEYPOINT_MIN_CONFIDENCE,
            "bbox_padding_ratio": BBOX_PADDING_RATIO,
            "temporal_smoothing": True,
        },
        "inference": {
            "imgsz": imgsz,
            "conf": conf,
            "iou": iou,
            "max_det": max_det,
            "court_crop_second_pass": bool(crop_bbox),
            "court_crop_imgsz": court_crop_imgsz,
            "court_crop_conf": court_crop_conf,
        },
        "frames": frames,
    }
    summary = build_summary(
        job_id=job_id,
        video_id=video_id,
        duration_sec=duration_sec,
        fps_sampled=fps_sampled,
        width=width,
        height=height,
        frames=frames,
        device=device,
        model_name=model_name,
        mode="yolo",
        locale=locale,
    )
    return pose, summary


def parse_result(
    result: Any,
    frame_index: int,
    timestamp: float,
    width: int,
    height: int,
    x_offset: int = 0,
    y_offset: int = 0,
    detection_pass: str = "full",
) -> dict[str, Any]:
    empty = {
        "frame_index": frame_index,
        "timestamp": round(timestamp, 3),
        "bbox": None,
        "keypoints": [],
        "person_confidence": 0,
        "center": None,
        "foot_midpoint": None,
        "persons": [],
    }
    if result.boxes is None or len(result.boxes) == 0 or result.keypoints is None:
        return empty

    boxes = result.boxes.xyxy.detach().cpu().numpy()
    confidences = result.boxes.conf.detach().cpu().numpy()
    key_xy = result.keypoints.xy.detach().cpu().numpy()
    key_conf = result.keypoints.conf.detach().cpu().numpy() if result.keypoints.conf is not None else None

    persons: list[dict[str, Any]] = []
    for index, bbox in enumerate(boxes):
        bbox_list = [
            round(float(bbox[0]) + x_offset, 2),
            round(float(bbox[1]) + y_offset, 2),
            round(float(bbox[2]) + x_offset, 2),
            round(float(bbox[3]) + y_offset, 2),
        ]
        raw_keypoints: list[list[float]] = []
        for point_index, xy in enumerate(key_xy[index]):
            confidence = float(key_conf[index][point_index]) if key_conf is not None else float(confidences[index])
            raw_keypoints.append([round(float(xy[0]) + x_offset, 2), round(float(xy[1]) + y_offset, 2), round(confidence, 3)])
        keypoints = filter_keypoints(raw_keypoints, bbox_list, width, height)
        center = [round((bbox_list[0] + bbox_list[2]) / 2, 2), round((bbox_list[1] + bbox_list[3]) / 2, 2)]
        foot_midpoint = midpoint_from_keypoints(keypoints, (15, 16)) or midpoint_from_keypoints(keypoints, (11, 12)) or center
        persons.append(
            {
                "track_id": None,
                "bbox": bbox_list,
                "keypoints": keypoints,
                "raw_keypoint_count": sum(1 for point in raw_keypoints if point[2] > 0.01),
                "valid_keypoint_count": sum(1 for point in keypoints if point[2] >= KEYPOINT_MIN_CONFIDENCE),
                "person_confidence": round(float(confidences[index]), 3),
                "center": center,
                "foot_midpoint": foot_midpoint,
                "detection_pass": detection_pass,
            }
        )

    frame = dict(empty)
    frame["persons"] = persons
    return frame


def court_crop_bbox(
    court_points: list[dict[str, float]] | None,
    width: int,
    height: int,
    padding_ratio: float,
) -> tuple[int, int, int, int] | None:
    if not court_points or len(court_points) != 4:
        return None
    points = normalized_to_pixels(court_points, width, height)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x1 = min(xs)
    y1 = min(ys)
    x2 = max(xs)
    y2 = max(ys)
    pad = max(x2 - x1, y2 - y1) * max(0.0, padding_ratio)
    left = max(0, int(math.floor(x1 - pad)))
    top = max(0, int(math.floor(y1 - pad)))
    right = min(width, int(math.ceil(x2 + pad)))
    bottom = min(height, int(math.ceil(y2 + pad)))
    if right - left < 64 or bottom - top < 64:
        return None
    return left, top, right, bottom


def merge_person_detections(frame: dict[str, Any], extra_frame: dict[str, Any], iou_threshold: float = 0.55) -> None:
    persons = frame.get("persons", [])
    for candidate in extra_frame.get("persons", []):
        best_index = -1
        best_iou = 0.0
        for index, existing in enumerate(persons):
            iou = bbox_iou(candidate["bbox"], existing["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_index = index
        if best_index < 0 or best_iou < iou_threshold:
            persons.append(candidate)
            continue
        existing = persons[best_index]
        candidate_quality = float(candidate.get("person_confidence") or 0) + (candidate.get("valid_keypoint_count") or 0) * 0.04
        existing_quality = float(existing.get("person_confidence") or 0) + (existing.get("valid_keypoint_count") or 0) * 0.04
        if candidate_quality > existing_quality:
            persons[best_index] = candidate
    frame["persons"] = persons


def bbox_iou(a: list[float], b: list[float]) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def filter_keypoints(keypoints: list[list[float]], bbox: list[float], width: int, height: int) -> list[list[float]]:
    x1, y1, x2, y2 = bbox
    pad_x = max(12.0, (x2 - x1) * BBOX_PADDING_RATIO)
    pad_y = max(12.0, (y2 - y1) * BBOX_PADDING_RATIO)
    min_x = max(0.0, x1 - pad_x)
    max_x = min(float(width), x2 + pad_x)
    min_y = max(0.0, y1 - pad_y)
    max_y = min(float(height), y2 + pad_y)
    filtered: list[list[float]] = []
    for x, y, confidence in keypoints:
        if confidence < KEYPOINT_MIN_CONFIDENCE or x < min_x or x > max_x or y < min_y or y > max_y:
            filtered.append([round(x, 2), round(y, 2), 0.0])
        else:
            filtered.append([round(x, 2), round(y, 2), round(confidence, 3)])
    return filtered


def assign_track_ids(frames: list[dict[str, Any]], width: int, height: int) -> None:
    next_track_id = 1
    active: dict[int, dict[str, Any]] = {}
    max_distance = max(width, height) * TRACK_MAX_DISTANCE_RATIO

    for frame in frames:
        persons = sorted(frame["persons"], key=lambda item: float(item["person_confidence"]), reverse=True)
        used_tracks: set[int] = set()
        for person in persons:
            point = person.get("foot_midpoint") or person.get("center")
            best_track_id: int | None = None
            best_distance = max_distance
            for track_id, state in active.items():
                if track_id in used_tracks:
                    continue
                distance = point_distance(point, state["point"])
                if distance < best_distance:
                    best_distance = distance
                    best_track_id = track_id
            if best_track_id is None:
                best_track_id = next_track_id
                next_track_id += 1
            person["track_id"] = best_track_id
            used_tracks.add(best_track_id)
            active[best_track_id] = {"point": point, "frame_index": frame["frame_index"]}
        frame["persons"] = persons


def smooth_tracked_keypoints(frames: list[dict[str, Any]]) -> None:
    previous_by_track: dict[int, list[list[float]]] = {}
    for frame in frames:
        for person in frame["persons"]:
            track_id = person.get("track_id")
            if track_id is None:
                continue
            previous = previous_by_track.get(track_id)
            bbox = person["bbox"]
            max_jump = max(50.0, math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.45)
            smoothed: list[list[float]] = []
            for index, point in enumerate(person["keypoints"]):
                if previous and index < len(previous) and previous[index][2] >= KEYPOINT_MIN_CONFIDENCE and point[2] >= KEYPOINT_MIN_CONFIDENCE:
                    jump = point_distance(point, previous[index])
                    if jump > max_jump and point[2] < 0.7:
                        smoothed.append([previous[index][0], previous[index][1], round(previous[index][2] * 0.9, 3)])
                    else:
                        smoothed.append(
                            [
                                round(previous[index][0] * (1 - SMOOTHING_ALPHA) + point[0] * SMOOTHING_ALPHA, 2),
                                round(previous[index][1] * (1 - SMOOTHING_ALPHA) + point[1] * SMOOTHING_ALPHA, 2),
                                point[2],
                            ]
                        )
                else:
                    smoothed.append(point)
            person["keypoints"] = smoothed
            person["foot_midpoint"] = midpoint_from_keypoints(smoothed, (15, 16)) or midpoint_from_keypoints(smoothed, (11, 12)) or person["center"]
            previous_by_track[track_id] = smoothed


def select_primary_track(
    frames: list[dict[str, Any]],
    width: int,
    height: int,
    roi: dict[str, float] | None,
    court_points: list[dict[str, float]] | None,
) -> int | None:
    scores: dict[int, float] = {}
    for frame in frames:
        for person in frame["persons"]:
            track_id = person.get("track_id")
            if track_id is None:
                continue
            scores[track_id] = scores.get(track_id, 0.0) + person_score(person, width, height, roi, court_points)
    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


def apply_primary_person(
    frames: list[dict[str, Any]],
    primary_track_id: int | None,
    width: int,
    height: int,
    roi: dict[str, float] | None,
    court_points: list[dict[str, float]] | None,
) -> None:
    for frame in frames:
        selected = None
        if primary_track_id is not None:
            selected = next((person for person in frame["persons"] if person.get("track_id") == primary_track_id), None)
        if selected is None and frame["persons"]:
            selected = max(frame["persons"], key=lambda person: person_score(person, width, height, roi, court_points))
        for person in frame["persons"]:
            person["selected"] = bool(selected and person.get("track_id") == selected.get("track_id"))
        if selected:
            frame["bbox"] = selected["bbox"]
            frame["keypoints"] = selected["keypoints"]
            frame["person_confidence"] = selected["person_confidence"]
            frame["center"] = selected["center"]
            frame["foot_midpoint"] = selected["foot_midpoint"]


def person_score(
    person: dict[str, Any],
    width: int,
    height: int,
    roi: dict[str, float] | None,
    court_points: list[dict[str, float]] | None,
) -> float:
    bbox = person["bbox"]
    area_ratio = max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / max(1, width * height)
    lower_ratio = ((bbox[1] + bbox[3]) / 2) / max(1, height)
    point = person.get("foot_midpoint") or person.get("center")
    roi_bonus = 0.0
    court_bonus = 0.0
    if roi:
        roi_bonus = 3.0 if point_in_roi(point, width, height, roi) else -4.0
    if court_points:
        court_bonus = 5.0 if point_in_court_polygon(point, court_points, width, height) else -6.0
    return area_ratio * 4.0 + lower_ratio * 0.7 + float(person["person_confidence"]) * 0.5 + roi_bonus + court_bonus


def point_in_roi(point: list[float] | None, width: int, height: int, roi: dict[str, float]) -> bool:
    if not point:
        return False
    x1 = roi["x"] * width
    y1 = roi["y"] * height
    x2 = x1 + roi["width"] * width
    y2 = y1 + roi["height"] * height
    return x1 <= point[0] <= x2 and y1 <= point[1] <= y2


def point_distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def midpoint_from_keypoints(keypoints: list[list[float]], indices: tuple[int, int]) -> list[float] | None:
    left, right = indices
    if len(keypoints) <= max(left, right):
        return None
    p1 = keypoints[left]
    p2 = keypoints[right]
    if p1[2] < KEYPOINT_MIN_CONFIDENCE or p2[2] < KEYPOINT_MIN_CONFIDENCE:
        return None
    return [round((p1[0] + p2[0]) / 2, 2), round((p1[1] + p2[1]) / 2, 2)]
