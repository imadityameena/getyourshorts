/** Typed client for the FastAPI backend. Mirrors backend/app/api/schemas.py. */

export type CropMode = "face" | "center" | "blur";
export type CaptionStyle = "bold" | "neon" | "minimal" | "none";
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export interface JobSettings {
  num_clips: number;
  min_len: number;
  max_len: number;
  crop_mode: CropMode;
  caption_style: CaptionStyle;
}

export interface CreateJobRequest extends JobSettings {
  url: string;
}

export interface JobCreated {
  job_id: string;
  cached: boolean;
}

export interface Job {
  id: string;
  video_id: string;
  url: string;
  status: JobStatus;
  stage: string;
  progress: number;
  error: string | null;
  video_title: string | null;
  ai_provider: string | null;
  settings: Partial<JobSettings>;
  created_at: string;
  finished_at: string | null;
}

export interface ScoreBreakdown {
  heatmap: number | null;
  ai_virality: number | null;
  hook: number | null;
  audio: number;
  pace: number;
  visual: number;
  weights: Record<string, number>;
}

export interface Clip {
  id: string;
  rank: number;
  start: number;
  end: number;
  duration: number;
  score: number;
  score_breakdown: ScoreBreakdown;
  title: string;
  hook: string;
  reason: string;
  ai_ranked: boolean;
  file_url: string;
  thumb_url: string;
}

export interface Health {
  status: "ok" | "degraded" | "error";
  ffmpeg: boolean;
  nvenc: boolean;
  disk_free_gb: number;
  ai_providers: Record<string, boolean>;
  gpu: boolean;
}

export const TERMINAL: readonly JobStatus[] = ["done", "failed", "cancelled"];

const BASE: string = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI returns {detail: string} or {detail: [{msg, loc}]} for validation errors. */
export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length > 0) {
      const first = d[0] as { msg?: unknown };
      if (typeof first.msg === "string") return first.msg.replace(/^Value error, /, "");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Can't reach the server. Is the backend running?", 0);
  }
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    throw new ApiError(errorMessage(body, `Request failed (${res.status})`), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  createJob: (body: CreateJobRequest) =>
    request<JobCreated>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  getJob: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  getClips: (id: string) => request<Clip[]>(`/api/jobs/${encodeURIComponent(id)}/clips`),
  cancelJob: (id: string) =>
    request<void>(`/api/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  health: () => request<Health>("/api/health"),
  eventsUrl: (id: string) => apiUrl(`/api/jobs/${encodeURIComponent(id)}/events`),
  zipUrl: (id: string) => apiUrl(`/api/jobs/${encodeURIComponent(id)}/zip`),
  fileUrl: (clip: Clip, download = false) =>
    apiUrl(clip.file_url + (download ? "?download=true" : "")),
  thumbUrl: (clip: Clip) => apiUrl(clip.thumb_url),
};

/** Quick client-side check so obvious typos fail before a round trip. */
export function looksLikeYouTubeUrl(input: string): boolean {
  const s = input.trim();
  return /^(https?:\/\/)?((www|m|music)\.)?(youtube\.com\/(watch\?.*v=|shorts\/|live\/|embed\/)|youtu\.be\/)[\w-]{11}/.test(
    s,
  );
}
