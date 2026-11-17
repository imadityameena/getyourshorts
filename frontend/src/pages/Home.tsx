import { ArrowRight, Clock, Loader2, Scissors, Sparkles, Wand2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { DEFAULT_SETTINGS, SettingsPanel } from "../components/SettingsPanel";
import { UrlInput } from "../components/UrlInput";
import { navigate } from "../hooks/useHashRoute";
import { api, type JobSettings, looksLikeYouTubeUrl } from "../lib/api";
import { loadRecent, rememberJob } from "../lib/recent";

const SETTINGS_KEY = "gys.settings";

function loadSettings(): JobSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<JobSettings>) } : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function saveSettings(s: JobSettings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

const FEATURES = [
  { icon: Sparkles, title: "Picks real highlights", text: "Most-replayed data + AI scoring, not random cuts." },
  { icon: Scissors, title: "Clean cuts", text: "Starts and ends on full sentences; dead air trimmed." },
  { icon: Wand2, title: "Ready to upload", text: "9:16, face-tracked, animated captions, −14 LUFS audio." },
];

export function Home() {
  const [url, setUrl] = useState("");
  const [settings, setSettings] = useState<JobSettings>(loadSettings);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const recent = loadRecent();

  const updateSettings = (s: JobSettings) => {
    setSettings(s);
    saveSettings(s);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!looksLikeYouTubeUrl(url)) {
      setError("Paste a link to a single YouTube video (youtube.com/watch?v=… or youtu.be/…).");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const { job_id } = await api.createJob({ url: url.trim(), ...settings });
      rememberJob({ id: job_id, url: url.trim(), title: null, createdAt: new Date().toISOString() });
      navigate({ page: "job", jobId: job_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 pt-12 pb-20 sm:pt-20">
      <header className="text-center">
        <h1 className="font-display text-4xl leading-tight font-extrabold tracking-tight sm:text-5xl">
          Turn long videos into <span className="text-brand-500">Shorts</span>
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-ink-300">
          Paste a YouTube link. We find the moments viewers replay most and hand back vertical clips
          with captions, ready to post.
        </p>
      </header>

      <form onSubmit={submit} className="card mt-10 space-y-6 p-5 sm:p-7" noValidate>
        <UrlInput
          value={url}
          onChange={(v) => {
            setUrl(v);
            if (error) setError(null);
          }}
          error={error}
          disabled={submitting}
        />
        <SettingsPanel value={settings} onChange={updateSettings} disabled={submitting} />
        <button type="submit" className="btn-primary w-full py-3 text-base" disabled={submitting || !url.trim()}>
          {submitting ? (
            <>
              <Loader2 className="size-5 animate-spin" aria-hidden /> Starting…
            </>
          ) : (
            <>
              Generate Shorts <ArrowRight className="size-5" aria-hidden />
            </>
          )}
        </button>
      </form>

      <ul className="mt-10 grid gap-4 sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, text }) => (
          <li key={title} className="rounded-2xl border border-ink-800 p-4">
            <Icon className="size-5 text-brand-400" aria-hidden />
            <p className="mt-2 font-semibold">{title}</p>
            <p className="mt-1 text-sm text-ink-400">{text}</p>
          </li>
        ))}
      </ul>

      {recent.length > 0 && (
        <section className="mt-12">
          <h2 className="label mb-3">Recent</h2>
          <ul className="divide-y divide-ink-800 overflow-hidden rounded-2xl border border-ink-800">
            {recent.map((j) => (
              <li key={j.id}>
                <a
                  href={`#/jobs/${j.id}`}
                  className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-ink-900"
                >
                  <Clock className="size-4 shrink-0 text-ink-400" aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{j.title ?? j.url}</span>
                  <span className="shrink-0 text-xs text-ink-400">
                    {new Date(j.createdAt).toLocaleDateString()}
                  </span>
                </a>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-ink-400">Files are deleted automatically after 24 hours.</p>
        </section>
      )}
    </div>
  );
}
