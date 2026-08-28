"""
Computes each team's upcoming fixture RUN (next N gameweeks) and its average
difficulty. Chip timing (Bench Boost, Wildcard, Free Hit) should be judged
against a run of matches, not a single week — a team with four winnable
fixtures in a row is a far stronger Wildcard target than one good match
sandwiched between two brutal ones.

This file ONLY computes fixture difficulty data: no ML, no squad-picking,
no chip decisions (see optimizer.py for that) — same single-responsibility
split as the rest of src/.
"""
import json
import os

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

DEFAULT_LOOKAHEAD = 4


def load_json(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


def get_upcoming_gw(bootstrap):
    """Same rule predict.py uses, kept in sync so the run always starts where predictions do."""
    for event in bootstrap["events"]:
        if event["is_next"]:
            return event["id"]
    for event in bootstrap["events"]:
        if not event["finished"]:
            return event["id"]
    raise ValueError("Could not determine the upcoming gameweek")


def build_fixture_run(n=DEFAULT_LOOKAHEAD, bootstrap=None, fixtures=None):
    """
    team_id -> {avg_difficulty, fixture_count, fixtures: [...]}, covering the
    next `n` gameweeks starting at the upcoming gameweek (inclusive).

    fixture_count can be less than n (a blank gameweek in this window) or
    more (a double gameweek) — both are informative for chip timing, so we
    surface the count rather than assuming exactly one fixture per gw.
    """
    bootstrap = bootstrap or load_json("bootstrap.json")
    fixtures = fixtures or load_json("fixtures.json")

    team_names = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    start_gw = get_upcoming_gw(bootstrap)
    window = set(range(start_gw, start_gw + n))

    runs = {tid: [] for tid in team_names}
    for fx in fixtures:
        if fx["event"] not in window:
            continue
        runs[fx["team_h"]].append({
            "gw": fx["event"], "opponent": team_names.get(fx["team_a"], "?"),
            "was_home": True, "difficulty": fx["team_h_difficulty"],
        })
        runs[fx["team_a"]].append({
            "gw": fx["event"], "opponent": team_names.get(fx["team_h"], "?"),
            "was_home": False, "difficulty": fx["team_a_difficulty"],
        })

    result = {}
    for tid, fx_list in runs.items():
        fx_list = sorted(fx_list, key=lambda f: f["gw"])
        avg = sum(f["difficulty"] for f in fx_list) / len(fx_list) if fx_list else None
        result[tid] = {
            "avg_difficulty": round(avg, 2) if avg is not None else None,
            "fixture_count": len(fx_list),
            "fixtures": fx_list,
        }
    return result


def get_player_fixture_run(player_id, fixture_run=None, n=DEFAULT_LOOKAHEAD):
    """
    Maps a player to their team's fixture run, for joining into predict.py's
    output. Pass a pre-built `fixture_run` (from build_fixture_run) when
    calling this per-player in a loop, so the fixtures file isn't re-read
    and re-aggregated for every single player.
    """
    bootstrap = load_json("bootstrap.json")
    player = next((p for p in bootstrap["elements"] if p["id"] == player_id), None)
    if player is None:
        return None
    fixture_run = fixture_run if fixture_run is not None else build_fixture_run(n)
    return fixture_run.get(player["team"])


def summarize_fixtures(fixtures):
    """e.g. 'ARS(H) CHE(A) EVE(H) NEW(A)' — short human-readable fixture-run string."""
    return " ".join(f"{f['opponent']}({'H' if f['was_home'] else 'A'})" for f in fixtures)


def to_dataframe(fixture_run):
    """
    Flattens build_fixture_run()'s dict into one row per (team_id, gw,
    fixture) — the shape optimizer.py's chip-timing logic needs, since it
    has to reason about individual future gameweeks, not a single pre-
    averaged number. A double gameweek naturally produces two rows for the
    same (team_id, gw).
    """
    rows = [
        {"team_id": team_id, "gw": fx["gw"], "opponent": fx["opponent"],
         "was_home": fx["was_home"], "difficulty": fx["difficulty"]}
        for team_id, info in fixture_run.items()
        for fx in info["fixtures"]
    ]
    return pd.DataFrame(rows, columns=["team_id", "gw", "opponent", "was_home", "difficulty"])


if __name__ == "__main__":
    bootstrap = load_json("bootstrap.json")
    team_names = {t["id"]: t["name"] for t in bootstrap["teams"]}
    runs = build_fixture_run(bootstrap=bootstrap)

    ranked = sorted(
        runs.items(),
        key=lambda kv: (kv[1]["avg_difficulty"] is None, kv[1]["avg_difficulty"] or 0),
    )
    for tid, info in ranked:
        print(f"{team_names[tid]:16s} avg={info['avg_difficulty']}  "
              f"n={info['fixture_count']}  {summarize_fixtures(info['fixtures'])}")
