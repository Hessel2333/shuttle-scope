from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw: str, base_dir: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


@dataclass(frozen=True)
class Settings:
    api_host: str
    api_port: int
    cors_origins: list[str]
    sample_fps: int
    model_name: str
    yolo_imgsz: int
    yolo_conf: float
    yolo_iou: float
    yolo_max_det: int
    yolo_court_crop_second_pass: bool
    yolo_court_crop_imgsz: int
    yolo_court_crop_conf: float
    yolo_court_crop_padding: float
    enable_shuttle_detection: bool
    enable_tracknet: bool
    tracknet_repo_dir: Path
    tracknet_tracknet_file: Path
    tracknet_inpaintnet_file: Path
    tracknet_batch_size: int
    tracknet_eval_mode: str
    tracknet_max_sample_num: int
    tracknet_use_inpaint: bool
    tracknet_proxy_max_width: int
    tracknet_large_video: bool
    tracknet_timeout_sec: int
    enable_mock_analysis: bool
    auto_download_model: bool
    data_dir: Path
    uploads_dir: Path
    outputs_dir: Path
    db_path: Path


def get_settings() -> Settings:
    api_dir = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    data_raw = os.getenv("DATA_DIR", str(repo_root / "data"))
    data_dir = Path(data_raw)
    if not data_dir.is_absolute():
        data_dir = (api_dir / data_dir).resolve()

    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return Settings(
        api_host=os.getenv("API_HOST", "127.0.0.1"),
        api_port=int(os.getenv("API_PORT", "8000")),
        cors_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        sample_fps=int(os.getenv("SAMPLE_FPS", "5")),
        model_name=os.getenv("MODEL_NAME", "yolo11n-pose.pt"),
        yolo_imgsz=int(os.getenv("YOLO_IMGSZ", "960")),
        yolo_conf=float(os.getenv("YOLO_CONF", "0.12")),
        yolo_iou=float(os.getenv("YOLO_IOU", "0.5")),
        yolo_max_det=int(os.getenv("YOLO_MAX_DET", "30")),
        yolo_court_crop_second_pass=_bool_env("YOLO_COURT_CROP_SECOND_PASS", True),
        yolo_court_crop_imgsz=int(os.getenv("YOLO_COURT_CROP_IMGSZ", "1280")),
        yolo_court_crop_conf=float(os.getenv("YOLO_COURT_CROP_CONF", "0.06")),
        yolo_court_crop_padding=float(os.getenv("YOLO_COURT_CROP_PADDING", "0.08")),
        enable_shuttle_detection=_bool_env("ENABLE_SHUTTLE_DETECTION", True),
        enable_tracknet=_bool_env("ENABLE_TRACKNET", True),
        tracknet_repo_dir=_resolve_path(os.getenv("TRACKNET_REPO_DIR", str(repo_root / "third_party" / "TrackNetV3")), api_dir),
        tracknet_tracknet_file=_resolve_path(os.getenv("TRACKNET_TRACKNET_FILE", str(repo_root / "data" / "models" / "tracknetv3" / "ckpts" / "TrackNet_best.pt")), api_dir),
        tracknet_inpaintnet_file=_resolve_path(os.getenv("TRACKNET_INPAINTNET_FILE", str(repo_root / "data" / "models" / "tracknetv3" / "ckpts" / "InpaintNet_best.pt")), api_dir),
        tracknet_batch_size=int(os.getenv("TRACKNET_BATCH_SIZE", "2")),
        tracknet_eval_mode=os.getenv("TRACKNET_EVAL_MODE", "nonoverlap"),
        tracknet_max_sample_num=int(os.getenv("TRACKNET_MAX_SAMPLE_NUM", "600")),
        tracknet_use_inpaint=_bool_env("TRACKNET_USE_INPAINT", False),
        tracknet_proxy_max_width=int(os.getenv("TRACKNET_PROXY_MAX_WIDTH", "960")),
        tracknet_large_video=_bool_env("TRACKNET_LARGE_VIDEO", False),
        tracknet_timeout_sec=int(os.getenv("TRACKNET_TIMEOUT_SEC", "360")),
        enable_mock_analysis=_bool_env("ENABLE_MOCK_ANALYSIS", True),
        auto_download_model=_bool_env("AUTO_DOWNLOAD_MODEL", True),
        data_dir=data_dir,
        uploads_dir=data_dir / "uploads",
        outputs_dir=data_dir / "outputs",
        db_path=data_dir / "db" / "shuttle_scope.sqlite3",
    )


settings = get_settings()


RUNTIME_SETTING_LIMITS: dict[str, tuple[float, float, type]] = {
    "sample_fps": (1, 15, int),
    "yolo_imgsz": (320, 1920, int),
    "yolo_conf": (0.01, 0.8, float),
    "yolo_iou": (0.1, 0.9, float),
    "yolo_max_det": (1, 80, int),
    "yolo_court_crop_imgsz": (320, 2560, int),
    "yolo_court_crop_conf": (0.01, 0.5, float),
    "tracknet_batch_size": (1, 8, int),
    "tracknet_proxy_max_width": (480, 1280, int),
    "tracknet_max_sample_num": (64, 1200, int),
    "tracknet_timeout_sec": (60, 1800, int),
}


def runtime_settings_path() -> Path:
    return settings.db_path.parent / "runtime_settings.json"


def load_runtime_settings() -> dict[str, Any]:
    path = runtime_settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_runtime_settings(overrides: dict[str, Any]) -> dict[str, Any]:
    current = load_runtime_settings()
    current.update(validate_runtime_settings(overrides))
    path = runtime_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def validate_runtime_settings(overrides: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in overrides.items():
        if key in RUNTIME_SETTING_LIMITS:
            minimum, maximum, caster = RUNTIME_SETTING_LIMITS[key]
            number = caster(value)
            if number < minimum or number > maximum:
                raise ValueError(f"{key} must be between {minimum} and {maximum}")
            cleaned[key] = number
        elif key in {"yolo_court_crop_second_pass", "enable_shuttle_detection", "enable_tracknet", "tracknet_large_video"}:
            cleaned[key] = bool(value)
    return cleaned


def effective_value(name: str) -> Any:
    overrides = load_runtime_settings()
    if name in overrides:
        return overrides[name]
    return getattr(settings, name)


def analysis_defaults() -> dict[str, Any]:
    return {
        "sample_fps": effective_value("sample_fps"),
        "yolo_imgsz": effective_value("yolo_imgsz"),
        "yolo_conf": effective_value("yolo_conf"),
        "yolo_iou": effective_value("yolo_iou"),
        "yolo_max_det": effective_value("yolo_max_det"),
        "yolo_court_crop_second_pass": effective_value("yolo_court_crop_second_pass"),
        "yolo_court_crop_imgsz": effective_value("yolo_court_crop_imgsz"),
        "yolo_court_crop_conf": effective_value("yolo_court_crop_conf"),
        "enable_shuttle_detection": effective_value("enable_shuttle_detection"),
        "enable_tracknet": effective_value("enable_tracknet"),
        "tracknet_large_video": effective_value("tracknet_large_video"),
        "tracknet_batch_size": effective_value("tracknet_batch_size"),
        "tracknet_proxy_max_width": effective_value("tracknet_proxy_max_width"),
        "tracknet_max_sample_num": effective_value("tracknet_max_sample_num"),
        "tracknet_timeout_sec": effective_value("tracknet_timeout_sec"),
    }


def ensure_data_dirs() -> None:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
