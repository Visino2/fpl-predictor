"""
Turns raw FPL JSON into a flat table: one row per (player, gameweek),
with features about their PREVIOUS match(es) and their NEXT fixture,
and the label being points actually scored in that next gameweek.

This is the table the model trains on.
"""
import json
import os
import pandas as pd

try:  # works both as `python src/build_features.py` and as the `src.build_features` package
    from .fetch_historical import get_last_season_team_strength
    from .season_form import season_to_date_features
except ImportError:
    from fetch_historical import get_last_season_team_strength
    from season_form import season_to_date_features

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

STRENGTH_KEYS = ("strength_attack_home", "strength_attack_away",
                  "strength_defence_home", "strength_defence_away")


def load_json(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


def build_team_strength_lookup(bootstrap):
    """
    Team id -> attack/defence strength (home & away), from bootstrap.
    bootstrap.json returns 0 for every team's attack/defence strength very
    early in a season (FPL hasn't calculated real values yet) — falls back
    to last season's final ratings (see fetch_historical.py) rather than
    silently treating 0 as "weakest possible team". A team with no
    top-flight history to fall back to (e.g. newly promoted) gets null,
    not a fake 0 — dropna/LightGBM's native missing-value handling deal
    with that correctly downstream, same as predict.py.
    """
    last_season_strength = get_last_season_team_strength()
    lookup = {}
    fallback_count = 0
    for t in bootstrap["teams"]:
        s = {
            "name": t["name"],
            "strength_overall_home": t["strength_overall_home"],
            "strength_overall_away": t["strength_overall_away"],
            "strength_attack_home": t["strength_attack_home"],
            "strength_attack_away": t["strength_attack_away"],
            "strength_defence_home": t["strength_defence_home"],
            "strength_defence_away": t["strength_defence_away"],
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
        lookup[t["id"]] = s
    if fallback_count:
        print(f"Team strength: {fallback_count}/{len(bootstrap['teams'])} teams used last-season fallback")
    return lookup


def build_player_meta(bootstrap):
    """Player id -> name, position, team, current price."""
    pos_map = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    meta = {}
    for p in bootstrap["elements"]:
        meta[p["id"]] = {
            "name": f"{p['first_name']} {p['second_name']}",
            "web_name": p["web_name"],
            "position": pos_map[p["element_type"]],
            "team_id": p["team"],
            "now_cost": p["now_cost"] / 10,
            "selected_by_percent": float(p["selected_by_percent"]),
        }
    return meta


def build_training_table():
    bootstrap = load_json("bootstrap.json")
    fixtures = load_json("fixtures.json")
    histories = load_json("player_histories.json")

    team_strength = build_team_strength_lookup(bootstrap)
    player_meta = build_player_meta(bootstrap)

    # fixture_id -> (opponent team, was_home, difficulty) per team, per gw
    fixture_lookup = {}  # (team_id, event) -> fixture info
    for fx in fixtures:
        if fx["event"] is None:
            continue
        fixture_lookup[(fx["team_h"], fx["event"])] = {
            "opponent": fx["team_a"], "was_home": True,
            "difficulty": fx["team_h_difficulty"]
        }
        fixture_lookup[(fx["team_a"], fx["event"])] = {
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
        if len(gw_history) < 2:
            continue  # need at least one prior match to predict the next

        # sort by gameweek/round just in case
        gw_history = sorted(gw_history, key=lambda x: x["round"])

        for i in range(1, len(gw_history)):
            prev = gw_history[i - 1]
            curr = gw_history[i]  # this is the LABEL gameweek

            next_fixture = fixture_lookup.get((meta["team_id"], curr["round"]))
            opp_strength = None
            if next_fixture:
                opp = next_fixture["opponent"]
                opp_strength = team_strength.get(opp, {})

            # season-to-date form: every match BEFORE this label gameweek
            season_feats = season_to_date_features(gw_history[:i])

            rows.append({
                "season": "current",
                "player_id": pid,
                "web_name": meta["web_name"],
                "position": meta["position"],
                "team_id": meta["team_id"],
                "gw": curr["round"],

                # --- features: rolling season-to-date form (see season_form.py) ---
                **season_feats,

                # --- features: derived from the PREVIOUS match ---
                "prev_minutes": prev["minutes"],
                "prev_points": prev["total_points"],
                "prev_goals": prev["goals_scored"],
                "prev_assists": prev["assists"],
                "prev_xg": float(prev.get("expected_goals", 0) or 0),
                "prev_xa": float(prev.get("expected_assists", 0) or 0),
                "prev_bonus": prev["bonus"],
                "prev_bps": prev["bps"],
                "prev_ict": float(prev.get("ict_index", 0) or 0),
                "prev_clean_sheet": prev["clean_sheets"],
                "prev_goals_conceded": prev["goals_conceded"],
                "prev_was_home": int(prev["was_home"]),
                "prev_value": prev["value"] / 10,

                # --- features: about the NEXT fixture (the one we predict for) ---
                "was_home": int(curr["was_home"]),
                "fixture_difficulty": next_fixture["difficulty"] if next_fixture else None,
                "opp_defence_strength": (
                    opp_strength.get("strength_defence_home" if curr["was_home"]
                                      else "strength_defence_away")
                    if opp_strength else None
                ),
                "opp_attack_strength": (
                    opp_strength.get("strength_attack_home" if curr["was_home"]
                                      else "strength_attack_away")
                    if opp_strength else None
                ),

                # --- label: what actually happened ---
                "target_points": curr["total_points"],
            })

    print(f"Current season: {len(rows)} training rows")
    df = pd.DataFrame(rows)

    # Multi-season historical data (see fetch_historical.py) — already
    # normalized to this same row shape and tagged with its own "season"
    # column, so it's a straight concat, not a re-derivation.
    multi_season_path = os.path.join(DATA_DIR, "historical_multi_season.csv")
    if os.path.exists(multi_season_path):
        historical_df = pd.read_csv(multi_season_path)
        print(f"Historical (multi-season): {len(historical_df)} training rows")
        df = pd.concat([df, historical_df], ignore_index=True)

    if df.empty:
        raise RuntimeError(
            "No training rows could be built — the current season has fewer "
            "than 2 completed gameweeks, and no historical data was found at "
            "data/historical_multi_season.csv. Run fetch_historical.py first."
        )

    df = df.dropna(subset=["fixture_difficulty"])  # drop rows we couldn't match a fixture for
    out_path = os.path.join(DATA_DIR, "training_table.csv")
    df.to_csv(out_path, index=False)
    print(f"Built training table: {len(df)} rows -> {out_path}")
    return df


if __name__ == "__main__":
    build_training_table()
