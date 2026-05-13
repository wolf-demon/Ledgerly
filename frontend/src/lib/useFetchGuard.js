import { useEffect, useRef } from "react";

/**
 * Returns a stable `guard(fetcher)` function for use inside data-fetching
 * effects. The fetcher receives an `isStale()` predicate it can call after
 * every await to bail out if a newer request has been issued.
 *
 * Usage:
 *
 *   const guard = useFetchGuard();
 *   useEffect(() => {
 *     guard(async ({ isStale }) => {
 *       const r = await api.get(...);
 *       if (isStale()) return;
 *       setData(r.data);
 *     });
 *   }, [deps]);
 *
 * Every time guard() is invoked, the previous in-flight request is marked
 * stale — so a slower response from a previous project can't overwrite the
 * newer project's state.
 */
export function useFetchGuard() {
  const epoch = useRef(0);

  // Reset epoch on unmount so the final in-flight fetch from the destroyed
  // component bails out instead of calling setState on an unmounted node.
  useEffect(() => {
    return () => { epoch.current++; };
  }, []);

  return (fetcher) => {
    const id = ++epoch.current;
    const isStale = () => id !== epoch.current;
    Promise.resolve(fetcher({ isStale })).catch((err) => {
      if (!isStale()) {
        // Use console.warn (not console.error) so React's dev error overlay
        // doesn't pop up for routine network errors during navigation /
        // project switches. The page's local catch blocks can still surface
        // user-friendly toasts when appropriate.
        // eslint-disable-next-line no-console
        console.warn("[fetch-guard] request failed:", err?.message || err);
      }
    });
  };
}
