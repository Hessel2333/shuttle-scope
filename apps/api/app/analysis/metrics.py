from __future__ import annotations

import math
from collections import Counter
from typing import Any


def point_distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def zone_for_point(point: list[float], width: int, height: int) -> tuple[str, str]:
    x, y = point
    horizontal = "left" if x < width / 3 else "right" if x >= width * 2 / 3 else "center"
    vertical = "front" if y < height / 3 else "back" if y >= height * 2 / 3 else "mid"
    return vertical, horizontal


def zone_for_court_point(point: list[float], court_width_m: float, court_length_m: float) -> tuple[str, str]:
    x, y = point
    horizontal = "left" if x < court_width_m / 3 else "right" if x >= court_width_m * 2 / 3 else "center"
    vertical = "front" if y < court_length_m / 3 else "back" if y >= court_length_m * 2 / 3 else "mid"
    return vertical, horizontal


def point_in_court_bounds(point: list[float], court_width_m: float, court_length_m: float) -> bool:
    return 0 <= point[0] <= court_width_m and 0 <= point[1] <= court_length_m


def build_summary(
    *,
    job_id: str,
    video_id: str,
    duration_sec: float,
    fps_sampled: int,
    width: int,
    height: int,
    frames: list[dict[str, Any]],
    device: str,
    model_name: str,
    mode: str,
    locale: str = "zh",
    fallback_error: str | None = None,
) -> dict[str, Any]:
    detected = [frame for frame in frames if frame.get("bbox") and frame.get("foot_midpoint")]
    court_width_m = 6.1
    court_length_m = 13.4
    court_detected = [
        frame
        for frame in detected
        if frame.get("court_point") and point_in_court_bounds(frame["court_point"], court_width_m, court_length_m)
    ]
    use_court = bool(court_detected)
    track_ids = {
        person.get("track_id")
        for frame in frames
        for person in frame.get("persons", [])
        if person.get("track_id") is not None
    }
    max_persons_per_frame = max((len(frame.get("persons", [])) for frame in frames), default=0)
    confidences = [float(frame.get("person_confidence") or 0) for frame in detected]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    movement = 0.0
    speeds: list[float] = []
    last_frame: dict[str, Any] | None = None
    movement_frames = court_detected if use_court else detected
    point_key = "court_point" if use_court else "foot_midpoint"
    for frame in movement_frames:
        if last_frame is not None:
            dist = point_distance(last_frame[point_key], frame[point_key])
            dt = max(0.001, float(frame["timestamp"]) - float(last_frame["timestamp"]))
            movement += dist
            speeds.append(dist / dt)
        last_frame = frame

    vertical_counts: Counter[str] = Counter()
    horizontal_counts: Counter[str] = Counter()
    zone_frames = court_detected if use_court else detected
    for frame in zone_frames:
        if use_court:
            vertical, horizontal = zone_for_court_point(frame["court_point"], court_width_m, court_length_m)
        else:
            vertical, horizontal = zone_for_point(frame["foot_midpoint"], width, height)
        vertical_counts[vertical] += 1
        horizontal_counts[horizontal] += 1

    total = max(1, len(zone_frames))
    zone_ratio = {
        "front": round(vertical_counts["front"] / total, 3),
        "mid": round(vertical_counts["mid"] / total, 3),
        "back": round(vertical_counts["back"] / total, 3),
        "left": round(horizontal_counts["left"] / total, 3),
        "center": round(horizontal_counts["center"] / total, 3),
        "right": round(horizontal_counts["right"] / total, 3),
    }

    report = generate_report(
        detected_frames=len(detected),
        sampled_frames=len(frames),
        avg_confidence=avg_confidence,
        movement_px=movement,
        zone_ratio=zone_ratio,
        speeds=speeds,
        mode=mode,
        locale=locale,
        fallback_error=fallback_error,
    )

    return {
        "job_id": job_id,
        "video_id": video_id,
        "duration_sec": round(duration_sec, 2),
        "fps_sampled": fps_sampled,
        "sampled_frames": len(frames),
        "detected_frames": len(detected),
        "avg_confidence": round(avg_confidence, 3),
        "estimated_movement_px": round(movement, 1),
        "avg_speed_px_s": round(sum(speeds) / len(speeds), 1) if speeds else 0,
        "movement_unit": "m" if use_court else "px",
        "avg_speed_unit": "m/s" if use_court else "px/s",
        "zone_ratio": zone_ratio,
        "analysis": {
            "mode": mode,
            "device": device,
            "model_name": model_name,
            "fallback_error": fallback_error,
            "track_count": len(track_ids),
            "max_persons_per_frame": max_persons_per_frame,
            "court_calibrated": use_court,
        },
        "report": report,
    }


def generate_report(
    *,
    detected_frames: int,
    sampled_frames: int,
    avg_confidence: float,
    movement_px: float,
    zone_ratio: dict[str, float],
    speeds: list[float],
    mode: str,
    locale: str,
    fallback_error: str | None,
) -> dict[str, Any]:
    if locale == "en":
        return generate_report_en(
            detected_frames=detected_frames,
            sampled_frames=sampled_frames,
            avg_confidence=avg_confidence,
            movement_px=movement_px,
            zone_ratio=zone_ratio,
            speeds=speeds,
            mode=mode,
            fallback_error=fallback_error,
        )

    detection_rate = detected_frames / max(1, sampled_frames)
    next_steps: list[str] = []

    if mode == "mock":
        overall = "当前报告来自 mock analysis，用于验证上传、任务流和前端可视化。接入真实模型后可替换为实际姿态结果。"
    elif detection_rate < 0.55:
        overall = "人体检测覆盖率偏低，统计结果只能作为粗略参考。建议优先改善拍摄角度、光照和画面清晰度。"
        next_steps.append("重新拍摄一段球员全身始终入镜的视频，再进行对比分析。")
    else:
        overall = "姿态检测覆盖率可用，可以据此观察移动覆盖、回位习惯和区域停留分布。"

    if zone_ratio["back"] > 0.48:
        positioning = "后场停留比例偏高，可能存在击球后回中不足或被连续压后场的问题。"
        next_steps.append("加入后场击球后两步回中训练，观察后场比例是否下降。")
    elif zone_ratio["front"] > 0.42:
        positioning = "前场停留比例偏高，可能说明上网后后撤衔接不足，需关注后场保护。"
        next_steps.append("练习网前处理后的交叉步后撤，保持前后场切换节奏。")
    else:
        positioning = "前中后场分布相对均衡，下一步可结合具体回合判断站位质量。"

    side_gap = abs(zone_ratio["left"] - zone_ratio["right"])
    if side_gap > 0.25:
        weak_side = "右侧" if zone_ratio["left"] > zone_ratio["right"] else "左侧"
        movement = f"左右覆盖不均衡，{weak_side}到位次数偏少，建议检查该侧启动和跨步质量。"
        next_steps.append(f"安排针对{weak_side}的多球移动训练，保持启动脚和重心回收一致。")
    elif movement_px > 4800 and speeds and max(speeds) > 900:
        movement = "跑动量较大且速度波动明显，可能存在被动追球或路线不够经济的问题。"
        next_steps.append("复盘大幅移动片段，优先优化回中路线而不是单纯增加步频。")
    else:
        movement = "左右覆盖和移动量没有明显异常，可继续结合击球质量做更细判断。"

    if avg_confidence < 0.58:
        video_quality = "关键点置信度偏低，建议使用固定机位、提高快门/照明，并避免球员被遮挡。"
        next_steps.append("优先使用横向广角、全场入镜的机位重新采集样片。")
    else:
        video_quality = "视频清晰度和人体可见性基本满足第一版姿态分析。"

    if fallback_error:
        next_steps.append("真实 YOLO 推理失败时已自动回退 mock，请按 README 检查 CUDA/PyTorch/Ultralytics 安装。")

    if not next_steps:
        next_steps = ["补充场地标定后，将像素移动距离换算为真实米数。", "加入击球/回合切分后，进一步评估跑动效率。"]

    return {
        "overall": overall,
        "movement": movement,
        "positioning": positioning,
        "video_quality": video_quality,
        "next_steps": next_steps[:4],
    }


def generate_report_en(
    *,
    detected_frames: int,
    sampled_frames: int,
    avg_confidence: float,
    movement_px: float,
    zone_ratio: dict[str, float],
    speeds: list[float],
    mode: str,
    fallback_error: str | None,
) -> dict[str, Any]:
    detection_rate = detected_frames / max(1, sampled_frames)
    next_steps: list[str] = []

    if mode == "mock":
        overall = "This report comes from mock analysis and is intended to validate the upload flow, job flow, and visualization."
    elif detection_rate < 0.55:
        overall = "Human detection coverage is low, so the metrics should be treated as rough directional signals."
        next_steps.append("Record another clip with the player fully visible, then compare the detection coverage.")
    else:
        overall = "Pose detection coverage is usable for reviewing movement coverage, recovery habits, and court-zone distribution."

    if zone_ratio["back"] > 0.48:
        positioning = "Back-court dwell time is high, which may indicate insufficient recovery to base after rear-court shots."
        next_steps.append("Add rear-court shot plus two-step recovery drills and compare the back-court ratio.")
    elif zone_ratio["front"] > 0.42:
        positioning = "Front-court dwell time is high, so watch the transition from net play back to rear-court coverage."
        next_steps.append("Practice retreat footwork after net shots, keeping the center of mass controlled.")
    else:
        positioning = "Front, mid, and back court distribution is relatively balanced."

    side_gap = abs(zone_ratio["left"] - zone_ratio["right"])
    if side_gap > 0.25:
        weak_side = "right" if zone_ratio["left"] > zone_ratio["right"] else "left"
        movement = f"Left/right coverage is uneven. The {weak_side} side appears under-covered."
        next_steps.append(f"Add multi-shuttle movement drills toward the {weak_side} side.")
    elif movement_px > 4800 and speeds and max(speeds) > 900:
        movement = "Movement volume and speed variation are high, which may indicate inefficient recovery routes."
        next_steps.append("Review high-movement segments and optimize recovery path before increasing foot speed.")
    else:
        movement = "Left/right coverage and movement volume do not show a major anomaly."

    if avg_confidence < 0.58:
        video_quality = "Keypoint confidence is low. Use a fixed camera, stronger lighting, and avoid occlusion."
        next_steps.append("Capture a wide, full-court sample with the full body visible throughout the rally.")
    else:
        video_quality = "Video clarity and body visibility are sufficient for the current pose-analysis MVP."

    if fallback_error:
        next_steps.append("Real YOLO inference fell back to mock output. Check CUDA, PyTorch, and Ultralytics setup.")

    if not next_steps:
        next_steps = ["Add court calibration to convert pixel movement into meters.", "Add rally and shot segmentation to evaluate movement efficiency."]

    return {
        "overall": overall,
        "movement": movement,
        "positioning": positioning,
        "video_quality": video_quality,
        "next_steps": next_steps[:4],
    }
