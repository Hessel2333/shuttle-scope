"use client";

import { useEffect, useRef, useState } from "react";
import type { PointerEvent } from "react";
import type { Roi } from "@/lib/types";
import { usePreferences } from "@/components/PreferencesProvider";

type DragState = {
  startX: number;
  startY: number;
};

export function RoiPicker({ file, roi, onChange }: { file: File | null; roi: Roi | null; onChange: (roi: Roi | null) => void }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const { t } = usePreferences();
  const [url, setUrl] = useState<string | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);

  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  if (!url) {
    return null;
  }

  const pointerToRoiPoint = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: clamp((event.clientX - rect.left) / rect.width),
      y: clamp((event.clientY - rect.top) / rect.height)
    };
  };

  const begin = (event: PointerEvent<HTMLDivElement>) => {
    const point = pointerToRoiPoint(event);
    setDrag({ startX: point.x, startY: point.y });
    onChange({ x: point.x, y: point.y, width: 0.01, height: 0.01 });
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const point = pointerToRoiPoint(event);
    onChange(normalizeRoi(drag.startX, drag.startY, point.x, point.y));
  };

  const end = () => {
    setDrag(null);
  };

  return (
    <div className="mt-5 rounded-md border border-line bg-subtle p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink">{t("roiTitle")}</div>
          <div className="text-xs text-muted">{t("roiHint")}</div>
        </div>
        <button
          type="button"
          className="focus-ring rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-muted hover:text-ink"
          onClick={() => onChange(null)}
        >
          {t("fullFrame")}
        </button>
      </div>
      <div
        className="relative overflow-hidden rounded-md bg-black"
        onPointerDown={begin}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
      >
        <video ref={videoRef} className="aspect-video w-full select-none" src={url} controls preload="metadata" />
        {roi ? <RoiBox roi={roi} /> : null}
      </div>
    </div>
  );
}

function RoiBox({ roi }: { roi: Roi }) {
  return (
    <div
      className="pointer-events-none absolute border-2 border-accent bg-accent/10 shadow-[0_0_0_9999px_rgba(0,0,0,0.18)]"
      style={{
        left: `${roi.x * 100}%`,
        top: `${roi.y * 100}%`,
        width: `${roi.width * 100}%`,
        height: `${roi.height * 100}%`
      }}
    />
  );
}

function normalizeRoi(x1: number, y1: number, x2: number, y2: number): Roi {
  const left = clamp(Math.min(x1, x2));
  const top = clamp(Math.min(y1, y2));
  const right = clamp(Math.max(x1, x2));
  const bottom = clamp(Math.max(y1, y2));
  return {
    x: left,
    y: top,
    width: Math.max(0.01, right - left),
    height: Math.max(0.01, bottom - top)
  };
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}
