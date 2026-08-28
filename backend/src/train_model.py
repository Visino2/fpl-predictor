"""
Trains a LightGBM regression model to predict a player's points in their
NEXT gameweek, based on their previous match performance + next fixture.

Why gradient boosting and not deep learning: this is small, tabular,
noisy sports data (a few thousand rows, ~15 features). Tree ensembles
consistently outperform neural nets on this kind of data and need far
less tuning.
"""
import os
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib

try:  # works both as `python src/train_model.py` and as the `src.train_model` package
    from .fetch_historical import SEASONS
    from .season_form import SEASON_FEATURES
except ImportError:
    from fetch_historical import SEASONS
    from season_form import SEASON_FEATURES

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

FEATURES = [
    "prev_minutes", "prev_points", "prev_goals", "prev_assists",
    "prev_xg", "prev_xa", "prev_bonus", "prev_bps", "prev_ict",
    "prev_clean_sheet", "prev_goals_conceded", "prev_was_home", "prev_value",
    "was_home", "fixture_difficulty", "opp_defence_strength", "opp_attack_strength",
    # rolling season-to-date form — kept ALONGSIDE the prev_* single-match
    # features, not replacing them (see season_form.py)
    *SEASON_FEATURES,
]
CATEGORICAL = []  # position handled separately below
TARGET = "target_points"

# Per-position training window: None = use every available season; an
# int N = only the N most-recent season labels (current season counts as
# the newest, then historical seasons newest-first). GKP defaults to a
# short window because multi-season data measurably hurt its accuracy
# (see analysis_followup_fixes.md) — tune here without touching train()
# below.
TRAINING_WINDOWS = {"GKP": 2, "DEF": None, "MID": None, "FWD": None}

# Most-recent-first ordering of every label that can appear in the
# "season" column — current-season rows are tagged "current" (see
# build_features.py); historical rows use fetch_historical.SEASONS' own
# labels, oldest-first there, so reversed here.
SEASON_RECENCY = ["current"] + list(reversed(SEASONS))


def _apply_training_window(sub, position):
    window = TRAINING_WINDOWS.get(position)
    if window is None:
        return sub
    allowed_seasons = set(SEASON_RECENCY[:window])
    return sub[sub["season"].isin(allowed_seasons)]


def train():
    df = pd.read_csv(os.path.join(DATA_DIR, "training_table.csv"))

    # one model per position tends to work better — a GK's points are driven
    # by totally different things (saves, clean sheets) than a forward's (goals)
    models = {}
    for position in df["position"].unique():
        sub = df[df["position"] == position].copy()
        sub = _apply_training_window(sub, position)
        if len(sub) < 50:
            print(f"Skipping {position}: not enough data ({len(sub)} rows)")
            continue

        X = sub[FEATURES]
        y = sub[TARGET]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        model = lgb.LGBMRegressor(
            n_estimators=300,
            learning_rate=0.03,
            max_depth=4,
            num_leaves=15,
            min_child_samples=20,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, y_train)

        preds = model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        window = TRAINING_WINDOWS.get(position)
        window_desc = "all seasons" if window is None else f"last {window} season label(s)"
        print(f"{position}: MAE = {mae:.2f} points ({len(sub)} rows, {window_desc})")

        models[position] = model

    joblib.dump(models, os.path.join(MODEL_DIR, "position_models.joblib"))
    print(f"Saved models -> {MODEL_DIR}/position_models.joblib")
    return models


if __name__ == "__main__":
    train()
