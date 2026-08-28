"""
Uses the trained per-position models to predict points for every player
for their NEXT gameweek — the one that hasn't happened yet.

Unlike build_features.py (which builds historical training rows with a
known "last match"), this script has to find each player's actual most
recent completed match and the actual upcoming fixture, since there's no
future match result to look up.

Output: a CSV ranked by predicted points, ready to feed into optimizer.py
"""
import os
import joblib
import pandas as pd

try:  # works both as `python src/predict.py` and as the `src.predict` package
    from .bootstrap_utils import get_upcoming_gw, load_json
    from .fixture_run import build_fixture_run, summarize_fixtures
    from .fetch_historical import get_last_season_team_strength
    from .season_form import season_to_date_features
    from .train_model import FEATURES
except ImportError:
    from bootstrap_utils import get_upcoming_gw, load_json
    from fixture_run import build_fixture_run, summarize_fixtures
    from fetch_historical import get_last_season_team_strength
    from season_form import season_to_date_features
    from train_model import FEATURES

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

# FEATURES is imported from train_model (single source of truth) — a local
# copy here silently drifted out of sync when features were added and broke
# inference with a shape mismatch.


def build_prediction_rows():
    bootstrap = load_json("bootstrap.json")
    fixtures = load_json("fixtures.json")
    histories = load_json("player_histories.json")

    upcoming_gw = get_upcoming_gw(bootstrap)
    print(f"Predicting for Gameweek {upcoming_gw}")

    # team strength lookup (same as build_features.py) — bootstrap.json
    # returns 0 for every team's attack/defence strength very early in a
    # season (FPL hasn't calculated real values yet); fall back to last
    # season's final ratings rather than silently treating 0 as "weakest
    # possible team", which would be wrong, not just imprecise.
    last_season_strength = get_last_season_team_strength()
    STRENGTH_KEYS = ("strength_attack_home", "strength_attack_away",
                      "strength_defence_home", "strength_defence_away")
    team_strength = {}
    fallback_count = 0
    for t in bootstrap["teams"]:
        s = {
            "name": t["name"],
            "short_name": t["short_name"],
            "strength_defence_home": t["strength_defence_home"],
            "strength_defence_away": t["strength_defence_away"],
            "strength_attack_home": t["strength_attack_home"],
            "strength_attack_away": t["strength_attack_away"],
        }
        if all(s[k] == 0 for k in STRENGTH_KEYS):
            fallback = last_season_strength.get(t["name"])
            if fallback:
                s.update(fallback)
                fallback_count += 1
                print(f"  {t['name']}: strength not calculated yet — using last season's ratings")
            else:
                for k in STRENGTH_KEYS:
                    s[k] = None
                print(f"  {t['name']}: strength not calculated yet, no historical fallback — leaving null")
        team_strength[t["id"]] = s
    print(f"Team strength: {fallback_count}/{len(bootstrap['teams'])} teams used last-season fallback")

    pos_map = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    player_meta = {
        p["id"]: {
            "web_name": p["web_name"],
            "position": pos_map[p["element_type"]],
            "team_id": p["team"],
            "now_cost": p["now_cost"] / 10,
            "status": p["status"],  # 'a' = available, 'i' = injured, 'd' = doubtful, 's' = suspended
            "chance_of_playing": p.get("chance_of_playing_next_round"),
        }
        for p in bootstrap["elements"]
    }

    # fixture for each team in the upcoming gameweek
    upcoming_fixture = {}
    for fx in fixtures:
        if fx["event"] != upcoming_gw:
            continue
        upcoming_fixture[fx["team_h"]] = {
            "opponent": fx["team_a"], "was_home": True,
            "difficulty": fx["team_h_difficulty"]
        }
        upcoming_fixture[fx["team_a"]] = {
            "opponent": fx["team_h"], "was_home": False,
            "difficulty": fx["team_a_difficulty"]
        }

    rows = []
    for pid_str, hist in histories.items():
        pid = int(pid_str)
        if pid not in player_meta:
            continue
        meta = player_meta[pid]

        gw_history = hist.get("history", [])
        if not gw_history:
            continue  # no matches played yet this season — skip (or fall back to last season)
        gw_history = sorted(gw_history, key=lambda x: x["round"])
        last_match = gw_history[-1]

        fixture = upcoming_fixture.get(meta["team_id"])
        if not fixture:
            continue  # team has no fixture next GW (blank gameweek)

        opp_strength = team_strength.get(fixture["opponent"], {})

        # season-to-date form: every match played so far this season (the
        # upcoming gameweek being predicted is unplayed, so it's all of them)
        season_feats = season_to_date_features(gw_history)

        rows.append({
            "player_id": pid,
            "web_name": meta["web_name"],
            "position": meta["position"],
            "team_id": meta["team_id"],
            "now_cost": meta["now_cost"],
            "status": meta["status"],
            "chance_of_playing": meta["chance_of_playing"],
            "opponent": opp_strength.get("short_name", "?"),

            # --- rolling season-to-date form (see season_form.py) ---
            **season_feats,

            "prev_minutes": last_match["minutes"],
            "prev_points": last_match["total_points"],
            "prev_goals": last_match["goals_scored"],
            "prev_assists": last_match["assists"],
            "prev_xg": float(last_match.get("expected_goals", 0) or 0),
            "prev_xa": float(last_match.get("expected_assists", 0) or 0),
            "prev_bonus": last_match["bonus"],
            "prev_bps": last_match["bps"],
            "prev_ict": float(last_match.get("ict_index", 0) or 0),
            "prev_clean_sheet": last_match["clean_sheets"],
            "prev_goals_conceded": last_match["goals_conceded"],
            "prev_was_home": int(last_match["was_home"]),
            "prev_value": last_match["value"] / 10,

            "was_home": int(fixture["was_home"]),
            "fixture_difficulty": fixture["difficulty"],
            "opp_defence_strength": opp_strength.get(
                "strength_defence_home" if fixture["was_home"] else "strength_defence_away"
            ),
            "opp_attack_strength": opp_strength.get(
                "strength_attack_home" if fixture["was_home"] else "strength_attack_away"
            ),
        })

    df = pd.DataFrame(rows)
    # Only fixture_difficulty is truly required — opp_defence_strength/
    # opp_attack_strength can legitimately be null for a team with no
    # historical fallback (see above), and LightGBM handles missing values
    # natively, same as train_model.py does. Dropping on all of FEATURES
    # would silently exclude every player on a newly-promoted team.
    df = df.dropna(subset=["fixture_difficulty"])
    return df, upcoming_gw


def predict():
    df, gw = build_prediction_rows()
    models = joblib.load(os.path.join(MODEL_DIR, "position_models.joblib"))

    predictions = []
    for position, model in models.items():
        sub = df[df["position"] == position].copy()
        if sub.empty:
            continue
        sub["predicted_points"] = model.predict(sub[FEATURES])
        predictions.append(sub)

    result = pd.concat(predictions, ignore_index=True)

    # flag players with fitness doubts so you can manually review, rather
    # than trusting the model blindly on players who might not even play
    result["fitness_flag"] = result.apply(
        lambda r: "⚠ doubtful/injured" if r["status"] != "a"
        or (r["chance_of_playing"] is not None and r["chance_of_playing"] < 75)
        else "",
        axis=1,
    )

    # Additive only — predicted_points above is still a single-gameweek number.
    # These two columns give chip-timing logic (optimizer.py) visibility into
    # the run of fixtures beyond just next week, without touching the model.
    fixture_run = build_fixture_run()
    result["avg_difficulty_next4"] = result["team_id"].map(
        lambda tid: fixture_run.get(tid, {}).get("avg_difficulty")
    )
    result["fixture_run_summary"] = result["team_id"].map(
        lambda tid: summarize_fixtures(fixture_run.get(tid, {}).get("fixtures", []))
    )

    result = result.sort_values("predicted_points", ascending=False)
    out_cols = ["player_id", "web_name", "position", "team_id", "now_cost", "opponent", "was_home",
                "predicted_points", "fitness_flag",
                "avg_difficulty_next4", "fixture_run_summary",
                # feature values behind the prediction — carried through so
                # optimizer.transfer_suggestions() can explain *why* one player
                # outscores another (form, fixture, opponent strength, fitness)
                "prev_points", "prev_minutes", "fixture_difficulty",
                "opp_defence_strength", "opp_attack_strength", "chance_of_playing"]
    out_path = os.path.join(DATA_DIR, f"predictions_gw{gw}.csv")
    result[out_cols].to_csv(out_path, index=False)
    print(f"Saved predictions -> {out_path}")
    print(result[out_cols].head(15).to_string(index=False))
    return result


if __name__ == "__main__":
    predict()
