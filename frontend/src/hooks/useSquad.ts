import { useCallback, useEffect, useState } from "react";
import type {
  ChipRecommendation,
  ChipTimingSuggestion,
  GwStatus,
  LineupRecommendation,
  MyTeam,
  OptimizedSquad,
  PlayerPrediction,
  SquadPlayer,
  TransferSuggestion,
} from "../types/fpl";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// TODO: make this user-configurable if this ever supports more than one person
const MY_ENTRY_ID = 6849416;

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} failed (${res.status}): ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed (${res.status}): ${await res.text()}`);
  return res.json() as Promise<T>;
}

interface UseSquadResult {
  loading: boolean;
  error: string | null;
  gw: number;
  requestedGw: number | null;
  gwStatus: GwStatus | null; // "locked" means this is the last-locked squad, not the upcoming gw's — see fetch_my_team
  teamName: string | null;
  squad: SquadPlayer[]; // your real 15, predicted_points attached, roles as actually set in FPL
  squadPredictedTotal: number;
  predictions: PlayerPrediction[]; // the full player pool's predictions for this gameweek
  optimized: OptimizedSquad | null; // the OPTIMIZER's suggested XI — may differ from your real one
  chips: ChipRecommendation[];
  chipTiming: ChipTimingSuggestion[];
  transfers: TransferSuggestion[];
  lineup: LineupRecommendation | null; // optimizer's best XI vs your actual XI
  refresh: () => void;
}

export function useSquad(): UseSquadResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gw, setGw] = useState(0);
  const [requestedGw, setRequestedGw] = useState<number | null>(null);
  const [gwStatus, setGwStatus] = useState<GwStatus | null>(null);
  const [teamName, setTeamName] = useState<string | null>(null);
  const [squad, setSquad] = useState<SquadPlayer[]>([]);
  const [optimized, setOptimized] = useState<OptimizedSquad | null>(null);
  const [chips, setChips] = useState<ChipRecommendation[]>([]);
  const [chipTiming, setChipTiming] = useState<ChipTimingSuggestion[]>([]);
  const [transfers, setTransfers] = useState<TransferSuggestion[]>([]);
  const [lineup, setLineup] = useState<LineupRecommendation | null>(null);
  const [predictions, setPredictions] = useState<PlayerPrediction[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const team = await apiGet<MyTeam>(`/team/${MY_ENTRY_ID}`);
      if (!team.picks || team.picks.length === 0) {
        throw new Error("No picks available for this entry/gameweek yet.");
      }

      const allPredictions = await apiGet<PlayerPrediction[]>("/predictions");
      setPredictions(allPredictions);
      const byId = new Map(allPredictions.map((p) => [p.player_id, p]));

      // team.py deliberately doesn't attach predicted_points, fixture
      // difficulty, or the upcoming opponent (that's model/fixture output,
      // not raw FPL squad data) — join it all in here by player_id.
      const realSquad: SquadPlayer[] = team.picks.map((pick) => {
        const pred = pick.player_id != null ? byId.get(pick.player_id) : undefined;
        return {
          ...pick,
          predicted_points: pred?.predicted_points ?? 0,
          avg_difficulty_next4: pred?.avg_difficulty_next4 ?? null,
          opponent: pred?.opponent ?? null,
          was_home: pred?.was_home ?? null,
        };
      });

      setGw(team.gw ?? 0);
      setRequestedGw(team.requested_gw);
      setGwStatus(team.gw_status);
      setTeamName(team.team_name);
      setSquad(realSquad);

      const playerIds = realSquad
        .map((p) => p.player_id)
        .filter((id): id is number => id != null);

      const [opt, chipRecs, timing, xfers, lineupRec] = await Promise.all([
        apiPost<OptimizedSquad>("/squad/optimize", { player_ids: playerIds }),
        apiPost<ChipRecommendation[]>("/squad/chips", { player_ids: playerIds }),
        apiPost<ChipTimingSuggestion[]>("/squad/chip-timing", { player_ids: playerIds }),
        apiPost<TransferSuggestion[]>("/squad/transfers", { player_ids: playerIds }),
        apiGet<LineupRecommendation>("/squad/lineup-recommendation"),
      ]);
      setOptimized(opt);
      setChips(chipRecs);
      setChipTiming(timing);
      setTransfers(xfers);
      setLineup(lineupRec);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const squadPredictedTotal = squad
    .filter((p) => p.is_starter)
    .reduce((sum, p) => {
      const pts = p.predicted_points ?? 0;
      return sum + pts + (p.is_captain ? pts : 0); // captain's points count double
    }, 0);

  return {
    loading,
    error,
    gw,
    requestedGw,
    gwStatus,
    teamName,
    squad,
    squadPredictedTotal,
    predictions,
    optimized,
    chips,
    chipTiming,
    transfers,
    lineup,
    refresh: load,
  };
}
