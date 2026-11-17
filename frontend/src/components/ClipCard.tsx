import { Check, ChevronDown, Copy, Download, Sparkles } from "lucide-react";
import { useState } from "react";
import { api, type Clip } from "../lib/api";
import { SIGNAL_LABELS, formatTime, scorePercent } from "../lib/format";

interface Props {
  clip: Clip;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <button
      type="button"
      onClick={copy}
      className="shrink-0 rounded-lg p-1.5 text-ink-400 hover:bg-ink-800 hover:text-ink-100"
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
    >
      {copied ? <Check className="size-4 text-ok-400" /> : <Copy className="size-4" />}
    </button>
  );
}

export function ScoreBreakdownBars({ clip }: Props) {
  const b = clip.score_breakdown;
  const rows = (["heatmap", "ai_virality", "hook", "audio", "pace", "visual"] as const).map((k) => ({
    key: k,
    value: b[k],
    weight: b.weights[k] ?? 0,
  }));
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-2 text-xs">
          <span className="text-ink-300">{SIGNAL_LABELS[r.key]}</span>
          {r.value === null ? (
            <span className="text-ink-400 italic">not available</span>
          ) : (
            <span className="h-1.5 overflow-hidden rounded-full bg-ink-800">
              <span
                className="block h-full rounded-full bg-brand-400"
                style={{ width: `${scorePercent(r.value)}%` }}
              />
            </span>
          )}
          <span className="text-right tabular-nums text-ink-400" title="Weight in the final score">
            {Math.round(r.weight * 100)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export function ClipCard({ clip }: Props) {
  const [open, setOpen] = useState(false);
  const pct = scorePercent(clip.score);

  return (
    <article className="card flex flex-col overflow-hidden">
      <div className="relative bg-black">
        <video
          className="aspect-[9/16] w-full object-cover"
          src={api.fileUrl(clip)}
          poster={api.thumbUrl(clip)}
          controls
          preload="none"
          playsInline
        />
        <span className="pointer-events-none absolute top-3 left-3 rounded-lg bg-black/70 px-2 py-1 font-display text-sm font-extrabold backdrop-blur">
          #{clip.rank}
        </span>
        <span
          className="pointer-events-none absolute top-3 right-3 rounded-lg bg-black/70 px-2 py-1 text-sm font-semibold tabular-nums backdrop-blur"
          title="Overall score"
        >
          {pct}
          <span className="text-ink-400">/100</span>
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start gap-2">
          <h3 className="flex-1 font-display text-base leading-snug font-bold">{clip.title}</h3>
          <CopyButton text={clip.title} label="Copy title" />
        </div>

        {clip.hook && (
          <p className="rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm">
            <span className="label mr-2">Hook</span>
            {clip.hook}
          </p>
        )}

        <p className="text-sm text-ink-300">{clip.reason}</p>

        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-400">
          <span className="tabular-nums">
            {formatTime(clip.start)} – {formatTime(clip.end)}
          </span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">{Math.round(clip.duration)}s</span>
          {clip.ai_ranked ? (
            <span className="ml-auto inline-flex items-center gap-1 text-ink-300">
              <Sparkles className="size-3.5" aria-hidden /> AI ranked
            </span>
          ) : (
            <span className="ml-auto rounded-md bg-warn-400/10 px-1.5 py-0.5 text-warn-400">
              AI ranking unavailable
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex items-center gap-1 self-start text-xs font-medium text-ink-400 hover:text-ink-100"
        >
          Why this score
          <ChevronDown className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {open && <ScoreBreakdownBars clip={clip} />}

        <a href={api.fileUrl(clip, true)} download className="btn-primary mt-auto">
          <Download className="size-4" aria-hidden />
          Download
        </a>
      </div>
    </article>
  );
}
