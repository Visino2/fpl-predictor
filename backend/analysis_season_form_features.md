# Season-to-date form features: did they help?

## What was added

The model previously used only a player's **single most recent match** as its
"recent form" signal (`prev_points`, `prev_goals`, `prev_xg`, `prev_minutes`,
…). Once a season is a few gameweeks deep, one match stops representing form —
it looks identical whether the player has been great all season or just had one
good week after three bad ones.

Added alongside (not replacing) the `prev_*` features — `src/season_form.py`,
wired identically into `build_features.py`, `fetch_historical.py` and
`predict.py`:

- `season_avg_points / goals / assists / xg / xa / minutes / bps / ict` — mean
  across every gameweek the player has played *before* the one being predicted
- `season_games_played` — 1 vs 10 games is a very different sample; the trees
  can split on this to weight the averages implicitly
- `form_trend` — mean points of the last 3 games minus the mean of every game
  before that (0 until 4+ games exist). Positive = heating up, negative =
  cooling off, ~0 = steady at the season average.

## MAE per position — same train/test split (`random_state=42`), 84,275 rows

| Position | Baseline (`prev_*` only) | + season-to-date | Change |
|---|---|---|---|
| FWD | 1.0866 | **1.0614** | −0.0252 (−2.3%) |
| DEF | 1.0790 | **1.0523** | −0.0267 (−2.5%) |
| MID | 0.9630 | **0.9227** | −0.0403 (−4.2%) |
| GKP | 0.5785 | **0.5602** | −0.0182 (−3.1%) |

## Verdict: yes, this one genuinely helped — every position, no regressions

Unlike the multi-season data experiment (which was a wash — 3/4 positions barely
moved and GKP got slightly worse), season-to-date form improved **all four
positions**, MID the most (−4.2% relative). Small in absolute points (these are
~1-point-MAE predictions on noisy football data — nothing transforms that), but
consistent and in the right direction.

The trees actually lean on the new features — importance ranks out of 27:

| Position | Top season features |
|---|---|
| MID | `form_trend` **#1**, `season_avg_ict` #6, `season_avg_xa` #7 |
| GKP | `season_avg_points` **#1**, `season_avg_bps` #2, `form_trend` #3 |
| DEF | `season_avg_points` #3, `season_avg_bps` #4, `form_trend` #5 |
| FWD | `form_trend` #4, `season_avg_xa` #5, `season_avg_bps` #6 |

`form_trend` and `season_avg_points`/`season_avg_bps` are doing real work — this
isn't the model politely ignoring dead columns.

## Caveat for the current gameweak (GW2)

The improvement is measured on historical data where players have 1–46 games of
season history. **In the live GW2 predictions, every current-season player has
played exactly 1 game**, so `season_avg_* == prev_*` exactly,
`season_games_played == 1`, and `form_trend == 0` for everyone. The season
features carry no new information for GW2 itself — they start mattering from
~GW4 onward, once `form_trend` can compare windows and the averages diverge from
the last single match.

Any change in the GW2 numbers after this landed is the **model retraining** on
the richer feature set (it learned different splits from the historical season
signal), not season form for these specific players — see below.

## Did the GW2 recommendations shift? (retrain effect only, not season signal)

`predicted_points`, before → after retrain:

| Player | Before | After | Δ |
|---|---|---|---|
| Semenyo | 3.63 | 3.59 | −0.04 |
| Cunha | 6.66 | 6.20 | −0.46 |
| Verbruggen | 2.48 | 1.99 | −0.49 |
| Kinsky | 3.78 | 3.67 | −0.11 |
| Thiago | 1.77 | 2.81 | +1.03 |
| McBurnie | 4.88 | 5.66 | +0.78 |
| Mbeumo | 7.03 | 6.02 | −1.02 |
| B.Fernandes | 5.60 | 7.24 | +1.63 |

**Semenyo → Cunha:** still recommended, but the gap narrowed. Cunha dropped
~0.5 and Semenyo held, so the suggested gain fell from **+3.1 → +2.6**. It also
dropped from the #1 transfer suggestion to #2, behind Thiago → McBurnie (+2.9,
which was previously tied at +3.1). The recommendation itself did not flip — it
just got less emphatic.

**Verbruggen vs Kinsky:** the gap in Kinsky's favour slightly *widened*
(1.30 → 1.68 pts) — Verbruggen fell more than Kinsky. This now shows up as the
top swap in the new **Lineup Check** card: "start Kinsky (3.7) instead of
Verbruggen (2.0), +1.7". Kinsky's easier fixture (difficulty 2 vs 4) is the
driver; the retrain widened it rather than changed the direction.

Net: the retrain nudged numbers around by ±0.5–1.6 pts and reshuffled the
ordering of near-tied suggestions, but did not reverse any recommendation. The
season features' real payoff is later in the season, and is backed by the MAE
table above rather than by GW2.
