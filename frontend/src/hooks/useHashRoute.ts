import { useEffect, useState } from "react";

export type Route = { page: "home" } | { page: "job"; jobId: string };

export function parseHash(hash: string): Route {
  const m = /^#\/jobs\/([\w-]+)\/?$/.exec(hash);
  return m?.[1] ? { page: "job", jobId: m[1] } : { page: "home" };
}

export function navigate(route: Route): void {
  window.location.hash = route.page === "job" ? `#/jobs/${route.jobId}` : "#/";
}

/** Tiny hash router: two pages don't justify a routing library, and it works on any static host. */
export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
