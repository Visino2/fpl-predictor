/**
 * Mirrors backend/api/schemas.py exactly — field names match 1:1 so
 * hooks/useSquad.ts never has to transform response shapes.
 */

export type Position = "GKP" | "DEF" | "MID" | "FWD";

export interface PlayerPrediction {
  player_id: number;
  web_name: string;
  position: Position;
  team_id: number;
  now_cost: number;
  opponent: string;
  was_home: number;
  predicted_points: number;
  fitness_flag: string;
  avg_difficulty_next4: number | null;
  fixture_run_summary: string;
}

/**
 * Shared shape for both a real FPL squad (GET /team/{entry_id}) and an
 * optimizer-picked one (POST /squad/optimize) — mirrors schemas.py's single
 * SquadPlayer model. Fields only one source supplies are optional there too.
 */
export interface SquadPlayer {
  player_id: number | null;
  web_name: string;
  position: Position;
  team: string | null;
  now_cost: number;
  predicted_points: number | null;
  is_starter: boolean | null;
  is_captain: boolean;
  // client-joined from PlayerPrediction by player_id (see useSquad.ts) — not
  // part of the backend's SquadPlayer, only present once that join has run
  avg_difficulty_next4?: number | null;
  opponent?: string | null;
  was_home?: number | null;
  is_vice_captain: boolean | null;
  pick_position: number | null;
}

export interface OptimizedSquad {
  gw: number;
  starters: SquadPlayer[];
  bench: SquadPlayer[];
  captain: string;
  total_predicted_points: number;
}

export interface ChipRecommendation {
  chip: string;
  recommend: boolean;
  headline: string; // short verdict stating the real reason — render verbatim, don't re-derive it
  note: string;
  detail: Record<string, unknown>;
}

export interface TransferSuggestion {
  out_player: string;
  in_player: string;
  out_predicted_points: number;
  in_predicted_points: number;
  predicted_gain: number;
  cost_change: number;
  transfer_cost: string; // "free" or "costs -{n}"
  reasons: string[]; // why the model favors the incoming player — see optimizer._transfer_reasons
}

export interface ChipTimingSuggestion {
  gameweek: number;
  chip: string;
  reason: string;
  predicted_gain: number;
  worth_playing: boolean; // absolute bar — "best of a bad bunch" vs "genuinely worth playing"
}

export interface LineupXiPlayer {
  web_name: string;
  position: Position;
  predicted_points: number;
  is_captain: boolean;
}

export interface LineupXi {
  formation: string; // "D-M-F", e.g. "3-4-3"
  predicted_points: number;
  players: LineupXiPlayer[];
}

export interface LineupSwap {
  out: string;
  in: string; // start `in` instead of `out`
  out_position: Position;
  in_position: Position;
  out_predicted_points: number;
  in_predicted_points: number;
  gain: number;
  reasons: string[]; // same reason-clause style as TransferSuggestion
}

export interface LineupRecommendation {
  gw: number | null;
  is_optimal: boolean;
  actual: LineupXi;
  suggested: LineupXi;
  predicted_points_gain: number;
  swaps: LineupSwap[];
  note: string;
}

export type GwStatus = "requested" | "locked";

export interface MyTeam {
  entry_id: number;
  team_name: string | null;
  overall_rank: number | null;
  gw: number | null;
  requested_gw: number | null;
  gw_status: GwStatus | null;
  bank_balance: number | null;
  squad_value: number | null;
  picks: SquadPlayer[] | null;
}

/** Request body shared by every /squad/* POST route. */
export interface SquadRequest {
  player_ids: number[];
}

export interface AccuracyWeek {
  gw: number;
  predicted_total: number;
  actual_total: number | null;
  difference: number | null;
}

export interface AccuracyReport {
  overall_mae: number | null;
  sample_size: number;
  mae_by_position: Record<string, number>;
  gameweeks_covered: number;
  weeks: AccuracyWeek[];
}

export interface ChipLogEntry {
  gw: number;
  chip_name: string;
  was_recommended: boolean | null;
  recommendation_reason: string | null;
  predicted_gain: number | null;
  was_played: boolean;
  actual_gain: number | null;
  logged_at: string;
}

/**
 * Season-strategy layer — mirrors schemas.py's WildcardFreehitAdvice /
 * TripleCaptainAdvice / SeasonCheckAdvice. Answers "does the season need a
 * structural move now", distinct from the weekly ChipRecommendation /
 * TransferSuggestion shapes above. The nested `checks` / `profile` /
 * `season_to_date` blobs stay loosely typed, same as backend.
 */
export interface WildcardFreehitAdvice {
  verdict: "play now" | "hold";
  headline: string;
  recommended_chip: string | null;
  chip_guidance: string;
  reasons: string[];
  checks: Record<string, unknown>;
}

export interface TripleCaptainCandidate {
  web_name: string;
  predicted_points: number;
  score: number;
}

export interface TripleCaptainAdvice {
  best_candidate: string | null;
  verdict: "play now" | "wait";
  profile: Record<string, unknown> | null;
  reasoning: string[];
  considered: TripleCaptainCandidate[];
  note: string;
}

export interface SeasonCheckAdvice {
  verdict: string; // on track | below pace | underperforming predictions | too early to call | not enough data
  season_to_date: Record<string, number | null>;
  pace_verdict: string | null;
  signals: string[];
  diagnosis: string;
}
