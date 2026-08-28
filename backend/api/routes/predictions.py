import glob
import os
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src import tracker
from src.predict import DATA_DIR, predict as run_predict
from api.routes.team import get_my_team
from api.schemas import AccuracyReport, PlayerPrediction

router = APIRouter(prefix="/predictions", tags=["predictions"])

OUT_COLS = ["player_id", "web_name", "position", "team_id", "now_cost", "opponent", "was_home",
            "predicted_points", "fitness_flag", "avg_difficulty_next4", "fixture_run_summary"]

# TODO: make this user-configurable if this ever supports more than one person
MY_ENTRY_ID = 6849416


def _latest_predictions_path():
    matches = sorted(glob.glob(os.path.join(DATA_DIR, "predictions_gw*.csv")))
    return matches[-1] if matches else None


@router.get("", response_model=list[PlayerPrediction])
def get_predictions():
    """
    Returns the most recently generated predictions_gw{N}.csv.
    Does NOT regenerate on every call — see POST /predictions/refresh.
    """
    path = _latest_predictions_path()
    if not path:
        raise HTTPException(404, "No predictions yet — call POST /predictions/refresh first.")
    df = pd.read_csv(path).fillna({"fitness_flag": ""})
    return df[OUT_COLS].to_dict(orient="records")


@router.post("/refresh", response_model=list[PlayerPrediction])
def refresh_predictions():
    """
    Re-runs model inference for the current gameweek and overwrites
    predictions_gw{N}.csv. Only needed once per gameweek cycle (see
    PROMPT_2's caching note) — not on every page load.
    """
    result = run_predict()
    return result[OUT_COLS].fillna({"fitness_flag": ""}).to_dict(orient="records")


@router.post("/log")
def log_predictions_route():
    """
    Logs this gameweek's predictions against your REAL squad (GET
    /team/{MY_ENTRY_ID}) — the actual starting XI and captain as configured
    in the live FPL app, not the optimizer's hypothetical best XI. That's
    the point: this measures how the model did for the team you actually
    fielded, not for a team you didn't. Call once per week, before the
    deadline, once predictions look right. Safe to call again before the
    deadline; rejected once POST /predictions/backfill/{gw} has already run
    for this gw.
    """
    team = get_my_team(MY_ENTRY_ID)
    if not team.picks:
        raise HTTPException(404, f"No real squad picks available yet for entry {MY_ENTRY_ID}.")

    predictions = run_predict().set_index("player_id")  # full df, incl. player_id — the CSV drops it

    rows = []
    starting_xi_ids = []
    captain_id = None
    for pick in team.picks:
        if pick.player_id is None or pick.player_id not in predictions.index:
            continue  # e.g. blank gameweek for that player's team — nothing to log a prediction for
        rows.append({
            "player_id": pick.player_id,
            "web_name": pick.web_name,
            "position": pick.position,
            "predicted_points": float(predictions.loc[pick.player_id, "predicted_points"]),
        })
        if pick.is_starter:
            starting_xi_ids.append(pick.player_id)
        if pick.is_captain:
            captain_id = pick.player_id

    if captain_id is None:
        raise HTTPException(409, "Your real squad has no captain flagged — nothing safe to log.")

    predictions_df = pd.DataFrame(rows)

    try:
        tracker.log_predictions(team.gw, predictions_df, starting_xi_ids, captain_id)
    except ValueError as e:
        raise HTTPException(409, str(e))

    return {"gw": team.gw, "logged_players": len(predictions_df)}


@router.post("/backfill/{gw}")
def backfill_route(gw: int):
    """Call after a gameweek's fixtures are all finished — fills in real points for comparison."""
    try:
        tracker.backfill_actuals(gw)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"gw": gw, "status": "backfilled"}


@router.get("/accuracy", response_model=AccuracyReport)
def accuracy_route(last_n_gws: Optional[int] = None):
    """Mean absolute error (overall + per position) and week-by-week squad totals."""
    return tracker.get_accuracy_report(last_n_gws)
