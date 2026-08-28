"""
Season-level strategy layer — a different question from optimizer.py.

optimizer.transfer_suggestions() answers "is there an obvious free upgrade
this week". The functions here answer "does the SEASON need a structural
move right now": should a Wildcard / Free Hit be played to fix a squad-wide
problem, is this genuinely a Triple Captain week or one to wait, and is the
real squad's points total tracking the pace a good rank needs.

Same single-responsibility discipline as the rest of src/: these functions
take plain DataFrames / dicts (mostly assembled by api/routes/strategy.py
from predict.py, fixture_run.py and tracker.py) and return verdict + reason
structures. They never call the model or the optimizer, and never write.

Everything degrades gracefully on thin data — early in a season there may be
only one or two logged gameweeks, so a check that needs a multi-week trend
reports "not enough history" rather than firing on noise.
"""
import json
import os
import statistics

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ---- tuning constants ----------------------------------------------------- #
# FPL fixture difficulty runs 1 (easiest) - 5 (hardest); 3 is a neutral tie.

# A player's fixture RUN (mean difficulty over the lookahead window) has to be
# this bad to count toward a squad-wide fixture problem. 3.5 is "slightly
# harder than average"; 3.8+ is a genuinely rough patch, not marginal.
BAD_FIXTURE_RUN = 3.8
# ...and this many outfield starters have to be in that state at once for it
# to be a squad problem rather than "sell one guy".
MIN_BAD_FIXTURE_PLAYERS = 3

# The squad's week-to-week points total must fall for this many gameweeks in a
# row to count as a real downtrend (needs DOWNTREND_WEEKS + 1 logged weeks).
DOWNTREND_WEEKS = 3

# Simultaneous fitness / rotation doubts in the squad.
MIN_FITNESS_DOUBTS = 3
# chance_of_playing at or below this (or any non-empty fitness flag) is a doubt.
DOUBT_CHANCE = 75

# Triple Captain gates.
TC_MIN_PREDICTED = 8.0          # a TC week needs a genuine ceiling, not "solid"
TC_STRONG_PREDICTED = 9.5       # at/above this the fixture bar is relaxed
TC_OUTLIER_FIXTURE = 2.0        # next fixture difficulty at/below this = easy
TC_OUTLIER_RUN_GAP = 1.0        # next fixture this much easier than the player's
                               # own run avg = a real outlier, not just an easy team
TC_CONSISTENT_STD = 3.0        # stdev of actual pts across logged GWs below this
                               # = a dependable scorer (spiky ones are worse TC bets)

# Season pace: rough average points-per-gameweek associated with a strong
# overall rank. Deliberately a blunt benchmark, not a rank model.
GOOD_RANK_PACE = 55.0
# Fraction of graded weeks the squad can fall short of its own prediction
# before it looks like a strategy problem rather than variance.
UNDERPERFORM_WEEK_FRACTION = 0.6
# ...backed by an average shortfall of at least this many points per week.
UNDERPERFORM_PER_WEEK = 4.0
# Below this many graded gameweeks, report the numbers but don't hand down a
# "strategy problem" verdict — one or two weeks is variance, not a pattern.
MIN_GRADED_WEEKS_FOR_VERDICT = 3


def _load_json(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


def _num(row, key):
    """DataFrame-row / dict value as float, or None if missing / NaN."""
    if key not in row:
        return None
    val = row[key]
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN check


def _has_doubt(row):
    chance = _num(row, "chance_of_playing")
    if chance is not None and chance <= DOUBT_CHANCE:
        return True
    flag = row.get("fitness_flag") if hasattr(row, "get") else None
    return bool(flag and str(flag).strip() and str(flag).lower() != "nan")


# ======================================================================== #
# 1. Wildcard / Free Hit — structural squad problems only                   #
# ======================================================================== #

def evaluate_wildcard_freehit(squad_df, fixture_run_df, predictions_history):
    """
    Recommend playing a Wildcard / Free Hit only for a STRUCTURAL problem,
    never for weekly tinkering. Fires on any one of:

      * 3+ outfield starters stuck in a genuinely bad fixture run
        (mean difficulty over the lookahead window >= BAD_FIXTURE_RUN),
      * the squad's points total trending down for DOWNTREND_WEEKS straight
        gameweeks (a real multi-week slide, not one bad week),
      * 3+ squad players carrying a fitness / rotation doubt at the same time.

    Args:
      squad_df: one row per squad player. Expected columns: web_name,
        position, team_id, is_starter, plus (optionally) avg_difficulty_next4,
        chance_of_playing, fitness_flag.
      fixture_run_df: fixture_run.to_dataframe() output (team_id, gw,
        difficulty rows) over the lookahead window. Used to recompute each
        team's run mean over exactly this window; falls back to squad_df's
        avg_difficulty_next4 column when a team isn't present.
      predictions_history: tracker.get_gameweek_summaries() — list of
        {gw, squad_predicted_total, squad_actual_total, ...} oldest gw first.

    Returns a dict with: verdict ("play now" | "hold"), headline, reasons
    (the specific structural findings that fired), chip_guidance, and a
    per-check breakdown.
    """
    checks = {}
    reasons = []

    # --- team fixture-run means over this exact window --------------------
    team_run_mean = {}
    if fixture_run_df is not None and not fixture_run_df.empty:
        for tid, grp in fixture_run_df.groupby("team_id"):
            team_run_mean[tid] = round(grp["difficulty"].mean(), 2)

    def run_for(row):
        tid = _num(row, "team_id")
        if tid is not None and int(tid) in team_run_mean:
            return team_run_mean[int(tid)]
        return _num(row, "avg_difficulty_next4")

    # --- check A: squad-wide bad fixture run -----------------------------
    outfield_starters = [
        r for _, r in squad_df.iterrows()
        if bool(r.get("is_starter")) and r.get("position") != "GKP"
    ]
    bad = []
    for r in outfield_starters:
        run = run_for(r)
        if run is not None and run >= BAD_FIXTURE_RUN:
            bad.append((r["web_name"], run))
    bad.sort(key=lambda x: -x[1])
    n_out = len(outfield_starters) or 8
    checks["fixture_run"] = {
        "bad_players": [{"web_name": n, "run_avg": v} for n, v in bad],
        "count": len(bad),
        "threshold": BAD_FIXTURE_RUN,
        "triggered": len(bad) >= MIN_BAD_FIXTURE_PLAYERS,
    }
    if checks["fixture_run"]["triggered"]:
        names = ", ".join(f"{n} ({v})" for n, v in bad)
        reasons.append(
            f"{len(bad)} of your {n_out} outfield starters average difficulty "
            f"{BAD_FIXTURE_RUN}+ over their next {_window_len(fixture_run_df)} "
            f"fixtures ({names}) — this is a squad-wide fixture problem, not one "
            f"bad transfer."
        )

    # --- check B: multi-week points downtrend ---------------------------
    trend = _downtrend(predictions_history)
    checks["points_trend"] = trend
    if trend["triggered"]:
        series = " → ".join(str(round(v, 1)) for v in trend["series"])
        reasons.append(
            f"Your squad's {trend['basis']} has fallen {trend['weeks']} gameweeks "
            f"running ({series}) — a sustained slide, not a single off week."
        )

    # --- check C: simultaneous fitness / rotation doubts --------------
    doubts = [r["web_name"] for _, r in squad_df.iterrows() if _has_doubt(r)]
    checks["fitness_cluster"] = {
        "players": doubts,
        "count": len(doubts),
        "threshold": MIN_FITNESS_DOUBTS,
        "triggered": len(doubts) >= MIN_FITNESS_DOUBTS,
    }
    if checks["fitness_cluster"]["triggered"]:
        reasons.append(
            f"{len(doubts)} squad players are flagged with a fitness or rotation "
            f"doubt at once ({', '.join(doubts)}) — too many holes to patch with "
            f"one transfer."
        )

    play = len(reasons) > 0
    if play:
        # Free Hit for a one-week hole (blank/double gameweek), Wildcard for a
        # sustained structural issue. Fixture-run and downtrend are sustained;
        # a lone fitness cluster around a single congested week leans Free Hit.
        sustained = checks["fixture_run"]["triggered"] or checks["points_trend"]["triggered"]
        chip = "Wildcard" if sustained else "Free Hit"
        guidance = (
            "Lean Wildcard — the problem spans several gameweeks, so a permanent "
            "rebuild is worth more than a one-week patch."
            if sustained else
            "Lean Free Hit — this looks like a single-week hole (injuries / a "
            "blank or double gameweek). Wildcard only if it persists."
        )
        headline = f"Play now — {reasons[0].split('—')[0].strip().rstrip('.')}"
    else:
        chip = None
        guidance = (
            "Hold both chips. None of the structural triggers are close — keep "
            "them for a real fixture swing, a sustained points slide, or a "
            "pile-up of injuries."
        )
        headline = "Hold — no structural problem, this is weekly-transfer territory"

    return {
        "verdict": "play now" if play else "hold",
        "headline": headline,
        "recommended_chip": chip,
        "chip_guidance": guidance,
        "reasons": reasons,
        "checks": checks,
    }


def _window_len(fixture_run_df):
    if fixture_run_df is None or fixture_run_df.empty:
        return 4
    return int(fixture_run_df["gw"].nunique())


def _downtrend(summaries):
    """
    Look for DOWNTREND_WEEKS consecutive strictly-decreasing gameweeks in the
    squad totals. Prefers actual totals where every recent week is backfilled,
    else falls back to the pre-deadline predicted totals.
    """
    rows = sorted(summaries or [], key=lambda r: r["gw"])
    out = {"triggered": False, "weeks": 0, "series": [], "basis": "predicted total",
           "note": None}
    if len(rows) < DOWNTREND_WEEKS + 1:
        out["note"] = (
            f"only {len(rows)} gameweek(s) logged — need {DOWNTREND_WEEKS + 1} "
            f"to judge a trend"
        )
        return out

    actuals = [r.get("squad_actual_total") for r in rows]
    use_actual = all(a is not None for a in actuals[-(DOWNTREND_WEEKS + 1):])
    key = "squad_actual_total" if use_actual else "squad_predicted_total"
    out["basis"] = "actual points" if use_actual else "predicted total"

    series = [r[key] for r in rows if r.get(key) is not None]
    tail = series[-(DOWNTREND_WEEKS + 1):]
    if len(tail) == DOWNTREND_WEEKS + 1 and all(b < a for a, b in zip(tail, tail[1:])):
        out.update(triggered=True, weeks=DOWNTREND_WEEKS, series=tail)
    else:
        out["series"] = tail
    return out


# ======================================================================== #
# 2. Triple Captain — profile the best candidate, or say "wait"             #
# ======================================================================== #

def evaluate_triple_captain(all_players_df, predictions_history, fixture_run_df,
                            bootstrap=None, player_histories=None):
    """
    Pick the single best Triple Captain candidate on a PROFILE, not just the
    highest predicted_points for next week, and say plainly when no one clears
    the bar and the chip should wait.

    Profile inputs per candidate:
      * Consistency — stdev of the player's actual points (and of the model's
        error on them) across logged gameweeks, from predictions_history.
        Spiky scorers are worse TC bets than steady ones at the same mean.
      * Underlying volume — mean xGI and BPS over their last few gameweeks
        from player_histories.json, not just the last match.
      * Fixture — is next week a genuine outlier (much easier than the
        player's own run) or only slightly above average.
      * Set pieces — penalties / direct free kicks / corners order from
        bootstrap.json, which raises a captain's floor.

    Args:
      all_players_df: predict.py's full output (predictions_gw{N}.csv). Uses
        player_id, web_name, position, team_id, predicted_points,
        fixture_difficulty, avg_difficulty_next4, prev_minutes,
        chance_of_playing.
      predictions_history: tracker.get_prediction_log() — per-player
        {gw, player_id, predicted_points, actual_points} rows.
      fixture_run_df: fixture_run.to_dataframe() output — used to spot a
        double gameweek (two rows for a team in the first gw of the window).
      bootstrap / player_histories: injectable for tests; loaded from
        data/*.json when omitted.

    Returns: best_candidate, verdict ("play now" | "wait"), the full profile,
    reasoning lines, a shortlist of the other candidates considered, and an
    explicit play-vs-wait note.
    """
    bootstrap = bootstrap or _load_json("bootstrap.json")
    player_histories = player_histories or _load_json("player_histories.json")

    set_piece = _set_piece_lookup(bootstrap)
    per_player_stats = _player_consistency(predictions_history)
    first_gw = None
    dgw_teams = set()
    if fixture_run_df is not None and not fixture_run_df.empty:
        first_gw = int(fixture_run_df["gw"].min())
        counts = fixture_run_df[fixture_run_df["gw"] == first_gw].groupby("team_id").size()
        dgw_teams = set(counts[counts > 1].index)

    # shortlist: realistic starters, ranked by raw ceiling
    df = all_players_df.copy()
    df = df[df.apply(lambda r: (_num(r, "prev_minutes") or 0) >= 45
                     and (_num(r, "chance_of_playing") is None
                          or _num(r, "chance_of_playing") >= DOUBT_CHANCE), axis=1)]
    df = df.sort_values("predicted_points", ascending=False).head(6)
    if df.empty:
        return {
            "best_candidate": None,
            "verdict": "wait",
            "profile": None,
            "reasoning": ["No candidate has a settled starting role and a clean bill of health this week."],
            "considered": [],
            "note": "Nothing to triple this week — wait.",
        }

    scored = []
    for _, r in df.iterrows():
        prof = _profile_candidate(r, per_player_stats, set_piece, player_histories,
                                  dgw_teams)
        scored.append(prof)

    scored.sort(key=lambda p: -p["_score"])
    best = scored[0]

    # --- play vs wait -------------------------------------------------
    reasons = []
    pts = best["predicted_points"]
    play = True

    if pts < TC_MIN_PREDICTED:
        play = False
        reasons.append(
            f"{best['web_name']} is the strongest option but only projects {pts} pts — "
            f"below the {TC_MIN_PREDICTED} a Triple Captain week really needs."
        )
    else:
        reasons.append(f"{best['web_name']} projects {pts} pts next week.")

    if best["fixture_outlier"]:
        reasons.append(best["fixture_note"])
    else:
        if pts < TC_STRONG_PREDICTED:
            play = False
        reasons.append(best["fixture_note"] + " — not the outlier fixture you want to burn the chip on.")

    if best["consistency_std"] is not None:
        reasons.append(best["consistency_note"])
        if best["consistency_std"] > TC_CONSISTENT_STD and pts < TC_STRONG_PREDICTED:
            play = False
    else:
        reasons.append(best["consistency_note"])

    reasons.append(best["volume_note"])
    reasons.append(best["set_piece_note"])
    if best["double_gameweek"]:
        reasons.append(f"{best['web_name']} has a double gameweek — two matches to triple, which is the textbook case.")
        play = play or pts >= TC_MIN_PREDICTED  # a DGW premium is enough on its own

    if play:
        note = (
            f"Play it on {best['web_name']} this week — the ceiling, fixture and "
            f"profile line up."
        )
    else:
        note = (
            f"Wait. {best['web_name']} is the best available but this isn't a strong "
            f"enough case — hold the chip for a double gameweek or a premium in form "
            f"against a bottom-three defence."
        )

    return {
        "best_candidate": best["web_name"],
        "verdict": "play now" if play else "wait",
        "profile": {k: v for k, v in best.items() if not k.startswith("_")},
        "reasoning": reasons,
        "considered": [
            {"web_name": p["web_name"], "predicted_points": p["predicted_points"],
             "score": round(p["_score"], 2)}
            for p in scored
        ],
        "note": note,
    }


def _set_piece_lookup(bootstrap):
    out = {}
    for p in bootstrap.get("elements", []):
        duties = []
        if p.get("penalties_order") == 1:
            duties.append("penalties")
        if p.get("direct_freekicks_order") in (1, 2):
            duties.append("direct free kicks")
        if p.get("corners_and_indirect_freekicks_order") in (1, 2):
            duties.append("corners")
        out[p["id"]] = duties
    return out


def _player_consistency(prediction_log):
    """player_id -> {actual_std, residual_std, mean_actual, gws} from logged rows."""
    by_player = {}
    for row in prediction_log or []:
        if row.get("actual_points") is None:
            continue
        by_player.setdefault(row["player_id"], []).append(row)
    stats = {}
    for pid, rows in by_player.items():
        actuals = [float(r["actual_points"]) for r in rows]
        residuals = [float(r["actual_points"]) - float(r["predicted_points"]) for r in rows]
        stats[pid] = {
            "gws": len(rows),
            "mean_actual": round(statistics.fmean(actuals), 2),
            "actual_std": round(statistics.pstdev(actuals), 2) if len(actuals) > 1 else None,
            "residual_std": round(statistics.pstdev(residuals), 2) if len(residuals) > 1 else None,
        }
    return stats


def _recent_history(player_histories, player_id, n=4):
    hist = player_histories.get(str(player_id), {}).get("history", [])
    return sorted(hist, key=lambda h: h["round"])[-n:]


def _profile_candidate(row, per_player_stats, set_piece, player_histories, dgw_teams):
    pid = int(row["player_id"])
    pts = round(float(row["predicted_points"]), 1)
    next_diff = _num(row, "fixture_difficulty")
    run_avg = _num(row, "avg_difficulty_next4")
    opp = row.get("opponent")
    home = _num(row, "was_home")
    where = "H" if home == 1 else "A" if home == 0 else "?"

    # fixture outlier: easy AND clearly easier than the player's own run
    outlier = (
        next_diff is not None and next_diff <= TC_OUTLIER_FIXTURE
        and run_avg is not None and (run_avg - next_diff) >= TC_OUTLIER_RUN_GAP
    )
    if next_diff is None:
        fixture_note = "No confirmed fixture next week"
    else:
        rel = (f", vs a {run_avg} run average" if run_avg is not None else "")
        kind = "a genuine outlier" if outlier else "not an outlier"
        fixture_note = f"Next fixture {opp or '?'} ({where}) difficulty {next_diff}{rel} — {kind}"

    cstats = per_player_stats.get(pid)
    if cstats and cstats["actual_std"] is not None:
        cstd = cstats["actual_std"]
        tag = "dependable" if cstd <= TC_CONSISTENT_STD else "spiky"
        consistency_note = (
            f"Consistency: {cstd} pts stdev across {cstats['gws']} logged GWs "
            f"(mean {cstats['mean_actual']}) — {tag}."
        )
    else:
        cstd = None
        consistency_note = (
            f"Consistency: only {cstats['gws'] if cstats else 0} graded GW(s) — "
            f"not enough history to judge how spiky this player is."
        )

    recent = _recent_history(player_histories, pid, n=4)
    if recent:
        xgi = statistics.fmean(
            float(h.get("expected_goal_involvements") or 0) for h in recent
        )
        bps = statistics.fmean(float(h.get("bps") or 0) for h in recent)
        volume_note = (
            f"Underlying: {round(xgi, 2)} xGI and {round(bps)} BPS per game over "
            f"the last {len(recent)} — {'strong' if xgi >= 0.5 or bps >= 25 else 'modest'} "
            f"volume behind the points."
        )
    else:
        xgi = bps = None
        volume_note = "Underlying: no match history yet this season."

    duties = set_piece.get(pid, [])
    set_piece_note = (
        f"Set pieces: on {', '.join(duties)} — raises the floor."
        if duties else "Set pieces: no dead-ball duty."
    )

    dgw = int(row["team_id"]) in dgw_teams if _num(row, "team_id") is not None else False

    # score: ceiling first, then fixture outlier, consistency, volume, set pieces, DGW
    score = pts
    score += 2.0 if outlier else 0.0
    if cstd is not None:
        score += max(0.0, (TC_CONSISTENT_STD - cstd)) * 0.5
    if xgi is not None:
        score += min(xgi, 1.5)
    score += 0.75 * len(duties)
    score += 3.0 if dgw else 0.0

    return {
        "web_name": row["web_name"],
        "predicted_points": pts,
        "next_fixture": None if next_diff is None else f"{opp or '?'} ({where}), difficulty {next_diff}",
        "fixture_run_avg": run_avg,
        "fixture_outlier": bool(outlier),
        "fixture_note": fixture_note,
        "consistency_std": cstd,
        "consistency_note": consistency_note,
        "xgi_recent": None if xgi is None else round(xgi, 2),
        "bps_recent": None if bps is None else round(bps),
        "volume_note": volume_note,
        "set_piece_duties": duties,
        "set_piece_note": set_piece_note,
        "double_gameweek": dgw,
        "_score": score,
    }


# ======================================================================== #
# 3. Season accumulation — pace & "is it the strategy, not the model"       #
# ======================================================================== #

def season_accumulation_check(gw, tracker_history):
    """
    A different question from /predictions/accuracy (which grades the MODEL):
    is the real squad's points total keeping the pace a good rank needs, and
    is it consistently scoring BELOW its own predictions — which points at the
    strategy (transfer churn, hits, captaincy, bench) rather than the model.

    Args:
      gw: the current gameweek (for context only).
      tracker_history: dict assembled by the route:
        {
          "summaries":   tracker.get_gameweek_summaries(),
          "accuracy":    tracker.get_accuracy_report(),
          "hits":        {"total_cost": int|None, "transfers": int|None,
                          "per_gw": [{"gw", "cost", "transfers"}], }  # optional
        }

    Returns: verdict, season-to-date totals, the signals that fired, and a
    plain-language diagnosis of whether strategy or variance is the likely
    culprit.
    """
    summaries = sorted(tracker_history.get("summaries", []), key=lambda r: r["gw"])
    graded = [r for r in summaries if r.get("squad_actual_total") is not None]
    signals = []

    if not graded:
        return {
            "verdict": "not enough data",
            "season_to_date": {"graded_gameweeks": 0},
            "signals": [],
            "diagnosis": (
                "No completed gameweeks logged yet — come back once a few weeks "
                "have been backfilled and this can compare your pace and your "
                "squad-vs-prediction gap."
            ),
        }

    actual_total = sum(r["squad_actual_total"] for r in graded)
    predicted_total = sum(r["squad_predicted_total"] for r in graded
                          if r.get("squad_predicted_total") is not None)
    n = len(graded)
    ppg = actual_total / n
    delta = actual_total - predicted_total
    under_weeks = sum(
        1 for r in graded
        if r.get("squad_predicted_total") is not None
        and r["squad_actual_total"] < r["squad_predicted_total"]
    )

    hits = tracker_history.get("hits") or {}
    hits_cost = hits.get("total_cost")
    bench_points = hits.get("bench_points_total")

    # --- pace ---------------------------------------------------------
    if ppg >= GOOD_RANK_PACE:
        pace_verdict = "on track"
        signals.append(f"Averaging {round(ppg, 1)} pts/GW — at or above the ~{GOOD_RANK_PACE:g} a strong rank needs.")
    elif ppg >= GOOD_RANK_PACE - 6:
        pace_verdict = "slightly behind"
        signals.append(f"Averaging {round(ppg, 1)} pts/GW — a touch under the ~{GOOD_RANK_PACE:g} pace for a good rank.")
    else:
        pace_verdict = "below pace"
        signals.append(f"Averaging {round(ppg, 1)} pts/GW — well short of the ~{GOOD_RANK_PACE:g} pace for a good rank.")

    # --- squad vs its own predictions -------------------------------
    frac_under = under_weeks / n
    avg_shortfall = -delta / n
    enough_weeks = n >= MIN_GRADED_WEEKS_FOR_VERDICT
    underperforming = (
        enough_weeks
        and frac_under >= UNDERPERFORM_WEEK_FRACTION
        and avg_shortfall >= UNDERPERFORM_PER_WEEK
    )
    if not enough_weeks:
        if frac_under >= UNDERPERFORM_WEEK_FRACTION and avg_shortfall >= UNDERPERFORM_PER_WEEK:
            signals.append(
                f"Squad is {round(avg_shortfall, 1)} pts/wk under its predictions so far, "
                f"but only {n} week(s) are graded — too early to call it a pattern."
            )
        else:
            signals.append(
                f"Squad vs its predictions so far: {round(delta, 1):+} pts over {n} "
                f"week(s) — too little to read into yet."
            )
    elif underperforming:
        signals.append(
            f"Squad has scored under its own prediction in {under_weeks}/{n} graded "
            f"weeks, {round(avg_shortfall, 1)} pts/wk below on average "
            f"({round(delta, 1)} total) — the model rated the players higher than "
            f"they returned in your XI."
        )
    elif delta >= 0:
        signals.append(f"Squad is running {round(delta, 1)} pts ahead of its predictions season-to-date — no strategy red flag there.")
    else:
        signals.append(f"Squad is {round(abs(delta), 1)} pts under its predictions season-to-date, but within normal variance.")

    if hits_cost:
        signals.append(f"Transfer hits have cost {hits_cost} pts so far — that's {round(hits_cost / n, 1)} pts/GW straight off the top.")
    elif hits_cost == 0:
        signals.append("No points taken on transfer hits — churn isn't costing you directly.")

    if bench_points:
        signals.append(f"{bench_points} pts left on the bench so far ({round(bench_points / n, 1)}/GW) — an execution leak the model can't see.")

    # --- overall verdict + diagnosis ------------------------------
    if not enough_weeks:
        verdict = "too early to call"
        diagnosis = (
            f"Only {n} completed gameweek(s) logged — not enough to separate a "
            f"strategy problem from normal variance. The numbers above are shown "
            f"for context; check back after {MIN_GRADED_WEEKS_FOR_VERDICT}+ graded "
            f"weeks for a real read on pace and the squad-vs-prediction gap."
        )
    elif underperforming:
        verdict = "underperforming predictions"
        diagnosis = (
            "This looks like a STRATEGY problem, not a model problem. The model's "
            "player ratings are being graded separately on the Accuracy tab; here "
            "your actual XI keeps landing below them. Usual causes: captaincy "
            "misses, leaving points on the bench, or paying "
            + (f"hits ({hits_cost} pts) " if hits_cost else "hits ")
            + "that don't pay for themselves. Tighten those before changing how you "
            "pick players."
        )
    elif pace_verdict == "below pace":
        verdict = "below pace"
        diagnosis = (
            "Behind the pace for a strong finish, but the squad is roughly matching "
            "its predictions — so the issue is player-pool quality / budget "
            "allocation, not week-to-week execution. A Wildcard to reshape the "
            "squad is the lever here, not more transfers."
        )
    else:
        verdict = "on track"
        diagnosis = (
            "Pace and squad-vs-prediction gap both look healthy. No structural "
            "change needed — keep making only clear-value weekly moves."
        )

    return {
        "verdict": verdict,
        "season_to_date": {
            "current_gw": gw,
            "graded_gameweeks": n,
            "squad_actual_total": round(actual_total, 1),
            "squad_predicted_total": round(predicted_total, 1),
            "delta_vs_predictions": round(delta, 1),
            "avg_points_per_gw": round(ppg, 1),
            "good_rank_pace": GOOD_RANK_PACE,
            "weeks_under_prediction": under_weeks,
            "transfer_hits_cost": hits_cost,
            "bench_points_total": bench_points,
        },
        "pace_verdict": pace_verdict,
        "signals": signals,
        "diagnosis": diagnosis,
    }
