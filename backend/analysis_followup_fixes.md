# Follow-up fixes: dead features and GKP's training window

## Fix 1 — opp_attack_strength / opp_defence_strength fallback

### Coverage: before vs after

| | Before | After |
|---|---|---|
| Teams with real (non-zero) strength | 0 / 20 | 17 / 20 (last-season fallback) |
| Teams left null (no fallback) | 20 / 20 (fake 0, not really "null") | 3 / 20 — **Coventry City, Hull City, Ipswich Town** (correctly: none of these were in the top flight in 2025-26, so there's nothing to fall back to) |

The fallback source is `historical/2025-26/teams.csv` — already downloaded by `fetch_historical.py`, no new fetch needed, matched to current teams by name (ids don't carry across seasons).

### The bigger finding: this wasn't just a "dead feature," it was an out-of-distribution bug

Checking `training_table.csv` (84,275 rows, spanning 3 seasons): **`opp_attack_strength` ranges 910–1400, `opp_defence_strength` ranges 990–1400, and zero rows have a value of 0.** The model has never once seen a 0 in either feature during training — every historical season's own `teams.csv` always had real values in that ~900–1400 band.

That means every prediction `predict.py` produced this whole season, before this fix, fed the model a value roughly 1000 points below the lowest number it had ever been trained on. This is worse than "the feature contributes nothing" (the original framing in `analysis_verbruggen_vs_kinsky.md`) — it was actively extrapolating outside the model's learned range on every single prediction, for every player, all season.

**No retraining was needed to fix this** — the existing model (already trained on real, non-zero historical values) just needed to be fed sane inputs. This is purely a `predict.py`/`build_features.py` change.

### Re-checking Verbruggen vs Kinsky after the fix

| | Before | After |
|---|---|---|
| Verbruggen predicted_points | 4.79 | **2.30** |
| Kinsky predicted_points | 5.15 | **3.19** |
| opp_defence_strength (Verbruggen, vs Chelsea) | 0 | 1250 |
| opp_attack_strength (Verbruggen, vs Chelsea) | 0 | 1140 |
| opp_defence_strength (Kinsky, vs Newcastle) | 0 | 1110 |
| opp_attack_strength (Kinsky, vs Newcastle) | 0 | 1130 |

Kinsky still edges Verbruggen (2.30 vs 3.19 — Newcastle's real strength profile is still slightly weaker than Chelsea's), so the *qualitative* Task 1 conclusion holds: fixture difficulty legitimately favors Kinsky. But both predictions dropped substantially in absolute terms — a direct, visible consequence of no longer extrapolating on 0. This makes every prediction this season more trustworthy, not just this one pair.

### One deliberate scope decision

The fix was also applied to `predict.py`'s row-filtering: previously `dropna(subset=FEATURES)` would have silently dropped every player from a team with no fallback (the 3 promoted teams) once their strength fields became `null` instead of `0`. Changed to only require `fixture_difficulty` (matching `build_features.py`'s existing convention) — LightGBM handles missing values natively, so Coventry/Hull/Ipswich players still get predictions instead of vanishing from the output. Confirmed live: Thomas (Hull), McBurnie (Coventry), and Rushworth (Hull, GKP) all appear in `predictions_gw2.csv` after the fix.

### A note on `build_features.py`

The same fallback logic was added to `build_team_strength_lookup()` for consistency, but it's currently **inert on real output** — the current season has 0 training rows (only GW1 has been played, not enough for a "prev match → next match" pair yet), so there's nothing for it to apply to yet. It's ready for when GW2+ finishes and current-season rows start being generated.

---

## Fix 2 — GKP's own training window

### Result

| | Rows | MAE |
|---|---|---|
| Original (1 season, 2025-26 only) | 3,330 | 0.58 |
| Multi-season (3 seasons) | 9,430 | 0.61 |
| **GKP window = 2 (current + most recent season)** | **3,330** | **0.58** |

The shorter window **exactly recovers the original accuracy** — not coincidentally: with 0 current-season rows available right now, "current + most recent 1 season" collapses to precisely the 2025-26-only dataset the original model used. Same rows, same result. This confirms the hypothesis cleanly: it really was the older (2023-24, 2024-25) goalkeeper rows dragging GKP's accuracy down, not train/test noise — pulling them out doesn't just move the number around, it reproduces the exact prior result.

DEF/MID/FWD are untouched (`TRAINING_WINDOWS` window = `None`, meaning "all seasons") and keep their multi-season improvement (1.08 / 0.96 / 1.09).

Once GW2+ actually finishes and current-season rows start accumulating, GKP's window will include real current-season data plus 2025-26 — worth re-checking then, since that's a materially different (larger, more current) dataset than what produced the 0.58 above.

```python
TRAINING_WINDOWS = {"GKP": 2, "DEF": None, "MID": None, "FWD": None}
```

in `train_model.py`, ready to retune per-position without touching the training function itself.
