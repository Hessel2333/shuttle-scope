from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def detect_court_points(video_path: str) -> dict[str, Any]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("Unable to read first frame")

    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Badminton courts are often green/cyan. Keep this broad; contour quality gates the result.
    mask = cv2.inRange(hsv, np.array([35, 35, 35]), np.array([100, 255, 255]))
    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"points": [], "confidence": 0.0, "method": "green_contour", "message": "no court-colored contour found"}

    min_area = width * height * 0.08
    candidates = [contour for contour in contours if cv2.contourArea(contour) >= min_area]
    if not candidates:
        return {"points": [], "confidence": 0.0, "method": "green_contour", "message": "no large court contour found"}

    contour = max(candidates, key=cv2.contourArea)
    points = contour_to_quad(contour, width, height)
    area_ratio = cv2.contourArea(contour) / max(1, width * height)
    confidence = max(0.1, min(0.9, area_ratio * 1.8))
    return {"points": points, "confidence": round(confidence, 3), "method": "green_contour", "message": "ok"}


def contour_to_quad(contour: np.ndarray, width: int, height: int) -> list[dict[str, float]]:
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
    if len(approx) >= 4:
        hull = cv2.convexHull(approx)
        rect = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rect)
    else:
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)

    ordered = order_quad(box)
    return [{"x": round(float(x) / width, 5), "y": round(float(y) / height, 5)} for x, y in ordered]


def order_quad(points: np.ndarray) -> np.ndarray:
    pts = np.array(points, dtype=np.float32)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(-1)
    top_left = pts[np.argmin(sums)]
    bottom_right = pts[np.argmax(sums)]
    top_right = pts[np.argmin(diffs)]
    bottom_left = pts[np.argmax(diffs)]
    # UI/backend order is near-left, near-right, far-right, far-left. In image terms near is bottom.
    return np.array([bottom_left, bottom_right, top_right, top_left], dtype=np.float32)
