from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
TRACKNET_DIR = ROOT / "third_party" / "TrackNetV3"
TRACKNET_FILE = ROOT / "data" / "models" / "tracknetv3" / "ckpts" / "TrackNet_best.pt"
INPAINT_FILE = ROOT / "data" / "models" / "tracknetv3" / "ckpts" / "InpaintNet_best.pt"
VIDEO = ROOT / "example_video" / "男单1分钟.mp4"
OUT_DIR = ROOT / "data" / "experiments" / "tracknet_men_single_1min"
COURT_WIDTH_M = 6.1
COURT_LENGTH_M = 13.4
COURT_POINTS = [
    {"x": 0.1063650132018067, "y": 0.9165078154784598},
    {"x": 0.7968798166490196, "y": 0.8982081585970263},
    {"x": 0.5841497902454061, "y": 0.23179565383149067},
    {"x": 0.3688464167482007, "y": 0.23637056805184903},
]


@dataclass(frozen=True)
class Experiment:
    name: str
    proxy_width: int
    batch_size: int = 2
    eval_mode: str = "nonoverlap"
    max_sample_num: int = 600
    use_inpaint: bool = False
    large_video: bool = False


EXPERIMENTS = {
    "w960_nonoverlap": Experiment(name="w960_nonoverlap", proxy_width=960),
    "w960_average": Experiment(name="w960_average", proxy_width=960, batch_size=4, eval_mode="average"),
    "w1280_nonoverlap": Experiment(name="w1280_nonoverlap", proxy_width=1280),
    "w1280_inpaint": Experiment(name="w1280_inpaint", proxy_width=1280, use_inpaint=True),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", nargs="*", default=list(EXPERIMENTS), choices=list(EXPERIMENTS))
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--contact-sheets-only", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []
    for name in args.names:
        exp = EXPERIMENTS[name]
        exp_dir = OUT_DIR / exp.name
        exp_dir.mkdir(parents=True, exist_ok=True)
        result_json = exp_dir / "shuttle.json"
        if not args.contact_sheets_only and not (args.skip_existing and result_json.exists()):
            run_experiment(exp, exp_dir)
        if result_json.exists():
            payload = json.loads(result_json.read_text(encoding="utf-8"))
            enrich_with_court(payload)
            write_filter_variants(payload, exp_dir)
            metrics = compute_metrics(payload)
            (exp_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
            write_contact_sheet(VIDEO, payload, exp_dir / "contact_sheet.jpg")
            for variant_path in sorted(exp_dir.glob("shuttle_filtered_*.json")):
                variant_payload = json.loads(variant_path.read_text(encoding="utf-8"))
                write_contact_sheet(VIDEO, variant_payload, exp_dir / f"{variant_path.stem}_contact_sheet.jpg")
            summary.append({"name": exp.name, **metrics})

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run_experiment(exp: Experiment, exp_dir: Path) -> None:
    started = time.perf_counter()
    width, height, fps, frame_count = video_meta(VIDEO)
    proxy_path, scaler = make_proxy(VIDEO, exp_dir, exp.proxy_width, width, height, fps)
    save_dir = exp_dir / "predict"
    if save_dir.exists():
        shutil.rmtree(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(TRACKNET_DIR / "predict.py"),
        "--video_file",
        str(proxy_path),
        "--tracknet_file",
        str(TRACKNET_FILE),
        "--save_dir",
        str(save_dir),
        "--batch_size",
        str(exp.batch_size),
        "--eval_mode",
        exp.eval_mode,
        "--max_sample_num",
        str(exp.max_sample_num),
    ]
    if exp.use_inpaint:
        command.extend(["--inpaintnet_file", str(INPAINT_FILE)])
    if exp.large_video:
        command.append("--large_video")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{TRACKNET_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("MKL_NUM_THREADS", "2")
    env.setdefault("OPENBLAS_NUM_THREADS", "2")
    env.setdefault("NUMEXPR_NUM_THREADS", "2")
    env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")
    result = subprocess.run(
        command,
        cwd=TRACKNET_DIR,
        env=env,
        text=True,
        capture_output=True,
        timeout=900,
        check=False,
    )
    (exp_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8", errors="replace")
    (exp_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"{exp.name} failed: {result.stderr[-1200:] or result.stdout[-1200:]}")

    csv_path = find_prediction_csv(exp_dir, proxy_path.stem)
    if not csv_path:
        raise RuntimeError(f"{exp.name} did not produce csv for {proxy_path.stem}")
    frames = parse_csv(csv_path, fps, scaler)
    payload = {
        "video_id": "example_video/男单1分钟.mp4",
        "fps_sampled": round(fps, 3),
        "duration_sec": round(frame_count / fps, 2) if fps > 0 else 0,
        "source_width": width,
        "source_height": height,
        "method": "tracknetv3",
        "experiment": exp.__dict__,
        "runtime_sec": round(time.perf_counter() - started, 2),
        "proxy_scaler": {"x": scaler[0], "y": scaler[1]},
        "detected_frames": sum(1 for frame in frames if frame["position"]),
        "frames": frames,
    }
    enrich_with_court(payload)
    (exp_dir / "shuttle.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def video_meta(path: Path) -> tuple[int, int, float, int]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return width, height, fps, frames


def make_proxy(source: Path, exp_dir: Path, proxy_width: int, width: int, height: int, fps: float) -> tuple[Path, tuple[float, float]]:
    if proxy_width <= 0 or width <= proxy_width:
        return source, (1.0, 1.0)
    proxy_height = int(round(height * (proxy_width / width)))
    proxy_height += proxy_height % 2
    proxy_path = exp_dir / f"{source.stem}_w{proxy_width}.mp4"
    if proxy_path.exists():
        return proxy_path, (width / proxy_width, height / proxy_height)
    cap = cv2.VideoCapture(str(source))
    writer = cv2.VideoWriter(str(proxy_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (proxy_width, proxy_height))
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(cv2.resize(frame, (proxy_width, proxy_height), interpolation=cv2.INTER_AREA))
    cap.release()
    writer.release()
    return proxy_path, (width / proxy_width, height / proxy_height)


def parse_csv(csv_path: Path, fps: float, scaler: tuple[float, float]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            frame_index = int(float(row["Frame"]))
            visible = int(float(row.get("Visibility", "0"))) == 1
            x = float(row.get("X", "0") or 0) * scaler[0]
            y = float(row.get("Y", "0") or 0) * scaler[1]
            position = [round(x, 2), round(y, 2)] if visible and (x > 0 or y > 0) else None
            frames.append(
                {
                    "frame_index": frame_index,
                    "timestamp": round(frame_index / fps, 3) if fps > 0 else 0,
                    "position": position,
                    "raw_position": position,
                    "confidence": 1.0 if position else 0.0,
                }
            )
    return frames


def find_prediction_csv(exp_dir: Path, proxy_stem: str) -> Path | None:
    expected = exp_dir / f"{proxy_stem}_ball.csv"
    if expected.exists():
        return expected
    candidates = sorted(exp_dir.rglob("*_ball.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def compute_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    frames = payload["frames"]
    positions = [(frame["frame_index"], frame["position"]) for frame in frames if frame.get("position")]
    jumps = []
    streak = 0
    max_static_streak = 0
    prev = None
    prev_frame = None
    unique = set()
    for frame_index, point in positions:
        rounded = (round(point[0] / 4) * 4, round(point[1] / 4) * 4)
        unique.add(rounded)
        if prev is not None and prev_frame is not None:
            dist = ((point[0] - prev[0]) ** 2 + (point[1] - prev[1]) ** 2) ** 0.5
            frame_gap = max(1, frame_index - prev_frame)
            jumps.append(dist / frame_gap)
            if dist < 4 and frame_gap == 1:
                streak += 1
                max_static_streak = max(max_static_streak, streak)
            else:
                streak = 0
        prev = point
        prev_frame = frame_index

    jump_sorted = sorted(jumps)
    def pct(percent: float) -> float:
        if not jump_sorted:
            return 0.0
        index = min(len(jump_sorted) - 1, int(round((len(jump_sorted) - 1) * percent)))
        return round(jump_sorted[index], 2)

    return {
        "runtime_sec": payload.get("runtime_sec"),
        "frames": len(frames),
        "detected_frames": len(positions),
        "detected_ratio": round(len(positions) / max(1, len(frames)), 4),
        "unique_positions": len(unique),
        "unique_ratio": round(len(unique) / max(1, len(positions)), 4),
        "max_static_streak": max_static_streak,
        "step_px_p50": pct(0.5),
        "step_px_p90": pct(0.9),
        "step_px_p99": pct(0.99),
        "jump_gt_120_count": sum(1 for value in jumps if value > 120),
        "jump_gt_240_count": sum(1 for value in jumps if value > 240),
        "proxy_scaler": payload.get("proxy_scaler"),
    }


def enrich_with_court(payload: dict[str, Any]) -> None:
    width = int(payload["source_width"])
    height = int(payload["source_height"])
    transform = build_court_transform(width, height)
    for frame in payload["frames"]:
        frame["raw_position"] = frame.get("raw_position") or frame.get("position")
        frame["court_point"] = map_to_court(frame.get("raw_position"), transform)


def build_court_transform(width: int, height: int) -> np.ndarray:
    source = np.array([[point["x"] * width, point["y"] * height] for point in COURT_POINTS], dtype=np.float32)
    destination = np.array(
        [[0.0, 0.0], [COURT_WIDTH_M, 0.0], [COURT_WIDTH_M, COURT_LENGTH_M], [0.0, COURT_LENGTH_M]],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(source, destination)


def map_to_court(point: list[float] | None, transform: np.ndarray) -> list[float] | None:
    if not point:
        return None
    source = np.array([[[float(point[0]), float(point[1])]]], dtype=np.float32)
    mapped = cv2.perspectiveTransform(source, transform)[0][0]
    if not np.isfinite(mapped[0]) or not np.isfinite(mapped[1]):
        return None
    return [round(float(mapped[0]), 3), round(float(mapped[1]), 3)]


def write_filter_variants(payload: dict[str, Any], exp_dir: Path) -> None:
    variants = {
        "loose": (-3.5, COURT_WIDTH_M + 3.5, -6.5, COURT_LENGTH_M + 6.5),
        "medium": (-2.0, COURT_WIDTH_M + 2.0, -4.0, COURT_LENGTH_M + 4.0),
        "strict": (-1.0, COURT_WIDTH_M + 1.0, -2.5, COURT_LENGTH_M + 2.5),
    }
    for name, bounds in variants.items():
        variant = json.loads(json.dumps(payload, ensure_ascii=False))
        apply_court_filter(variant, bounds)
        variant["post_filter"] = {"name": name, "court_bounds": bounds}
        variant["detected_frames"] = sum(1 for frame in variant["frames"] if frame.get("position"))
        variant_path = exp_dir / f"shuttle_filtered_{name}.json"
        variant_path.write_text(json.dumps(variant, ensure_ascii=False, indent=2), encoding="utf-8")
        metrics = compute_metrics(variant)
        (exp_dir / f"metrics_filtered_{name}.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_court_filter(payload: dict[str, Any], bounds: tuple[float, float, float, float]) -> None:
    min_x, max_x, min_y, max_y = bounds
    previous: list[float] | None = None
    previous_frame: int | None = None
    rejected = 0
    for frame in payload["frames"]:
        raw = frame.get("raw_position")
        court_point = frame.get("court_point")
        frame["position"] = raw
        frame["filtered_position"] = None
        frame["rejected_reason"] = None
        if not raw:
            continue
        if court_point and not (min_x <= court_point[0] <= max_x and min_y <= court_point[1] <= max_y):
            frame["position"] = None
            frame["confidence"] = 0.0
            frame["rejected_reason"] = "outside_target_court_airspace"
            rejected += 1
            continue
        if previous is not None and previous_frame is not None:
            frame_gap = max(1, int(frame["frame_index"]) - previous_frame)
            jump = ((raw[0] - previous[0]) ** 2 + (raw[1] - previous[1]) ** 2) ** 0.5 / frame_gap
            if frame_gap <= 3 and jump > 520:
                frame["position"] = None
                frame["confidence"] = 0.0
                frame["rejected_reason"] = "large_single_frame_jump"
                rejected += 1
                continue
        frame["filtered_position"] = raw
        previous = raw
        previous_frame = int(frame["frame_index"])
    if payload["frames"]:
        payload["frames"][0]["filter_summary"] = {"rejected_frames": rejected}


def write_contact_sheet(video_path: Path, payload: dict[str, Any], output: Path) -> None:
    times = [0.5, 3, 6, 9, 12, 14, 18, 22, 28, 34, 42, 52]
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60
    frames_by_index = {int(frame["frame_index"]): frame for frame in payload["frames"] if frame.get("position")}
    thumbs = []
    for seconds in times:
        target = int(round(seconds * fps))
        nearest = nearest_prediction(frames_by_index, target)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, image = cap.read()
        if not ok:
            continue
        image = cv2.resize(image, (640, 360), interpolation=cv2.INTER_AREA)
        if nearest:
            point = nearest["position"]
            x = int(round(point[0] * 640 / payload["source_width"]))
            y = int(round(point[1] * 360 / payload["source_height"]))
            cv2.circle(image, (x, y), 9, (0, 0, 255), 3)
            cv2.circle(image, (x, y), 3, (255, 255, 255), -1)
            label = f"{seconds:.1f}s pred f{nearest['frame_index']}"
        else:
            label = f"{seconds:.1f}s no pred"
        cv2.rectangle(image, (0, 0), (220, 30), (0, 0, 0), -1)
        cv2.putText(image, label, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        thumbs.append(image)
    cap.release()
    if not thumbs:
        return
    rows = []
    for i in range(0, len(thumbs), 3):
        row = thumbs[i : i + 3]
        while len(row) < 3:
            row.append(255 * row[0])
        rows.append(cv2.hconcat(row))
    sheet = cv2.vconcat(rows)
    cv2.imwrite(str(output), sheet)


def nearest_prediction(frames_by_index: dict[int, dict[str, Any]], target: int) -> dict[str, Any] | None:
    if not frames_by_index:
        return None
    best_index = min(frames_by_index, key=lambda index: abs(index - target))
    if abs(best_index - target) > 12:
        return None
    return frames_by_index[best_index]


if __name__ == "__main__":
    main()
