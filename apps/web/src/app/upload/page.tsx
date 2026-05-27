"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Play, UploadCloud } from "lucide-react";
import { createAnalysisJob, detectCourt, uploadVideo } from "@/lib/api";
import type { CourtPoint, Roi, VideoRecord } from "@/lib/types";
import { CourtCalibrationPicker } from "@/components/CourtCalibrationPicker";
import { RoiPicker } from "@/components/RoiPicker";
import { usePreferences } from "@/components/PreferencesProvider";

export default function UploadPage() {
  const router = useRouter();
  const { language, t } = usePreferences();
  const [file, setFile] = useState<File | null>(null);
  const [video, setVideo] = useState<VideoRecord | null>(null);
  const [roi, setRoi] = useState<Roi | null>(null);
  const [courtPoints, setCourtPoints] = useState<CourtPoint[]>([]);
  const [mock, setMock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [detectingCourt, setDetectingCourt] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const uploaded = await uploadVideo(file);
      setVideo(uploaded);
      await handleDetectCourt(uploaded.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleDetectCourt(videoId = video?.id) {
    if (!videoId) return;
    setDetectingCourt(true);
    setError(null);
    try {
      const result = await detectCourt(videoId);
      if (result.points.length === 4) {
        setCourtPoints(result.points);
      } else {
        setError(t("courtDetectFailed"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("courtDetectFailed"));
    } finally {
      setDetectingCourt(false);
    }
  }

  async function handleAnalyze() {
    if (!video) return;
    setBusy(true);
    setError(null);
    try {
      const job = await createAnalysisJob(video.id, mock, roi, language, courtPoints);
      router.push(`/analysis/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analyze failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink">{t("uploadTitle")}</h1>
          <p className="mt-1 text-sm text-muted">{t("uploadDescription")}</p>
        </div>
      </header>

      <section className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-md border border-line bg-surface p-5 shadow-soft">
          <label className="flex min-h-80 cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-line bg-subtle px-6 text-center transition hover:border-court">
            <UploadCloud className="mb-4 text-court" size={42} />
            <span className="text-base font-semibold text-ink">{file ? file.name : t("chooseVideo")}</span>
            <span className="mt-2 text-sm text-muted">{t("videoFormats")}</span>
            <input
              className="hidden"
              type="file"
              accept="video/*"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <div className="mt-5 flex items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={mock} onChange={(event) => setMock(event.target.checked)} />
              {t("mockAnalysis")}
            </label>
            <div className="flex gap-3">
              <button
                className="focus-ring rounded-md border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink hover:bg-subtle disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!file || busy}
                onClick={handleUpload}
              >
                {busy && !video ? t("uploading") : t("uploadAction")}
              </button>
              <button
                className="focus-ring inline-flex items-center gap-2 rounded-md bg-court px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!video || busy}
                onClick={handleAnalyze}
              >
                <Play size={16} />
                {busy && video ? t("creating") : t("analyze")}
              </button>
            </div>
          </div>
          <CourtCalibrationPicker
            file={file}
            points={courtPoints}
            detecting={detectingCourt}
            onAutoDetect={() => handleDetectCourt()}
            onChange={setCourtPoints}
          />
          <RoiPicker file={file} roi={roi} onChange={setRoi} />
          {error ? <div className="mt-4 rounded-md bg-danger/10 p-3 text-sm text-danger">{error}</div> : null}
        </div>

        <aside className="rounded-md border border-line bg-surface p-5 shadow-soft">
          <h2 className="text-base font-semibold text-ink">{t("currentVideo")}</h2>
          {video ? (
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="text-muted">{t("file")}</dt>
                <dd className="font-medium text-ink">{video.original_filename}</dd>
              </div>
              <div>
                <dt className="text-muted">{t("videoId")}</dt>
                <dd className="break-all font-mono text-xs text-muted">{video.id}</dd>
              </div>
              <div>
                <dt className="text-muted">{t("size")}</dt>
                <dd className="text-ink">{(video.size_bytes / 1024 / 1024).toFixed(2)} MB</dd>
              </div>
            </dl>
          ) : (
            <div className="mt-4 rounded-md bg-subtle p-4 text-sm text-muted">{t("noVideo")}</div>
          )}
        </aside>
      </section>
    </div>
  );
}
