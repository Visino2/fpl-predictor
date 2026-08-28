import { useCallback, useEffect, useState } from "react";
import type {
  SeasonCheckAdvice,
  TripleCaptainAdvice,
  WildcardFreehitAdvice,
} from "../types/fpl";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} failed (${res.status}): ${await res.text()}`);
  return res.json() as Promise<T>;
}

interface UseStrategyResult {
  loading: boolean;
  error: string | null;
  wildcard: WildcardFreehitAdvice | null;
  tripleCaptain: TripleCaptainAdvice | null;
  seasonCheck: SeasonCheckAdvice | null;
  refresh: () => void;
}

// Season-level advice (Strategy tab) — separate hook from useSquad (weekly
// tactical view) so the two data flows never get tangled again.
export function useStrategy(): UseStrategyResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wildcard, setWildcard] = useState<WildcardFreehitAdvice | null>(null);
  const [tripleCaptain, setTripleCaptain] = useState<TripleCaptainAdvice | null>(null);
  const [seasonCheck, setSeasonCheck] = useState<SeasonCheckAdvice | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [wc, tc, sc] = await Promise.all([
        apiGet<WildcardFreehitAdvice>("/strategy/wildcard-freehit"),
        apiGet<TripleCaptainAdvice>("/strategy/triple-captain"),
        apiGet<SeasonCheckAdvice>("/strategy/season-check"),
      ]);
      setWildcard(wc);
      setTripleCaptain(tc);
      setSeasonCheck(sc);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { loading, error, wildcard, tripleCaptain, seasonCheck, refresh: load };
}
