import { useState, useEffect, useRef } from 'react';
import { getVideoContent } from '../services/api';

export function useVideoSas(videoId: string | undefined) {
  const [sasUrl, setSasUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!videoId) return;

    let cancelled = false;

    async function fetchSas() {
      try {
        const data = await getVideoContent(videoId!);
        if (cancelled) return;

        setSasUrl(data.url);
        setError(null);

        // Refresh 60 seconds before the SAS token expires (minimum 30 seconds delay)
        const refreshAfterMs = Math.max((data.expires_in_seconds - 60) * 1000, 30_000);
        timerRef.current = setTimeout(() => {
          if (!cancelled) void fetchSas();
        }, refreshAfterMs);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }

    void fetchSas();

    return () => {
      cancelled = true;
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [videoId]);

  return { sasUrl, error };
}
