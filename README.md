# FPL Predictor — v1

Predicts a player's next-gameweek points from their last match's performance
and their upcoming fixture, then uses that to pick your best XI, suggest
transfers, and recommend chip timing (Bench Boost, Triple Captain, Wildcard,
Free Hit).

## Why this design

Two separate problems, two separate tools:

1. **"How many points will this player score next week?"** — genuinely
   uncertain, pattern-based → this is where ML (gradient boosting) belongs.
2. **"Given those predictions, what's the legal squad/captain/chip choice
   that maximizes points?"** — fully rule-bound, no uncertainty → this is
   a constrained optimization problem (integer programming), not something
   to train a model on. Rules are hardcoded and always obeyed exactly.

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage (run in order)

```bash
# 1. Pull data from the official FPL API (public, no key needed)
python src/fetch_data.py
# Takes a few minutes — one request per player (~700 players) with a
# small delay to be polite to the API. Re-running resumes from cache.

# 2. Build the training table (past match -> next match points)
python src/build_features.py

# 3. Train the prediction model (one model per position: GKP/DEF/MID/FWD)
python src/train_model.py

# 4. (next: predict.py — generates predictions for the upcoming gameweek)
# 5. Feed predictions into src/optimizer.py to get your best XI + chip advice
```

## Project structure

```
fpl-predictor/
├── data/                    # raw + processed data (gitignored, regenerate anytime)
│   ├── bootstrap.json       # players, teams, gameweeks
│   ├── fixtures.json        # full fixture list with difficulty ratings
│   ├── player_histories.json
│   └── training_table.csv   # engineered features, ready for the model
├── models/
│   └── position_models.joblib
└── src/
    ├── fetch_data.py        # pulls raw data from fantasy.premierleague.com/api
    ├── build_features.py    # raw JSON -> flat training table
    ├── train_model.py       # trains LightGBM regressor per position
    └── optimizer.py         # rule-based squad/chip decision engine (PuLP)
```

## What's next to build

- `predict.py`: apply the trained model to the CURRENT gameweek's players
  (their most recent match + next fixture) to get this week's predictions
- A small FastAPI wrapper around predict + optimizer, so you can hit an
  endpoint instead of running scripts
- A simple frontend (reuse your job-hunt tool's React + Tailwind setup)
  showing your squad, predicted points, and chip recommendations
- Track prediction accuracy week over week so you can see if it's actually
  beating "just pick highest-form player" as a baseline

## Deployment (once it's more than a personal script)

- **Backend**: FastAPI on Railway or Render (both have simple free/cheap
  Python deploys with cron-style scheduled jobs for weekly refresh)
- **Frontend**: Vercel
- **DB**: start with SQLite (file-based, zero setup); move to Postgres if
  you add multi-user support or historical tracking across seasons
- **Refresh schedule**: FPL matches finish Sun/Mon, deadlines are usually
  Fri — so a scheduled job Sat morning (after weekend fixtures + any
  Monday game resolve... actually just run it once all GW fixtures are
  marked "finished" in bootstrap-static) works well

## Honest limitations to know going in

- Predicting football is noisy. Expect the model's mean absolute error to
  land around 2-3 points per player — useful for *ranking* players
  relative to each other, not for exact score prediction.
- This model only uses last-match + fixture data. It doesn't know about
  injuries, rotation risk, or press conference news — you'll want to
  manually override predictions for players with flagged fitness news
  (bootstrap.json's `chance_of_playing_next_round` field helps here).
- Small sample sizes early in a season (like right now, GW2) mean the
  model has very little history to learn from. It'll get more useful as
  the season progresses. For the first few gameweeks, lean more on last
  season's data + underlying stats (xG/xA) than this model's raw output.
