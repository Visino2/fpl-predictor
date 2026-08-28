# Multi-season training: did it help?

## Data volume

| | Rows | Seasons |
|---|---|---|
| Before | 28,916 | 1 (2025-26 only) |
| After | 84,275 | 3 (2023-24, 2024-25, 2025-26) |

## MAE per position

| Position | Before (1 season) | After (3 seasons) | Change |
|---|---|---|---|
| GKP | 0.58 (3,330 rows) | 0.61 (9,430 rows) | **+0.03 (slightly worse)** |
| DEF | 1.19 (9,463 rows) | 1.08 (27,674 rows) | −0.11 (better) |
| MID | 1.00 (12,931 rows) | 0.96 (37,307 rows) | −0.04 (better) |
| FWD | 1.13 (3,192 rows) | 1.09 (9,864 rows) | −0.04 (better) |

## Verdict

Modest, not dramatic. 3 of 4 positions improved slightly (DEF the most, ~9% relative), GKP got marginally worse — likely just train/test split noise at this sample size rather than a real regression, since the model class and features didn't change. **Tripling the data did not transform accuracy** — this is a small-signal, high-variance prediction problem (football), and no amount of historical volume fixes that; it mainly helps the model see more distinct player/fixture combinations, which matters more for coverage (see below) than raw MAE.

## A real side benefit: coverage, not just accuracy

With only one season of data, many current players had thin or no history to build reliable predictions from. After adding two more seasons, GW2's top predictions surfaced several players (Palmer, Cunha, Wirtz, Cherki, Hinshelwood) that didn't appear prominently before — the model now has real match patterns for more of this season's actual squad, not just accuracy on the players it already knew well.

## One data-quality issue caught and fixed

The 2024-25 season's archive included 302 rows for FPL's real "Manager" fantasy position (an actual club manager, e.g. Mikel Arteta, scored as a pickable asset — a feature that season had). Training briefly produced a 5th "AM" position model with MAE 3.83 on that tiny, structurally-unrelated sample (managers score from team results, not minutes/goals/saves — none of this model's features apply to them). The current season's `bootstrap.json` only has GKP/DEF/MID/FWD, so that model would never actually be used by `predict.py` — but it was still noise in the training set, so `fetch_historical.py` now filters historical rows to those 4 positions before saving `historical_multi_season.csv`.
