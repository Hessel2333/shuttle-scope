from __future__ import annotations

from pydantic import BaseModel


class Roi(BaseModel):
    x: float
    y: float
    width: float
    height: float


class CourtPoint(BaseModel):
    x: float
    y: float


class AnalyzeRequest(BaseModel):
    mock: bool = False
    roi: Roi | None = None
    court_points: list[CourtPoint] | None = None
    locale: str = "zh"


class VideoRecord(BaseModel):
    id: str
    filename: str
    original_filename: str
    content_type: str | None = None
    file_path: str
    size_bytes: int
    created_at: str


class JobRecord(BaseModel):
    id: str
    video_id: str
    status: str
    progress: float
    error: str | None = None
    pose_status: str | None = None
    pose_progress: float | None = None
    pose_error: str | None = None
    shuttle_status: str | None = None
    shuttle_progress: float | None = None
    shuttle_error: str | None = None
    pose_path: str | None = None
    summary_path: str | None = None
    shuttle_path: str | None = None
    roi_json: str | None = None
    court_points_json: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None
    original_filename: str | None = None
    video_path: str | None = None


class UploadResponse(BaseModel):
    video: VideoRecord


class AnalyzeResponse(BaseModel):
    job: JobRecord


class HealthResponse(BaseModel):
    status: str
    device: str
    cuda_available: bool
    model_name: str
    yolo_imgsz: int
    yolo_conf: float
    yolo_iou: float
    yolo_max_det: int
    yolo_court_crop_second_pass: bool
    yolo_court_crop_imgsz: int
    yolo_court_crop_conf: float
    shuttle_detection_enabled: bool
    tracknet_enabled: bool
    tracknet_ready: bool
    tracknet_busy: bool
    tracknet_repo_dir: str
    tracknet_tracknet_file: str
    tracknet_inpaintnet_file: str
    tracknet_batch_size: int
    tracknet_proxy_max_width: int
    tracknet_max_sample_num: int
    tracknet_timeout_sec: int
    sample_fps: int
    mock_enabled: bool
    data_dir: str


class AnalysisSettingsResponse(BaseModel):
    sample_fps: int
    yolo_imgsz: int
    yolo_conf: float
    yolo_iou: float
    yolo_max_det: int
    yolo_court_crop_second_pass: bool
    yolo_court_crop_imgsz: int
    yolo_court_crop_conf: float
    enable_shuttle_detection: bool
    enable_tracknet: bool
    tracknet_large_video: bool
    tracknet_batch_size: int
    tracknet_proxy_max_width: int
    tracknet_max_sample_num: int
    tracknet_timeout_sec: int


class AnalysisSettingsUpdate(BaseModel):
    sample_fps: int | None = None
    yolo_imgsz: int | None = None
    yolo_conf: float | None = None
    yolo_iou: float | None = None
    yolo_max_det: int | None = None
    yolo_court_crop_second_pass: bool | None = None
    yolo_court_crop_imgsz: int | None = None
    yolo_court_crop_conf: float | None = None
    enable_shuttle_detection: bool | None = None
    enable_tracknet: bool | None = None
    tracknet_large_video: bool | None = None
    tracknet_batch_size: int | None = None
    tracknet_proxy_max_width: int | None = None
    tracknet_max_sample_num: int | None = None
    tracknet_timeout_sec: int | None = None


class BulkDeleteJobsRequest(BaseModel):
    job_ids: list[str]


class DeleteJobsResponse(BaseModel):
    deleted: int
    job_ids: list[str]


class CourtDetectionResponse(BaseModel):
    points: list[CourtPoint]
    confidence: float
    method: str
    message: str
