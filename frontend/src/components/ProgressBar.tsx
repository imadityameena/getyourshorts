import { Check, Loader2 } from "lucide-react";
import { STAGES, stageIndex, stageLabel } from "../lib/format";

interface Props {
  stage: string;
  status: string;
  progress: number;
}

export function ProgressBar({ stage, status, progress }: Props) {
  const current = stageIndex(stage, status);
  const failed = status === "failed" || status === "cancelled";
  const pct = Math.max(2, Math.min(100, progress));

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <p className="font-medium" aria-live="polite">
          {stageLabel(stage, status)}
        </p>
        <span className="tabular-nums text-sm text-ink-400">{progress}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
        aria-label="Job progress"
        className="h-2.5 overflow-hidden rounded-full bg-ink-800"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${
            failed ? "bg-ink-600" : "bg-gradient-to-r from-brand-500 to-brand-400"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <ol className="mt-5 grid grid-cols-3 gap-y-3 sm:grid-cols-6">
        {STAGES.map((s, i) => {
          const done = i < current;
          const active = i === current && !failed && status !== "queued";
          return (
            <li key={s.key} className="flex items-center gap-2 text-xs sm:flex-col sm:text-center">
              <span
                className={`grid size-6 shrink-0 place-items-center rounded-full border ${
                  done
                    ? "border-ok-400 bg-ok-400/15 text-ok-400"
                    : active
                      ? "border-brand-400 text-brand-400"
                      : "border-ink-700 text-ink-600"
                }`}
                aria-hidden
              >
                {done ? (
                  <Check className="size-3.5" />
                ) : active ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <span className="size-1.5 rounded-full bg-current" />
                )}
              </span>
              <span className={done || active ? "text-ink-100" : "text-ink-400"}>{s.label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
