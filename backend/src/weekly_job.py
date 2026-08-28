"""
Runs the full weekly cycle end to end without going through the API — this
is meant to run as a background job (see api/main.py's startup scheduler),
so every step here calls existing src/ functions directly. Nothing here
changes predict.py/optimizer.py/tracker.py's own logic; this only sequences
calls to them.

Two entry points:
- run_weekly_refresh(): fetch -> predict -> log predictions + chip advice
  against your REAL squad. Scheduled dynamically for REFRESH_BUFFER before
  the *next gameweek's actual deadline_time* (from bootstrap.json), not a
  fixed weekday — midweek/rearranged rounds move the deadline around. Every
  run re-reads the calendar and reschedules itself for the following one.
- check_and_backfill(): finds any FPL-finished gameweek that hasn't had its
  actual_points filled in yet and backfills it. Scheduled daily, AND nudged
  once shortly after each gameweek's real last-fixture kickoff (kickoff +
  KICKOFF_BUFFER) so results land without waiting for the next daily tick.

Every run's outcome — and the computed next-run time — is appended to
data/job_log.txt, so the schedule is checkable without digging through
server logs.
"""
import os
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

try:  # works both as `python src/weekly_job.py` and as the `src.weekly_job` package
    from . import fetch_data, tracker
    from .bootstrap_utils import get_gw_last_kickoff, get_next_gw_deadline
    from .fixture_run import build_fixture_run, to_dataframe
    from .optimizer import should_play_bench_boost, should_play_triple_captain, suggest_chip_timing
    from .predict import DATA_DIR, load_json, predict as run_predict
    from .squad_resolver import resolve_squad_picks
except ImportError:
    import fetch_data
    import tracker
    from bootstrap_utils import get_gw_last_kickoff, get_next_gw_deadline
    from fixture_run import build_fixture_run, to_dataframe
    from optimizer import should_play_bench_boost, should_play_triple_captain, suggest_chip_timing
    from predict import DATA_DIR, load_json, predict as run_predict
    from squad_resolver import resolve_squad_picks

# TODO: make this user-configurable if this ever supports more than one person
MY_ENTRY_ID = 6849416


def _hours_env(name, default_hours):
    """Read a buffer (in hours) from the environment, falling back to a default."""
    try:
        return timedelta(hours=float(os.environ[name]))
    except (KeyError, ValueError):
        return timedelta(hours=default_hours)


# How long before a gameweek's deadline the main refresh should run. 24h by
# default so there's a day to review predictions/advice before transfers.
REFRESH_BUFFER = _hours_env("WEEKLY_REFRESH_BUFFER_HOURS", 24)
# After a gameweek's last kickoff, how long until results are assumed complete
# (full-time + stoppage + FPL's own data settle). Drives the post-round
# backfill nudge.
KICKOFF_BUFFER = _hours_env("BACKFILL_KICKOFF_BUFFER_HOURS", 3)
# "Run immediately" isn't literally now — a few seconds out keeps APScheduler
# from logging it as a misfire.
IMMEDIATE_DELAY = timedelta(seconds=30)

# Bound to the live APScheduler by init_scheduler() at server startup. Left
# None when this module is run standalone (`python src/weekly_job.py`), in
# which case rescheduling is simply skipped.
_scheduler = None

# Mirrors api/routes/squad.py's CHIP_CODE — src/ can't import from api/
# (wrong direction), and it's only two entries, so it's duplicated rather
# than restructured for this alone.
CHIP_CODE = {"Bench Boost": "bboost", "Triple Captain": "3xc"}

JOB_LOG_PATH = os.path.join(DATA_DIR, "job_log.txt")


def _log(message):
    line = f"[{datetime.now(timezone.utc).isoformat()}] {message}"
    print(line)
    with open(JOB_LOG_PATH, "a") as f:
        f.write(line + "\n")


# --------------------------------------------------------------------------- #
# Dynamic scheduling — planning helpers are pure (take bootstrap/fixtures/now  #
# as args) so they're testable without a live scheduler.                       #
# --------------------------------------------------------------------------- #

def _prev_gw_expected_done(gw, fixtures):
    """
    When the gameweek before `gw` should be finished and backfillable —
    its last kickoff + KICKOFF_BUFFER. None for GW1, or if the previous
    round has no confirmed kickoffs yet.
    """
    if gw <= 1:
        return None
    prev_last_kick = get_gw_last_kickoff(gw - 1, fixtures)
    if prev_last_kick is None:
        return None
    return prev_last_kick + KICKOFF_BUFFER


def compute_next_refresh(bootstrap, fixtures, now=None):
    """
    Decide when run_weekly_refresh should next fire.

    Normal week: REFRESH_BUFFER (default 24h) before the next gameweek's real
    deadline_time.

    Congested calendar (double/blank gameweeks, midweek rounds): if that slot
    lands before the *previous* gameweek is even expected to have finished —
    i.e. we'd be predicting on incomplete results — don't skip the week and
    don't run silently on bad data. Emit a warning and run immediately instead.

    Returns (gw, deadline, run_at, warnings): `warnings` is a list of strings
    the caller should log; empty when the normal slot is used.
    """
    now = now or datetime.now(timezone.utc)
    gw, deadline = get_next_gw_deadline(bootstrap)
    run_at = deadline - REFRESH_BUFFER
    warnings = []

    prev_done = _prev_gw_expected_done(gw, fixtures)
    if prev_done is not None and run_at < prev_done:
        warnings.append(
            f"compressed schedule: the {_fmt_delta(REFRESH_BUFFER)}-before-deadline slot "
            f"({run_at.isoformat()}) falls before GW{gw - 1} is expected to finish "
            f"(~{prev_done.isoformat()}). Running the GW{gw} refresh immediately on "
            f"possibly-incomplete GW{gw - 1} data rather than skipping the week."
        )
        run_at = now + IMMEDIATE_DELAY
    elif run_at <= now:
        warnings.append(
            f"GW{gw} deadline ({deadline.isoformat()}) is already inside the "
            f"{_fmt_delta(REFRESH_BUFFER)} buffer. Running immediately."
        )
        run_at = now + IMMEDIATE_DELAY

    return gw, deadline, run_at, warnings


def compute_post_gw_backfill(gw, fixtures, now=None):
    """
    When to nudge check_and_backfill for `gw`: its last fixture kickoff +
    KICKOFF_BUFFER. Returns None if that gameweek has no confirmed kickoffs
    yet (then we just rely on the daily check). Never returns a past time —
    clamped to now + IMMEDIATE_DELAY.
    """
    now = now or datetime.now(timezone.utc)
    last_kick = get_gw_last_kickoff(gw, fixtures)
    if last_kick is None:
        return None
    return max(last_kick + KICKOFF_BUFFER, now + IMMEDIATE_DELAY)


def _fmt_delta(td):
    hours = td.total_seconds() / 3600
    return f"{hours:g}h"


def reschedule_jobs(reason=""):
    """
    Re-read the FPL calendar and (re)register the next weekly_refresh and the
    post-round backfill nudge. Called at startup and at the end of every
    run_weekly_refresh (deadlines shift week to week, so last week's schedule
    can't be trusted for this one). No-op when run standalone.
    """
    if _scheduler is None:
        _log(f"reschedule_jobs [{reason}]: no scheduler bound (standalone run) — skipping")
        return

    try:
        bootstrap = load_json("bootstrap.json")
        fixtures = load_json("fixtures.json")
    except (OSError, ValueError) as e:
        _log(f"reschedule_jobs [{reason}]: can't read calendar ({e}) — leaving existing jobs in place")
        return

    now = datetime.now(timezone.utc)
    try:
        gw, deadline, run_at, warnings = compute_next_refresh(bootstrap, fixtures, now)
    except (KeyError, ValueError) as e:
        _log(f"reschedule_jobs [{reason}]: can't determine next deadline ({e}) — leaving existing jobs in place")
        return

    for w in warnings:
        _log(f"reschedule_jobs [{reason}]: WARNING — {w}")

    _scheduler.add_job(
        run_weekly_refresh, DateTrigger(run_date=run_at),
        id="weekly_refresh", replace_existing=True,
    )
    _log(
        f"reschedule_jobs [{reason}]: next weekly_refresh -> {run_at.isoformat()} "
        f"(GW{gw} deadline {deadline.isoformat()}, buffer {_fmt_delta(REFRESH_BUFFER)})"
    )

    backfill_at = compute_post_gw_backfill(gw, fixtures, now)
    if backfill_at is not None:
        _scheduler.add_job(
            check_and_backfill, DateTrigger(run_date=backfill_at),
            id="post_gw_backfill", replace_existing=True,
        )
        _log(
            f"reschedule_jobs [{reason}]: post-GW{gw} backfill nudge -> {backfill_at.isoformat()} "
            f"(last kickoff + {_fmt_delta(KICKOFF_BUFFER)})"
        )
    else:
        _log(
            f"reschedule_jobs [{reason}]: GW{gw} has no confirmed fixture kickoffs yet — "
            f"relying on the daily backfill check"
        )


def init_scheduler(scheduler):
    """
    Wire this module to the app's APScheduler (called once from api/main.py's
    startup). Registers the fixed daily backfill check, then computes the
    first dynamic weekly_refresh / backfill-nudge from the current calendar.
    """
    global _scheduler
    _scheduler = scheduler
    scheduler.add_job(
        check_and_backfill,
        CronTrigger(hour=6, minute=0),
        id="daily_backfill",
        replace_existing=True,
    )
    reschedule_jobs(reason="startup")


def run_weekly_refresh():
    """
    Refreshes raw data, regenerates predictions, then logs this gameweek's
    predictions and chip advice against your real squad (GET /team's logic,
    called in-process — see squad_resolver.py) — not a placeholder squad.
    """
    try:
        bootstrap = fetch_data.fetch_bootstrap()
        fetch_data.fetch_fixtures()
        fetch_data.fetch_player_histories([p["id"] for p in bootstrap["elements"]])
        fetch_data.fetch_my_team(MY_ENTRY_ID)

        full_predictions = run_predict()
        predictions_by_id = full_predictions.set_index("player_id")

        my_team = load_json("my_team.json")
        resolved = resolve_squad_picks(my_team["picks"], load_json("bootstrap.json"))
        gw = my_team.get("event_id")

        if not resolved:
            _log(f"run_weekly_refresh: GW{gw} — no squad picks resolved, nothing to log")
            return

        rows, starting_xi_ids, captain_id = [], [], None
        for pick in resolved:
            pid = pick["player_id"]
            if pid not in predictions_by_id.index:
                continue  # e.g. blank gameweek for that player's team
            rows.append({
                "player_id": pid,
                "web_name": pick["web_name"],
                "position": pick["position"],
                "predicted_points": float(predictions_by_id.loc[pid, "predicted_points"]),
            })
            if pick["is_starter"]:
                starting_xi_ids.append(pid)
            if pick["is_captain"]:
                captain_id = pid

        if not rows or captain_id is None:
            _log(f"run_weekly_refresh: GW{gw} — squad incomplete against current predictions, skipping log")
        else:
            try:
                tracker.log_predictions(gw, pd.DataFrame(rows), starting_xi_ids, captain_id)
                _log(f"run_weekly_refresh: logged {len(rows)} predictions for GW{gw}")
            except ValueError as e:
                _log(f"run_weekly_refresh: GW{gw} predictions not logged — {e}")

        # Chip advice against the same real squad
        squad_ids = [p["player_id"] for p in resolved]
        squad_df = full_predictions[full_predictions["player_id"].isin(squad_ids)].reset_index(drop=True)

        fixture_run_df = to_dataframe(build_fixture_run())
        bb = should_play_bench_boost(squad_df, fixture_run_df)
        tc = should_play_triple_captain(squad_df, fixture_run_df)
        tracker.log_chip_recommendation(gw, "bboost", bb["recommend"], bb["note"], bb["bench_predicted_points"])
        tracker.log_chip_recommendation(gw, "3xc", tc["recommend"], tc["note"], tc["predicted_points"])

        timing = suggest_chip_timing(squad_df, to_dataframe(build_fixture_run(n=5)))
        for s in timing:
            tracker.log_chip_recommendation(
                s["gameweek"], CHIP_CODE.get(s["chip"], s["chip"]),
                was_recommended=True, reason=s["reason"], predicted_gain=s["predicted_gain"],
            )

        _log(f"run_weekly_refresh: SUCCESS for GW{gw} — chip advice logged ({len(timing)} timing suggestions)")
    except Exception as e:
        _log(f"run_weekly_refresh: FAILED — {e}\n{traceback.format_exc()}")
        raise
    finally:
        # Always reschedule from the freshly-fetched calendar, even on failure —
        # one bad run must not leave the pipeline with no future runs booked.
        try:
            reschedule_jobs(reason="after run_weekly_refresh")
        except Exception as e:
            _log(f"run_weekly_refresh: could not reschedule next run — {e}\n{traceback.format_exc()}")


def check_and_backfill():
    """Backfills any gameweek FPL has marked finished that isn't backfilled yet."""
    try:
        bootstrap = load_json("bootstrap.json")
        finished_gws = {e["id"] for e in bootstrap["events"] if e["finished"]}
        pending = [gw for gw in tracker.get_logged_gameweeks_missing_actuals() if gw in finished_gws]

        if not pending:
            _log("check_and_backfill: nothing pending")
            return

        for gw in pending:
            try:
                tracker.backfill_actuals(gw)
                _log(f"check_and_backfill: backfilled GW{gw}")
            except ValueError as e:
                _log(f"check_and_backfill: GW{gw} not ready yet — {e}")
    except Exception as e:
        _log(f"check_and_backfill: FAILED — {e}\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    run_weekly_refresh()
    check_and_backfill()
