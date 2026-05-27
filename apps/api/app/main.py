from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import db
from .analysis.court_detect import detect_court_points
from .analysis.engine import analyze_shuttle_job, analyze_video_job
from .analysis.yolo_pose import detect_device
from .config import analysis_defaults, ensure_data_dirs, save_runtime_settings, settings
from .tracknet.runner import tracknet_status
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnalysisSettingsResponse,
    AnalysisSettingsUpdate,
    BulkDeleteJobsRequest,
    CourtDetectionResponse,
    DeleteJobsResponse,
    HealthResponse,
    JobRecord,
    UploadResponse,
    VideoRecord,
)


app = FastAPI(title="Shuttle Scope API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_data_dirs()
    db.init_db()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    device, cuda_available = detect_device()
    defaults = analysis_defaults()
    tracknet = tracknet_status()
    return HealthResponse(
        status="ok",
        device=device,
        cuda_available=cuda_available,
        model_name=settings.model_name,
        yolo_imgsz=defaults["yolo_imgsz"],
        yolo_conf=defaults["yolo_conf"],
        yolo_iou=defaults["yolo_iou"],
        yolo_max_det=defaults["yolo_max_det"],
        yolo_court_crop_second_pass=defaults["yolo_court_crop_second_pass"],
        yolo_court_crop_imgsz=defaults["yolo_court_crop_imgsz"],
        yolo_court_crop_conf=defaults["yolo_court_crop_conf"],
        shuttle_detection_enabled=defaults["enable_shuttle_detection"],
        tracknet_enabled=defaults["enable_tracknet"],
        tracknet_ready=tracknet["ready"],
        tracknet_busy=tracknet["busy"],
        tracknet_repo_dir=tracknet["repo_dir"],
        tracknet_tracknet_file=tracknet["tracknet_file"],
        tracknet_inpaintnet_file=tracknet["inpaintnet_file"],
        tracknet_batch_size=defaults["tracknet_batch_size"],
        tracknet_proxy_max_width=defaults["tracknet_proxy_max_width"],
        tracknet_max_sample_num=defaults["tracknet_max_sample_num"],
        tracknet_timeout_sec=defaults["tracknet_timeout_sec"],
        sample_fps=defaults["sample_fps"],
        mock_enabled=settings.enable_mock_analysis,
        data_dir=str(settings.data_dir),
    )


@app.get("/api/settings/analysis", response_model=AnalysisSettingsResponse)
def get_analysis_settings() -> AnalysisSettingsResponse:
    return AnalysisSettingsResponse(**analysis_defaults())


@app.patch("/api/settings/analysis", response_model=AnalysisSettingsResponse)
def update_analysis_settings(request: AnalysisSettingsUpdate) -> AnalysisSettingsResponse:
    try:
        save_runtime_settings(request.model_dump(exclude_none=True))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalysisSettingsResponse(**analysis_defaults())


@app.post("/api/videos/upload", response_model=UploadResponse)
def upload_video(file: UploadFile = File(...)) -> UploadResponse:
    original = Path(file.filename or "upload.mp4").name
    extension = Path(original).suffix.lower() or ".mp4"
    video_id = str(uuid.uuid4())
    stored_name = f"{video_id}{extension}"
    target = settings.uploads_dir / stored_name
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    record = db.insert_video(
        video_id=video_id,
        filename=stored_name,
        original_filename=original,
        content_type=file.content_type,
        file_path=target,
        size_bytes=target.stat().st_size,
    )
    return UploadResponse(video=VideoRecord(**record))


@app.post("/api/jobs/{video_id}/analyze", response_model=AnalyzeResponse)
def create_analysis_job(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: AnalyzeRequest | None = None,
) -> AnalyzeResponse:
    if not db.get_video(video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    job_id = str(uuid.uuid4())
    roi = request.roi.model_dump() if request and request.roi else None
    court_points = [point.model_dump() for point in request.court_points] if request and request.court_points and len(request.court_points) == 4 else None
    job = db.insert_job(job_id=job_id, video_id=video_id, roi=roi, court_points=court_points)
    locale = request.locale if request and request.locale in {"zh", "en"} else "zh"
    background_tasks.add_task(analyze_video_job, job_id, video_id, bool(request and request.mock), roi, court_points, locale)
    return AnalyzeResponse(job=JobRecord(**job))


@app.get("/api/jobs", response_model=list[JobRecord])
def get_jobs() -> list[JobRecord]:
    return [JobRecord(**row) for row in db.list_jobs()]


@app.get("/api/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str) -> JobRecord:
    row = db.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobRecord(**row)


@app.post("/api/jobs/{job_id}/analyze-shuttle", response_model=AnalyzeResponse)
def create_shuttle_analysis_job(job_id: str, background_tasks: BackgroundTasks) -> AnalyzeResponse:
    row = db.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {row['status']}")
    db.update_job(job_id, shuttle_status="queued", shuttle_progress=0, shuttle_error=None)
    background_tasks.add_task(analyze_shuttle_job, job_id)
    next_row = db.get_job(job_id)
    return AnalyzeResponse(job=JobRecord(**next_row))


@app.delete("/api/jobs/{job_id}", response_model=DeleteJobsResponse)
def delete_job(job_id: str) -> DeleteJobsResponse:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cleanup_job_outputs(job_id, job)
    deleted = db.delete_job(job_id)
    return DeleteJobsResponse(deleted=1 if deleted else 0, job_ids=[job_id] if deleted else [])


@app.post("/api/jobs/delete", response_model=DeleteJobsResponse)
def delete_jobs(request: BulkDeleteJobsRequest) -> DeleteJobsResponse:
    unique_ids = list(dict.fromkeys(request.job_ids))
    deleted_ids: list[str] = []
    for job_id in unique_ids:
        job = db.get_job(job_id)
        if not job:
            continue
        cleanup_job_outputs(job_id, job)
        deleted_ids.append(job_id)
    deleted_count = db.delete_jobs(deleted_ids)
    return DeleteJobsResponse(deleted=deleted_count, job_ids=deleted_ids)


@app.get("/api/videos/{video_id}/file")
def get_video_file(video_id: str) -> FileResponse:
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    path = Path(video["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")
    return FileResponse(path, media_type=video.get("content_type") or "video/mp4", filename=video["original_filename"])


@app.post("/api/videos/{video_id}/detect-court", response_model=CourtDetectionResponse)
def detect_court(video_id: str) -> CourtDetectionResponse:
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    path = Path(video["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")
    result = detect_court_points(str(path))
    return CourtDetectionResponse(**result)


@app.get("/api/outputs/{job_id}/pose")
def get_pose(job_id: str) -> dict:
    job = require_completed_job(job_id)
    return read_json_file(job.get("pose_path"), "pose output")


@app.get("/api/outputs/{job_id}/summary")
def get_summary(job_id: str) -> dict:
    job = require_completed_job(job_id)
    return read_json_file(job.get("summary_path"), "summary output")


@app.get("/api/outputs/{job_id}/shuttle")
def get_shuttle(job_id: str) -> dict:
    job = require_completed_job(job_id)
    return read_json_file(job.get("shuttle_path") or str(settings.outputs_dir / job_id / "shuttle.json"), "shuttle output")


def require_completed_job(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {job['status']}")
    return job


def read_json_file(path_value: str | None, label: str) -> dict:
    if not path_value:
        raise HTTPException(status_code=404, detail=f"{label} not available")
    path = Path(path_value)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{label} missing")
    return json.loads(path.read_text(encoding="utf-8"))


def cleanup_job_outputs(job_id: str, job: dict) -> None:
    paths: set[Path] = set()
    for key in ("pose_path", "summary_path", "shuttle_path"):
        value = job.get(key)
        if value:
            paths.add(Path(value))
    paths.add(settings.outputs_dir / job_id)

    output_root = settings.outputs_dir.resolve()
    for path in paths:
        try:
            resolved = path.resolve()
            if output_root not in resolved.parents and resolved != output_root:
                continue
            if resolved.is_dir():
                shutil.rmtree(resolved, ignore_errors=True)
            elif resolved.exists():
                resolved.unlink()
        except OSError:
            continue
