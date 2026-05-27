from __future__ import annotations

import math
from typing import Any

from .court import add_court_points_to_frames, build_court_transform
from .metrics import build_summary


COCO_TEMPLATE = [
    (0.0, -0.32),
    (-0.04, -0.36),
    (0.04, -0.36),
    (-0.08, -0.33),
    (0.08, -0.33),
    (-0.16, -0.14),
    (0.16, -0.14),
    (-0.22, 0.06),
    (0.22, 0.06),
    (-0.18, 0.22),
    (0.18, 0.22),
    (-0.1, 0.18),
    (0.1, 0.18),
    (-0.12, 0.42),
    (0.12, 0.42),
    (-0.12, 0.68),
    (0.12, 0.68),
]


def make_mock_analysis(
    *,
    job_id: str,
    video_id: str,
    duration_sec: float,
    fps_sampled: int,
    width: int,
    height: int,
    device: str,
    model_name: str,
    roi: dict[str, float] | None = None,
    court_points: list[dict[str, float]] | None = None,
    locale: str = "zh",
    fallback_error: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    total_frames = max(30, int(duration_sec * fps_sampled) if duration_sec > 0 else 120)
    frames: list[dict[str, Any]] = []
    for index in range(total_frames):
        phase = index / max(1, total_frames - 1)
        cx = width * (0.5 + 0.28 * math.sin(phase * math.tau * 1.7))
        cy = height * (0.6 + 0.18 * math.sin(phase * math.tau * 2.3 + 0.7))
        body_h = height * (0.34 + 0.03 * math.sin(phase * math.tau * 3))
        body_w = body_h * 0.42
        x1 = max(0, cx - body_w / 2)
        y1 = max(0, cy - body_h * 0.55)
        x2 = min(width, cx + body_w / 2)
        y2 = min(height, cy + body_h * 0.75)
        keypoints = [
            [round(cx + ox * body_h, 2), round(cy + oy * body_h, 2), round(0.76 + 0.14 * math.sin(index + i), 3)]
            for i, (ox, oy) in enumerate(COCO_TEMPLATE)
        ]
        foot_midpoint = [
            round((keypoints[15][0] + keypoints[16][0]) / 2, 2),
            round((keypoints[15][1] + keypoints[16][1]) / 2, 2),
        ]
        selected_person = {
            "track_id": 1,
            "selected": True,
            "bbox": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
            "keypoints": keypoints,
            "raw_keypoint_count": 17,
            "valid_keypoint_count": 17,
            "person_confidence": 0.82,
            "center": [round(cx, 2), round(cy, 2)],
            "foot_midpoint": foot_midpoint,
        }
        opponent_cx = width * (0.5 + 0.18 * math.sin(phase * math.tau * 1.3 + 1.4))
        opponent_cy = height * (0.28 + 0.1 * math.sin(phase * math.tau * 1.8))
        opponent_h = body_h * 0.78
        opponent_keypoints = [
            [round(opponent_cx + ox * opponent_h, 2), round(opponent_cy + oy * opponent_h, 2), 0.72]
            for ox, oy in COCO_TEMPLATE
        ]
        opponent_person = {
            "track_id": 2,
            "selected": False,
            "bbox": [
                round(opponent_cx - body_w * 0.42, 2),
                round(opponent_cy - opponent_h * 0.55, 2),
                round(opponent_cx + body_w * 0.42, 2),
                round(opponent_cy + opponent_h * 0.75, 2),
            ],
            "keypoints": opponent_keypoints,
            "raw_keypoint_count": 17,
            "valid_keypoint_count": 17,
            "person_confidence": 0.76,
            "center": [round(opponent_cx, 2), round(opponent_cy, 2)],
            "foot_midpoint": [
                round((opponent_keypoints[15][0] + opponent_keypoints[16][0]) / 2, 2),
                round((opponent_keypoints[15][1] + opponent_keypoints[16][1]) / 2, 2),
            ],
        }
        frames.append(
            {
                "frame_index": index,
                "timestamp": round(index / fps_sampled, 3),
                "bbox": selected_person["bbox"],
                "keypoints": selected_person["keypoints"],
                "person_confidence": selected_person["person_confidence"],
                "center": selected_person["center"],
                "foot_midpoint": selected_person["foot_midpoint"],
                "persons": [selected_person, opponent_person],
            }
        )

    court_transform = build_court_transform(court_points, width, height)
    add_court_points_to_frames(frames, court_transform)
    pose = {
        "video_id": video_id,
        "fps_sampled": fps_sampled,
        "source_width": width,
        "source_height": height,
        "roi": roi,
        "court": court_transform,
        "primary_track_id": 1,
        "keypoint_filter": {
            "min_confidence": 0.35,
            "bbox_padding_ratio": 0.18,
            "temporal_smoothing": True,
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
        mode="mock",
        locale=locale,
        fallback_error=fallback_error,
    )
    return pose, summary
