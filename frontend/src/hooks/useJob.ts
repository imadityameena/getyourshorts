import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type Clip, type Job, TERMINAL } from "../lib/api";

export interface UseJobResult {
  job: Job | null;
  clips: Clip[];
  error: string | null;
  notFound: boolean;
  reload: () => void;
}

const POLL_MS = 2000;

/**
 * Follows a job: live updates over Server-Sent Events, falling back to polling
 * if the stream can't be opened (e.g. a proxy that buffers responses).
 * Loads the clip list once the job is done.
 */
export function useJob(jobId: string): UseJobResult {
  const [job, setJob] = useState<Job | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [nonce, setNonce] = useState(0);
  const clipsLoadedFor = useRef<string | null>(null);

  const reload = useCallback(() => {
    clipsLoadedFor.current = null;
    setNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    setJob(null);
    setClips([]);
    setError(null);
    setNotFound(false);

    const apply = (j: Job) => {
      if (cancelled) return;
      setJob(j);
      setError(null);
      if (TERMINAL.includes(j.status)) {
        source?.close();
        if (pollTimer) clearTimeout(pollTimer);
      }
    };

    const poll = async () => {
      try {
        const j = await api.getJob(jobId);
        apply(j);
        if (!TERMINAL.includes(j.status) && !cancelled) pollTimer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true);
          return;
        }
        setError(e instanceof Error ? e.message : "Lost connection to the server");
        pollTimer = setTimeout(poll, POLL_MS * 2);
      }
    };

    const start = async () => {
      // One plain fetch first: gives a fast first paint and a clean 404.
      try {
        const j = await api.getJob(jobId);
        apply(j);
        if (TERMINAL.includes(j.status)) return;
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true);
          return;
        }
      }
      if (cancelled) return;
      if (typeof EventSource === "undefined") {
        void poll();
        return;
      }
      source = new EventSource(api.eventsUrl(jobId));
      source.onmessage = (ev: MessageEvent<string>) => {
        try {
          apply(JSON.parse(ev.data) as Job);
        } catch {
          /* ignore malformed frame */
        }
      };
      source.onerror = () => {
        // Stream ended or failed: switch to polling until the job is terminal.
        source?.close();
        source = null;
        if (!cancelled) void poll();
      };
    };

    void start();
    return () => {
      cancelled = true;
      source?.close();
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [jobId, nonce]);

  useEffect(() => {
    if (job?.status !== "done" || clipsLoadedFor.current === job.id) return;
    clipsLoadedFor.current = job.id;
    api
      .getClips(job.id)
      .then(setClips)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Couldn't load clips"));
  }, [job?.status, job?.id]);

  return { job, clips, error, notFound, reload };
}
