"""
Pulls and normalizes several past seasons of full match-by-match FPL data
into one consolidated, training-ready CSV: data/historical_multi_season.csv.

fetch_data.py already bootstraps training with ONE prior season (see its
fetch_historical_season + build_features.build_historical_rows). This
extends that same idea to several seasons — more historical rows genuinely
means more for train_model.py to learn from before the current season has
enough of its own gameweeks — and normalizes them all up front into a
single file, rather than build_features.py re-normalizing per season on
every run.

Each output row is tagged with a "season" column (e.g. "2023-24") so the
model or future analysis can weight recent seasons differently if needed.
"""
import os

import pandas as pd

try:  # works both as `python src/fetch_historical.py` and as the `src.fetch_historical` package
    from .fetch_data import fetch_historical_season, DATA_DIR
    from .season_form import season_to_date_features
except ImportError:
    from fetch_data import fetch_historical_season, DATA_DIR
    from season_form import season_to_date_features

SEASONS = ["2023-24", "2024-25", "2025-26"]


def get_last_season_team_strength():
    """
    Team NAME -> last season's final attack/defence strength ratings
    (keyed by name, not id — historical season ids don't match current-
    season bootstrap ids). Used as a fallback by predict.py/build_features.py
    when bootstrap.json's own ratings are still zeroed out early in a new
    season (FPL hasn't calculated them yet). Reuses the teams.csv this
    module already downloads — no new fetch needed.

    Returns {} if the most recent season hasn't been fetched yet. A team
    with no top-flight history in that season (e.g. newly promoted) simply
    won't be in the returned dict — callers treat that as "no fallback."
    """
    if not SEASONS:
        return {}
    teams_path = os.path.join(DATA_DIR, "historical", SEASONS[-1], "teams.csv")
    if not os.path.exists(teams_path):
        return {}

    teams = pd.read_csv(teams_path)
    return {
        row["name"]: {
            "strength_attack_home": row["strength_attack_home"],
            "strength_attack_away": row["strength_attack_away"],
            "strength_defence_home": row["strength_defence_home"],
            "strength_defence_away": row["strength_defence_away"],
        }
        for _, row in teams.iterrows()
    }

POSITION_MAP = {"GK": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}

# The current season's bootstrap.json only has these 4 (see predict.py's
# pos_map) — some historical seasons also include "AM" (FPL's real-money
# "Manager" pickable position, e.g. an actual club manager like Mikel
# Arteta scored as a fantasy asset). Its scoring model is entirely
# team-result-based, nothing like the minutes/goals/saves features here,
# and predict.py would never predict for it anyway — so it's just noise
# in training, not a position the model needs to support.
VALID_POSITIONS = {"GKP", "DEF", "MID", "FWD"}


def normalize_season(season):
    """
    Same feature schema build_features.py uses for the current season — one
    row per (player, gameweek): prev-match features, next-fixture features,
    and the label. Self-contained within the season: player/team ids don't
    need to reconcile across seasons, since these rows only ever feed the
    trainer, never predict.py.
    """
    season_dir = os.path.join(DATA_DIR, "historical", season)
    gw_path = os.path.join(season_dir, "merged_gw.csv")
    if not os.path.exists(gw_path):
        print(f"{season}: no data on disk (fetch may have failed) — skipping")
        return pd.DataFrame()

    gw = pd.read_csv(gw_path)
    teams = pd.read_csv(os.path.join(season_dir, "teams.csv")).set_index("id")
    fixtures = pd.read_csv(os.path.join(season_dir, "fixtures.csv")).set_index("id")

    rows = []
    for element, group in gw.groupby("element"):
        recs = group.sort_values("round").to_dict("records")
        if len(recs) < 2:
            continue
        for i in range(1, len(recs)):
            prev, curr = recs[i - 1], recs[i]
            if curr["fixture"] not in fixtures.index or curr["opponent_team"] not in teams.index:
                continue
            position = POSITION_MAP.get(curr["position"], curr["position"])
            if position not in VALID_POSITIONS:
                continue
            fx = fixtures.loc[curr["fixture"]]
            opp = teams.loc[curr["opponent_team"]]
            was_home = bool(curr["was_home"])

            # season-to-date form: every match this player played before curr
            season_feats = season_to_date_features(recs[:i])

            rows.append({
                "season": season,
                "player_id": f"{season}_{element}",
                "web_name": curr["name"],
                "position": position,
                "team_id": None,
                "gw": curr["round"],

                # --- rolling season-to-date form (see season_form.py) ---
                **season_feats,

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
                "prev_was_home": int(bool(prev["was_home"])),
                "prev_value": prev["value"] / 10,

                "was_home": int(was_home),
                "fixture_difficulty": fx["team_h_difficulty"] if was_home else fx["team_a_difficulty"],
                "opp_defence_strength": opp["strength_defence_home" if was_home else "strength_defence_away"],
                "opp_attack_strength": opp["strength_attack_home" if was_home else "strength_attack_away"],

                "target_points": curr["total_points"],
            })

    print(f"{season}: {len(rows)} rows normalized")
    return pd.DataFrame(rows)


def build_multi_season_csv(seasons=SEASONS):
    for season in seasons:
        fetch_historical_season(season)  # no-op if already cached — see its own docstring

    frames = [normalize_season(s) for s in seasons]
    frames = [f for f in frames if not f.empty]

    if not frames:
        raise RuntimeError(f"No historical data could be normalized for any of {seasons}.")

    combined = pd.concat(frames, ignore_index=True)
    out_path = os.path.join(DATA_DIR, "historical_multi_season.csv")
    combined.to_csv(out_path, index=False)

    print(f"Saved {len(combined)} rows across {len(frames)}/{len(seasons)} seasons -> {out_path}")
    print(combined.groupby("season").size().to_string())
    return combined


if __name__ == "__main__":
    build_multi_season_csv()
