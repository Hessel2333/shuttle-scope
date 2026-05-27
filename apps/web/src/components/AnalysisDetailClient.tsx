"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, RefreshCw } from "lucide-react";
import { getJob, getPose, getShuttle, getSummary, rerunShuttle, videoUrl } from "@/lib/api";
import type { I18nKey } from "@/lib/i18n";
import type { JobRecord, PoseOutput, ShuttleOutput, SummaryOutput } from "@/lib/types";
import { CourtMovementMap } from "@/components/AnalysisCharts";
import { MetricTile } from "@/components/MetricTile";
import { SkeletonOverlay } from "@/components/SkeletonOverlay";
import { StatusBadge } from "@/components/StatusBadge";
import { usePreferences } from "@/components/PreferencesProvider";

export function AnalysisDetailClient({ jobId }: { jobId: string }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [job, setJob] = useState<JobRecord | null>(null);
  const [pose, setPose] = useState<PoseOutput | null>(null);
  const [summary, setSummary] = useState<SummaryOutput | null>(null);
  const [shuttle, setShuttle] = useState<ShuttleOutput | null>(null);
  const [showAllPersons, setShowAllPersons] = useState(false);
  const [showCourtOverlay, setShowCourtOverlay] = useState(true);
  const [showPersonOverlay, setShowPersonOverlay] = useState(true);
  const [showShuttleOverlay, setShowShuttleOverlay] = useState(true);
  const { t } = usePreferences();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rerunningShuttle, setRerunningShuttle] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const nextJob = await getJob(jobId);
      setJob(nextJob);
      if (nextJob.status === "completed") {
        const [nextPose, nextSummary] = await Promise.all([getPose(nextJob.id), getSummary(nextJob.id)]);
        setPose(nextPose);
        setSummary(nextSummary);
        getShuttle(nextJob.id).then(setShuttle).catch(() => setShuttle(null));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadAnalysisFailed"));
    } finally {
      setLoading(false);
    }
  }, [jobId, t]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  const seekVideo = useCallback((timestamp: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, timestamp);
    video.pause();
    video.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const handleRerunShuttle = useCallback(async () => {
    if (!job) return;
    setRerunningShuttle(true);
    setError(null);
    try {
      const nextJob = await rerunShuttle(job.id);
      setJob(nextJob);
      setShuttle(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadAnalysisFailed"));
    } finally {
      setRerunningShuttle(false);
    }
  }, [job, load, t]);

  return (
    <div>
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink">{t("analysisTitle")}</h1>
          <p className="mt-1 text-sm text-muted">{job?.original_filename || t("loadingAnalysis")}</p>
        </div>
        <div className="flex items-center gap-3">
          {job ? <StatusBadge status={job.status} /> : null}
          <button className="focus-ring inline-flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm font-semibold" onClick={load}>
            <RefreshCw size={16} />
            {t("refresh")}
          </button>
        </div>
      </header>

      {loading ? <div className="rounded-md border border-line bg-surface p-6 text-sm text-muted shadow-soft">{t("loadingAnalysis")}</div> : null}
      {error ? <div className="mb-4 rounded-md bg-danger/10 p-3 text-sm text-danger">{error}</div> : null}

      {job ? <PhaseProgressPanel job={job} onRerunShuttle={handleRerunShuttle} rerunningShuttle={rerunningShuttle} /> : null}

      {job && pose && summary ? (
        <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(390px,0.75fr)]">
          <section className="rounded-md border border-line bg-surface p-4 shadow-soft">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm font-semibold text-ink">{t("poseOverlay")}</div>
              <div className="flex flex-wrap items-center gap-3">
                <OverlayToggle label={t("showCourtOverlay")} checked={showCourtOverlay} onChange={setShowCourtOverlay} />
                <OverlayToggle label={t("showPersonOverlay")} checked={showPersonOverlay} onChange={setShowPersonOverlay} />
                <OverlayToggle label={t("showShuttleOverlay")} checked={showShuttleOverlay} onChange={setShowShuttleOverlay} />
                <OverlayToggle label={t("showAllPlayers")} checked={showAllPersons} onChange={setShowAllPersons} disabled={!showPersonOverlay} />
              </div>
            </div>
            <div className="relative overflow-hidden rounded-md bg-black">
              <video ref={videoRef} className="aspect-video w-full" src={videoUrl(job.video_id)} controls preload="metadata" />
              <SkeletonOverlay
                videoRef={videoRef}
                pose={pose}
                shuttle={shuttle}
                showAllPersons={showAllPersons}
                showCourtOverlay={showCourtOverlay}
                showPersonOverlay={showPersonOverlay}
                showShuttleOverlay={showShuttleOverlay}
              />
            </div>
            {summary.analysis.fallback_error ? (
              <div className="mt-3 flex gap-2 rounded-md bg-accent/15 p-3 text-sm text-ink">
                <AlertCircle className="mt-0.5 shrink-0" size={16} />
                <span>{t("fallbackPrefix")}{summary.analysis.fallback_error}</span>
              </div>
            ) : null}
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <MetricTile label={t("duration")} value={`${summary.duration_sec}s`} hint={`${summary.fps_sampled} ${t("fpsSampled")}`} />
              <MetricTile label={t("detectedFrames")} value={`${summary.detected_frames}/${summary.sampled_frames}`} />
              <MetricTile label={t("avgConfidence")} value={`${Math.round(summary.avg_confidence * 100)}%`} />
              <MetricTile label={t("shuttleFrames")} value={shuttle ? `${shuttle.detected_frames}/${shuttle.frames.length}` : "-"} />
              <MetricTile
                label={t("movement")}
                value={`${summary.estimated_movement_px.toFixed(summary.movement_unit === "m" ? 1 : 0)} ${summary.movement_unit ?? "px"}`}
                hint={`${summary.avg_speed_px_s.toFixed(summary.avg_speed_unit === "m/s" ? 2 : 1)} ${summary.avg_speed_unit ?? "px/s"} ${t("average")}`}
              />
              <MetricTile label={t("inference")} value={summary.analysis.device} hint={`${summary.analysis.model_name} · ${summary.analysis.mode}`} />
              <MetricTile
                label={t("players")}
                value={`${summary.analysis.track_count ?? 0}`}
                hint={`${t("maxPerFrame")} ${summary.analysis.max_persons_per_frame ?? 0}`}
              />
            </div>
          </section>

          <aside className="grid gap-4">
            <section className="rounded-md border border-line bg-surface p-4 shadow-soft">
              <h2 className="mb-3 text-base font-semibold text-ink">{t("courtMovementMap")}</h2>
              <CourtMovementMap pose={pose} onSeek={seekVideo} />
            </section>
          </aside>

          <section className="rounded-md border border-line bg-surface p-5 shadow-soft xl:col-span-2">
            <h2 className="text-base font-semibold text-ink">{t("report")}</h2>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <ReportBlock title={t("overall")} text={summary.report.overall} />
              <ReportBlock title={t("movement")} text={summary.report.movement} />
              <ReportBlock title={t("positioning")} text={summary.report.positioning} />
              <ReportBlock title={t("videoQuality")} text={summary.report.video_quality} />
            </div>
            <div className="mt-5">
              <h3 className="text-sm font-semibold text-ink">{t("nextSteps")}</h3>
              <ul className="mt-2 grid gap-2 text-sm text-muted">
                {summary.report.next_steps.map((step) => (
                  <li key={step} className="rounded-md bg-subtle p-3">
                    {step}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </div>
      ) : null}

      {!loading && !job ? (
        <div className="rounded-md border border-line bg-surface p-6 text-sm text-muted shadow-soft">
          {t("notFoundJob")} <Link className="font-semibold text-court" href="/jobs">{t("returnJobs")}</Link>
        </div>
      ) : null}
    </div>
  );
}

function PhaseProgressPanel({
  job,
  rerunningShuttle,
  onRerunShuttle
}: {
  job: JobRecord;
  rerunningShuttle: boolean;
  onRerunShuttle: () => void;
}) {
  const { t } = usePreferences();
  const poseProgress = job.pose_progress ?? job.progress ?? 0;
  const shuttleProgress = job.shuttle_progress ?? (job.shuttle_path ? 100 : 0);
  const poseStatus = job.pose_status ?? job.status;
  const shuttleStatus = job.shuttle_status ?? "queued";

  return (
    <section className="rounded-md border border-line bg-surface p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">{t("phaseProgress")}</h2>
        <div className="flex items-center gap-3">
          {job.error ? <span className="text-xs text-danger">{job.error}</span> : null}
          {job.status === "completed" ? (
            <button
              className="focus-ring rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
              disabled={rerunningShuttle || job.shuttle_status === "running" || job.shuttle_status === "waiting"}
              type="button"
              onClick={onRerunShuttle}
            >
              {rerunningShuttle ? t("rerunningShuttle") : t("rerunShuttle")}
            </button>
          ) : null}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <PhaseProgressBar
          label={t("poseProgress")}
          progress={poseProgress}
          status={translatePhaseStatus(poseStatus, t)}
          tone="pose"
          error={job.pose_error}
        />
        <PhaseProgressBar
          label={t("shuttleProgress")}
          progress={shuttleProgress}
          status={translatePhaseStatus(shuttleStatus, t)}
          tone="shuttle"
          error={job.shuttle_error}
        />
      </div>
    </section>
  );
}

function PhaseProgressBar({
  label,
  progress,
  status,
  tone,
  error
}: {
  label: string;
  progress: number;
  status: string;
  tone: "pose" | "shuttle";
  error?: string | null;
}) {
  const clamped = Math.min(100, Math.max(0, Math.round(progress || 0)));
  const color = tone === "pose" ? "bg-court" : "bg-sky-400";

  return (
    <div className="rounded-md bg-subtle p-4">
      <div className="mb-3 flex items-center justify-between gap-3 text-sm">
        <div>
          <div className="font-semibold text-ink">{label}</div>
          <div className="mt-1 text-xs text-muted">{status}</div>
        </div>
        <div className="text-lg font-semibold text-ink tabular-nums">{clamped}%</div>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line">
        <div className={`h-full ${color}`} style={{ width: `${clamped}%` }} />
      </div>
      {error ? <div className="mt-3 rounded-md bg-danger/10 p-2 text-xs text-danger">{error}</div> : null}
    </div>
  );
}

function translatePhaseStatus(status: string | null | undefined, t: (key: I18nKey) => string) {
  switch (status) {
    case "queued":
      return t("statusQueued");
    case "running":
      return t("statusRunning");
    case "waiting":
      return t("statusWaiting");
    case "completed":
      return t("statusCompleted");
    case "failed":
      return t("statusFailed");
    case "skipped":
      return t("statusSkipped");
    default:
      return status || t("statusQueued");
  }
}

function OverlayToggle({
  label,
  checked,
  disabled,
  onChange
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className={`flex items-center gap-2 text-xs font-medium ${disabled ? "text-muted opacity-45" : "text-muted"}`}>
      <input
        className="h-4 w-4 accent-court"
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}

function ReportBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-md bg-subtle p-4">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted">{text}</p>
    </div>
  );
}
