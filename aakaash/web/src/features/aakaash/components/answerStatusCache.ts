/** One shared status request. A "ready" answer is kept for the page session; any other answer (not_ready, or a failure)
 *  is kept for `retryMs` only, so a tab opened before the key was loaded shows the AI parts once the API is ready. */
export function createStatusCache<T extends { status: string }>(load: () => Promise<T>, now: () => number = Date.now, retryMs = 15000) {
  let p: Promise<T> | null = null;
  let at = 0;
  return () => {
    if (p && at !== Infinity && now() - at >= retryMs) p = null;
    if (!p) {
      at = now();
      const mine = (p = load());
      mine.then((r) => { if (p === mine && r.status === "ready") at = Infinity; }, () => { if (p === mine) p = null; });
    }
    return p;
  };
}
