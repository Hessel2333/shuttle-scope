from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import db
from ..config import analysis_defaults, settings
from ..tracknet.runner import run_tracknetv3, tracknet_execution_slot, tracknet_ready
from .mock import make_mock_analysis
from .yolo_pose import detect_device, run_yolo_pose_analysis, video_metadata


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def analyze_video_job(
    job_id: str,
    video_id: str,
    force_mock: bool = False,
    roi: dict[str, float] | None = None,
    court_points: list[dict[str, float]] | None = None,
    locale: str = "zh",
) -> None:
    job_dir = settings.outputs_dir / job_id
    pose_path = job_dir / "pose.json"
    summary_path = job_dir / "summary.json"
    shuttle_path = job_dir / "shuttle.json"
    device, _ = detect_device()
    defaults = analysis_defaults()

    try:
        video = db.get_video(video_id)
        if not video:
            raise RuntimeError(f"Video not found: {video_id}")
        db.update_job(
            job_id,
            status="running",
            progress=3,
            pose_status="running",
            pose_progress=3,
            pose_error=None,
            shuttle_status="queued",
            shuttle_progress=0,
            shuttle_error=None,
            error=None,
        )

        video_path = video["file_path"]
        if force_mock:
            pose, summary = build_mock(job_id, video_id, video_path, device, roi=roi, court_points=court_points, locale=locale)
        else:
            try:
                pose, summary = run_yolo_pose_analysis(
                    job_id=job_id,
                    video_id=video_id,
                    video_path=video_path,
                    fps_sampled=defaults["sample_fps"],
                    model_name=settings.model_name,
                    imgsz=defaults["yolo_imgsz"],
                    conf=defaults["yolo_conf"],
                    iou=defaults["yolo_iou"],
                    max_det=defaults["yolo_max_det"],
                    court_crop_second_pass=defaults["yolo_court_crop_second_pass"],
                    court_crop_imgsz=defaults["yolo_court_crop_imgsz"],
                    court_crop_conf=defaults["yolo_court_crop_conf"],
                    court_crop_padding=settings.yolo_court_crop_padding,
                    device=device,
                    auto_download_model=settings.auto_download_model,
                    roi=roi,
                    court_points=court_points,
                    locale=locale,
                    progress_callback=lambda progress: db.update_job(
                        job_id,
                        progress=round(float(progress), 1),
                        pose_progress=round(float(progress), 1),
                    ),
                )
            except Exception as exc:
                if not settings.enable_mock_analysis:
                    raise
                pose, summary = build_mock(job_id, video_id, video_path, device, roi=roi, court_points=court_points, locale=locale, fallback_error=str(exc))

        write_json(pose_path, pose)
        write_json(summary_path, summary)
        db.update_job(
            job_id,
            status="completed",
            progress=100,
            pose_status="completed",
            pose_progress=100,
            pose_error=None,
            pose_path=str(pose_path),
            summary_path=str(summary_path),
            error=None,
        )
        if defaults["enable_shuttle_detection"] and not force_mock:
            try:
                db.update_job(job_id, shuttle_status="running", shuttle_progress=5, shuttle_error=None)
                if not defaults["enable_tracknet"]:
                    raise RuntimeError("TrackNetV3 is disabled. Enable TrackNetV3 in Settings to detect shuttle trajectory.")
                if not tracknet_ready():
                    raise RuntimeError("TrackNetV3 is not ready. Run scripts/setup-tracknet.ps1 and confirm model files exist.")
                with tracknet_execution_slot(
                    on_wait=lambda: db.update_job(
                        job_id,
                        shuttle_status="waiting",
                        shuttle_progress=3,
                        shuttle_error=None,
                    )
                ):
                    db.update_job(job_id, shuttle_status="running", shuttle_progress=10)
                    shuttle = run_tracknetv3(
                        video_id=video_id,
                        video_path=video_path,
                        court_points=court_points,
                    )
                db.update_job(job_id, shuttle_progress=90)
                write_json(shuttle_path, shuttle)
                db.update_job(
                    job_id,
                    shuttle_status="completed",
                    shuttle_progress=100,
                    shuttle_error=None,
                    shuttle_path=str(shuttle_path),
                )
            except Exception as shuttle_exc:
                error_message = f"Shuttle detection failed: {shuttle_exc}"
                write_json(
                    shuttle_path,
                    {
                        "video_id": video_id,
                        "fps_sampled": max(defaults["sample_fps"], 15),
                        "method": "failed",
                        "detected_frames": 0,
                        "error": error_message,
                        "frames": [],
                    },
                )
                db.update_job(
                    job_id,
                    shuttle_status="failed",
                    shuttle_progress=100,
                    shuttle_error=error_message,
                    shuttle_path=str(shuttle_path),
                )
        else:
            db.update_job(job_id, shuttle_status="skipped", shuttle_progress=100, shuttle_error=None)
    except Exception as exc:
        db.update_job(
            job_id,
            status="failed",
            progress=100,
            pose_status="failed",
            pose_progress=100,
            pose_error=str(exc),
            error=str(exc),
        )


def analyze_shuttle_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        return
    if job["status"] != "completed":
        db.update_job(job_id, shuttle_status="failed", shuttle_progress=100, shuttle_error="Pose analysis must complete before shuttle detection.")
        return

    defaults = analysis_defaults()
    shuttle_path = settings.outputs_dir / job_id / "shuttle.json"
    court_points = None
    if job.get("court_points_json"):
        try:
            court_points = json.loads(job["court_points_json"])
        except json.JSONDecodeError:
            court_points = None

    try:
        db.update_job(job_id, shuttle_status="running", shuttle_progress=5, shuttle_error=None)
        if not defaults["enable_tracknet"]:
            raise RuntimeError("TrackNetV3 is disabled. Enable TrackNetV3 in Settings to detect shuttle trajectory.")
        if not tracknet_ready():
            raise RuntimeError("TrackNetV3 is not ready. Run scripts/setup-tracknet.ps1 and confirm model files exist.")
        with tracknet_execution_slot(
            on_wait=lambda: db.update_job(
                job_id,
                shuttle_status="waiting",
                shuttle_progress=3,
                shuttle_error=None,
            )
        ):
            db.update_job(job_id, shuttle_status="running", shuttle_progress=10)
            shuttle = run_tracknetv3(
                video_id=job["video_id"],
                video_path=job["video_path"],
                court_points=court_points,
            )
        db.update_job(job_id, shuttle_progress=90)
        write_json(shuttle_path, shuttle)
        db.update_job(job_id, shuttle_status="completed", shuttle_progress=100, shuttle_error=None, shuttle_path=str(shuttle_path))
    except Exception as exc:
        error_message = f"Shuttle detection failed: {exc}"
        write_json(
            shuttle_path,
            {
                "video_id": job["video_id"],
                "fps_sampled": max(defaults["sample_fps"], 15),
                "method": "failed",
                "detected_frames": 0,
                "error": error_message,
                "frames": [],
            },
        )
        db.update_job(job_id, shuttle_status="failed", shuttle_progress=100, shuttle_error=error_message, shuttle_path=str(shuttle_path))


def build_mock(
    job_id: str,
    video_id: str,
    video_path: str,
    device: str,
    roi: dict[str, float] | None = None,
    court_points: list[dict[str, float]] | None = None,
    locale: str = "zh",
    fallback_error: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    defaults = analysis_defaults()
    try:
        duration_sec, width, height, _ = video_metadata(video_path)
    except Exception:
        duration_sec, width, height = 24.0, 1280, 720
    return make_mock_analysis(
        job_id=job_id,
        video_id=video_id,
        duration_sec=duration_sec,
        fps_sampled=defaults["sample_fps"],
        width=width,
        height=height,
        device=device,
        model_name=settings.model_name,
        roi=roi,
        court_points=court_points,
        locale=locale,
        fallback_error=fallback_error,
    )
