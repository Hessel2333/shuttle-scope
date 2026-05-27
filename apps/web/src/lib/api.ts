import type { AnalysisSettings, CourtPoint, Health, JobRecord, PoseOutput, Roi, ShuttleOutput, SummaryOutput, VideoRecord } from "@/lib/types";
import type { Language } from "@/lib/i18n";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers
    }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function getHealth(): Promise<Health> {
  return request<Health>("/api/health", { cache: "no-store" });
}

export async function getAnalysisSettings(): Promise<AnalysisSettings> {
  return request<AnalysisSettings>("/api/settings/analysis", { cache: "no-store" });
}

export async function updateAnalysisSettings(settings: Partial<AnalysisSettings>): Promise<AnalysisSettings> {
  return request<AnalysisSettings>("/api/settings/analysis", {
    method: "PATCH",
    body: JSON.stringify(settings)
  });
}

export async function uploadVideo(file: File): Promise<VideoRecord> {
  const body = new FormData();
  body.append("file", file);
  const result = await request<{ video: VideoRecord }>("/api/videos/upload", {
    method: "POST",
    body
  });
  return result.video;
}

export async function detectCourt(videoId: string): Promise<{ points: CourtPoint[]; confidence: number; method: string; message: string }> {
  return request<{ points: CourtPoint[]; confidence: number; method: string; message: string }>(`/api/videos/${videoId}/detect-court`, {
    method: "POST"
  });
}

export async function createAnalysisJob(
  videoId: string,
  mock = false,
  roi?: Roi | null,
  locale?: Language,
  courtPoints?: CourtPoint[] | null
): Promise<JobRecord> {
  const result = await request<{ job: JobRecord }>(`/api/jobs/${videoId}/analyze`, {
    method: "POST",
    body: JSON.stringify({ mock, roi, locale, court_points: courtPoints?.length === 4 ? courtPoints : null })
  });
  return result.job;
}

export async function listJobs(): Promise<JobRecord[]> {
  return request<JobRecord[]>("/api/jobs", { cache: "no-store" });
}

export async function deleteJob(jobId: string): Promise<{ deleted: number; job_ids: string[] }> {
  return request<{ deleted: number; job_ids: string[] }>(`/api/jobs/${jobId}`, {
    method: "DELETE"
  });
}

export async function deleteJobs(jobIds: string[]): Promise<{ deleted: number; job_ids: string[] }> {
  return request<{ deleted: number; job_ids: string[] }>("/api/jobs/delete", {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds })
  });
}

export async function getJob(jobId: string): Promise<JobRecord> {
  return request<JobRecord>(`/api/jobs/${jobId}`, { cache: "no-store" });
}

export async function rerunShuttle(jobId: string): Promise<JobRecord> {
  const result = await request<{ job: JobRecord }>(`/api/jobs/${jobId}/analyze-shuttle`, {
    method: "POST"
  });
  return result.job;
}

export async function getPose(jobId: string): Promise<PoseOutput> {
  return request<PoseOutput>(`/api/outputs/${jobId}/pose`, { cache: "no-store" });
}

export async function getSummary(jobId: string): Promise<SummaryOutput> {
  return request<SummaryOutput>(`/api/outputs/${jobId}/summary`, { cache: "no-store" });
}

export async function getShuttle(jobId: string): Promise<ShuttleOutput> {
  return request<ShuttleOutput>(`/api/outputs/${jobId}/shuttle`, { cache: "no-store" });
}

export function videoUrl(videoId: string): string {
  return `${API_BASE}/api/videos/${videoId}/file`;
}
