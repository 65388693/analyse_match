"""Persist displayed pre-match 1X2 predictions and score their outcomes."""

from contextlib import contextmanager
from datetime import datetime, timezone
import math
import os
import re
import sqlite3

from config import DATA_DIR

PREDICTIONS_DB = os.path.join(DATA_DIR, "predictions.sqlite3")
OUTCOME_INDEX = {"dom": 0, "nul": 1, "ext": 2}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    fixture_id TEXT NOT NULL,
    match_date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    competition TEXT,
    country TEXT,
    selection TEXT NOT NULL,
    probability REAL NOT NULL,
    odds REAL NOT NULL,
    bookmaker TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    settled_home_score INTEGER,
    settled_away_score INTEGER,
    settled_at TEXT,
    PRIMARY KEY (fixture_id, match_date, selection, model_version)
)
"""

_MODEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_predictions (
    fixture_id TEXT NOT NULL,
    match_date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    competition TEXT,
    country TEXT,
    selection TEXT NOT NULL,
    probability REAL NOT NULL,
    odds REAL,
    bookmaker TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    settled_home_score INTEGER,
    settled_away_score INTEGER,
    settled_at TEXT,
    PRIMARY KEY (fixture_id, match_date, selection, model_version)
)
"""


@contextmanager
def _connection():
    os.makedirs(os.path.dirname(PREDICTIONS_DB) or ".", exist_ok=True)
    connection = sqlite3.connect(PREDICTIONS_DB, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(_SCHEMA)
        connection.execute(_MODEL_SCHEMA)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS predictions_settlement_idx "
            "ON predictions(settled_at, match_date)"
        )
        yield connection
        connection.commit()
    finally:
        connection.close()


def save_predictions(match_date, picks, model_version, *, observations=None):
    """Upsert all 1X2 model outcomes and the simple bets actually displayed."""
    recorded_at = datetime.now(timezone.utc).isoformat()
    bet_rows = []
    for pick in picks:
        selection = pick.get("selection")
        probability = pick.get("probability")
        odds = pick.get("odds")
        if selection not in OUTCOME_INDEX:
            continue
        if not isinstance(probability, (int, float)) or not 0 < probability < 1:
            continue
        if not isinstance(odds, (int, float)) or odds <= 1:
            continue
        fixture_id = str(pick.get("match_id") or "")
        home_team = str(pick.get("home_team") or "").strip()
        away_team = str(pick.get("away_team") or "").strip()
        if not fixture_id or not home_team or not away_team:
            continue
        if not math.isfinite(float(probability)) or not math.isfinite(float(odds)):
            continue
        bet_rows.append((
            fixture_id,
            match_date,
            home_team,
            away_team,
            str(pick.get("competition") or ""),
            str(pick.get("country") or ""),
            selection,
            float(probability),
            float(odds),
            str(pick.get("bookmaker") or "1xBet"),
            str(model_version),
            str(pick.get("data_quality") or "limited"),
            recorded_at,
        ))

    model_rows = []
    for observation in observations or []:
        selection = observation.get("selection")
        probability = observation.get("probability")
        odds = observation.get("odds")
        if selection not in OUTCOME_INDEX:
            continue
        if not isinstance(probability, (int, float)) or not 0 < probability < 1:
            continue
        if not math.isfinite(float(probability)):
            continue
        if not isinstance(odds, (int, float)) or not math.isfinite(float(odds)) or odds <= 1:
            odds = None
        fixture_id = str(observation.get("match_id") or "")
        home_team = str(observation.get("home_team") or "").strip()
        away_team = str(observation.get("away_team") or "").strip()
        if not fixture_id or not home_team or not away_team:
            continue
        model_rows.append((
            fixture_id,
            match_date,
            home_team,
            away_team,
            str(observation.get("competition") or ""),
            str(observation.get("country") or ""),
            selection,
            float(probability),
            float(odds) if odds is not None else None,
            str(observation.get("bookmaker") or "1xBet"),
            str(model_version),
            str(observation.get("data_quality") or "limited"),
            recorded_at,
        ))

    if not bet_rows and not model_rows:
        return {"model_predictions": 0, "simple_bets": 0}

    saved_model_count = 0
    saved_bet_count = 0
    with _connection() as connection:
        if model_rows:
            cursor = connection.executemany(
                """INSERT INTO model_predictions (
                    fixture_id, match_date, home_team, away_team, competition, country,
                    selection, probability, odds, bookmaker, model_version, data_quality,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id, match_date, selection, model_version) DO NOTHING""",
                model_rows,
            )
            saved_model_count = cursor.rowcount
        if bet_rows:
            cursor = connection.executemany(
            """INSERT INTO predictions (
                fixture_id, match_date, home_team, away_team, competition, country,
                selection, probability, odds, bookmaker, model_version, data_quality,
                recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id, match_date, selection, model_version) DO NOTHING""",
                bet_rows,
            )
            saved_bet_count = cursor.rowcount
    return {
        "model_predictions": saved_model_count,
        "simple_bets": saved_bet_count,
    }


def settle_finished_predictions(matches):
    """Attach final regulation-time scores from the provider's finished fixtures."""
    completed = []
    for match in matches or []:
        status = re.sub(r"[^a-z]+", " ", str(match.get("status") or "").lower()).strip()
        if not any(token in status.split() for token in ("finished", "complete", "completed", "ft")):
            continue
        score = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", str(match.get("score") or ""))
        fixture_id = str(match.get("source_match_id") or "")
        if not score or not fixture_id or not match.get("match_date"):
            continue
        completed.append((
            int(score.group(1)),
            int(score.group(2)),
            datetime.now(timezone.utc).isoformat(),
            fixture_id,
            match["match_date"],
        ))

    if not completed:
        return 0
    with _connection() as connection:
        bets_cursor = connection.executemany(
            """UPDATE predictions
               SET settled_home_score = ?, settled_away_score = ?, settled_at = ?
               WHERE fixture_id = ? AND match_date = ? AND settled_at IS NULL""",
            completed,
        )
        model_cursor = connection.executemany(
            """UPDATE model_predictions
               SET settled_home_score = ?, settled_away_score = ?, settled_at = ?
               WHERE fixture_id = ? AND match_date = ? AND settled_at IS NULL""",
            completed,
        )
        return bets_cursor.rowcount + model_cursor.rowcount


def get_prediction_stats():
    """Return model calibration metrics and separate displayed-single bet results."""
    with _connection() as connection:
        model_rows = connection.execute(
            """SELECT fixture_id, match_date, model_version, selection, probability,
                      settled_home_score, settled_away_score
               FROM model_predictions"""
        ).fetchall()
        bet_rows = connection.execute(
            """SELECT selection, probability, odds, settled_home_score,
                      settled_away_score
               FROM predictions"""
        ).fetchall()

    groups = {}
    for row in model_rows:
        key = (row["fixture_id"], row["match_date"], row["model_version"])
        group = groups.setdefault(key, {"outcomes": {}})
        group["outcomes"][row["selection"]] = row

    bins = [
        {"range": f"{index / 5:.1f}-{(index + 1) / 5:.1f}", "count": 0,
         "mean_probability": 0.0, "observed_rate": 0.0}
        for index in range(5)
    ]
    correct_top_outcomes = 0
    brier_total = 0.0
    log_loss_total = 0.0
    epsilon = 1e-12

    settled_groups = []
    required_outcomes = set(OUTCOME_INDEX)
    for group in groups.values():
        outcomes = group["outcomes"]
        if set(outcomes) != required_outcomes:
            continue
        rows = list(outcomes.values())
        if any(row["settled_home_score"] is None for row in rows):
            continue
        scores = {(row["settled_home_score"], row["settled_away_score"]) for row in rows}
        if len(scores) != 1:
            continue
        home_score, away_score = next(iter(scores))
        actual_outcome = 0 if home_score > away_score else 2 if home_score < away_score else 1
        probabilities = {
            OUTCOME_INDEX[selection]: outcomes[selection]["probability"]
            for selection in OUTCOME_INDEX
        }
        correct_top_outcomes += int(max(probabilities, key=probabilities.get) == actual_outcome)
        brier_total += sum(
            (probabilities[outcome] - int(outcome == actual_outcome)) ** 2
            for outcome in range(3)
        )
        actual_probability = min(max(probabilities[actual_outcome], epsilon), 1 - epsilon)
        log_loss_total -= math.log(actual_probability)
        settled_groups.append(group)

        for outcome, probability in probabilities.items():
            observed = int(outcome == actual_outcome)
            bin_index = min(int(probability * 5), 4)
            bins[bin_index]["count"] += 1
            bins[bin_index]["mean_probability"] += probability
            bins[bin_index]["observed_rate"] += observed

    for item in bins:
        count = item["count"]
        if count:
            item["mean_probability"] = round(item["mean_probability"] / count, 4)
            item["observed_rate"] = round(item["observed_rate"] / count, 4)

    settled_bets = [row for row in bet_rows if row["settled_home_score"] is not None]
    bet_wins = 0
    bet_profit = 0.0
    bet_odds_total = 0.0
    for row in settled_bets:
        home_score = row["settled_home_score"]
        away_score = row["settled_away_score"]
        actual_outcome = "dom" if home_score > away_score else "ext" if home_score < away_score else "nul"
        hit = int(row["selection"] == actual_outcome)
        bet_wins += hit
        bet_profit += row["odds"] - 1 if hit else -1
        bet_odds_total += row["odds"]

    settled_count = len(settled_groups)
    return {
        "total_predictions": len(groups),
        "settled_predictions": settled_count,
        "pending_predictions": len(groups) - settled_count,
        "wins": correct_top_outcomes,
        "hit_rate": correct_top_outcomes / settled_count if settled_count else None,
        "brier_score": brier_total / settled_count if settled_count else None,
        "log_loss": log_loss_total / settled_count if settled_count else None,
        "simple_bets_total": len(bet_rows),
        "settled_simple_bets": len(settled_bets),
        "simple_bet_hit_rate": bet_wins / len(settled_bets) if settled_bets else None,
        "flat_stake_yield": bet_profit / len(settled_bets) if settled_bets else None,
        "average_decimal_odds": bet_odds_total / len(settled_bets) if settled_bets else None,
        "calibration_bins": bins,
        "warning": (
            "Échantillon trop petit pour conclure. Les résultats historiques ne garantissent pas les prochains."
            if settled_count < 200 else
            "Résultats historiques, non garantis pour les prochains matchs."
        ),
    }
