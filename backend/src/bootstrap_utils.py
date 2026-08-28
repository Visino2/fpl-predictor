"""
Tiny shared helpers for reading data/*.json and finding the current
gameweek. Split out from predict.py so fetch_data.py can use
get_upcoming_gw (for fetch_my_team's default event_id) without creating a
circular import: predict.py -> fetch_historical.py -> fetch_data.py would
otherwise need to import back into predict.py.
"""
import json
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_json(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


def parse_fpl_time(ts):
    """
    FPL timestamps are ISO-8601 with a 'Z' suffix (e.g. 2026-08-28T17:30:00Z).
    datetime.fromisoformat() only learned to parse 'Z' in 3.11, and this runs
    on 3.9, so normalise it. Returns a tz-aware UTC datetime, or None.
    """
    if not ts:
        return None
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


def get_upcoming_gw(bootstrap):
    """Find the next gameweek that hasn't been played yet."""
    for event in bootstrap["events"]:
        if event["is_next"]:
            return event["id"]
    # fallback: first not-finished event
    for event in bootstrap["events"]:
        if not event["finished"]:
            return event["id"]
    raise ValueError("Could not determine the upcoming gameweek")


def get_next_gw_deadline(bootstrap=None):
    """
    (event_id, deadline) for the next gameweek that hasn't happened yet — the
    one flagged is_next, else the first non-finished event. `deadline` is a
    tz-aware UTC datetime parsed from the event's deadline_time.

    Used by the scheduler to time the weekly refresh relative to FPL's real
    calendar instead of a fixed weekday, since deadlines move week to week
    (midweek rounds, international breaks, TV picks).
    """
    if bootstrap is None:
        bootstrap = load_json("bootstrap.json")
    events = bootstrap["events"]
    event = next((e for e in events if e.get("is_next")), None)
    if event is None:
        event = next((e for e in events if not e.get("finished")), None)
    if event is None:
        raise ValueError("No upcoming gameweek with a deadline in bootstrap.json")
    return event["id"], parse_fpl_time(event["deadline_time"])


def get_gw_last_kickoff(gw, fixtures=None):
    """
    Latest kickoff_time among a gameweek's fixtures, as a tz-aware UTC
    datetime — i.e. when the round's final match starts. Returns None if no
    fixtures for that gw have a confirmed kickoff yet (kickoff_time is null
    until the PL confirms the slot).

    Read from fixtures.json rather than assumed from the deadline, because the
    gap between deadline and last kickoff varies a lot (Sat-only rounds vs
    Fri–Mon spreads vs Tue/Wed midweek rounds).
    """
    if fixtures is None:
        fixtures = load_json("fixtures.json")
    kickoffs = [
        parse_fpl_time(fx["kickoff_time"])
        for fx in fixtures
        if fx.get("event") == gw and fx.get("kickoff_time")
    ]
    return max(kickoffs) if kickoffs else None
