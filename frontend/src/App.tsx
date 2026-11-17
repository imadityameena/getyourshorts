import { useHashRoute } from "./hooks/useHashRoute";
import { Home } from "./pages/Home";
import { Results } from "./pages/Results";

export function App() {
  const route = useHashRoute();
  return (
    <div className="flex min-h-dvh flex-col">
      <nav className="mx-auto flex w-full max-w-6xl items-center px-4 py-4">
        <a href="#/" className="flex items-center gap-2 font-display text-lg font-extrabold tracking-tight">
          <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
            <rect x="7" y="2" width="18" height="28" rx="5" fill="#ff3d5a" />
            <path d="M13 11v10l8-5z" fill="#fff" />
          </svg>
          GetYourShorts
        </a>
      </nav>
      <main className="flex-1">
        {route.page === "job" ? <Results key={route.jobId} jobId={route.jobId} /> : <Home />}
      </main>
      <footer className="px-4 py-6 text-center text-xs text-ink-400">
        Only clip videos you own or have permission to use.
      </footer>
    </div>
  );
}
