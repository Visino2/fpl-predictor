"""
Pure logging/tracking layer — records what predict.py and optimizer.py
output over time, so real accuracy can be measured across a season.

Deliberately dependency-free of predict.py/optimizer.py: every function here
takes plain dicts/DataFrames as input and never imports their functions.
That keeps this file correct no matter how the prediction/optimization
logic changes later — it only needs to know the SHAPE of what it's logging,
not how that data was produced. Same reasoning as fixture_run.py staying
free of ML/squad-picking logic.

Uses plain sqlite3 (no ORM) — this is a single-user, low-volume log
(a few hundred rows per gameweek at most), so anything heavier is overkill.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DATA_DIR, "tracking.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions_log (
    gw                INTEGER NOT NULL,
    player_id         INTEGER NOT NULL,
    web_name          TEXT NOT NULL,
    position          TEXT NOT NULL,
    predicted_points  REAL NOT NULL,
    actual_points     REAL,
    was_starter       INTEGER NOT NULL,
    was_captain       INTEGER NOT NULL,
    logged_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (gw, player_id)
);

CREATE TABLE IF NOT EXISTS gameweek_summary (
    gw                     INTEGER PRIMARY KEY,
    predicted_total        REAL,
    actual_total            REAL,
    squad_predicted_total  REAL,
    squad_actual_total     REAL,
    created_at             TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS chip_log (
    gw                      INTEGER NOT NULL,
    chip_name               TEXT NOT NULL,
    was_recommended         INTEGER,
    recommendation_reason   TEXT,
    predicted_gain          REAL,
    was_played              INTEGER NOT NULL DEFAULT 0,
    actual_gain             REAL,
    logged_at               TIMESTAMP NOT NULL,
    PRIMARY KEY (gw, chip_name)
);
"""


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def log_predictions(gw, predictions_df, starting_xi_ids, captain_id):
    """
    Records this gameweek's squad predictions before the deadline, so
    backfill_actuals() has something real to compare against later.

    predictions_df needs columns: player_id, web_name, position,
    predicted_points — one row per SQUAD player (typically your 15, not the
    full player pool; was_starter/was_captain only mean something for
    players actually in your squad).

    Safe to call again before the deadline (e.g. predictions refreshed after
    a late fitness update) — REPLACEs existing rows for this gw. Once
    backfill_actuals has filled in actual_points for this gw, further calls
    are rejected outright, so a stray late refresh can't silently erase a
    completed comparison.
    """
    starting_xi_ids = {int(pid) for pid in starting_xi_ids}
    captain_id = int(captain_id)
    now = _now()

    conn = _connect()
    try:
        already_backfilled = conn.execute(
            "SELECT COUNT(*) FROM predictions_log WHERE gw = ? AND actual_points IS NOT NULL",
            (gw,),
        ).fetchone()[0]
        if already_backfilled > 0:
            raise ValueError(
                f"GW{gw} already has backfilled actuals — refusing to overwrite a "
                f"completed comparison. log_predictions is only for before the deadline."
            )

        rows = []
        predicted_total = 0.0
        squad_predicted_total = 0.0
        for _, p in predictions_df.iterrows():
            player_id = int(p["player_id"])
            is_starter = player_id in starting_xi_ids
            is_captain = player_id == captain_id
            points = float(p["predicted_points"])

            rows.append((gw, player_id, p["web_name"], p["position"], points, is_starter, is_captain, now))

            predicted_total += points
            if is_starter:
                squad_predicted_total += points
                if is_captain:
                    squad_predicted_total += points  # captain's points count double

        conn.executemany(
            """
            INSERT INTO predictions_log
                (gw, player_id, web_name, position, predicted_points, actual_points, was_starter, was_captain, logged_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(gw, player_id) DO UPDATE SET
                web_name = excluded.web_name,
                position = excluded.position,
                predicted_points = excluded.predicted_points,
                was_starter = excluded.was_starter,
                was_captain = excluded.was_captain,
                logged_at = excluded.logged_at
            """,
            rows,
        )

        conn.execute(
            """
            INSERT INTO gameweek_summary (gw, predicted_total, actual_total, squad_predicted_total, squad_actual_total, created_at)
            VALUES (?, ?, NULL, ?, NULL, ?)
            ON CONFLICT(gw) DO UPDATE SET
                predicted_total = excluded.predicted_total,
                squad_predicted_total = excluded.squad_predicted_total,
                created_at = excluded.created_at
            """,
            (gw, predicted_total, squad_predicted_total, now),
        )
        conn.commit()
    finally:
        conn.close()


def log_chip_recommendation(gw, chip_name, was_recommended, reason, predicted_gain):
    """
    Records the advice optimizer.py gave for a chip this gameweek, regardless
    of whether it was actually played — this is what lets "was the model's
    advice actually good" be graded later, including every "save it" call.

    chip_name is a short code: bboost / 3xc / wildcard / freehit.

    Safe to call repeatedly (e.g. advice refreshed as fixtures update) —
    REPLACEs the recommendation fields, but leaves was_played/actual_gain
    untouched if this chip was already marked played for this gw.
    """
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO chip_log (gw, chip_name, was_recommended, recommendation_reason, predicted_gain, was_played, actual_gain, logged_at)
            VALUES (?, ?, ?, ?, ?, 0, NULL, ?)
            ON CONFLICT(gw, chip_name) DO UPDATE SET
                was_recommended = excluded.was_recommended,
                recommendation_reason = excluded.recommendation_reason,
                predicted_gain = excluded.predicted_gain,
                logged_at = excluded.logged_at
            """,
            (gw, chip_name, int(bool(was_recommended)), reason, predicted_gain, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def record_chip_played(gw, chip_name):
    """
    Call manually (via the API) when you actually activate a chip in the
    real FPL app. Upserts, so this works even if no recommendation was ever
    logged for this exact gw/chip (e.g. you played a chip the model never
    got asked to weigh in on).
    """
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO chip_log (gw, chip_name, was_recommended, recommendation_reason, predicted_gain, was_played, actual_gain, logged_at)
            VALUES (?, ?, NULL, NULL, NULL, 1, NULL, ?)
            ON CONFLICT(gw, chip_name) DO UPDATE SET was_played = 1
            """,
            (gw, chip_name, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_chip_history():
    """All chip_log rows, most recent gameweek first — every recommendation and outcome logged."""
    conn = _connect()
    try:
        cols = ["gw", "chip_name", "was_recommended", "recommendation_reason",
                "predicted_gain", "was_played", "actual_gain", "logged_at"]
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM chip_log ORDER BY gw DESC, chip_name"
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def get_logged_gameweeks_missing_actuals():
    """
    Gameweeks that have logged predictions but haven't been backfilled yet —
    weekly_job.check_and_backfill() intersects this with bootstrap.json's
    "finished" gameweeks to decide what's actually ready to backfill.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT gw FROM predictions_log WHERE actual_points IS NULL"
        ).fetchall()
        return sorted(r[0] for r in rows)
    finally:
        conn.close()


def backfill_actuals(gw):
    """
    Call after a gameweek's fixtures are all "finished" in bootstrap.json.
    Looks up each logged player's real points for this gw from
    player_histories.json — already fetched by fetch_data.py; this file
    deliberately never calls the FPL API itself, staying a pure logging
    layer over data other scripts already pulled — and fills in
    actual_points, gameweek_summary's actual totals, and actual_gain for
    any chip marked played this gw.
    """
    histories_path = os.path.join(DATA_DIR, "player_histories.json")
    with open(histories_path) as f:
        histories = json.load(f)

    conn = _connect()
    try:
        logged = conn.execute(
            "SELECT player_id, was_starter, was_captain FROM predictions_log WHERE gw = ?",
            (gw,),
        ).fetchall()
        if not logged:
            raise ValueError(f"No logged predictions for GW{gw} — call log_predictions first.")

        actual_total = 0.0
        squad_actual_total = 0.0
        bench_actual_total = 0.0
        captain_actual_points = None
        any_actual_found = False

        for player_id, was_starter, was_captain in logged:
            gw_history = histories.get(str(player_id), {}).get("history", [])
            match = next((h for h in gw_history if h["round"] == gw), None)
            actual = float(match["total_points"]) if match is not None else None

            conn.execute(
                "UPDATE predictions_log SET actual_points = ? WHERE gw = ? AND player_id = ?",
                (actual, gw, player_id),
            )
            if actual is None:
                continue  # e.g. transferred out / blank gameweek — leave NULL, excluded from MAE

            any_actual_found = True
            actual_total += actual
            if was_starter:
                squad_actual_total += actual
                if was_captain:
                    squad_actual_total += actual  # captain's points count double
                    captain_actual_points = actual
            else:
                bench_actual_total += actual

        if not any_actual_found:
            conn.rollback()
            raise ValueError(
                f"No completed match data found for GW{gw} yet — it likely hasn't finished. "
                f"Wait until its fixtures are marked finished before backfilling."
            )

        conn.execute(
            "UPDATE gameweek_summary SET actual_total = ?, squad_actual_total = ? WHERE gw = ?",
            (actual_total, squad_actual_total, gw),
        )

        played_chips = conn.execute(
            "SELECT chip_name FROM chip_log WHERE gw = ? AND was_played = 1", (gw,)
        ).fetchall()
        for (chip_name,) in played_chips:
            if chip_name == "bboost":
                gain = bench_actual_total
            elif chip_name == "3xc":
                gain = captain_actual_points
            else:
                # wildcard/freehit are full squad rebuilds — no single-number
                # "gain" to compute against a pre-chip prediction here
                continue
            if gain is not None:
                conn.execute(
                    "UPDATE chip_log SET actual_gain = ? WHERE gw = ? AND chip_name = ?",
                    (gain, gw, chip_name),
                )

        conn.commit()
    finally:
        conn.close()


def get_prediction_log(last_n_gws=None):
    """
    Every predictions_log row (optionally just the most recent `last_n_gws`
    gameweeks), oldest gw first. season_strategy.py uses this to build a
    per-player consistency profile — the spread of a player's actual points
    and of the model's error on them across gameweeks — for Triple Captain
    candidate selection.
    """
    conn = _connect()
    try:
        cols = ["gw", "player_id", "web_name", "position",
                "predicted_points", "actual_points", "was_starter", "was_captain"]
        params = ()
        where = ""
        if last_n_gws:
            recent = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT gw FROM predictions_log ORDER BY gw DESC"
                ).fetchall()
            ][:last_n_gws]
            if recent:
                where = f" WHERE gw IN ({','.join('?' * len(recent))})"
                params = tuple(recent)
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM predictions_log{where} ORDER BY gw, player_id",
            params,
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def get_gameweek_summaries():
    """
    Every gameweek_summary row, oldest gw first — including gameweeks that
    have predictions logged but no actuals backfilled yet (unlike
    get_accuracy_report, which only covers backfilled weeks).

    season_strategy.py uses this for the "is my squad's predicted total
    trending down week over week" check, which needs the pre-deadline
    predicted totals even before results exist.
    """
    conn = _connect()
    try:
        cols = ["gw", "predicted_total", "actual_total",
                "squad_predicted_total", "squad_actual_total", "created_at"]
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM gameweek_summary ORDER BY gw"
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def get_accuracy_report(last_n_gws=None):
    """
    The real answer to "is this actually working": mean absolute error
    between predicted and actual points — overall and per position — across
    every backfilled gameweek (or just the last `last_n_gws`), plus a
    week-by-week squad-level predicted-vs-actual list.
    """
    conn = _connect()
    try:
        all_gws = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT gw FROM predictions_log WHERE actual_points IS NOT NULL ORDER BY gw DESC"
            ).fetchall()
        ]
        gws = all_gws[:last_n_gws] if last_n_gws else all_gws

        if not gws:
            return {
                "overall_mae": None, "sample_size": 0, "mae_by_position": {},
                "gameweeks_covered": 0, "weeks": [],
            }

        placeholders = ",".join("?" * len(gws))

        overall_mae, n = conn.execute(
            f"""
            SELECT AVG(ABS(predicted_points - actual_points)), COUNT(*)
            FROM predictions_log
            WHERE actual_points IS NOT NULL AND gw IN ({placeholders})
            """,
            gws,
        ).fetchone()

        by_position = {
            row[0]: round(row[1], 3)
            for row in conn.execute(
                f"""
                SELECT position, AVG(ABS(predicted_points - actual_points))
                FROM predictions_log
                WHERE actual_points IS NOT NULL AND gw IN ({placeholders})
                GROUP BY position
                """,
                gws,
            ).fetchall()
        }

        weeks = [
            {
                "gw": r[0],
                "predicted_total": r[1],
                "actual_total": r[2],
                "difference": round(r[2] - r[1], 2) if r[2] is not None else None,
            }
            for r in conn.execute(
                f"""
                SELECT gw, squad_predicted_total, squad_actual_total
                FROM gameweek_summary
                WHERE gw IN ({placeholders})
                ORDER BY gw
                """,
                gws,
            ).fetchall()
        ]

        return {
            "overall_mae": round(overall_mae, 3) if overall_mae is not None else None,
            "sample_size": n,
            "mae_by_position": by_position,
            "gameweeks_covered": len(gws),
            "weeks": weeks,
        }
    finally:
        conn.close()
