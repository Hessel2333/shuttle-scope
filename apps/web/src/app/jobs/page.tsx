"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { deleteJob, deleteJobs, listJobs } from "@/lib/api";
import type { JobRecord } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePreferences } from "@/components/PreferencesProvider";

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const { t } = usePreferences();
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const nextJobs = await listJobs();
      setJobs(nextJobs);
      setSelected((current) => {
        const validIds = new Set(nextJobs.map((job) => job.id));
        return new Set([...current].filter((id) => validIds.has(id)));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadJobsFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  const deletableJobs = jobs.filter((job) => job.status !== "running" && job.status !== "queued");
  const selectedDeletableIds = [...selected].filter((id) => deletableJobs.some((job) => job.id === id));
  const allSelected = deletableJobs.length > 0 && deletableJobs.every((job) => selected.has(job.id));

  function toggleJob(job: JobRecord) {
    if (job.status === "running" || job.status === "queued") {
      setError(t("cannotDeleteRunning"));
      return;
    }
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(job.id)) next.delete(job.id);
      else next.add(job.id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((current) => {
      if (allSelected) {
        const next = new Set(current);
        for (const job of deletableJobs) next.delete(job.id);
        return next;
      }
      return new Set([...current, ...deletableJobs.map((job) => job.id)]);
    });
  }

  async function handleDeleteJob(job: JobRecord) {
    if (job.status === "running" || job.status === "queued") {
      setError(t("cannotDeleteRunning"));
      return;
    }
    if (!window.confirm(t("confirmDeleteJob"))) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteJob(job.id);
      setSelected((current) => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("deleteFailed"));
    } finally {
      setDeleting(false);
    }
  }

  async function handleBulkDelete() {
    if (!selectedDeletableIds.length) return;
    if (!window.confirm(t("confirmDeleteJobs"))) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteJobs(selectedDeletableIds);
      setSelected(new Set());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("deleteFailed"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink">{t("jobsTitle")}</h1>
          <p className="mt-1 text-sm text-muted">{t("jobsDescription")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="focus-ring inline-flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!selectedDeletableIds.length || deleting}
            onClick={handleBulkDelete}
          >
            <Trash2 size={16} />
            {t("deleteSelected")} · {selectedDeletableIds.length} {t("selectedCount")}
          </button>
          <button className="focus-ring inline-flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm font-semibold" onClick={load}>
            <RefreshCw size={16} />
            {t("refresh")}
          </button>
        </div>
      </header>

      <div className="rounded-md border border-line bg-surface shadow-soft">
        {loading ? <div className="p-6 text-sm text-muted">{t("loadingJobs")}</div> : null}
        {error ? <div className="m-4 rounded-md bg-danger/10 p-3 text-sm text-danger">{error}</div> : null}
        {!loading && !error && jobs.length === 0 ? <div className="p-6 text-sm text-muted">{t("emptyJobs")}</div> : null}
        {jobs.length > 0 ? (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line bg-subtle text-left text-xs uppercase text-muted">
                <th className="w-12 px-4 py-3">
                  <input type="checkbox" checked={allSelected} disabled={!deletableJobs.length} onChange={toggleAll} aria-label={t("selectAllJobs")} />
                </th>
                <th className="px-4 py-3">{t("video")}</th>
                <th className="px-4 py-3">{t("status")}</th>
                <th className="px-4 py-3">{t("progress")}</th>
                <th className="px-4 py-3">{t("created")}</th>
                <th className="px-4 py-3 text-right">{t("action")}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(job.id)}
                      disabled={job.status === "running" || job.status === "queued"}
                      onChange={() => toggleJob(job)}
                      aria-label={`Select job ${job.id}`}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{job.original_filename || job.video_id}</div>
                    <div className="font-mono text-xs text-muted">{job.id}</div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-4 py-3">
                    <JobPhaseProgress job={job} />
                  </td>
                  <td className="px-4 py-3 text-muted">{new Date(job.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <Link className="mr-4 font-semibold text-court hover:underline" href={`/analysis/${job.id}`}>
                      {t("open")}
                    </Link>
                    <button
                      className="font-semibold text-danger hover:underline disabled:cursor-not-allowed disabled:opacity-45"
                      disabled={deleting || job.status === "running" || job.status === "queued"}
                      onClick={() => handleDeleteJob(job)}
                    >
                      {t("delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  );
}

function JobPhaseProgress({ job }: { job: JobRecord }) {
  const { t } = usePreferences();
  const poseProgress = job.pose_progress ?? job.progress ?? 0;
  const shuttleProgress = job.shuttle_progress ?? (job.shuttle_path ? 100 : 0);
  return (
    <div className="grid w-44 gap-2">
      <MiniProgress label={t("poseProgress")} progress={poseProgress} tone="pose" />
      <MiniProgress label={t("shuttleProgress")} progress={shuttleProgress} tone="shuttle" />
    </div>
  );
}

function MiniProgress({ label, progress, tone }: { label: string; progress: number; tone: "pose" | "shuttle" }) {
  const clamped = Math.min(100, Math.max(0, Math.round(progress || 0)));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[11px] text-muted">
        <span>{label}</span>
        <span className="tabular-nums">{clamped}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-subtle">
        <div className={`h-full ${tone === "pose" ? "bg-court" : "bg-sky-400"}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}
