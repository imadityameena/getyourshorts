import { AlertTriangle, ArrowLeft, FileArchive, Loader2, RotateCcw, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { ClipCard } from "../components/ClipCard";
import { ProgressBar } from "../components/ProgressBar";
import { navigate } from "../hooks/useHashRoute";
import { useJob } from "../hooks/useJob";
import { api, type CreateJobRequest, type Job } from "../lib/api";
import { forgetJob, rememberJob, updateRecentTitle } from "../lib/recent";

function retryRequest(job: Job): CreateJobRequest {
  return {
    url: job.url,
    num_clips: job.settings.num_clips ?? 5,
    min_len: job.settings.min_len ?? 30,
    max_len: job.settings.max_len ?? 60,
    crop_mode: job.settings.crop_mode ?? "face",
    caption_style: job.settings.caption_style ?? "bold",
  };
}

export function Results({ jobId }: { jobId: string }) {
  const { job, clips, error, notFound } = useJob(jobId);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (job?.video_title) updateRecentTitle(job.id, job.video_title);
  }, [job?.id, job?.video_title]);

  const cancel = async () => {
    if (!confirm("Cancel this job and delete its files?")) return;
    setBusy(true);
    try {
      await api.cancelJob(jobId);
      forgetJob(jobId);
      navigate({ page: "home" });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Couldn't cancel");
      setBusy(false);
    }
  };

  const retry = async () => {
    if (!job) return;
    setBusy(true);
    setActionError(null);
    try {
      const { job_id } = await api.createJob(retryRequest(job));
      rememberJob({ id: job_id, url: job.url, title: job.video_title, createdAt: new Date().toISOString() });
      navigate({ page: "job", jobId: job_id });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Couldn't restart");
    } finally {
      setBusy(false);
    }
  };

  const back = (
    <a href="#/" className="inline-flex items-center gap-1 text-sm text-ink-400 hover:text-ink-100">
      <ArrowLeft className="size-4" aria-hidden /> New video
    </a>
  );

  if (notFound) {
    return (
      <div className="mx-auto max-w-xl px-4 py-20 text-center">
        <p className="font-display text-2xl font-bold">Job not found</p>
        <p className="mt-2 text-ink-400">It may have expired (files are kept for 24 hours) or been cancelled.</p>
        <div className="mt-6">{back}</div>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="grid place-items-center py-32 text-ink-400">
        <Loader2 className="size-6 animate-spin" aria-label="Loading" />
        {error && <p className="mt-4 text-sm">{error}</p>}
      </div>
    );
  }

  const running = job.status === "queued" || job.status === "running";
  const done = job.status === "done";

  return (
    <div className="mx-auto max-w-6xl px-4 pt-8 pb-20">
      {back}

      <header className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate font-display text-2xl font-extrabold sm:text-3xl">
            {job.video_title ?? "Processing video"}
          </h1>
          <a
            href={job.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-ink-400 hover:text-ink-100"
          >
            {job.url}
          </a>
        </div>
        {done && clips.length > 0 && (
          <a href={api.zipUrl(job.id)} download className="btn-primary">
            <FileArchive className="size-4" aria-hidden />
            Download all ({clips.length})
          </a>
        )}
      </header>

      {!done && (
        <section className="card mt-6 p-5 sm:p-7">
          <ProgressBar stage={job.stage} status={job.status} progress={job.progress} />

          {job.status === "failed" && (
            <div role="alert" className="mt-6 flex items-start gap-3 rounded-xl bg-brand-500/10 p-4">
              <XCircle className="mt-0.5 size-5 shrink-0 text-brand-400" aria-hidden />
              <div className="flex-1">
                <p className="font-semibold">This video couldn't be processed</p>
                <p className="mt-1 text-sm text-ink-300">{job.error ?? "Unknown error."}</p>
              </div>
              <button type="button" onClick={retry} disabled={busy} className="btn-ghost">
                <RotateCcw className="size-4" aria-hidden /> Try again
              </button>
            </div>
          )}

          {running && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-sm text-ink-400">
              <p>You can leave this page; processing continues on the server.</p>
              <button type="button" onClick={cancel} disabled={busy} className="btn-ghost">
                Cancel
              </button>
            </div>
          )}
          {error && running && <p className="mt-3 text-sm text-warn-400">{error} Retrying…</p>}
        </section>
      )}

      {actionError && (
        <p role="alert" className="mt-4 text-sm text-brand-400">
          {actionError}
        </p>
      )}

      {done && (
        <>
          {job.ai_provider === null && clips.length > 0 && (
            <p className="mt-6 flex items-center gap-2 rounded-xl bg-warn-400/10 px-4 py-3 text-sm text-warn-400">
              <AlertTriangle className="size-4 shrink-0" aria-hidden />
              AI ranking was unavailable, so clips were ranked by replay data, audio and pacing.
            </p>
          )}
          {clips.length === 0 ? (
            <p className="mt-10 text-center text-ink-400">
              {error ?? "No clips were produced for this video. Try a shorter clip length."}
            </p>
          ) : (
            <ul className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {clips.map((c) => (
                <li key={c.id}>
                  <ClipCard clip={c} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
