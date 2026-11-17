import type { CaptionStyle, CropMode, JobSettings } from "../lib/api";

interface Props {
  value: JobSettings;
  onChange: (value: JobSettings) => void;
  disabled?: boolean;
}

export const DEFAULT_SETTINGS: JobSettings = {
  num_clips: 5,
  min_len: 30,
  max_len: 60,
  crop_mode: "face",
  caption_style: "bold",
};

const LENGTH_PRESETS: { label: string; min: number; max: number }[] = [
  { label: "15–30s", min: 15, max: 30 },
  { label: "30–60s", min: 30, max: 60 },
  { label: "45–90s", min: 45, max: 90 },
];

const CROP_MODES: { value: CropMode; label: string; hint: string }[] = [
  { value: "face", label: "Face track", hint: "Follows the speaker" },
  { value: "center", label: "Center", hint: "Fixed middle crop" },
  { value: "blur", label: "Blurred fill", hint: "Whole frame, blurred bars" },
];

const CAPTION_STYLES: { value: CaptionStyle; label: string; preview: React.ReactNode }[] = [
  {
    value: "bold",
    label: "Bold",
    preview: (
      <>
        WATCH <span className="text-[#00e5ff]">THIS</span>
      </>
    ),
  },
  {
    value: "neon",
    label: "Neon",
    preview: (
      <>
        WATCH <span className="text-[#39ff14]">THIS</span>
      </>
    ),
  },
  { value: "minimal", label: "Minimal", preview: <>Watch this</> },
  { value: "none", label: "None", preview: <span className="text-ink-400">—</span> },
];

/** Keep min ≤ max with at least 5 s between them (the API enforces the same rule). */
export function clampLengths(min: number, max: number, changed: "min" | "max"): [number, number] {
  const clamp = (v: number, lo: number, hi: number) =>
    Math.min(hi, Math.max(lo, Number.isFinite(v) ? Math.round(v) : lo));
  const lo = clamp(min, 15, 85);
  const hi = clamp(max, 20, 90);
  if (hi - lo >= 5) return [lo, hi];
  // Move the *other* bound so the value the user just typed is respected.
  return changed === "min" ? [lo, lo + 5] : [hi - 5, hi];
}

function Segmented<T extends string>({
  name,
  options,
  value,
  onChange,
  disabled,
  render,
}: {
  name: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
  render?: (o: { value: T; label: string }) => React.ReactNode;
}) {
  return (
    <div role="radiogroup" aria-label={name} className="grid auto-cols-fr grid-flow-col gap-2">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(o.value)}
            className={`rounded-xl border px-2 py-2.5 text-center text-sm transition-colors ${
              active
                ? "border-brand-500 bg-brand-500/10 text-ink-100"
                : "border-ink-700 bg-ink-850 text-ink-300 hover:border-ink-600"
            }`}
          >
            {render ? render(o) : o.label}
          </button>
        );
      })}
    </div>
  );
}

export function SettingsPanel({ value, onChange, disabled }: Props) {
  const set = (patch: Partial<JobSettings>) => onChange({ ...value, ...patch });
  const presetActive = (p: { min: number; max: number }) =>
    p.min === value.min_len && p.max === value.max_len;

  return (
    <fieldset disabled={disabled} className="grid gap-6 sm:grid-cols-2">
      <legend className="sr-only">Clip settings</legend>

      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <label htmlFor="num-clips" className="label">
            Number of clips
          </label>
          <span className="font-display text-lg font-bold">{value.num_clips}</span>
        </div>
        <input
          id="num-clips"
          type="range"
          min={1}
          max={10}
          value={value.num_clips}
          onChange={(e) => set({ num_clips: Number(e.target.value) })}
          className="w-full"
        />
      </div>

      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="label">Clip length</span>
          <span className="text-sm text-ink-300">
            {value.min_len}–{value.max_len}s
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {LENGTH_PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              aria-pressed={presetActive(p)}
              onClick={() => set({ min_len: p.min, max_len: p.max })}
              className={`rounded-xl border px-2 py-2 text-sm transition-colors ${
                presetActive(p)
                  ? "border-brand-500 bg-brand-500/10"
                  : "border-ink-700 bg-ink-850 text-ink-300 hover:border-ink-600"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <details className="mt-2 text-sm text-ink-400">
          <summary className="cursor-pointer select-none hover:text-ink-300">Custom</summary>
          <div className="mt-2 flex items-center gap-2">
            <input
              aria-label="Minimum length (seconds)"
              type="number"
              min={15}
              max={85}
              value={value.min_len}
              onChange={(e) => {
                const [min_len, max_len] = clampLengths(Number(e.target.value), value.max_len, "min");
                set({ min_len, max_len });
              }}
              className="w-20 rounded-lg border border-ink-700 bg-ink-850 px-2 py-1 text-ink-100"
            />
            <span>to</span>
            <input
              aria-label="Maximum length (seconds)"
              type="number"
              min={20}
              max={90}
              value={value.max_len}
              onChange={(e) => {
                const [min_len, max_len] = clampLengths(value.min_len, Number(e.target.value), "max");
                set({ min_len, max_len });
              }}
              className="w-20 rounded-lg border border-ink-700 bg-ink-850 px-2 py-1 text-ink-100"
            />
            <span>seconds</span>
          </div>
        </details>
      </div>

      <div>
        <span className="label mb-2 block">Framing</span>
        <Segmented
          name="Framing"
          options={CROP_MODES}
          value={value.crop_mode}
          onChange={(crop_mode) => set({ crop_mode })}
          disabled={disabled}
          render={(o) => (
            <span className="block">
              <span className="block font-medium">{o.label}</span>
              <span className="block text-xs text-ink-400">
                {CROP_MODES.find((c) => c.value === o.value)?.hint}
              </span>
            </span>
          )}
        />
      </div>

      <div>
        <span className="label mb-2 block">Captions</span>
        <Segmented
          name="Captions"
          options={CAPTION_STYLES}
          value={value.caption_style}
          onChange={(caption_style) => set({ caption_style })}
          disabled={disabled}
          render={(o) => (
            <span className="block">
              <span className="block font-display text-xs font-extrabold tracking-tight">
                {CAPTION_STYLES.find((c) => c.value === o.value)?.preview}
              </span>
              <span className="block text-xs text-ink-400">{o.label}</span>
            </span>
          )}
        />
      </div>
    </fieldset>
  );
}
