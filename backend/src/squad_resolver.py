"""
Turns raw FPL picks (player ids + squad-slot/captain flags only) into a
flat list with names/position/team/cost attached, using bootstrap.json.

Shared by api/routes/team.py (wraps these into SquadPlayer for the API
response) and weekly_job.py (uses the plain dicts directly, no HTTP —
importing api/ code from src/ would run the dependency the wrong way), so
the picks-to-names logic lives in exactly one place.
"""


def resolve_squad_picks(picks_payload, bootstrap):
    """
    picks_payload: the raw "picks" dict from fetch_my_team's saved file
    (has a "picks" list of {element, position, is_captain, is_vice_captain}).
    Returns a list of plain dicts, sorted by pick_position (1-15; 1-11 are
    the starting XI, 12-15 the bench) — empty if there's nothing to resolve.
    """
    if not picks_payload or not picks_payload.get("picks"):
        return []

    pos_map = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    team_names = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    player_meta = {p["id"]: p for p in bootstrap["elements"]}

    resolved = []
    for pick in picks_payload["picks"]:
        player = player_meta.get(pick["element"])
        if player is None:
            continue  # stale cache referencing a player id bootstrap no longer has
        resolved.append({
            "player_id": pick["element"],
            "web_name": player["web_name"],
            "position": pos_map[player["element_type"]],
            "team": team_names.get(player["team"], "?"),
            "now_cost": player["now_cost"] / 10,
            "is_starter": pick["position"] <= 11,
            "is_captain": pick["is_captain"],
            "is_vice_captain": pick["is_vice_captain"],
            "pick_position": pick["position"],
        })

    resolved.sort(key=lambda p: p["pick_position"])
    return resolved
