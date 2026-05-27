"use client";

import { useEffect, useRef, useState } from "react";
import type { PointerEvent } from "react";
import type { CourtPoint } from "@/lib/types";
import { usePreferences } from "@/components/PreferencesProvider";

const HIT_RADIUS = 0.035;

export function CourtCalibrationPicker({
  file,
  points,
  detecting,
  onAutoDetect,
  onChange
}: {
  file: File | null;
  points: CourtPoint[];
  detecting: boolean;
  onAutoDetect: () => void;
  onChange: (points: CourtPoint[]) => void;
}) {
  const { t } = usePreferences();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const previewReadyRef = useRef(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [previewReady, setPreviewReady] = useState(false);
  const [previewError, setPreviewError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    let fallbackTimer: number | null = null;
    setPreviewReady(false);
    previewReadyRef.current = false;
    setPreviewError(false);
    if (!file || !canvasRef.current) return;
    objectUrl = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "auto";
    video.muted = true;
    video.playsInline = true;
    video.crossOrigin = "anonymous";

    const cleanup = () => {
      if (fallbackTimer) window.clearTimeout(fallbackTimer);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };

    const draw = () => {
      if (cancelled) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const width = video.videoWidth || 1280;
      const height = video.videoHeight || 720;
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (context) {
        context.drawImage(video, 0, 0, width, height);
        previewReadyRef.current = true;
        setPreviewReady(true);
        setPreviewError(false);
      }
    };

    video.onloadedmetadata = () => {
      try {
        video.currentTime = Math.min(0.1, Math.max(0, (video.duration || 1) / 20));
      } catch {
        draw();
      }
    };
    video.onseeked = draw;
    video.oncanplay = () => {
      if (!previewReadyRef.current) draw();
    };
    video.onerror = () => {
      if (!cancelled) setPreviewError(true);
      cleanup();
    };
    fallbackTimer = window.setTimeout(() => {
      if (!cancelled && !previewReadyRef.current) {
        try {
          draw();
        } catch {
          setPreviewError(true);
        }
      }
    }, 2500);
    video.src = objectUrl;
    video.load();
    return () => {
      cancelled = true;
      cleanup();
    };
  }, [file]);

  if (!file) return null;

  const pointerPoint = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: clamp((event.clientX - rect.left) / rect.width),
      y: clamp((event.clientY - rect.top) / rect.height)
    };
  };

  const begin = (event: PointerEvent<HTMLDivElement>) => {
    if (!previewReady) return;
    const point = pointerPoint(event);
    const existingIndex = nearestPointIndex(point, points);
    if (existingIndex !== null) {
      setDragIndex(existingIndex);
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (points.length < 4) {
      onChange([...points, point]);
    }
  };

  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (dragIndex === null) return;
    const point = pointerPoint(event);
    onChange(points.map((item, index) => (index === dragIndex ? point : item)));
  };

  const end = () => setDragIndex(null);

  return (
    <div className="mt-5 rounded-md border border-line bg-subtle p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink">{t("courtCalibration")}</div>
          <div className="text-xs leading-5 text-muted">{t("courtCalibrationHint")}</div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-surface px-2.5 py-1 text-xs font-semibold text-muted">
            {points.length}/4 {t("pointCount")}
          </span>
          <button
            type="button"
            className="focus-ring rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted hover:text-ink"
            onClick={onAutoDetect}
            disabled={detecting}
          >
            {detecting ? t("detectingCourt") : t("autoDetectCourt")}
          </button>
          <button
            type="button"
            className="focus-ring rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted hover:text-ink"
            onClick={() => onChange(points.slice(0, -1))}
            disabled={!points.length}
          >
            {t("undoPoint")}
          </button>
          <button
            type="button"
            className="focus-ring rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted hover:text-ink"
            onClick={() => onChange([])}
          >
            {t("clearCourt")}
          </button>
        </div>
      </div>
      <div
        className="relative overflow-hidden rounded-md bg-black"
        onPointerDown={begin}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
      >
        <canvas ref={canvasRef} className="aspect-video w-full select-none" />
        {!previewReady ? (
          <div className="absolute inset-0 flex items-center justify-center bg-black text-sm font-semibold text-white/75">
            {previewError ? t("previewFailed") : t("previewLoading")}
          </div>
        ) : null}
        <CourtPolygon points={points} />
      </div>
    </div>
  );
}

function CourtPolygon({ points }: { points: CourtPoint[] }) {
  const polyline = points.map((point) => `${point.x * 100},${point.y * 100}`).join(" ");
  const polygon = points.length === 4 ? polyline : "";
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
      {points.length === 4 ? <polygon points={polygon} fill="rgba(232,185,35,0.12)" stroke="rgba(232,185,35,0.9)" strokeWidth="0.35" /> : null}
      {points.length > 1 ? <polyline points={polyline} fill="none" stroke="rgba(232,185,35,0.9)" strokeWidth="0.3" /> : null}
      {points.map((point, index) => (
        <g key={`${point.x}-${point.y}-${index}`}>
          <circle cx={point.x * 100} cy={point.y * 100} r="1.45" fill="#f3c83f" stroke="#17202a" strokeWidth="0.25" />
          <text x={point.x * 100 + 1.7} y={point.y * 100 - 1.2} fill="#ffffff" fontSize="3" stroke="#17202a" strokeWidth="0.25">
            {index + 1}
          </text>
        </g>
      ))}
    </svg>
  );
}

function nearestPointIndex(point: CourtPoint, points: CourtPoint[]): number | null {
  let bestIndex: number | null = null;
  let bestDistance = HIT_RADIUS;
  points.forEach((candidate, index) => {
    const distance = Math.hypot(candidate.x - point.x, candidate.y - point.y);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}
