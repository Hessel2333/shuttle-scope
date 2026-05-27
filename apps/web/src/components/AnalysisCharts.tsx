"use client";

import { useId, useState } from "react";
import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import type { PoseOutput } from "@/lib/types";
import { usePreferences } from "@/components/PreferencesProvider";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });
const PLAYER_A_COLOR = "#ff9500";
const PLAYER_B_COLOR = "#007aff";

type TooltipParam = { value?: unknown };
type CourtTrackPoint = { x: number; y: number; timestamp: number };
type CourtTrack = {
  id: number;
  displayId: 1 | 2;
  label: "A" | "B";
  selected: boolean;
  points: CourtTrackPoint[];
  displayPoints: CourtTrackPoint[];
  color: string;
};
type CourtMapMode = "heat" | "contour" | "scatter" | "path";
type HeatSpot = { x: number; y: number; value: number; rx: number; ry: number };

function chartValue(params: TooltipParam | TooltipParam[]): [number, number, number] {
  const raw = Array.isArray(params) ? params[0]?.value : params.value;
  return Array.isArray(raw) ? (raw as [number, number, number]) : [0, 0, 0];
}

export function TrajectoryChart({ pose }: { pose: PoseOutput }) {
  const { resolvedTheme } = usePreferences();
  const dark = resolvedTheme === "dark";
  const calibrated = Boolean(pose.court);
  const maxX = pose.court?.court_width_m ?? pose.source_width;
  const maxY = pose.court?.court_length_m ?? pose.source_height;
  const points = pose.frames
    .filter((frame) => (calibrated ? frame.court_point : frame.foot_midpoint))
    .map((frame) => {
      const point = calibrated ? frame.court_point! : frame.foot_midpoint!;
      return [point[0], maxY - point[1], frame.timestamp];
    });

  const option: EChartsOption = {
    grid: { left: 34, right: 18, top: 24, bottom: 30 },
    tooltip: {
      formatter: (params: TooltipParam | TooltipParam[]) => {
        const value = chartValue(params);
        const suffix = calibrated ? "m" : "px";
        return `x ${value[0].toFixed(calibrated ? 2 : 0)}${suffix}, y ${value[1].toFixed(calibrated ? 2 : 0)}${suffix}<br/>${value[2]}s`;
      }
    },
    textStyle: { color: dark ? "#9eaab8" : "#607080" },
    xAxis: { min: 0, max: maxX, splitLine: { lineStyle: { color: dark ? "#3a4450" : "#d7dee8" } } },
    yAxis: { min: 0, max: maxY, splitLine: { lineStyle: { color: dark ? "#3a4450" : "#d7dee8" } } },
    series: [
      {
        type: "line",
        data: points,
        symbolSize: 5,
        lineStyle: { color: PLAYER_B_COLOR, width: 3 },
        itemStyle: { color: PLAYER_A_COLOR }
      }
    ]
  };

  return <ReactECharts option={option} style={{ height: 300 }} theme={dark ? "dark" : undefined} notMerge lazyUpdate />;
}

export function CourtMovementMap({ pose, onSeek }: { pose: PoseOutput; onSeek?: (timestamp: number) => void }) {
  const { resolvedTheme, t } = usePreferences();
  const heatId = useId().replace(/:/g, "");
  const [mode, setMode] = useState<CourtMapMode>("path");
  const dark = resolvedTheme === "dark";
  const courtWidth = pose.court?.court_width_m ?? 6.1;
  const courtLength = pose.court?.court_length_m ?? 13.4;
  const tracks = buildCourtTracks(pose, 2);
  const heatSpots = buildHeatSpots(tracks, courtWidth, courtLength);
  const metrics = tracks.map((track) => buildTrackMetrics(track, courtWidth, courtLength));
  const maxHeat = Math.max(1, ...heatSpots.map((spot) => spot.value));
  const hasCourt = Boolean(pose.court);
  const showHeat = mode === "heat";
  const showContour = mode === "contour";
  const showPath = mode === "path";
  const showPoints = mode === "path" || mode === "scatter";
  const clipId = `court-clip-${heatId}`;
  const blurId = `heat-blur-${heatId}`;
  const contourBlurId = `contour-blur-${heatId}`;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4 text-sm font-semibold text-muted">
          {tracks.map((track) => (
            <span key={track.id} className="inline-flex items-center gap-2">
              <span className="h-3 w-3 rounded-full" style={{ backgroundColor: track.color }} />
              {track.label === "A" ? t("playerA") : t("playerB")}
            </span>
          ))}
        </div>
        <div className="grid grid-cols-4 gap-1 rounded-md border border-line bg-subtle p-1">
          {(["path", "scatter", "heat", "contour"] as const).map((item) => (
            <button
              key={item}
              type="button"
              className={`focus-ring rounded px-3 py-1.5 text-xs font-semibold transition ${mode === item ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"}`}
              onClick={() => setMode(item)}
            >
              {t(item === "contour" ? "contourHeatView" : item === "heat" ? "heatView" : item === "scatter" ? "scatterView" : "pathView")}
            </button>
          ))}
        </div>
      </div>
      {!hasCourt ? (
        <div className="mb-3 rounded-md bg-subtle p-3 text-sm text-muted">{t("courtMapHint")}</div>
      ) : null}
      <div className="overflow-hidden rounded-md border border-line bg-subtle p-3">
        <div className="relative grid items-center">
          {showHeat ? (
            <div className="pointer-events-none absolute left-2 top-1/2 z-10 hidden h-40 -translate-y-1/2 flex-col items-center justify-between text-[10px] font-semibold text-muted sm:flex">
              <span>{t("high")}</span>
              <div className="h-28 w-2 rounded-full bg-gradient-to-t from-[#18206f] via-[#0a84ff] via-[#2fd37b] via-[#ffe45c] via-[#ff9f0a] to-[#ff3b30]" />
              <span>{t("low")}</span>
            </div>
          ) : null}
          <svg viewBox={`0 0 ${courtWidth} ${courtLength}`} className="mx-auto block aspect-[6.1/13.4] max-h-[560px] w-full max-w-[560px]" role="img">
          {showHeat ? (
            <CourtHeatLayer
              spots={heatSpots}
              maxHeat={maxHeat}
              width={courtWidth}
              length={courtLength}
              clipId={clipId}
              blurId={blurId}
              dark={dark}
            />
          ) : showContour ? (
            <CourtContourHeatLayer
              tracks={tracks}
              width={courtWidth}
              length={courtLength}
              clipId={clipId}
              blurId={contourBlurId}
            />
          ) : (
            <rect width={courtWidth} height={courtLength} rx="0.08" fill={dark ? "#101722" : "#f2f7ff"} />
          )}
          <CourtLines width={courtWidth} length={courtLength} dark={dark || showContour} />
          <text x="-0.3" y={courtLength * 0.28} textAnchor="end" fontSize="0.28" fontWeight="700" fill={dark || showContour ? "#8d949e" : "#66727f"}>
            {t("playerB")}
          </text>
          <text x="-0.3" y={courtLength * 0.72} textAnchor="end" fontSize="0.28" fontWeight="700" fill={dark || showContour ? "#8d949e" : "#66727f"}>
            {t("playerA")}
          </text>
          {tracks.map((track) => (
            <g key={track.id}>
              {showPath ? <polyline
                points={track.displayPoints.map((point) => `${point.x},${point.y}`).join(" ")}
                fill="none"
                stroke={track.color}
                strokeWidth="0.055"
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity="0.78"
              /> : null}
              {showPoints ? track.displayPoints.map((point, index) => (
                <circle
                  key={`${track.id}-${index}`}
                  cx={point.x}
                  cy={point.y}
                  r={mode === "scatter" ? 0.045 : index === track.displayPoints.length - 1 ? 0.09 : 0.055}
                  fill={track.color}
                  opacity={mode === "scatter" ? 0.9 : 0.78}
                  className={onSeek ? "cursor-pointer outline-none transition-opacity hover:opacity-100" : undefined}
                  tabIndex={onSeek ? 0 : undefined}
                  role={onSeek ? "button" : undefined}
                  aria-label={`P${track.displayId} ${point.timestamp.toFixed(2)}s`}
                  onClick={() => onSeek?.(point.timestamp)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSeek?.(point.timestamp);
                    }
                  }}
                >
                  <title>{`P${track.displayId} · ${point.timestamp.toFixed(2)}s`}</title>
                </circle>
              )) : null}
              {showPoints && track.displayPoints[0] ? (
                <g transform={`translate(${track.displayPoints[0].x} ${track.displayPoints[0].y})`}>
                  <rect x="-0.18" y="-0.34" width="0.72" height="0.28" rx="0.06" fill={track.color} opacity="0.95" />
                  <text x="0.18" y="-0.13" textAnchor="middle" fontSize="0.18" fontWeight="700" fill="#ffffff">
                    P{track.displayId}
                  </text>
                </g>
              ) : null}
            </g>
          ))}
          </svg>
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DualMetric label={t("courtCoverage")} values={metrics.map((item) => `${Math.round(item.coverage * 100)}%`)} colors={tracks.map((track) => track.color)} />
        <DualMetric label={t("runningDistance")} values={metrics.map((item) => `${item.distance.toFixed(1)}m`)} colors={tracks.map((track) => track.color)} />
        <DualMetric label={t("avgSpeed")} values={metrics.map((item) => `${item.avgSpeed.toFixed(1)}m/s`)} colors={tracks.map((track) => track.color)} />
        <DualMetric label={t("maxSpeed")} values={metrics.map((item) => `${item.maxSpeed.toFixed(1)}m/s`)} colors={tracks.map((track) => track.color)} />
      </div>
    </div>
  );
}

function CourtHeatLayer({
  spots,
  maxHeat,
  width,
  length,
  clipId,
  blurId,
  dark
}: {
  spots: HeatSpot[];
  maxHeat: number;
  width: number;
  length: number;
  clipId: string;
  blurId: string;
  dark: boolean;
}) {
  return (
    <>
      <defs>
        <clipPath id={clipId}>
          <rect width={width} height={length} rx="0.08" />
        </clipPath>
        <filter id={blurId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="0.18" />
        </filter>
      </defs>
      <rect width={width} height={length} rx="0.08" fill={dark ? "#030b32" : "#f3f8ff"} />
      <g clipPath={`url(#${clipId})`}>
        <rect width={width} height={length} fill={dark ? "#07135f" : "#eaf3ff"} opacity={dark ? "0.96" : "0.9"} />
        <g filter={`url(#${blurId})`} style={{ mixBlendMode: dark ? "screen" : "multiply" }}>
          {spots.map((spot, index) => {
            const normalized = spot.value / maxHeat;
            return (
              <ellipse
                key={`${spot.x}-${spot.y}-${index}`}
                cx={spot.x}
                cy={spot.y}
                rx={spot.rx}
                ry={spot.ry}
                fill={heatRampColor(normalized, dark)}
                opacity={heatOpacity(normalized, dark)}
              />
            );
          })}
        </g>
      </g>
    </>
  );
}

function CourtContourHeatLayer({
  tracks,
  width,
  length,
  clipId,
  blurId
}: {
  tracks: CourtTrack[];
  width: number;
  length: number;
  clipId: string;
  blurId: string;
}) {
  const outlineLevels = [
    { min: 0.16, rxScale: 2.1, ryScale: 2, opacity: 0.07 },
    { min: 0.28, rxScale: 1.82, ryScale: 1.72, opacity: 0.09 },
    { min: 0.4, rxScale: 1.56, ryScale: 1.48, opacity: 0.12 },
    { min: 0.54, rxScale: 1.32, ryScale: 1.24, opacity: 0.16 },
    { min: 0.7, rxScale: 1.08, ryScale: 1.02, opacity: 0.22 },
    { min: 0.84, rxScale: 0.88, ryScale: 0.84, opacity: 0.28 }
  ];

  return (
    <>
      <defs>
        <clipPath id={clipId}>
          <rect width={width} height={length} rx="0.08" />
        </clipPath>
        <filter id={blurId} x="-8%" y="-8%" width="116%" height="116%">
          <feGaussianBlur stdDeviation="0.065" />
          <feComponentTransfer>
            <feFuncA type="discrete" tableValues="0 0.06 0.1 0.16 0.24 0.34 0.46 0.6" />
          </feComponentTransfer>
        </filter>
      </defs>
      <rect width={width} height={length} rx="0.08" fill="#050607" />
      <g clipPath={`url(#${clipId})`}>
        <rect width={width} height={length} fill="#020303" />
        <g filter={`url(#${blurId})`}>
          {tracks.map((track) => {
            const spots = buildContourSpots([track], width, length);
            const maxTrackHeat = Math.max(1, ...spots.map((spot) => spot.value));
            const fill = track.label === "B" ? PLAYER_B_COLOR : PLAYER_A_COLOR;
            const stroke = track.label === "B" ? "#6bb6ff" : "#ffc46b";
            return (
              <g key={`contour-${track.id}`}>
                <g filter={`url(#${blurId})`}>
                  {spots.map((spot, index) => (
                    <ellipse
                      key={`${spot.x}-${spot.y}-fill-${index}`}
                      cx={spot.x}
                      cy={spot.y}
                      rx={spot.rx * 1.12}
                      ry={spot.ry * 1.06}
                      fill={fill}
                      opacity={0.72 * Math.min(1, spot.value / maxTrackHeat + 0.18)}
                    />
                  ))}
                </g>
                {outlineLevels.map((level) => (
                  <g key={`${track.id}-${level.min}`}>
                    {spots
                      .filter((spot) => spot.value / maxTrackHeat >= level.min)
                      .map((spot, index) => (
                        <ellipse
                          key={`${spot.x}-${spot.y}-${level.min}-${index}`}
                          cx={spot.x}
                          cy={spot.y}
                          rx={spot.rx * level.rxScale}
                          ry={spot.ry * level.ryScale}
                          fill="none"
                          stroke={stroke}
                          strokeWidth="0.022"
                          opacity={level.opacity}
                        />
                      ))}
                  </g>
                ))}
              </g>
            );
          })}
        </g>
      </g>
    </>
  );
}

function CourtLines({ width, length, dark }: { width: number; length: number; dark: boolean }) {
  const line = dark ? "#d9eaff" : "#ffffff";
  const muted = dark ? "rgba(217, 234, 255, 0.62)" : "rgba(255, 255, 255, 0.86)";
  const centerX = width / 2;
  const netY = length / 2;
  const shortTop = netY - 1.98;
  const shortBottom = netY + 1.98;
  const backTop = 0.76;
  const backBottom = length - 0.76;
  const singlesLeft = 0.46;
  const singlesRight = width - 0.46;

  return (
    <g fill="none" strokeLinecap="square">
      <rect x="0" y="0" width={width} height={length} stroke={line} strokeWidth="0.045" />
      <line x1="0" y1={netY} x2={width} y2={netY} stroke="#1f2937" strokeWidth="0.065" opacity={dark ? 0.9 : 0.65} />
      <line x1="0" y1={shortTop} x2={width} y2={shortTop} stroke={line} strokeWidth="0.04" />
      <line x1="0" y1={shortBottom} x2={width} y2={shortBottom} stroke={line} strokeWidth="0.04" />
      <line x1="0" y1={backTop} x2={width} y2={backTop} stroke={muted} strokeWidth="0.035" />
      <line x1="0" y1={backBottom} x2={width} y2={backBottom} stroke={muted} strokeWidth="0.035" />
      <line x1={centerX} y1={backTop} x2={centerX} y2={shortTop} stroke={line} strokeWidth="0.035" />
      <line x1={centerX} y1={shortBottom} x2={centerX} y2={backBottom} stroke={line} strokeWidth="0.035" />
      <line x1={singlesLeft} y1="0" x2={singlesLeft} y2={length} stroke={muted} strokeWidth="0.03" />
      <line x1={singlesRight} y1="0" x2={singlesRight} y2={length} stroke={muted} strokeWidth="0.03" />
    </g>
  );
}

function DualMetric({ label, values, colors }: { label: string; values: string[]; colors: string[] }) {
  const first = values[0] ?? "-";
  const second = values[1] ?? "-";
  return (
    <div className="rounded-md border border-line bg-subtle p-3">
      <div className="grid gap-1.5">
        <div className="flex min-w-0 items-baseline justify-between gap-3">
          <span className="shrink-0 text-[11px] font-semibold text-muted">A</span>
          <span className="min-w-0 text-right text-lg font-bold leading-none tracking-normal" style={{ color: colors[0] ?? PLAYER_A_COLOR }}>
            {first}
          </span>
        </div>
        <div className="flex min-w-0 items-baseline justify-between gap-3">
          <span className="shrink-0 text-[11px] font-semibold text-muted">B</span>
          <span className="min-w-0 text-right text-lg font-bold leading-none tracking-normal" style={{ color: colors[1] ?? PLAYER_B_COLOR }}>
            {second}
          </span>
        </div>
      </div>
      <div className="mt-1 text-xs font-semibold text-muted">{label}</div>
    </div>
  );
}

function buildCourtTracks(pose: PoseOutput, limit: number): CourtTrack[] {
  if (!pose.court) return [];
  const width = pose.court.court_width_m;
  const length = pose.court.court_length_m;
  const tracks = new Map<number, { selected: boolean; points: CourtTrackPoint[] }>();

  for (const frame of pose.frames) {
    for (const person of frame.persons ?? []) {
      const trackId = person.track_id;
      const point = person.court_point;
      if (trackId === null || !point || person.in_court === false || !pointInsideCourt(point, width, length)) continue;
      const entry = tracks.get(trackId) ?? { selected: false, points: [] };
      entry.selected = entry.selected || person.selected === true || pose.primary_track_id === trackId;
      entry.points.push({ x: point[0], y: point[1], timestamp: frame.timestamp });
      tracks.set(trackId, entry);
    }
  }

  return selectPlayerTracks([...tracks.entries()], length, limit).map(([id, track], index) => ({
      id,
      displayId: index === 0 ? 1 : 2,
      label: index === 0 ? "A" : "B",
      selected: track.selected,
      points: track.points,
      displayPoints: thinPoints(track.points, 240).map((point) => displayCourtPoint(point, length)),
      color: index === 0 ? PLAYER_A_COLOR : PLAYER_B_COLOR
    }));
}

function selectPlayerTracks(
  entries: [number, { selected: boolean; points: CourtTrackPoint[] }][],
  courtLength: number,
  limit: number
) {
  const lowerHalf = entries
    .filter((entry) => averageDisplayY(entry[1].points, courtLength) >= courtLength / 2)
    .sort((a, b) => playerCandidateRank(a, 1) - playerCandidateRank(b, 1));
  const upperHalf = entries
    .filter((entry) => averageDisplayY(entry[1].points, courtLength) < courtLength / 2)
    .sort((a, b) => playerCandidateRank(a, 2) - playerCandidateRank(b, 2));
  const selected: [number, { selected: boolean; points: CourtTrackPoint[] }][] = [];
  if (lowerHalf[0]) selected.push(lowerHalf[0]);
  if (upperHalf[0] && upperHalf[0][0] !== selected[0]?.[0]) selected.push(upperHalf[0]);
  if (selected.length < limit) {
    const used = new Set(selected.map(([id]) => id));
    const fallback = entries
      .filter(([id]) => !used.has(id))
      .sort((a, b) => b[1].points.length - a[1].points.length);
    selected.push(...fallback.slice(0, limit - selected.length));
  }
  return selected.slice(0, limit);
}

function playerCandidateRank([id, track]: [number, { selected: boolean; points: CourtTrackPoint[] }], preferredId: number) {
  if (id === preferredId) return 0;
  return 1 - Math.min(track.points.length / 100000, 0.9);
}

function averageDisplayY(points: CourtTrackPoint[], courtLength: number) {
  if (!points.length) return courtLength / 2;
  return points.reduce((sum, point) => sum + (courtLength - point.y), 0) / points.length;
}

function thinPoints(points: CourtTrackPoint[], maxPoints: number): CourtTrackPoint[] {
  if (points.length <= maxPoints) return points;
  const step = Math.ceil(points.length / maxPoints);
  return points.filter((_, index) => index % step === 0);
}

function buildHeatSpots(tracks: CourtTrack[], width: number, length: number): HeatSpot[] {
  return buildDensitySpots(tracks, width, length, {
    columns: 18,
    rows: 36,
    radius: 3,
    falloff: 5.5,
    rxScale: 1.55,
    ryScale: 1.48,
    threshold: 0.12
  });
}

function buildContourSpots(tracks: CourtTrack[], width: number, length: number): HeatSpot[] {
  return buildDensitySpots(tracks, width, length, {
    columns: 26,
    rows: 52,
    radius: 4,
    falloff: 7.2,
    rxScale: 1.22,
    ryScale: 1.18,
    threshold: 0.06
  });
}

function buildDensitySpots(
  tracks: CourtTrack[],
  width: number,
  length: number,
  options: { columns: number; rows: number; radius: number; falloff: number; rxScale: number; ryScale: number; threshold: number }
): HeatSpot[] {
  const { columns, rows, radius, falloff, rxScale, ryScale, threshold } = options;
  const cellWidth = width / columns;
  const cellHeight = length / rows;
  const density = Array.from({ length: rows }, () => Array.from({ length: columns }, () => 0));
  for (const track of tracks) {
    for (const point of track.points) {
      const displayY = length - point.y;
      const column = Math.min(columns - 1, Math.max(0, Math.floor(point.x / cellWidth)));
      const row = Math.min(rows - 1, Math.max(0, Math.floor(displayY / cellHeight)));
      for (let rowOffset = -radius; rowOffset <= radius; rowOffset += 1) {
        for (let columnOffset = -radius; columnOffset <= radius; columnOffset += 1) {
          const nextRow = row + rowOffset;
          const nextColumn = column + columnOffset;
          if (nextRow < 0 || nextRow >= rows || nextColumn < 0 || nextColumn >= columns) continue;
          const distance = columnOffset * columnOffset + rowOffset * rowOffset;
          density[nextRow][nextColumn] += Math.exp(-distance / falloff);
        }
      }
    }
  }
  const maxDensity = Math.max(1, ...density.flat());
  return density.flatMap((row, rowIndex) =>
    row
      .map((value, columnIndex) => ({
        x: (columnIndex + 0.5) * cellWidth,
        y: (rowIndex + 0.5) * cellHeight,
        value,
        rx: cellWidth * rxScale,
        ry: cellHeight * ryScale
      }))
      .filter((spot) => spot.value / maxDensity > threshold)
  );
}

function buildTrackMetrics(track: CourtTrack, width: number, length: number) {
  const columns = 12;
  const rows = 24;
  const visited = new Set<string>();
  let distance = 0;
  let speedSum = 0;
  let speedCount = 0;
  let maxSpeed = 0;

  for (let index = 0; index < track.points.length; index += 1) {
    const point = track.points[index];
    const column = Math.min(columns - 1, Math.max(0, Math.floor(point.x / (width / columns))));
    const row = Math.min(rows - 1, Math.max(0, Math.floor(point.y / (length / rows))));
    visited.add(`${column}-${row}`);

    const previous = track.points[index - 1];
    if (!previous) continue;
    const dt = Math.max(0.001, point.timestamp - previous.timestamp);
    const step = Math.hypot(point.x - previous.x, point.y - previous.y);
    const speed = step / dt;
    if (speed > 8) continue;
    distance += step;
    speedSum += speed;
    speedCount += 1;
    maxSpeed = Math.max(maxSpeed, speed);
  }

  return {
    coverage: visited.size / (columns * rows),
    distance,
    avgSpeed: speedCount ? speedSum / speedCount : 0,
    maxSpeed
  };
}

function pointInsideCourt(point: [number, number], width: number, length: number) {
  return point[0] >= 0 && point[0] <= width && point[1] >= 0 && point[1] <= length;
}

function displayCourtPoint(point: CourtTrackPoint, courtLength: number): CourtTrackPoint {
  return { ...point, y: courtLength - point.y };
}

function heatRampColor(normalized: number, dark: boolean) {
  const value = Math.max(0, Math.min(1, normalized));
  if (value > 0.88) return "#ff3b30";
  if (value > 0.72) return dark ? "#ff9f0a" : "#ff8a00";
  if (value > 0.56) return dark ? "#ffe45c" : "#ffd60a";
  if (value > 0.4) return dark ? "#2fd37b" : "#30d158";
  if (value > 0.24) return dark ? "#32d7ff" : "#5ac8fa";
  if (value > 0.12) return dark ? "#0a84ff" : "#007aff";
  return dark ? "#18206f" : "#3b5bdb";
}

function heatOpacity(normalized: number, dark: boolean) {
  const value = Math.max(0, Math.min(1, normalized));
  if (value < 0.16) return dark ? 0.1 : 0.08;
  if (value < 0.3) return dark ? 0.22 : 0.18;
  if (value < 0.5) return dark ? 0.42 : 0.36;
  if (value < 0.72) return dark ? 0.62 : 0.54;
  if (value < 0.88) return dark ? 0.78 : 0.68;
  return dark ? 0.9 : 0.78;
}
