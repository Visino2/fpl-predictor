import glob
import logging
import os
import time
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src import tracker, transfer_budget
from src.fetch_data import fetch_entry_history
from src.predict import DATA_DIR, load_json
from src.fixture_run import build_fixture_run, to_dataframe
from src.optimizer import (
    chip_timing_consistency_warnings,
    pick_best_xi,
    recommend_lineup,
    should_play_bench_boost,
    should_play_triple_captain,
    suggest_chip_timing,
    transfer_suggestions,
)
from api.routes.team import get_my_team
from api.schemas import (
    ChipLogEntry,
    ChipRecommendation,
    LineupRecommendation,
    OptimizedSquad,
    SquadPlayer,
    TransferSuggestion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/squad", tags=["squad"])

# chip_log uses short codes (bboost/3xc/wildcard/freehit); the optimizer/API
# layer talks in human-readable names — this is the one place they meet.
CHIP_CODE = {"Bench Boost": "bboost", "Triple Captain": "3xc"}

# TODO: make this user-configurable if this ever supports more than one person
MY_ENTRY_ID = 6849416

ENTRY_HISTORY_CACHE_PATH = os.path.join(DATA_DIR, "entry_history.json")
ENTRY_HISTORY_TTL_SECONDS = 60 * 60  # same low-frequency caching note as team.py's my_team.json


def _load_cached_entry_history(entry_id):
    is_stale = (
        not os.path.exists(ENTRY_HISTORY_CACHE_PATH)
        or (time.time() - os.path.getmtime(ENTRY_HISTORY_CACHE_PATH)) > ENTRY_HISTORY_TTL_SECONDS
    )
    if is_stale:
        fetch_entry_history(entry_id)
    return load_json("entry_history.json")


class SquadRequest(BaseModel):
    player_ids: list[int]  # FPL element ids — the stable identifier a real squad uses


class ChipPlayedRequest(BaseModel):
    gw: int
    chip_name: str  # short code: bboost / 3xc / wildcard / freehit


def _latest_predictions_df():
    matches = sorted(glob.glob(os.path.join(DATA_DIR, "predictions_gw*.csv")))
    if not matches:
        raise HTTPException(404, "No predictions available — call POST /predictions/refresh first.")
    gw = int(matches[-1].split("_gw")[-1].split(".csv")[0])
    return pd.read_csv(matches[-1]), gw


def _squad_df(player_ids):
    preds, gw = _latest_predictions_df()
    squad = preds[preds["player_id"].isin(player_ids)].reset_index(drop=True)
    missing = set(player_ids) - set(squad["player_id"])
    if missing:
        raise HTTPException(400, f"Player ids not found in latest predictions: {sorted(missing)}")
    return squad, gw


@router.post("/optimize", response_model=OptimizedSquad)
def optimize_squad(req: SquadRequest):
    """Best legal starting XI + captain for a given 15-man squad (System 2 — pure PuLP, zero ML)."""
    if len(req.player_ids) != 15:
        raise HTTPException(400, "Squad must have exactly 15 players.")
    squad, gw = _squad_df(req.player_ids)
    starters, bench = pick_best_xi(squad)
    captain = starters.loc[starters["is_captain"], "web_name"].iloc[0]

    starter_cols = ["player_id", "web_name", "position", "now_cost", "predicted_points", "is_captain"]
    bench_cols = ["player_id", "web_name", "position", "now_cost", "predicted_points"]
    total = starters["predicted_points"].sum() + starters.loc[starters["is_captain"], "predicted_points"].sum()

    return OptimizedSquad(
        gw=gw,
        starters=[SquadPlayer(**r) for r in starters[starter_cols].to_dict(orient="records")],
        bench=[SquadPlayer(**r, is_captain=False) for r in bench[bench_cols].to_dict(orient="records")],
        captain=captain,
        total_predicted_points=round(float(total), 1),
    )


@router.get("/lineup-recommendation", response_model=LineupRecommendation)
def lineup_recommendation():
    """
    Your real starting XI + formation vs the optimizer's best legal XI from
    the same 15 players — predicted-point difference and the specific
    start-instead-of swaps. A suggestion to action manually in the FPL app,
    not an automatic change. See optimizer.recommend_lineup.
    """
    team = get_my_team(MY_ENTRY_ID)
    if not team.picks:
        raise HTTPException(404, "No real squad available yet for this entry/gameweek.")

    preds, gw = _latest_predictions_df()
    picks = pd.DataFrame([p.model_dump() for p in team.picks])

    # join the prediction feature columns (used to explain each swap, same as
    # transfer_suggestions) + the real predicted_points onto the real picks
    feat_cols = [
        c for c in (
            "prev_points", "prev_minutes", "fixture_difficulty",
            "opp_defence_strength", "opp_attack_strength", "chance_of_playing",
            "avg_difficulty_next4", "fitness_flag",
        )
        if c in preds.columns
    ]
    merged = picks.merge(
        preds[["player_id", "predicted_points", *feat_cols]],
        on="player_id", how="left", suffixes=("", "_pred"),
    )
    # team.py never attaches predicted_points — take the CSV's value
    merged["predicted_points"] = merged["predicted_points_pred"].fillna(merged["predicted_points"])
    merged = merged.drop(columns=["predicted_points_pred"])

    rec = recommend_lineup(merged)
    rec["gw"] = gw
    return rec


@router.post("/chips", response_model=list[ChipRecommendation])
def chip_recommendations(req: SquadRequest, use_fixture_run: bool = True):
    """
    Bench Boost / Triple Captain recommendations for a given 15-man squad,
    for the CURRENT gameweek only. By default also factors in the squad's
    upcoming fixture run (pass use_fixture_run=false for the original
    single-gameweek-only judgment). See POST /squad/chip-timing to compare
    across multiple future gameweeks instead of just this one.
    """
    if len(req.player_ids) != 15:
        raise HTTPException(400, "Squad must have exactly 15 players.")
    squad, gw = _squad_df(req.player_ids)
    fixture_run_df = to_dataframe(build_fixture_run()) if use_fixture_run else None

    bb = should_play_bench_boost(squad, fixture_run_df)
    tc = should_play_triple_captain(squad, fixture_run_df)

    tracker.log_chip_recommendation(
        gw, "bboost", was_recommended=bb["recommend"], reason=bb["note"],
        predicted_gain=bb["bench_predicted_points"],
    )
    tracker.log_chip_recommendation(
        gw, "3xc", was_recommended=tc["recommend"], reason=tc["note"],
        predicted_gain=tc["predicted_points"],
    )

    _hidden = ("recommend", "note", "headline")
    return [
        ChipRecommendation(
            chip="Bench Boost", recommend=bool(bb["recommend"]),
            headline=bb["headline"], note=bb["note"],
            detail={k: v for k, v in bb.items() if k not in _hidden},
        ),
        ChipRecommendation(
            chip="Triple Captain", recommend=bool(tc["recommend"]),
            headline=tc["headline"], note=tc["note"],
            detail={k: v for k, v in tc.items() if k not in _hidden},
        ),
    ]


@router.post("/chip-timing")
def chip_timing(req: SquadRequest, lookahead: int = 5):
    """
    Ranks upcoming gameweeks (default next 5) as Bench Boost / Triple
    Captain opportunities for a given squad — see optimizer.suggest_chip_timing
    for the heuristic and its limits (it re-weights current predicted_points
    by future fixture ease; it does not forecast future points).
    """
    squad, gw = _squad_df(req.player_ids)
    fixture_run_df = to_dataframe(build_fixture_run(n=lookahead))
    suggestions = suggest_chip_timing(squad, fixture_run_df)

    # Internal consistency guardrail: the "best gameweek" ranking and the
    # "play it now?" verdict are computed by different functions (and shown in
    # different panels) — if the ranking says the current GW is #1 for a chip
    # but the verdict says hold, the two panels contradict each other. Same
    # squad + same fixture_run_df here, so any disagreement is a logic bug, not
    # stale data. Log it rather than raise, so the endpoint still responds.
    bb = should_play_bench_boost(squad, fixture_run_df)
    tc = should_play_triple_captain(squad, fixture_run_df)
    for warning in chip_timing_consistency_warnings(gw, suggestions, bb, tc):
        logger.warning("chip advice inconsistency (GW%s): %s", gw, warning)

    for s in suggestions:
        tracker.log_chip_recommendation(
            s["gameweek"], CHIP_CODE.get(s["chip"], s["chip"]),
            was_recommended=True, reason=s["reason"], predicted_gain=s["predicted_gain"],
        )

    return suggestions


@router.post("/chips/played")
def mark_chip_played(req: ChipPlayedRequest):
    """Call once you actually activate a chip in the real FPL app."""
    tracker.record_chip_played(req.gw, req.chip_name)
    return {"gw": req.gw, "chip_name": req.chip_name, "status": "recorded"}


@router.get("/chips/history", response_model=list[ChipLogEntry])
def chip_history():
    """Every chip recommendation and outcome logged this season."""
    return tracker.get_chip_history()


@router.post("/transfers", response_model=list[TransferSuggestion])
def transfer_recs(req: SquadRequest, free_transfers: Optional[int] = None):
    """
    Suggested swaps: same-position, affordable, higher-predicted-points
    replacements. Uses your REAL bank balance (from /team/{entry_id}'s
    cached entry data) as the budget cap — not just the outgoing player's
    own price — and your REAL free-transfer count (derived from transfer
    history, since FPL's API has no direct field for it). Pass
    free_transfers to override the computed value.
    """
    squad, _ = _squad_df(req.player_ids)
    all_players, _ = _latest_predictions_df()

    team = get_my_team(MY_ENTRY_ID)
    bank_balance = team.bank_balance or 0.0

    if free_transfers is None:
        history = _load_cached_entry_history(MY_ENTRY_ID)
        free_transfers = transfer_budget.compute_free_transfers(history.get("current", []))

    suggestions = transfer_suggestions(
        squad, all_players, free_transfers=free_transfers, bank_balance=bank_balance,
    )
    return [
        TransferSuggestion(
            out_player=s["out"], in_player=s["in"],
            out_predicted_points=s["out_predicted_points"],
            in_predicted_points=s["in_predicted_points"],
            predicted_gain=s["predicted_gain"], cost_change=s["cost_change"],
            transfer_cost=s["transfer_cost"], reasons=s["reasons"],
        )
        for s in suggestions
    ]
