export const STAGES = [
  { key: "downloading", label: "Downloading" },
  { key: "transcribing", label: "Transcribing" },
  { key: "analyzing", label: "Analyzing" },
  { key: "selecting", label: "Selecting" },
  { key: "rendering", label: "Rendering" },
  { key: "packaging", label: "Packaging" },
] as const;

export type StageKey = (typeof STAGES)[number]["key"];

/** Index of the current stage in STAGES; -1 before start, STAGES.length when done. */
export function stageIndex(stage: string, status: string): number {
  if (status === "done") return STAGES.length;
  const i = STAGES.findIndex((s) => s.key === stage);
  return i;
}

export function stageLabel(stage: string, status: string): string {
  if (status === "queued") return stage === "resuming" ? "Resuming…" : "Waiting in queue…";
  if (status === "done") return "Done";
  if (status === "failed") return "Failed";
  if (status === "cancelled") return "Cancelled";
  if (stage === "retrying") return "Retrying after an error…";
  const s = STAGES.find((x) => x.key === stage);
  return s ? `${s.label}…` : "Starting…";
}

/** 75.4 → "1:15" */
export function formatTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** 0.734 → 73 */
export function scorePercent(score: number): number {
  return Math.round(Math.min(1, Math.max(0, score)) * 100);
}

export const SIGNAL_LABELS: Record<string, string> = {
  heatmap: "Most replayed",
  ai_virality: "AI virality",
  hook: "Hook strength",
  audio: "Audio energy",
  pace: "Speech pace",
  visual: "Visual change",
};
