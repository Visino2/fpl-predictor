"""
Rolling season-to-date form features.

The existing prev_* features only describe a player's single most recent
match. Once a season is a few gameweeks deep that stops representing real
form — one good match looks the same whether it followed three good weeks
or three bad ones. These features add the season average alongside the
single-match signal (both are kept — very recent form still matters for
rotation/injury reads).

Computed here in ONE place so build_features.py (current-season training
rows), fetch_historical.py (past-season training rows) and predict.py
(prediction rows) all derive them identically — train/inference skew here
would be silent and hard to spot.

"Season to date" = every match the player has played BEFORE the one being
predicted or labelled. Same definition in all three callers: a mid-season
training row sees the matches before its label gameweek; a prediction row
sees every match played so far this season.
"""

_TREND_WINDOW = 3       # "recent" = last 3 games
_FORM_TREND_MIN_GAMES = 4  # need 3 recent + >=1 earlier for a meaningful delta

# (feature name, match-record key). The keys are common to
# player_histories.json entries and the historical merged_gw.csv rows.
_AVG_FIELDS = [
    ("season_avg_points", "total_points"),
    ("season_avg_goals", "goals_scored"),
    ("season_avg_assists", "assists"),
    ("season_avg_xg", "expected_goals"),
    ("season_avg_xa", "expected_assists"),
    ("season_avg_minutes", "minutes"),
    ("season_avg_bps", "bps"),
    ("season_avg_ict", "ict_index"),
]

# Every feature this module produces — import into train_model.FEATURES and
# predict/build_features row dicts so the list stays in one place.
SEASON_FEATURES = [name for name, _ in _AVG_FIELDS] + ["season_games_played", "form_trend"]


def _val(rec, key):
    """Numeric match-record value, or 0.0 for missing / None / NaN / non-numeric."""
    v = rec.get(key, 0.0)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f  # NaN


def season_to_date_features(prior_matches):
    """
    prior_matches: the player's match records (dicts) from BEFORE the match
    being predicted/labelled. Sorted here by "round" when present, so callers
    don't have to. Returns a dict keyed by SEASON_FEATURES.

    Empty list -> all-zero averages, season_games_played 0, form_trend 0.0:
    exactly the "no season history yet" state in the opening weeks, which the
    trees can split on via season_games_played.
    """
    matches = list(prior_matches)
    if matches and "round" in matches[0]:
        matches = sorted(matches, key=lambda m: m["round"])
    n = len(matches)

    feats = {name: 0.0 for name, _ in _AVG_FIELDS}
    feats["season_games_played"] = n
    feats["form_trend"] = 0.0
    if n == 0:
        return feats

    for name, key in _AVG_FIELDS:
        feats[name] = sum(_val(m, key) for m in matches) / n

    # form_trend: last 3 games' mean points minus the mean of everything
    # before that. Positive = heating up, negative = cooling off, ~0 =
    # steady at the season average. Left at 0.0 until there are enough games
    # to actually compare the two windows.
    if n >= _FORM_TREND_MIN_GAMES:
        recent = matches[-_TREND_WINDOW:]
        earlier = matches[:-_TREND_WINDOW]
        recent_avg = sum(_val(m, "total_points") for m in recent) / len(recent)
        earlier_avg = sum(_val(m, "total_points") for m in earlier) / len(earlier)
        feats["form_trend"] = recent_avg - earlier_avg

    return feats
