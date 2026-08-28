"""
Season-strategy endpoints — the "does my season need a structural move"
questions, kept deliberately separate from /squad/* (weekly tactics) and
/predictions/accuracy (model grading).

Thin wrappers only: assemble the DataFrames / history dicts that
src/season_strategy.py expects (from predict.py's CSV, fixture_run.py and
tracker.py) and serialize the verdict structures it returns.
"""
import pandas as pd
from fastapi import APIRouter, HTTPException

from src import season_strategy, tracker
from src.fixture_run import build_fixture_run, to_dataframe
from api.routes.squad import _latest_predictions_df, _load_cached_entry_history, MY_ENTRY_ID
from api.routes.team import get_my_team
from api.schemas import SeasonCheckAdvice, TripleCaptainAdvice, WildcardFreehitAdvice

router = APIRouter(prefix="/strategy", tags=["strategy"])

# Wildcard/Free Hit and Triple Captain are multi-week calls — judge them
# against a longer run than the weekly chip advice does.
STRATEGY_LOOKAHEAD = 5


def _fixture_run_df():
    return to_dataframe(build_fixture_run(n=STRATEGY_LOOKAHEAD))


def _rich_squad_df():
    """
    Your real 15, with roles (is_starter / is_captain from team.py) joined to
    the per-player prediction features (fixture run, fitness, predicted points
    from predictions_gw{N}.csv) that season_strategy needs.
    """
    team = get_my_team(MY_ENTRY_ID)
    if not team.picks:
        raise HTTPException(404, "No real squad available yet for this entry/gameweek.")

    picks = pd.DataFrame([p.model_dump() for p in team.picks])
    preds, _ = _latest_predictions_df()
    feat_cols = [
        c for c in (
            "player_id", "team_id", "predicted_points", "avg_difficulty_next4",
            "fitness_flag", "chance_of_playing", "fixture_difficulty",
            "prev_minutes", "opponent", "was_home",
        )
        if c in preds.columns
    ]
    merged = picks.merge(preds[feat_cols], on="player_id", how="left", suffixes=("", "_pred"))
    # team.py never attaches predicted_points (that's model output, not squad
    # data) — take the CSV's value where the join found one.
    if "predicted_points_pred" in merged.columns:
        merged["predicted_points"] = merged["predicted_points_pred"].fillna(merged["predicted_points"])
        merged = merged.drop(columns=["predicted_points_pred"])
    return merged


def _hits_summary():
    """
    Season-to-date transfer-hit cost and points-left-on-bench, from the cached
    entry history (entry.event_transfers_cost / points_on_bench per gameweek).
    None when the history isn't available, which season_accumulation_check
    treats as "not tracked".
    """
    try:
        history = _load_cached_entry_history(MY_ENTRY_ID)
    except Exception:
        return {"total_cost": None, "transfers": None, "bench_points_total": None, "per_gw": []}

    current = history.get("current", []) or []
    return {
        "total_cost": sum(int(w.get("event_transfers_cost", 0) or 0) for w in current),
        "transfers": sum(int(w.get("event_transfers", 0) or 0) for w in current),
        "bench_points_total": sum(int(w.get("points_on_bench", 0) or 0) for w in current),
        "per_gw": [
            {
                "gw": w.get("event"),
                "cost": w.get("event_transfers_cost", 0),
                "transfers": w.get("event_transfers", 0),
            }
            for w in current
        ],
    }


@router.get("/wildcard-freehit", response_model=WildcardFreehitAdvice)
def wildcard_freehit_advice():
    """
    Should a Wildcard / Free Hit be played NOW for a structural squad problem
    (bad fixture run across the squad, a multi-week points slide, or a cluster
    of fitness doubts) — not for a single weekly upgrade.
    """
    return season_strategy.evaluate_wildcard_freehit(
        _rich_squad_df(), _fixture_run_df(), tracker.get_gameweek_summaries()
    )


@router.get("/triple-captain", response_model=TripleCaptainAdvice)
def triple_captain_advice():
    """
    The single best Triple Captain candidate on a full profile (consistency,
    underlying volume, whether the fixture is a real outlier, set-piece duty)
    — or an explicit "wait" when no one clears the bar this week.
    """
    preds, _ = _latest_predictions_df()
    return season_strategy.evaluate_triple_captain(
        preds, tracker.get_prediction_log(), _fixture_run_df()
    )


@router.get("/season-check", response_model=SeasonCheckAdvice)
def season_check_advice():
    """
    Is the real squad's points total tracking the pace a good rank needs, and
    is it consistently scoring below its own predictions (a sign the strategy
    — churn, hits, captaincy, bench — is the problem, not the model)?
    """
    summaries = tracker.get_gameweek_summaries()
    current_gw = summaries[-1]["gw"] if summaries else 0
    return season_strategy.season_accumulation_check(
        current_gw,
        {
            "summaries": summaries,
            "accuracy": tracker.get_accuracy_report(),
            "hits": _hits_summary(),
        },
    )
