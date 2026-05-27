"use client";

import { RefObject, useEffect, useRef } from "react";
import type { PoseFrame, PoseOutput, PosePerson, ShuttleFrame, ShuttleOutput } from "@/lib/types";

const EDGES = [
  [5, 7],
  [7, 9],
  [6, 8],
  [8, 10],
  [5, 6],
  [5, 11],
  [6, 12],
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [0, 5],
  [0, 6]
] as const;
const PLAYER_A_COLOR = "#ff9500";
const PLAYER_B_COLOR = "#007aff";

export function SkeletonOverlay({
  videoRef,
  pose,
  shuttle,
  showAllPersons,
  showCourtOverlay,
  showPersonOverlay,
  showShuttleOverlay
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  pose: PoseOutput;
  shuttle?: ShuttleOutput | null;
  showAllPersons: boolean;
  showCourtOverlay: boolean;
  showPersonOverlay: boolean;
  showShuttleOverlay: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    let raf = 0;
    let videoFrameCallback = 0;
    const renderedTime = { current: video.currentTime };
    const supportsVideoFrameCallback = typeof video.requestVideoFrameCallback === "function";

    const syncRenderedTime = (_now: number, metadata: VideoFrameCallbackMetadata) => {
      renderedTime.current = metadata.mediaTime;
      videoFrameCallback = video.requestVideoFrameCallback(syncRenderedTime);
    };

    if (supportsVideoFrameCallback) {
      videoFrameCallback = video.requestVideoFrameCallback(syncRenderedTime);
    }

    const resize = () => {
      const rect = video.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
    };

    const draw = () => {
      const context = canvas.getContext("2d");
      if (!context) return;
      const dpr = window.devicePixelRatio || 1;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, canvas.width, canvas.height);

      const renderTime = supportsVideoFrameCallback ? renderedTime.current : video.currentTime;
      const frame = nearestFrame(pose.frames, renderTime);
      if (frame) {
        const rect = video.getBoundingClientRect();
        const scaleX = rect.width / pose.source_width;
        const scaleY = rect.height / pose.source_height;
        if (showCourtOverlay) {
          drawRoi(context, pose, scaleX, scaleY);
          drawCourtPolygon(context, pose, scaleX, scaleY);
        }
        if (showPersonOverlay) {
          drawFrame(context, frame, scaleX, scaleY, showAllPersons);
        }
        if (showShuttleOverlay && shuttle) {
          const shuttleFrame = nearestShuttleFrame(shuttle.frames, renderTime);
          drawShuttleTrail(context, shuttle.frames, renderTime, scaleX, scaleY);
          if (shuttleFrame) drawShuttle(context, shuttleFrame, scaleX, scaleY);
        }
      }
      raf = requestAnimationFrame(draw);
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(video);
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      if (videoFrameCallback) video.cancelVideoFrameCallback(videoFrameCallback);
      observer.disconnect();
    };
  }, [pose, shuttle, showAllPersons, showCourtOverlay, showPersonOverlay, showShuttleOverlay, videoRef]);

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden />;
}

function nearestShuttleFrame(frames: ShuttleFrame[], time: number): ShuttleFrame | undefined {
  if (!frames.length) return undefined;
  let left = 0;
  let right = frames.length - 1;
  while (left < right) {
    const mid = Math.floor((left + right) / 2);
    if (frames[mid].timestamp < time) left = mid + 1;
    else right = mid;
  }
  const current = frames[left];
  const previous = frames[left - 1];
  const selected = previous && Math.abs(previous.timestamp - time) < Math.abs(current.timestamp - time) ? previous : current;
  return Math.abs(selected.timestamp - time) < 0.18 ? selected : undefined;
}

function drawShuttle(context: CanvasRenderingContext2D, frame: ShuttleFrame, scaleX: number, scaleY: number) {
  context.save();
  for (const candidate of frame.candidates?.slice(1, 4) ?? []) {
    const [x, y] = candidate.position;
    context.beginPath();
    context.arc(x * scaleX, y * scaleY, 4, 0, Math.PI * 2);
    context.strokeStyle = "rgba(255, 255, 255, 0.45)";
    context.lineWidth = 1.5;
    context.stroke();
  }
  const position = shuttlePosition(frame);
  if (position) {
    const [x, y] = position;
    context.shadowColor = "rgba(0, 0, 0, 0.55)";
    context.shadowBlur = 6;
    context.fillStyle = "#ffffff";
    context.strokeStyle = "#ef4444";
    context.lineWidth = 3;
    context.beginPath();
    context.arc(x * scaleX, y * scaleY, 7, 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.beginPath();
    context.arc(x * scaleX, y * scaleY, 14, 0, Math.PI * 2);
    context.strokeStyle = "rgba(239, 68, 68, 0.45)";
    context.lineWidth = 2;
    context.stroke();
  }
  context.restore();
}

function drawShuttleTrail(context: CanvasRenderingContext2D, frames: ShuttleFrame[], time: number, scaleX: number, scaleY: number) {
  const trail = frames
    .filter((frame) => frame.timestamp <= time && frame.timestamp >= time - 1.2)
    .map((frame) => ({ ...frame, point: shuttlePosition(frame) }))
    .filter((frame): frame is ShuttleFrame & { point: [number, number] } => Boolean(frame.point));
  if (trail.length < 2) return;

  context.save();
  context.lineCap = "round";
  context.lineJoin = "round";
  for (let index = 1; index < trail.length; index += 1) {
    const prev = trail[index - 1];
    const current = trail[index];
    const age = Math.max(0, Math.min(1, (time - current.timestamp) / 1.2));
    context.strokeStyle = `rgba(255, ${Math.round(220 - age * 120)}, 64, ${0.18 + (1 - age) * 0.62})`;
    context.lineWidth = 2.5 + (1 - age) * 2;
    context.beginPath();
    context.moveTo(prev.point[0] * scaleX, prev.point[1] * scaleY);
    context.lineTo(current.point[0] * scaleX, current.point[1] * scaleY);
    context.stroke();
  }
  for (const frame of trail) {
    const age = Math.max(0, Math.min(1, (time - frame.timestamp) / 1.2));
    context.fillStyle = `rgba(255, 211, 60, ${0.18 + (1 - age) * 0.72})`;
    context.beginPath();
    context.arc(frame.point[0] * scaleX, frame.point[1] * scaleY, 3 + (1 - age) * 2.5, 0, Math.PI * 2);
    context.fill();
  }
  context.restore();
}

function shuttlePosition(frame: ShuttleFrame): [number, number] | null {
  return frame.filtered_position ?? frame.position;
}

function nearestFrame(frames: PoseFrame[], time: number): PoseFrame | undefined {
  if (!frames.length) return undefined;
  let left = 0;
  let right = frames.length - 1;
  while (left < right) {
    const mid = Math.floor((left + right) / 2);
    if (frames[mid].timestamp < time) left = mid + 1;
    else right = mid;
  }
  const current = frames[left];
  const previous = frames[left - 1];
  if (!previous) return current;
  return Math.abs(previous.timestamp - time) < Math.abs(current.timestamp - time) ? previous : current;
}

function drawCourtPolygon(context: CanvasRenderingContext2D, pose: PoseOutput, scaleX: number, scaleY: number) {
  if (!pose.court?.points?.length) return;
  context.save();
  context.shadowBlur = 0;
  context.strokeStyle = "rgba(255, 149, 0, 0.9)";
  context.fillStyle = "rgba(255, 149, 0, 0.08)";
  context.lineWidth = 2;
  context.beginPath();
  pose.court.points.forEach((point, index) => {
    const x = point.x * pose.source_width * scaleX;
    const y = point.y * pose.source_height * scaleY;
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.closePath();
  context.fill();
  context.stroke();
  context.restore();
}

function drawRoi(context: CanvasRenderingContext2D, pose: PoseOutput, scaleX: number, scaleY: number) {
  if (!pose.roi) return;
  const x = pose.roi.x * pose.source_width * scaleX;
  const y = pose.roi.y * pose.source_height * scaleY;
  const width = pose.roi.width * pose.source_width * scaleX;
  const height = pose.roi.height * pose.source_height * scaleY;
  context.save();
  context.shadowBlur = 0;
  context.strokeStyle = "rgba(255, 149, 0, 0.72)";
  context.lineWidth = 2;
  context.setLineDash([8, 6]);
  context.strokeRect(x, y, width, height);
  context.restore();
}

function drawFrame(context: CanvasRenderingContext2D, frame: PoseFrame, scaleX: number, scaleY: number, showAllPersons: boolean) {
  const persons = frame.persons?.length
    ? visiblePersons(frame.persons, showAllPersons)
    : frame.bbox && frame.keypoints.length
      ? [
          {
            track_id: null,
            selected: true,
            bbox: frame.bbox,
            keypoints: frame.keypoints,
            person_confidence: frame.person_confidence,
            center: frame.center ?? [0, 0],
            foot_midpoint: frame.foot_midpoint ?? [0, 0],
            in_court: frame.in_court
          }
        ]
      : [];

  for (const person of persons) {
    drawPerson(context, person, scaleX, scaleY);
  }
}

function visiblePersons(persons: PosePerson[], showOutsideDetections: boolean) {
  if (showOutsideDetections) return persons;
  const courtTagged = persons.some((person) => typeof person.in_court === "boolean");
  if (!courtTagged) return persons;
  return persons.filter((person) => person.in_court !== false);
}

function drawPerson(context: CanvasRenderingContext2D, person: PosePerson, scaleX: number, scaleY: number) {
  const selected = person.selected !== false;
  const outsideCourt = person.in_court === false;
  context.lineWidth = 3;
  context.strokeStyle = outsideCourt ? "rgba(148, 163, 184, 0.48)" : selected ? PLAYER_A_COLOR : PLAYER_B_COLOR;
  context.fillStyle = "#ffffff";
  context.shadowColor = "rgba(0, 0, 0, 0.35)";
  context.shadowBlur = 4;

  for (const [a, b] of EDGES) {
    const p1 = person.keypoints[a];
    const p2 = person.keypoints[b];
    if (!p1 || !p2 || p1[2] < 0.35 || p2[2] < 0.35) continue;
    context.beginPath();
    context.moveTo(p1[0] * scaleX, p1[1] * scaleY);
    context.lineTo(p2[0] * scaleX, p2[1] * scaleY);
    context.stroke();
  }

  for (const point of person.keypoints) {
    if (point[2] < 0.35) continue;
    context.beginPath();
    context.arc(point[0] * scaleX, point[1] * scaleY, 4, 0, Math.PI * 2);
    context.fill();
    context.stroke();
  }

  const [x1, y1, x2, y2] = person.bbox;
  context.shadowBlur = 0;
  context.strokeStyle = outsideCourt ? "rgba(148, 163, 184, 0.45)" : selected ? "rgba(255, 149, 0, 0.9)" : "rgba(0, 122, 255, 0.55)";
  context.lineWidth = selected ? 2 : 1.5;
  context.setLineDash(outsideCourt ? [6, 5] : []);
  context.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);
  context.setLineDash([]);

  if (person.track_id !== null) {
    context.fillStyle = outsideCourt ? "rgba(100, 116, 139, 0.72)" : selected ? "rgba(255, 149, 0, 0.92)" : "rgba(0, 122, 255, 0.8)";
    context.fillRect(x1 * scaleX, Math.max(0, y1 * scaleY - 22), 46, 20);
    context.fillStyle = "#ffffff";
    context.font = "12px sans-serif";
    context.fillText(`P${person.track_id}`, x1 * scaleX + 8, Math.max(14, y1 * scaleY - 7));
  }
}
