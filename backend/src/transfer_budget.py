"""
Computes your real transfer budget for the upcoming gameweek: bank balance
(leftover budget) and free transfers available. FPL's public API has no
single field for free-transfers-remaining — it has to be derived from your
transfer history, one played gameweek at a time.
"""

FREE_TRANSFER_CAP = 5  # 2024-25+ rule (was 2 in earlier seasons)


def compute_free_transfers(history_current, cap=FREE_TRANSFER_CAP):
    """
    history_current: the "current" list from fetch_data.fetch_entry_history
    — one entry per already-played gameweek, each with event_transfers
    (how many transfers were actually made that gameweek).

    Returns free transfers available for the NEXT (upcoming, not-yet-
    played) gameweek: starts at 1 for the first transfer-eligible
    gameweek (GW1 is initial squad selection, not a transfer week), banks
    an unused one each week after that, capped.

    Known simplification: doesn't special-case Wildcard/Free Hit
    gameweeks (unlimited transfers that gameweek only, no banking
    impact) — detecting those needs each gameweek's active_chip, which
    isn't in this endpoint. Not an issue for an account that hasn't used
    either chip yet; worth revisiting once chip history exists.
    """
    free = 1
    for gw_entry in sorted(history_current, key=lambda e: e["event"]):
        if gw_entry["event"] < 2:
            continue
        used = gw_entry["event_transfers"]
        unused = max(free - used, 0)
        free = min(unused + 1, cap)
    return free


def get_transfer_budget(entry, history):
    """
    entry: the raw dict from fetch_data.fetch_my_team's "entry" key (has
    last_deadline_bank in £0.1m units, e.g. 5 -> £0.5m).
    history: the raw dict from fetch_data.fetch_entry_history.
    Returns {"bank_balance": float (£m), "free_transfers": int}.
    """
    return {
        "bank_balance": entry.get("last_deadline_bank", 0) / 10,
        "free_transfers": compute_free_transfers(history.get("current", [])),
    }
