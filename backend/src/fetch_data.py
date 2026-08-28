"""
Pulls raw data from the official FPL API and saves it locally as JSON/CSV.
Run this once per gameweek (after matches finish) to refresh your dataset.

No API key needed — it's a public, unauthenticated API.
"""
import requests
import json
import os
import time

BASE = "https://fantasy.premierleague.com/api"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Community archive of full match-by-match FPL history, season by season.
# Used to bootstrap the model early in a new season, before the live API has
# enough current-season gameweeks to build "prev match -> next match" rows.
HISTORICAL_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
HISTORICAL_SEASONS = ["2025-26"]

try:  # works both as `python src/fetch_data.py` and as the `src.fetch_data` package
    from .bootstrap_utils import get_upcoming_gw, load_json
except ImportError:
    from bootstrap_utils import get_upcoming_gw, load_json


def get_json(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def fetch_bootstrap():
    """Players, teams, positions, gameweeks — the core reference data."""
    data = get_json(f"{BASE}/bootstrap-static/")
    with open(os.path.join(DATA_DIR, "bootstrap.json"), "w") as f:
        json.dump(data, f)
    print(f"Saved bootstrap.json — {len(data['elements'])} players, "
          f"{len(data['teams'])} teams, {len(data['events'])} gameweeks")
    return data


def fetch_fixtures():
    """Full fixture list with difficulty ratings (FDR)."""
    data = get_json(f"{BASE}/fixtures/")
    with open(os.path.join(DATA_DIR, "fixtures.json"), "w") as f:
        json.dump(data, f)
    print(f"Saved fixtures.json — {len(data)} fixtures")
    return data


def fetch_player_histories(player_ids, delay=0.15):
    """
    Per-player match-by-match history (this season + last season summary).
    This is the expensive call — one request per player — so we cache it.
    """
    out = {}
    path = os.path.join(DATA_DIR, "player_histories.json")

    # resume from cache if it exists
    if os.path.exists(path):
        with open(path) as f:
            out = json.load(f)

    todo = [pid for pid in player_ids if str(pid) not in out]
    print(f"Fetching {len(todo)} player histories ({len(out)} already cached)...")

    for i, pid in enumerate(todo):
        try:
            out[str(pid)] = get_json(f"{BASE}/element-summary/{pid}/")
        except Exception as e:
            print(f"  failed for player {pid}: {e}")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}")
            with open(path, "w") as f:
                json.dump(out, f)
        time.sleep(delay)  # be polite to the API

    with open(path, "w") as f:
        json.dump(out, f)
    print(f"Saved player_histories.json — {len(out)} players total")
    return out


def fetch_historical_season(season):
    """
    Pulls one full past season's match-by-match data (every player, every
    gameweek) from the vaastav/Fantasy-Premier-League community archive —
    public, no key needed. Only pulled once; a finished season never changes.
    """
    season_dir = os.path.join(DATA_DIR, "historical", season)
    os.makedirs(season_dir, exist_ok=True)

    files = {
        "merged_gw.csv": "gws/merged_gw.csv",
        "teams.csv": "teams.csv",
        "fixtures.csv": "fixtures.csv",
    }
    for out_name, remote_path in files.items():
        out_path = os.path.join(season_dir, out_name)
        if os.path.exists(out_path):
            continue  # finished seasons don't change; don't refetch
        r = requests.get(f"{HISTORICAL_BASE}/{season}/{remote_path}",
                          headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(out_path, "w") as f:
            f.write(r.text)
    print(f"Saved historical season {season} -> {season_dir}")


def fetch_my_team(entry_id, event_id=None):
    """
    Your specific squad. entry_id is the number in your FPL team URL, e.g.
    the number in .../entry/1234567/event/1. Defaults event_id to the
    current/next gameweek — same get_upcoming_gw logic predict.py uses, so
    your squad and your predictions line up on the same gameweek.

    The FPL API only publishes a gameweek's "picks" once its deadline has
    passed (your live, not-yet-locked draft for the upcoming gameweek needs
    an authenticated /my-team/ call, which this public API doesn't have
    access to). If the upcoming gameweek isn't published yet, this falls
    back to the most recently finished gameweek's locked squad instead of
    erroring out — event_id in the saved file tells you which gw you got.
    """
    bootstrap = load_json("bootstrap.json")
    requested_event_id = event_id if event_id is not None else get_upcoming_gw(bootstrap)
    event_id = requested_event_id
    gw_status = "requested"  # flips to "locked" if we have to fall back below

    data = get_json(f"{BASE}/entry/{entry_id}/")

    try:
        picks = get_json(f"{BASE}/entry/{entry_id}/event/{event_id}/picks/")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            current_gw = next((ev["id"] for ev in bootstrap["events"] if ev["is_current"]), event_id - 1)
            print(f"GW{event_id} picks not published yet — falling back to GW{current_gw} (last locked squad).")
            event_id = current_gw
            gw_status = "locked"
            picks = get_json(f"{BASE}/entry/{entry_id}/event/{event_id}/picks/")
        else:
            raise

    with open(os.path.join(DATA_DIR, "my_team.json"), "w") as f:
        json.dump({
            "entry": data,
            "picks": picks,
            "event_id": event_id,
            "requested_event_id": requested_event_id,
            "gw_status": gw_status,
        }, f)
    print(f"Saved my_team.json (GW{event_id}, gw_status={gw_status})")
    return data, picks


def fetch_entry_history(entry_id):
    """
    Your full season history — one row per already-played gameweek
    (points, bank, event_transfers) plus past-seasons summaries and chip
    usage. The public API has no single "free transfers remaining" field;
    it has to be derived from this (see transfer_budget.py), one gameweek
    at a time.
    """
    data = get_json(f"{BASE}/entry/{entry_id}/history/")
    with open(os.path.join(DATA_DIR, "entry_history.json"), "w") as f:
        json.dump(data, f)
    print(f"Saved entry_history.json — {len(data.get('current', []))} gameweeks played")
    return data


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    bootstrap = fetch_bootstrap()
    fetch_fixtures()

    # Fetch full history for every player (takes a few minutes, ~700 players)
    all_ids = [p["id"] for p in bootstrap["elements"]]
    fetch_player_histories(all_ids)

    # Bootstrap data: past season(s) of full match history, so there's
    # something real to train on before the current season has enough gws
    for season in HISTORICAL_SEASONS:
        fetch_historical_season(season)

    # Optional: pull your own squad. Find your entry_id in the URL when you're
    # logged into fantasy.premierleague.com, e.g. .../entry/1234567/event/1
    # fetch_my_team(entry_id=YOUR_ID_HERE, event_id=1)
