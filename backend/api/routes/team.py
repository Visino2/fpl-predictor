import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.fetch_data import fetch_my_team
from src.predict import DATA_DIR, load_json
from src.squad_resolver import resolve_squad_picks
from api.schemas import MyTeam, SquadPlayer

router = APIRouter(prefix="/team", tags=["team"])

CACHE_PATH = os.path.join(DATA_DIR, "my_team.json")
CACHE_TTL_SECONDS = 60 * 60  # PROMPT_2's caching note: low-frequency, single-user lookup


def _load_cached_team(entry_id, event_id):
    is_stale = (
        not os.path.exists(CACHE_PATH)
        or (time.time() - os.path.getmtime(CACHE_PATH)) > CACHE_TTL_SECONDS
    )
    if is_stale:
        try:
            fetch_my_team(entry_id, event_id)
        except Exception as e:
            raise HTTPException(502, f"Could not fetch FPL entry {entry_id}: {e}")
    return load_json("my_team.json")


@router.get("/{entry_id}", response_model=MyTeam)
def get_my_team(entry_id: int, event_id: Optional[int] = None):
    """
    Your real FPL squad, with names/positions/team/cost attached (picks only
    return player ids) and starting-XI/bench/captain roles already resolved.
    Cached to backend/data/my_team.json for up to an hour; refetched
    automatically once stale — see fetch_my_team for the "gw not published
    yet" fallback to the last locked gameweek.
    """
    cached = _load_cached_team(entry_id, event_id)
    entry = cached["entry"]
    gw = cached.get("event_id")
    requested_gw = cached.get("requested_event_id", gw)
    gw_status = cached.get("gw_status", "requested")

    resolved = resolve_squad_picks(cached["picks"], load_json("bootstrap.json"))

    return MyTeam(
        entry_id=entry_id,
        team_name=entry.get("name"),
        overall_rank=entry.get("summary_overall_rank"),
        gw=gw,
        requested_gw=requested_gw,
        gw_status=gw_status,
        bank_balance=entry.get("last_deadline_bank", 0) / 10,
        squad_value=entry.get("last_deadline_value", 0) / 10,
        picks=[SquadPlayer(**r) for r in resolved] if resolved else None,
    )
