"""
This is NOT a machine-learned model — chip/squad decisions are governed by
fixed FPL rules, so they're solved as a constrained optimization problem
using integer programming (PuLP). This is the correct tool for "pick the
best legal combination given these constraints," and it will always obey
the rules exactly (unlike an ML model, which could hallucinate an illegal squad).

Feed it your predicted points per player (from train_model.py / predict.py)
and it picks the best XI, captain, and vice-captain.
"""
import pandas as pd
import pulp

SQUAD_RULES = {
    "GKP": {"squad": 2, "min_start": 1, "max_start": 1},
    "DEF": {"squad": 5, "min_start": 3, "max_start": 5},
    "MID": {"squad": 5, "min_start": 2, "max_start": 5},
    "FWD": {"squad": 3, "min_start": 1, "max_start": 3},
}
BUDGET = 100.0
MAX_PER_TEAM = 3
SQUAD_SIZE = 15
STARTING_XI = 11


def pick_best_xi(squad_df):
    """
    Given your current 15-man squad (with predicted_points), pick the
    legal starting XI that maximizes total predicted points, plus captain
    (2x) and vice-captain (backup 2x if captain doesn't play).

    squad_df needs columns: web_name, position, predicted_points
    """
    prob = pulp.LpProblem("pick_xi", pulp.LpMaximize)
    players = squad_df.index.tolist()
    start = pulp.LpVariable.dicts("start", players, cat="Binary")
    captain = pulp.LpVariable.dicts("captain", players, cat="Binary")

    # objective: predicted points, with captain doubled
    prob += pulp.lpSum(
        squad_df.loc[i, "predicted_points"] * start[i]
        + squad_df.loc[i, "predicted_points"] * captain[i]  # extra x1 on top of the x1 from starting
        for i in players
    )

    # exactly 11 starters
    prob += pulp.lpSum(start[i] for i in players) == STARTING_XI

    # exactly 1 captain, must be a starter
    prob += pulp.lpSum(captain[i] for i in players) == 1
    for i in players:
        prob += captain[i] <= start[i]

    # position constraints among starters
    for pos, rules in SQUAD_RULES.items():
        pos_players = [i for i in players if squad_df.loc[i, "position"] == pos]
        prob += pulp.lpSum(start[i] for i in pos_players) >= rules["min_start"]
        prob += pulp.lpSum(start[i] for i in pos_players) <= rules["max_start"]

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    starters = [i for i in players if pulp.value(start[i]) == 1]
    cap = [i for i in players if pulp.value(captain[i]) == 1][0]
    bench = [i for i in players if i not in starters]

    result = squad_df.loc[starters].copy()
    result["is_captain"] = result.index == cap
    return result.sort_values("predicted_points", ascending=False), squad_df.loc[bench]


def _formation(starters_df):
    """'D-M-F' outfield shape of an 11 (the 1 GK is implied)."""
    c = starters_df["position"].value_counts()
    return f"{int(c.get('DEF', 0))}-{int(c.get('MID', 0))}-{int(c.get('FWD', 0))}"


def _xi_players(starters_df):
    return [
        {
            "web_name": r["web_name"],
            "position": r["position"],
            "predicted_points": round(float(r["predicted_points"]), 1),
            "is_captain": bool(r.get("is_captain", False)),
        }
        for _, r in starters_df.sort_values("predicted_points", ascending=False).iterrows()
    ]


def recommend_lineup(squad_df):
    """
    Compare the ACTUAL starting XI (is_starter flags straight from the real
    FPL picks) against the optimizer's best legal XI picked from the same 15
    players — surfacing pick_best_xi(), which is otherwise only used
    internally.

    squad_df needs: web_name, position, predicted_points, is_starter, and
    ideally player_id. Any prev_* / fixture_* / opponent columns that happen
    to be present are reused to explain each swap, exactly like
    transfer_suggestions (via _transfer_reasons).

    Returns a dict:
      is_optimal              — your XI already equals the optimizer's pick
      actual / suggested      — {formation, predicted_points, players:[...]}
      predicted_points_gain   — suggested XI pts - actual XI pts (>= 0)
      swaps                   — [] when optimal, else one entry per change:
            {out, in, out_position, in_position,
             out_predicted_points, in_predicted_points, gain, reasons:[...]}
      note                    — plain-language summary; framed as a manual
                                suggestion, never an automatic change
    """
    df = squad_df.copy()
    df["predicted_points"] = pd.to_numeric(df["predicted_points"], errors="coerce").fillna(0.0)
    df["is_starter"] = df["is_starter"].fillna(False).astype(bool)

    actual_starters = df[df["is_starter"]]
    suggested_starters, _ = pick_best_xi(df)

    actual_pts = float(actual_starters["predicted_points"].sum())
    suggested_pts = float(suggested_starters["predicted_points"].sum())

    def _key(frame):
        if "player_id" in frame.columns and frame["player_id"].notna().all():
            return set(frame["player_id"])
        return set(frame["web_name"])

    is_optimal = _key(actual_starters) == _key(suggested_starters)

    result = {
        "is_optimal": is_optimal,
        "actual": {
            "formation": _formation(actual_starters),
            "predicted_points": round(actual_pts, 1),
            "players": _xi_players(actual_starters),
        },
        "suggested": {
            "formation": _formation(suggested_starters),
            "predicted_points": round(suggested_pts, 1),
            "players": _xi_players(suggested_starters),
        },
        "predicted_points_gain": round(suggested_pts - actual_pts, 1),
        "swaps": [],
    }

    if is_optimal:
        result["note"] = "Your lineup is already optimal for this gameweek."
        return result

    # players to bench (in your XI, not the optimizer's) vs players to start
    # (in the optimizer's XI, not yours). Pair same-position first — a GK
    # only ever swaps for the other GK, and a like-for-like DEF/MID/FWD swap
    # reads clearest — then pair whatever's left (a formation change) by
    # strength: weakest benched with strongest brought in.
    out_rows = actual_starters[~actual_starters.index.isin(suggested_starters.index)]
    in_rows = suggested_starters[~suggested_starters.index.isin(actual_starters.index)]
    outs = [r for _, r in out_rows.sort_values("predicted_points").iterrows()]
    ins = [r for _, r in in_rows.sort_values("predicted_points", ascending=False).iterrows()]

    pairs, used = [], set()
    for o in outs:
        match = next((j for j, n in enumerate(ins)
                      if j not in used and n["position"] == o["position"]), None)
        if match is not None:
            pairs.append((o, ins[match]))
            used.add(match)
    leftover_outs = [o for o in outs if not any(o is p[0] for p in pairs)]
    leftover_ins = [ins[j] for j in range(len(ins)) if j not in used]
    pairs.extend(zip(leftover_outs, leftover_ins))

    for o, n in pairs:
        result["swaps"].append({
            "out": o["web_name"],
            "in": n["web_name"],
            "out_position": o["position"],
            "in_position": n["position"],
            "out_predicted_points": round(float(o["predicted_points"]), 1),
            "in_predicted_points": round(float(n["predicted_points"]), 1),
            "gain": round(float(n["predicted_points"]) - float(o["predicted_points"]), 1),
            "reasons": _transfer_reasons(o, n),
        })
    result["swaps"].sort(key=lambda s: -s["gain"])

    n_swaps = len(result["swaps"])
    result["note"] = (
        f"You could start {result['swaps'][0]['in']} instead of "
        f"{result['swaps'][0]['out']}" + (f" (+{n_swaps - 1} more change"
        f"{'s' if n_swaps > 2 else ''})" if n_swaps > 1 else "")
        + f" for about +{result['predicted_points_gain']} projected pts this "
        f"gameweek. Make the change yourself in the FPL app if you agree — "
        f"this is a suggestion, not an automatic move."
    )
    return result


def _squad_avg_difficulty(squad_df, fixture_run_df, gw_window):
    """
    Mean fixture difficulty across the squad's teams over `gw_window`
    gameweeks starting at the earliest gameweek present in fixture_run_df.
    Returns None if there's nothing to compute (no fixture data passed, or
    squad_df has no team_id to join on) — callers treat that as "skip the
    fixture-run adjustment," not an error, since fixture_run_df is optional.
    """
    if fixture_run_df is None or fixture_run_df.empty or "team_id" not in squad_df.columns:
        return None
    start_gw = fixture_run_df["gw"].min()
    window = fixture_run_df[fixture_run_df["gw"] < start_gw + gw_window]
    team_avg = window.groupby("team_id")["difficulty"].mean()
    squad_teams = squad_df["team_id"].dropna().unique()
    relevant = team_avg.reindex(squad_teams).dropna()
    return round(relevant.mean(), 2) if not relevant.empty else None


def should_play_bench_boost(squad_df, fixture_run_df=None):
    """
    Bench Boost is worth it when your bench's combined predicted points
    is high relative to a normal gameweek — i.e. all 4 bench players have
    good, high-confidence fixtures (not just decent ones).
    Rule of thumb: worth it if bench predicted total > ~15-18 pts.

    fixture_run_df is optional (see fixture_run.to_dataframe) — when passed,
    a good bench total is downgraded if the squad's fixture run over the
    next 3 gameweeks is tough, since a high bench total in front of a rough
    run is weaker evidence than the same total heading into good fixtures
    (this week's spike is less likely to repeat, and a tough run ahead is
    itself a reason to wait for a better week to burn the chip). Omitting
    fixture_run_df keeps the original single-gameweek recommendation as-is.
    """
    starters, bench = pick_best_xi(squad_df)
    bench_total = bench["predicted_points"].sum()
    bench_strong = bench_total >= 15
    recommend = bench_strong

    result = {
        "bench_predicted_points": round(bench_total, 1),
        "recommend": recommend,
        "note": "Bench Boost adds your 4 bench players' points to your total. "
                "Only worth playing when your bench has strong fixtures too, "
                "not just your starting XI."
    }

    downgraded_for_fixtures = False
    avg_difficulty = _squad_avg_difficulty(squad_df, fixture_run_df, gw_window=3)
    if avg_difficulty is not None:
        result["squad_avg_difficulty_next3"] = avg_difficulty
        if recommend and avg_difficulty > 3.2:
            result["recommend"] = recommend = False
            downgraded_for_fixtures = True
            result["note"] += (
                f" Downgraded: bench total looks good this week, but the squad's "
                f"fixture run over the next 3 gameweeks is tough (avg difficulty "
                f"{avg_difficulty}) — consider waiting for an easier week."
            )
        elif not recommend and avg_difficulty <= 2.5:
            result["note"] += (
                f" Bench total isn't quite there yet, but fixtures are easing "
                f"(avg difficulty {avg_difficulty} over the next 3 gameweeks) — "
                f"worth reassessing soon."
            )

    # Headline states the ACTUAL reason for the verdict — the frontend renders
    # this verbatim, so it must never imply "wait for better fixtures" when the
    # real problem is a weak bench (that mismatch was the Chip Advice vs. Best
    # Gameweek contradiction — see chip_timing_consistency_warnings).
    bench_pts = result["bench_predicted_points"]
    if result["recommend"]:
        result["headline"] = "Worth playing this week"
    elif downgraded_for_fixtures:
        result["headline"] = (
            f"Hold — bench is strong ({bench_pts} pts) but the fixture run ahead "
            f"is tough; wait for an easier week"
        )
    else:
        result["headline"] = (
            f"Hold — bench only projects {bench_pts} pts, not enough to boost yet "
            f"(regardless of fixtures)"
        )

    return result


def should_play_triple_captain(squad_df, fixture_run_df=None):
    """
    Triple Captain is worth it when your best captain option's predicted
    points is a significant outlier vs. your next-best option — i.e. a
    double-gameweek premium player, or someone in outstanding form against
    a weak defence.

    fixture_run_df is optional (see fixture_run.to_dataframe) — when passed,
    the recommendation is downgraded if the captain's own fixture run over
    the next 2 gameweeks is tough, since a one-off predicted spike against a
    weak defence is a much weaker Triple Captain case if it's an outlier in
    an otherwise brutal run for that player's team. Omitting fixture_run_df
    keeps the original single-gameweek recommendation as-is.
    """
    starters, _ = pick_best_xi(squad_df)
    top2 = starters.sort_values("predicted_points", ascending=False).head(2)
    best, second = top2.iloc[0], top2.iloc[1]
    gap = best["predicted_points"] - second["predicted_points"]
    ceiling_ok = best["predicted_points"] >= 9
    gap_ok = gap >= 2
    recommend = ceiling_ok and gap_ok

    result = {
        "best_captain_option": best["web_name"],
        "predicted_points": round(best["predicted_points"], 1),
        "gap_to_next_best": round(gap, 1),
        "recommend": recommend,
        "note": "Triple Captain triples (not just doubles) your captain's points. "
                "Best used on a clear standout — often in a double gameweek."
    }

    downgraded_for_fixtures = False
    if fixture_run_df is not None and not fixture_run_df.empty and "team_id" in best.index:
        start_gw = fixture_run_df["gw"].min()
        window = fixture_run_df[fixture_run_df["gw"] < start_gw + 2]
        captain_fixtures = window[window["team_id"] == best["team_id"]]
        if not captain_fixtures.empty:
            captain_avg = round(captain_fixtures["difficulty"].mean(), 2)
            result["captain_avg_difficulty_next2"] = captain_avg
            if recommend and captain_avg > 3.5:
                result["recommend"] = recommend = False
                downgraded_for_fixtures = True
                result["note"] += (
                    f" Downgraded: this looks like a one-off spike — "
                    f"{best['web_name']}'s next fixtures are tough (avg difficulty "
                    f"{captain_avg}), so the captaincy case is weaker than the raw "
                    f"prediction suggests."
                )

    # Headline states the actual reason — see should_play_bench_boost's note.
    name = best["web_name"]
    pts = result["predicted_points"]
    if result["recommend"]:
        result["headline"] = "Worth playing this week"
    elif downgraded_for_fixtures:
        result["headline"] = (
            f"Hold — {name} projects {pts} but a tough fixture run makes it a "
            f"likely one-off; wait for a cleaner spot"
        )
    elif not ceiling_ok:
        result["headline"] = (
            f"Hold — no standout captain this week ({name} tops the squad at only "
            f"{pts} pts)"
        )
    else:  # ceiling fine, gap too small
        result["headline"] = (
            f"Hold — {name} ({pts}) isn't clear enough of your next-best option "
            f"(+{result['gap_to_next_best']}); little upside over a normal captain"
        )

    return result


def suggest_chip_timing(squad_df, fixture_run_df):
    """
    Scans every gameweek in fixture_run_df and ranks it as a chip-play
    opportunity, instead of only judging the current week (that's what
    should_play_bench_boost / should_play_triple_captain do).

    We don't have per-future-gameweek predicted_points — predict.py only
    forecasts the next single gameweek — so this uses each player's CURRENT
    predicted_points as the best available estimate of their underlying
    quality/form, and re-weights it per gameweek by how favorable that
    gameweek's fixture is (FPL difficulty 1-5, lower = easier). That's a
    heuristic for "which upcoming gameweek suits this squad best", not a
    real forecast of future points — treat predicted_gain as a ranking
    signal, not a promised score.

    Only covers Bench Boost and Triple Captain. Wildcard and Free Hit are
    full squad-rebuild decisions with no equivalent single-squad scoring
    function yet (there's no should_play_wildcard to extend), so there's
    nothing here to rank a gameweek against for those two.

    Returns a list of {gameweek, chip, reason, predicted_gain, worth_playing},
    sorted by predicted_gain descending within each chip. `worth_playing` is
    the ABSOLUTE bar (same thresholds as should_play_bench_boost /
    should_play_triple_captain), so a caller can tell "GW2 is the best of a
    bad bunch" from "GW2 is genuinely a play" — the ranking alone can't.
    """
    if fixture_run_df is None or fixture_run_df.empty or "team_id" not in squad_df.columns:
        return []

    starters, bench = pick_best_xi(squad_df)
    top2 = starters.sort_values("predicted_points", ascending=False).head(2)
    captain_row = top2.iloc[0]
    captain_gap = float(top2.iloc[0]["predicted_points"]) - float(top2.iloc[1]["predicted_points"])
    bench_total = bench["predicted_points"].sum()
    # same gates as should_play_* — kept here so both features agree on
    # "is this chip actually worth playing", independent of which week ranks top
    bb_worth_playing = bool(bench_total >= 15)
    tc_worth_playing = bool(captain_row["predicted_points"] >= 9 and captain_gap >= 2)
    squad_teams = squad_df["team_id"].dropna().unique()

    def difficulty_weight(diff):
        # 1 (easiest) -> 1.0x, 5 (hardest) -> 0.2x
        return max((6 - diff) / 5, 0.2)

    suggestions = []
    for gw in sorted(fixture_run_df["gw"].unique()):
        gw_fixtures = fixture_run_df[fixture_run_df["gw"] == gw]

        squad_fixtures = gw_fixtures[gw_fixtures["team_id"].isin(squad_teams)]
        if not squad_fixtures.empty:
            squad_avg_diff = round(squad_fixtures["difficulty"].mean(), 2)
            suggestions.append({
                "gameweek": int(gw),
                "chip": "Bench Boost",
                "reason": f"Bench predicted {round(bench_total, 1)} pts at current form; "
                          f"squad's avg fixture difficulty this gameweek is {squad_avg_diff}.",
                "predicted_gain": round(bench_total * difficulty_weight(squad_avg_diff), 1),
                "worth_playing": bb_worth_playing,
            })

        captain_fixtures = gw_fixtures[gw_fixtures["team_id"] == captain_row.get("team_id")]
        if not captain_fixtures.empty:
            captain_diff = round(captain_fixtures["difficulty"].mean(), 2)
            suggestions.append({
                "gameweek": int(gw),
                "chip": "Triple Captain",
                "reason": f"{captain_row['web_name']} predicted "
                          f"{round(captain_row['predicted_points'], 1)} pts at current form; "
                          f"fixture difficulty this gameweek is {captain_diff}.",
                "predicted_gain": round(captain_row["predicted_points"] * difficulty_weight(captain_diff), 1),
                "worth_playing": tc_worth_playing,
            })

    suggestions.sort(key=lambda s: (s["chip"], -s["predicted_gain"]))
    return suggestions


def chip_timing_consistency_warnings(current_gw, timing_suggestions, bench_boost, triple_captain):
    """
    Guardrail against the "Chip Advice card says hold / Best Gameweek list says
    play now" contradiction.

    The invariant: if suggest_chip_timing() ranks the CURRENT gameweek #1 for a
    chip AND marks it worth_playing (clears the same absolute bar
    should_play_*() uses), then should_play_*() for that chip must also
    recommend playing it now. A mismatch means the two threshold checks have
    drifted apart — a real logic bug, since both get the same squad and the
    same fixture_run_df from the route.

    worth_playing is part of the condition on purpose: suggest_chip_timing
    always has *some* #1 gameweek (it's a pure ranking), so "current GW is #1
    but nothing clears the bar" is not a contradiction — both features are
    saying "not yet", and the UI shows the list as relative-only. Only a #1
    that claims to clear the bar while the verdict says hold is inconsistent.

    Pure function; returns human-readable warning strings (empty when
    consistent). The route logs them — it never raises, so drift degrades to a
    log line, not a 500.
    """
    verdict_for = {"Bench Boost": bench_boost, "Triple Captain": triple_captain}
    ranked_for = {}
    for s in timing_suggestions:
        ranked_for.setdefault(s["chip"], []).append(s)  # already gain-sorted within chip

    warnings = []
    for chip, verdict in verdict_for.items():
        ranked = ranked_for.get(chip)
        if not ranked or verdict is None:
            continue
        top = ranked[0]
        if (
            int(top["gameweek"]) == int(current_gw)
            and top.get("worth_playing")
            and not verdict.get("recommend")
        ):
            warnings.append(
                f"{chip}: suggest_chip_timing ranks the current GW{current_gw} #1 "
                f"and worth_playing=True (predicted_gain +{top['predicted_gain']}), "
                f"but should_play_* returned recommend={verdict.get('recommend')} — "
                f"\"{verdict.get('headline') or verdict.get('note')}\". The two "
                f"threshold checks disagree for GW{current_gw}; the Chip Advice "
                f"card and the Best Gameweek panel will contradict each other."
            )
    return warnings


# Minimum gap on each feature before it's worth mentioning as a reason — below
# this the two players are effectively level on that dimension and saying so
# would just be noise.
_REASON_THRESHOLDS = {
    "fixture_difficulty": 1.0,   # FPL's 1-5 integer scale
    "avg_difficulty_next4": 0.5,
    "prev_points": 2.0,          # points scored in their last match
    "prev_minutes": 20.0,        # minutes in their last match
    "opp_strength": 40.0,        # FPL team-strength units (~1000-1400 range)
}


def _num(row, key):
    """Row value as float, or None if the column is absent / NaN."""
    if key not in row:
        return None
    val = row[key]
    return float(val) if pd.notna(val) else None


def _fmt(x):
    """Trim trailing .0 so '90.0' prints as '90' but '2.5' stays '2.5'."""
    if x is None:
        return "?"
    return f"{x:g}"


def _transfer_reasons(out_row, in_row):
    """
    Human-readable clauses explaining why `in_row` is predicted to outscore
    `out_row`, derived from the actual feature columns predict.py writes to
    predictions_gw{N}.csv. Only differences past _REASON_THRESHOLDS are
    included, so near-identical stats don't pad the list. Each clause is
    self-contained ("easier next fixture (difficulty 2 vs 4)") and phrased
    from the incoming player's side; the frontend prefixes the player name.

    Returns [] when nothing meaningful separates them (the raw predicted-points
    gap still stands on its own in that case).
    """
    reasons = []
    in_name, out_name = in_row["web_name"], out_row["web_name"]

    # --- recent form: last match points & minutes -------------------------
    ip, op = _num(in_row, "prev_points"), _num(out_row, "prev_points")
    if ip is not None and op is not None and ip - op >= _REASON_THRESHOLDS["prev_points"]:
        reasons.append(f"better recent form ({_fmt(ip)} vs {_fmt(op)} pts last match)")

    imin, omin = _num(in_row, "prev_minutes"), _num(out_row, "prev_minutes")
    if imin is not None and omin is not None and imin - omin >= _REASON_THRESHOLDS["prev_minutes"]:
        reasons.append(f"more minutes last match ({_fmt(imin)} vs {_fmt(omin)})")

    # --- next fixture difficulty (lower is easier) ------------------------
    idiff, odiff = _num(in_row, "fixture_difficulty"), _num(out_row, "fixture_difficulty")
    if idiff is not None and odiff is not None and odiff - idiff >= _REASON_THRESHOLDS["fixture_difficulty"]:
        reasons.append(f"easier next fixture (difficulty {_fmt(idiff)} vs {_fmt(odiff)})")

    # --- opponent strength for the next fixture --------------------------
    # An attacker cares about the opponent's DEFENCE; a defender/keeper cares
    # about the opponent's ATTACK. Lower opponent strength on the relevant
    # side favours the incoming player.
    pos = in_row.get("position")
    if pos in ("GKP", "DEF"):
        key, label = "opp_attack_strength", "weaker opponent attack"
    else:
        key, label = "opp_defence_strength", "weaker opponent defence"
    istr, ostr = _num(in_row, key), _num(out_row, key)
    if istr is not None and ostr is not None and ostr - istr >= _REASON_THRESHOLDS["opp_strength"]:
        reasons.append(f"{label} ({_fmt(istr)} vs {_fmt(ostr)})")

    # --- fixture run over the next 4 (optional lookahead) ---------------
    irun, orun = _num(in_row, "avg_difficulty_next4"), _num(out_row, "avg_difficulty_next4")
    if irun is not None and orun is not None and orun - irun >= _REASON_THRESHOLDS["avg_difficulty_next4"]:
        reasons.append(f"kinder fixture run ({_fmt(round(irun, 1))} vs {_fmt(round(orun, 1))} avg, next 4)")

    # --- fitness doubts on either side ---------------------------------
    def _doubt(row):
        chance = _num(row, "chance_of_playing")
        if chance is not None and chance < 100:
            return f"{_fmt(chance)}% to play"
        flag = row.get("fitness_flag")
        if flag is not None and pd.notna(flag) and str(flag).strip():
            return "flagged doubtful"
        return None

    out_doubt, in_doubt = _doubt(out_row), _doubt(in_row)
    if out_doubt and not in_doubt:
        reasons.append(f"{out_name} is a fitness doubt ({out_doubt})")
    elif in_doubt and not out_doubt:
        reasons.append(f"note: {in_name} carries a fitness doubt ({in_doubt})")
    elif in_doubt and out_doubt:
        reasons.append(f"both carry fitness doubts ({in_name} {in_doubt}, {out_name} {out_doubt})")

    return reasons


def transfer_suggestions(current_squad_df, all_players_df, free_transfers=1, hit_cost=4, bank_balance=0):
    """
    Suggests swaps: for each squad player, check if there's a same-position,
    affordable, higher-predicted-points replacement available.

    budget_cap uses your REAL bank balance (leftover budget from
    /entry/{id}, passed in by the caller — see api/routes/squad.py), not
    just the outgoing player's own price: if you have money in the bank,
    you can afford a pricier replacement than a straight swap would allow.
    bank_balance defaults to 0 for backward compatibility with callers that
    don't have it (equivalent to the old hardcoded-0 behavior).

    Ranks all worthwhile upgrades by predicted gain, then labels the top
    `free_transfers` of them "free" (making that many transfers costs
    nothing this week) and the rest "costs -{hit_cost}" (a paid transfer)
    — a paid one is only kept if its predicted_gain still beats the hit
    cost, since taking a hit that doesn't pay for itself isn't worth
    recommending at all.
    """
    suggestions = []

    for idx, player in current_squad_df.iterrows():
        pos = player["position"]
        budget_cap = player["now_cost"] + bank_balance
        candidates = all_players_df[
            (all_players_df["position"] == pos)
            & (all_players_df["now_cost"] <= budget_cap)
            & (~all_players_df["web_name"].isin(current_squad_df["web_name"]))
        ].sort_values("predicted_points", ascending=False)

        if candidates.empty:
            continue

        best = candidates.iloc[0]
        gain = best["predicted_points"] - player["predicted_points"]
        if gain > 0.5:  # only flag meaningful upgrades (gate on the precise gap)
            # Display values: round the two endpoints first, then derive the
            # shown gain from them, so the card's "1.8 -> 4.9  +3.1" always adds
            # up rather than showing a rounding-mismatched "+3.0".
            out_pp = round(float(player["predicted_points"]), 1)
            in_pp = round(float(best["predicted_points"]), 1)
            suggestions.append({
                "out": player["web_name"],
                "in": best["web_name"],
                "out_predicted_points": out_pp,
                "in_predicted_points": in_pp,
                "predicted_gain": round(in_pp - out_pp, 1),
                "cost_change": round(best["now_cost"] - player["now_cost"], 1),
                "reasons": _transfer_reasons(player, best),
            })

    suggestions = sorted(suggestions, key=lambda x: -x["predicted_gain"])

    labeled = []
    for i, s in enumerate(suggestions):
        if i < free_transfers:
            s["transfer_cost"] = "free"
        else:
            if s["predicted_gain"] <= hit_cost:
                continue  # a hit that doesn't pay for itself isn't worth recommending
            s["transfer_cost"] = f"costs -{hit_cost}"
        labeled.append(s)

    return labeled[:5]  # top 5 candidate swaps


if __name__ == "__main__":
    # Example usage with dummy data — replace with real predictions from predict.py
    demo_squad = pd.DataFrame([
        {"web_name": "Pedro", "position": "FWD", "predicted_points": 8.2, "now_cost": 7.5},
        {"web_name": "Haaland", "position": "FWD", "predicted_points": 9.1, "now_cost": 14.5},
        {"web_name": "Fernandes", "position": "MID", "predicted_points": 6.5, "now_cost": 8.5},
    ])
    print(demo_squad)
