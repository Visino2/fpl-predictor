import { useCallback, useEffect, useState } from "react";
import type { AccuracyReport, ChipLogEntry } from "../types/fpl";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} failed (${res.status}): ${await res.text()}`);
  return res.json() as Promise<T>;
}

interface UseAccuracyResult {
  loading: boolean;
  error: string | null;
  report: AccuracyReport | null;
  chipHistory: ChipLogEntry[];
  refresh: () => void;
}

export function useAccuracy(): UseAccuracyResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<AccuracyReport | null>(null);
  const [chipHistory, setChipHistory] = useState<ChipLogEntry[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rep, chips] = await Promise.all([
        apiGet<AccuracyReport>("/predictions/accuracy"),
        apiGet<ChipLogEntry[]>("/squad/chips/history"),
      ]);
      setReport(rep);
      setChipHistory(chips);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { loading, error, report, chipHistory, refresh: load };
}
