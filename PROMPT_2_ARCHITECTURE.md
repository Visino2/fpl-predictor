# FPL Predictor — ARCHITECTURE PROMPT
(Paste this as a second, separate instruction — after the structure prompt.
This explains WHY the system is shaped this way and HOW data flows, so an
AI coding assistant doesn't quietly merge components together.)

## Core architectural principle: two decoupled systems, one pipeline

This app is not "one AI that plays FPL." It is two independent systems
chained together:

**System 1 — Prediction Engine (machine learning, genuinely uncertain)**
Answers: "How many points will this specific player score in their next
match?" This is learned from data because it's a real forecasting problem
— nobody, including FPL's own algorithm, knows this with certainty.

**System 2 — Decision Engine (rule-based, zero uncertainty)**
Answers: "Given these predictions, what's the legal squad, captain, and
chip choice that maximizes points?" This is NOT learned. FPL's rules
(budget £100m, max 3 players per real team, exact squad composition,
chip effects) are fixed and public. Solving this correctly means using
constrained optimization (integer programming via PuLP), not training a
model to "guess" good squads. An ML model asked to pick a squad can output
an illegal one (wrong budget, 4 players from one team); an optimizer
mathematically cannot.

Keeping these separate means: if your predictions are mediocre, your squad
logic is still 100% rule-compliant. And if you improve the model later,
you don't have to touch the optimizer at all.

## Data flow (this is the actual pipeline, in order)

```
┌─────────────────┐
│ FPL Official API │  (free, public, no key — fantasy.premierleague.com/api)
└────────┬─────────┘
         │ fetch_data.py
         ▼
┌─────────────────────────────────┐
│ Raw JSON: bootstrap, fixtures,   │
│ per-player match histories       │
└────────┬─────────────────────────┘
         │ build_features.py
         │ (joins: player's last match stats + their NEXT opponent's
         │  attack/defence strength + home/away + fixture difficulty)
         ▼
┌─────────────────────────────────┐
│ training_table.csv               │  one row per (player, past gameweek)
│ features: prev_minutes,          │  label: points actually scored
│ prev_goals, prev_xg, prev_bps,   │  that gameweek
│ fixture_difficulty, opp_strength │
└────────┬─────────────────────────┘
         │ train_model.py
         │ (LightGBM gradient boosting — ONE MODEL PER POSITION,
         │  because a GK scores points from saves/clean sheets,
         │  a forward from goals — totally different feature importance)
         ▼
┌─────────────────────────────────┐
│ position_models.joblib           │  4 trained models: GKP, DEF, MID, FWD
└────────┬─────────────────────────┘
         │ predict.py
         │ (applies models to CURRENT squad's most recent match +
         │  their actual upcoming fixture — this is System 1's final output)
         ▼
┌─────────────────────────────────┐
│ predictions_gw{N}.csv            │  predicted_points per player, ranked
└────────┬─────────────────────────┘
         │ optimizer.py  ← SYSTEM 2 STARTS HERE, NO ML BEYOND THIS POINT
         │ (PuLP integer programming: max predicted points subject to
         │  FPL's actual rules — formation limits, captain=2x, budget)
         ▼
┌─────────────────────────────────┐
│ Best legal XI + captain +        │
│ chip recommendation + transfer   │
│ suggestions                       │
└────────┬─────────────────────────┘
         │ FastAPI wraps this
         ▼
┌─────────────────────────────────┐
│ React frontend renders it on     │
│ the pitch graphic                │
└───────────────────────────────────┘
```

## Why gradient boosting (LightGBM) and not a neural network

This is small, noisy, tabular data — a few thousand rows, ~17 features,
updated weekly. Tree ensembles (LightGBM/XGBoost) are the standard choice
here and consistently beat neural nets on this kind of data without heavy
tuning. Every serious open-source FPL prediction project (vaastav's
dataset consumers, OpenFPL, several university course projects) converges
on gradient boosting or random forests, not deep learning, for exactly
this reason — this isn't a hunch, it's the community consensus after
years of people trying LSTMs and neural tabular models and getting worse
results than plain XGBoost.

## Why per-position models instead of one global model

A goalkeeper's points come overwhelmingly from saves, clean sheets, and
minutes played. A forward's come from goals and assists. Feeding both
into one model dilutes feature importance and produces worse predictions
for both. Splitting by position (GKP/DEF/MID/FWD) is standard practice in
every FPL ML project referenced above.

## Why the chip logic is explicit rules, not learned thresholds

Bench Boost, Triple Captain, Wildcard, and Free Hit each have one
specific, unambiguous effect defined by FPL's rules (e.g., Triple Captain
= captain's points × 3 instead of × 2, for exactly one gameweek). There is
nothing to learn here — the "decision" is just: given predicted points,
compute the expected gain of playing the chip this week vs. saving it,
using its known mathematical effect. Encode this as explicit comparison
logic in optimizer.py, not as another ML model.

## API layer responsibility

FastAPI (`backend/api/`) is a thin wrapper. It should not contain any
prediction or optimization logic itself — it calls into `backend/src/`
functions and serializes the result. If you find business logic creeping
into a route file, move it into `src/`.

## State & caching

- `data/bootstrap.json` and `fixtures.json` change slowly (a few times a
  week at most) — refetch once per day is enough.
- `player_histories.json` only changes after matches are played — refetch
  once per gameweek, after all that gameweek's fixtures show
  `"finished": true"` in bootstrap-static.
- Predictions (`predictions_gw{N}.csv`) should be regenerated once per
  gameweek cycle, not on every page load. Cache in the API layer (simple
  in-memory cache or a timestamp check is enough for a single-user app).
