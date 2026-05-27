from __future__ import annotations

import csv
import threading
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import cv2

from ..analysis.court import COURT_LENGTH_M, COURT_WIDTH_M, build_court_transform, map_point_to_court
from ..analysis.yolo_pose import video_metadata
from ..config import effective_value, settings

_TRACKNET_LOCK = threading.Lock()


@contextmanager
def tracknet_execution_slot(on_wait: Callable[[], None] | None = None) -> Iterator[None]:
    acquired = _TRACKNET_LOCK.acquire(blocking=False)
    if not acquired:
        if on_wait:
            on_wait()
        _TRACKNET_LOCK.acquire()
    try:
        yield
    finally:
        _TRACKNET_LOCK.release()


def tracknet_busy() -> bool:
    acquired = _TRACKNET_LOCK.acquire(blocking=False)
    if acquired:
        _TRACKNET_LOCK.release()
        return False
    return True


def tracknet_ready() -> bool:
    return (
        (settings.tracknet_repo_dir / "predict.py").exists()
        and settings.tracknet_tracknet_file.exists()
    )


def tracknet_status() -> dict[str, Any]:
    return {
        "ready": tracknet_ready(),
        "repo_dir": str(settings.tracknet_repo_dir),
        "tracknet_file": str(settings.tracknet_tracknet_file),
        "inpaintnet_file": str(settings.tracknet_inpaintnet_file),
        "has_repo": (settings.tracknet_repo_dir / "predict.py").exists(),
        "has_tracknet": settings.tracknet_tracknet_file.exists(),
        "has_inpaintnet": settings.tracknet_inpaintnet_file.exists(),
        "busy": tracknet_busy(),
    }


def run_tracknetv3(
    *,
    video_id: str,
    video_path: str,
    court_points: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    if not tracknet_ready():
        status = tracknet_status()
        raise RuntimeError(
            "TrackNetV3 is not ready. "
            f"repo={status['has_repo']}, tracknet={status['has_tracknet']}"
        )

    duration_sec, width, height, source_fps = video_metadata(video_path)
    transform = build_court_transform(court_points, width, height)
    batch_size = int(effective_value("tracknet_batch_size"))
    max_sample_num = int(effective_value("tracknet_max_sample_num"))
    timeout_sec = int(effective_value("tracknet_timeout_sec"))
    large_video = bool(effective_value("tracknet_large_video"))

    with tempfile.TemporaryDirectory(prefix="tracknetv3_") as temp_dir:
        save_dir = Path(temp_dir)
        proxy_video_path, scaler = make_proxy_video(video_path, save_dir, width, height, source_fps)
        command = [
            sys.executable,
            str(settings.tracknet_repo_dir / "predict.py"),
            "--video_file",
            str(proxy_video_path),
            "--tracknet_file",
            str(settings.tracknet_tracknet_file),
            "--save_dir",
            str(save_dir),
            "--batch_size",
            str(batch_size),
            "--eval_mode",
            settings.tracknet_eval_mode,
            "--max_sample_num",
            str(max_sample_num),
        ]
        if settings.tracknet_use_inpaint and settings.tracknet_inpaintnet_file.exists():
            command.extend(["--inpaintnet_file", str(settings.tracknet_inpaintnet_file)])
        if large_video:
            command.append("--large_video")

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{settings.tracknet_repo_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"
        env.setdefault("OMP_NUM_THREADS", "2")
        env.setdefault("MKL_NUM_THREADS", "2")
        env.setdefault("OPENBLAS_NUM_THREADS", "2")
        env.setdefault("NUMEXPR_NUM_THREADS", "2")
        env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")
        result = subprocess.run(
            command,
            cwd=settings.tracknet_repo_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"TrackNetV3 failed: {stderr[-1200:]}")

        csv_path = save_dir / f"{Path(proxy_video_path).stem}_ball.csv"
        if not csv_path.exists():
            raise RuntimeError(f"TrackNetV3 did not produce prediction csv: {csv_path}")
        frames = parse_tracknet_csv(csv_path, source_fps, transform, scaler, width, height)
        filter_tracknet_frames(frames, source_fps, width, height)

    detected = [frame for frame in frames if frame["position"]]
    return {
        "video_id": video_id,
        "fps_sampled": round(source_fps, 3),
        "duration_sec": round(duration_sec, 2),
        "source_width": width,
        "source_height": height,
        "method": "tracknetv3",
        "proxy_scaler": {"x": scaler[0], "y": scaler[1]},
        "detected_frames": len(detected),
        "frames": frames,
    }


def make_proxy_video(video_path: str, save_dir: Path, width: int, height: int, source_fps: float) -> tuple[Path, tuple[float, float]]:
    max_width = int(effective_value("tracknet_proxy_max_width"))
    if max_width <= 0 or width <= max_width:
        return Path(video_path), (1.0, 1.0)

    proxy_width = max_width
    proxy_height = int(round(height * (proxy_width / width)))
    proxy_height += proxy_height % 2
    proxy_path = save_dir / f"{Path(video_path).stem}_tracknet_proxy.mp4"
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video for TrackNet proxy: {video_path}")
    writer = cv2.VideoWriter(
        str(proxy_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        source_fps if source_fps > 0 else 30,
        (proxy_width, proxy_height),
    )
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        resized = cv2.resize(frame, (proxy_width, proxy_height), interpolation=cv2.INTER_AREA)
        writer.write(resized)
    cap.release()
    writer.release()
    return proxy_path, (width / proxy_width, height / proxy_height)


def parse_tracknet_csv(
    csv_path: Path,
    source_fps: float,
    transform: dict[str, Any] | None,
    scaler: tuple[float, float],
    width: int,
    height: int,
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            frame_index = int(float(row["Frame"]))
            visible = int(float(row.get("Visibility", "0"))) == 1
            x = float(row.get("X", "0") or 0) * scaler[0]
            y = float(row.get("Y", "0") or 0) * scaler[1]
            position = [round(x, 2), round(y, 2)] if visible and (x > 0 or y > 0) else None
            court_point = map_point_to_court(position, transform) if position else None
            edge_score = edge_margin_score(position, width, height) if position else 0.0
            frames.append(
                {
                    "frame_index": frame_index,
                    "timestamp": round(frame_index / source_fps, 3) if source_fps > 0 else 0,
                    "position": position,
                    "court_point": court_point,
                    "confidence": 1.0 if position else 0.0,
                    "edge_score": round(edge_score, 3),
                    "candidates": [],
                }
            )
    return frames


def filter_tracknet_frames(frames: list[dict[str, Any]], source_fps: float, width: int, height: int) -> None:
    last_kept: dict[str, Any] | None = None
    previous_kept: dict[str, Any] | None = None
    rejected_streak = 0
    rejected = 0
    for frame in frames:
        position = frame.get("position")
        court_point = frame.get("court_point")
        frame["raw_position"] = position
        frame["filtered_position"] = None
        frame["rejected_reason"] = None
        if not position:
            continue

        reason = reject_reason(frame, last_kept, previous_kept, source_fps, width, height, rejected_streak)
        if reason:
            frame["rejected_reason"] = reason
            frame["position"] = None
            frame["court_point"] = court_point
            frame["confidence"] = 0.0
            rejected_streak += 1
            rejected += 1
            continue

        frame["filtered_position"] = position
        previous_kept = last_kept
        last_kept = frame
        rejected_streak = 0
    if frames:
        frames[0]["filter_summary"] = {"rejected_frames": rejected}


def reject_reason(
    frame: dict[str, Any],
    last_kept: dict[str, Any] | None,
    previous_kept: dict[str, Any] | None,
    source_fps: float,
    width: int,
    height: int,
    rejected_streak: int,
) -> str | None:
    position = frame.get("position")
    if position and is_hard_edge(position, width, height):
        return "edge_candidate"

    court_point = frame.get("court_point")
    if court_point and not plausible_target_court_projection(court_point):
        return "outside_target_court_projection"
    if not last_kept or not position or not last_kept.get("filtered_position"):
        return None

    dt = max(1 / max(source_fps, 1), float(frame["timestamp"]) - float(last_kept["timestamp"]))
    px_distance = distance(position, last_kept["filtered_position"])
    predicted = predict_next_position(last_kept, previous_kept, float(frame["timestamp"]))
    predicted_distance = distance(position, predicted) if predicted else px_distance
    court_distance = None
    if court_point and last_kept.get("court_point"):
        court_distance = distance(court_point, last_kept["court_point"])

    # After a short dropout, allow reacquisition. Before that, do not let a
    # distant point on another court hijack the current rally trajectory.
    if rejected_streak < int(source_fps * 0.35) and predicted_distance > max(160, 2600 * dt):
        return "trajectory_jump"
    if dt <= 0.12 and px_distance > 360:
        return "pixel_jump"
    if court_distance is not None and dt <= 0.12 and court_distance > 4.2:
        return "court_jump"
    return None


def plausible_target_court_projection(point: list[float]) -> bool:
    # The shuttle is airborne, so allow it well outside the floor rectangle, but
    # reject points that clearly belong to another court or the stands.
    return -3.5 <= point[0] <= COURT_WIDTH_M + 3.5 and -6.5 <= point[1] <= COURT_LENGTH_M + 6.5


def distance(a: list[float], b: list[float]) -> float:
    return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)


def edge_margin_score(point: list[float] | None, width: int, height: int) -> float:
    if not point:
        return 0.0
    margin = min(point[0], point[1], width - point[0], height - point[1])
    return max(0.0, min(1.0, margin / max(1.0, min(width, height) * 0.08)))


def is_hard_edge(point: list[float], width: int, height: int) -> bool:
    edge_margin = min(width, height) * 0.025
    return point[0] < edge_margin or point[0] > width - edge_margin or point[1] < edge_margin or point[1] > height - edge_margin


def predict_next_position(last_kept: dict[str, Any], previous_kept: dict[str, Any] | None, timestamp: float) -> list[float] | None:
    last_position = last_kept.get("filtered_position")
    previous_position = previous_kept.get("filtered_position") if previous_kept else None
    if not last_position or not previous_position:
        return last_position
    dt_prev = max(0.001, float(last_kept["timestamp"]) - float(previous_kept["timestamp"]))
    dt_next = max(0.0, timestamp - float(last_kept["timestamp"]))
    vx = (last_position[0] - previous_position[0]) / dt_prev
    vy = (last_position[1] - previous_position[1]) / dt_prev
    return [last_position[0] + vx * dt_next, last_position[1] + vy * dt_next]
