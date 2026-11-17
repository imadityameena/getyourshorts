/** Recently submitted jobs, remembered in this browser only (no accounts in v1). */

export interface RecentJob {
  id: string;
  url: string;
  title: string | null;
  createdAt: string;
}

const KEY = "gys.recentJobs";
const MAX = 8;

export function loadRecent(): RecentJob[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as RecentJob[]).slice(0, MAX) : [];
  } catch {
    return [];
  }
}

export function rememberJob(job: RecentJob): void {
  try {
    const rest = loadRecent().filter((j) => j.id !== job.id);
    localStorage.setItem(KEY, JSON.stringify([job, ...rest].slice(0, MAX)));
  } catch {
    /* storage unavailable (private mode): not critical */
  }
}

export function updateRecentTitle(id: string, title: string): void {
  try {
    const list = loadRecent();
    const item = list.find((j) => j.id === id);
    if (item && item.title !== title) {
      item.title = title;
      localStorage.setItem(KEY, JSON.stringify(list));
    }
  } catch {
    /* ignore */
  }
}

export function forgetJob(id: string): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(loadRecent().filter((j) => j.id !== id)));
  } catch {
    /* ignore */
  }
}
