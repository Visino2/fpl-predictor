"""
Pydantic response models — keep API contracts explicit here so
frontend/src/types/fpl.ts has one clear source of truth to mirror.
"""
from typing import Optional
from pydantic import BaseModel, Field


class PlayerPrediction(BaseModel):
    player_id: int
    web_name: str
    position: str
    team_id: int
    now_cost: float
    opponent: str
    was_home: int
    predicted_points: float
    fitness_flag: str = ""
    avg_difficulty_next4: Optional[float] = None
    fixture_run_summary: str = ""


class SquadPlayer(BaseModel):
    """
    Shared shape for both a real FPL squad (GET /team/{entry_id}) and an
    optimizer-picked one (POST /squad/optimize) — one model, not two parallel
    ones, since most fields mean the same thing either way. Fields only one
    of those sources can supply (team.py has no predicted_points; optimize
    has no pick_position/is_vice_captain) are optional.
    """
    player_id: Optional[int] = None
    web_name: str
    position: str
    team: Optional[str] = None
    now_cost: float
    predicted_points: Optional[float] = None
    is_starter: Optional[bool] = None
    is_captain: bool = False
    is_vice_captain: Optional[bool] = None
    pick_position: Optional[int] = None  # FPL's own 1-15 squad slot ordering


class OptimizedSquad(BaseModel):
    gw: int
    starters: list[SquadPlayer]
    bench: list[SquadPlayer]
    captain: str
    total_predicted_points: float


class ChipRecommendation(BaseModel):
    chip: str
    recommend: bool
    headline: str = ""  # short verdict stating the ACTUAL reason — frontend
                        # renders it verbatim (see optimizer.should_play_*)
    note: str
    detail: dict


class TransferSuggestion(BaseModel):
    out_player: str
    in_player: str
    out_predicted_points: float
    in_predicted_points: float
    predicted_gain: float
    cost_change: float
    transfer_cost: str = "free"  # "free" or "costs -{hit_cost}" — see optimizer.transfer_suggestions
    # short clauses (form / fixture / opponent strength / fitness) explaining
    # why the incoming player is projected higher — see optimizer._transfer_reasons
    reasons: list[str] = []


class LineupXiPlayer(BaseModel):
    web_name: str
    position: str
    predicted_points: float
    is_captain: bool = False


class LineupXi(BaseModel):
    formation: str  # "D-M-F", e.g. "3-4-3"
    predicted_points: float
    players: list[LineupXiPlayer]


class LineupSwap(BaseModel):
    out: str  # start `in` instead of `out`
    in_: str = Field(alias="in")  # "in" is a Python keyword
    out_position: str
    in_position: str
    out_predicted_points: float
    in_predicted_points: float
    gain: float
    reasons: list[str] = []

    model_config = {"populate_by_name": True}


class LineupRecommendation(BaseModel):
    gw: Optional[int] = None
    is_optimal: bool
    actual: LineupXi
    suggested: LineupXi
    predicted_points_gain: float
    swaps: list[LineupSwap] = []
    note: str


# --- Season strategy (src/season_strategy.py, /strategy/* routes) ---------
# These answer "does the season need a structural move right now", a different
# question from the week-to-week TransferSuggestion / ChipRecommendation above.
# Verdict + reasoning strings are the payload; the nested detail dicts stay
# loosely typed on purpose (like ChipRecommendation.detail).

class WildcardFreehitAdvice(BaseModel):
    verdict: str  # "play now" | "hold"
    headline: str
    recommended_chip: Optional[str] = None  # "Wildcard" | "Free Hit" | None
    chip_guidance: str
    reasons: list[str]  # the specific structural findings that fired
    checks: dict  # per-check breakdown (fixture_run / points_trend / fitness_cluster)


class TripleCaptainCandidate(BaseModel):
    web_name: str
    predicted_points: float
    score: float


class TripleCaptainAdvice(BaseModel):
    best_candidate: Optional[str] = None
    verdict: str  # "play now" | "wait"
    profile: Optional[dict] = None  # full profile of the best candidate
    reasoning: list[str]
    considered: list[TripleCaptainCandidate]
    note: str  # explicit play-vs-wait sentence


class SeasonCheckAdvice(BaseModel):
    verdict: str  # on track | below pace | underperforming predictions | too early to call | not enough data
    season_to_date: dict
    pace_verdict: Optional[str] = None
    signals: list[str]
    diagnosis: str


class MyTeam(BaseModel):
    entry_id: int
    team_name: Optional[str] = None
    overall_rank: Optional[int] = None
    gw: Optional[int] = None  # which gameweek these picks actually belong to
    requested_gw: Optional[int] = None  # the gw we originally asked for (== gw unless fell back)
    gw_status: Optional[str] = None  # "requested" (got the gw we asked for) or "locked" (fell back — see fetch_my_team)
    bank_balance: Optional[float] = None  # leftover budget in £m, from entry.last_deadline_bank
    squad_value: Optional[float] = None  # total squad value in £m, from entry.last_deadline_value
    picks: Optional[list[SquadPlayer]] = None


class PredictionLogEntry(BaseModel):
    gw: int
    player_id: int
    web_name: str
    position: str
    predicted_points: float
    actual_points: Optional[float] = None
    was_starter: bool
    was_captain: bool
    logged_at: str


class GameweekSummary(BaseModel):
    gw: int
    predicted_total: float
    actual_total: Optional[float] = None
    squad_predicted_total: float
    squad_actual_total: Optional[float] = None
    created_at: str


class ChipLogEntry(BaseModel):
    gw: int
    chip_name: str
    was_recommended: Optional[bool] = None
    recommendation_reason: Optional[str] = None
    predicted_gain: Optional[float] = None
    was_played: bool
    actual_gain: Optional[float] = None
    logged_at: str


class AccuracyWeek(BaseModel):
    gw: int
    predicted_total: float
    actual_total: Optional[float] = None
    difference: Optional[float] = None


class AccuracyReport(BaseModel):
    overall_mae: Optional[float] = None
    sample_size: int
    mae_by_position: dict[str, float]
    gameweeks_covered: int
    weeks: list[AccuracyWeek]
