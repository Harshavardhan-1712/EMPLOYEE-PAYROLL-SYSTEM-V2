import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface QueryState<T> { data: T | undefined; error: ApiError | null; loading: boolean; reload: () => void }

/** Minimal fetch hook: aborts stale requests, keeps previous data while refreshing. */
export function useQuery<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: unknown[]): QueryState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const ctl = new AbortController();
    setLoading(true);
    setError(null);
    fetcherRef.current(ctl.signal)
      .then((d) => { setData(d); setLoading(false); })
      .catch((e: unknown) => {
        if ((e as Error).name === "AbortError") return;
        setError(e instanceof ApiError ? e : new ApiError(0, "error", "Unexpected error"));
        setLoading(false);
      });
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
