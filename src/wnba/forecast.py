"""Forecast snapshots: re-run the simulation whenever new games come in, and
keep the history.

Each snapshot appends to two CSVs in data/forecasts/ (committed with the data):
  {season}_odds.csv   one row per team: rating, record, and playoff/title odds
  {season}_games.csv  one row per upcoming game: home win probability and spread
Predictions are written down before the games are played, so they can later be
scored honestly against results the model had never seen.

A new result moves every team's odds (it reshapes the bracket), so the whole
league is re-simulated, but the summary calls out the teams that just played.
"""

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from wnba import predict, simulate
from wnba.config import FORECAST_DIR

ODDS_HEADERS = [
    "snapshot_date", "through_date", "games", "team", "seed", "elo", "wins", "losses",
    "projected_wins", "projected_losses", "playoffs", "semifinals", "finals", "champion",
]
GAME_HEADERS = ["snapshot_date", "game_id", "game_date", "label", "home", "away", "home_win_prob", "home_spread"]


@dataclass
class ForecastUpdate:
    season: int
    through_date: str
    new_games: list[str]  # e.g. "NYL 80 @ MIN 85"
    teams_played: set[str]
    odds: list[dict]  # this snapshot's odds rows
    previous: dict[str, dict]  # team -> the previous snapshot's row (empty for the first)


def update_forecast(conn: sqlite3.Connection, sims: int = 20_000, forecast_dir: Path = FORECAST_DIR,
                    today: date | None = None, seed: int | None = None) -> ForecastUpdate | None:
    """Take a new snapshot if games were played since the last one; otherwise return None."""
    season, games_played, through_date = conn.execute(
        "SELECT season, COUNT(*), MAX(game_date) FROM games WHERE season = (SELECT MAX(season) FROM games) GROUP BY season"
    ).fetchone()
    odds_path = forecast_dir / f"{season}_odds.csv"
    history = _read(odds_path)
    previous_rows = [r for r in history if (r["snapshot_date"], r["games"]) == (history[-1]["snapshot_date"], history[-1]["games"])] if history else []
    if previous_rows and int(previous_rows[0]["games"]) == games_played:
        return None
    previous_through = previous_rows[0]["through_date"] if previous_rows else None

    abbr = dict(conn.execute("SELECT team_id, abbreviation FROM team_seasons WHERE season = ?", (season,)).fetchall())
    new_games, teams_played = [], set()
    if previous_through:
        for g in conn.execute(
            "SELECT home_team_id, away_team_id, home_pts, away_pts FROM games WHERE season = ? AND game_date > ? ORDER BY game_date, game_id",
            (season, previous_through),
        ):
            home, away = abbr[g["home_team_id"]], abbr[g["away_team_id"]]
            new_games.append(f"{away} {g['away_pts']} @ {home} {g['home_pts']}")
            teams_played |= {home, away}

    snapshot_date = (today or date.today()).isoformat()
    outlook = simulate.simulate_season(conn, season, sims=sims, seed=seed)
    odds = [{
        "snapshot_date": snapshot_date, "through_date": through_date, "games": games_played,
        "team": t.abbreviation, "seed": t.seed or "", "elo": round(t.rating, 1), "wins": t.wins, "losses": t.losses,
        "projected_wins": round(t.projected_wins, 2), "projected_losses": round(t.projected_losses, 2),
        "playoffs": _prob(t.playoff_prob),
        **{stage.lower(): _prob(t.stage_probs.get(stage)) for stage in simulate.STAGES},
    } for t in outlook.teams]

    state = predict.model_state(conn, season)
    game_rows = []
    for g in predict.upcoming_games(conn, limit=None):
        p = predict.predict_game(state, g["home_team_id"], g["away_team_id"])
        game_rows.append({
            "snapshot_date": snapshot_date, "game_id": g["game_id"], "game_date": g["game_date"], "label": g["label"],
            "home": abbr[g["home_team_id"]], "away": abbr[g["away_team_id"]],
            "home_win_prob": round(p.home_win_prob, 4), "home_spread": round(p.home_spread, 1),
        })

    _append(odds_path, odds, ODDS_HEADERS)
    if game_rows:
        _append(forecast_dir / f"{season}_games.csv", game_rows, GAME_HEADERS)
    return ForecastUpdate(season, through_date, new_games, teams_played, odds, {r["team"]: r for r in previous_rows})


def summarize(update: ForecastUpdate, movers: int = 6) -> str:
    """One line for the update log: new games, then the biggest changes in title
    (or, before the playoffs are simulated, projected wins)."""
    metric = "champion" if any(r["champion"] != "" for r in update.odds) else "projected_wins"
    label = "title odds" if metric == "champion" else "projected wins"
    fmt = (lambda v: f"{float(v):.0%}") if metric == "champion" else (lambda v: f"{float(v):.1f}")

    if not update.previous:
        top = sorted(update.odds, key=lambda r: -float(r[metric] or 0))[:3]
        return f"first {update.season} forecast; {label}: " + ", ".join(f"{r['team']} {fmt(r[metric])}" for r in top)

    changes = []
    for r in update.odds:
        before = update.previous.get(r["team"])
        if before is None or r[metric] == "" or before[metric] == "":
            continue
        delta = float(r[metric]) - float(before[metric])
        if r["team"] in update.teams_played or abs(delta) >= (0.01 if metric == "champion" else 0.5):
            changes.append((abs(delta), f"{r['team']} {fmt(before[metric])}->{fmt(r[metric])}"))
    changes.sort(reverse=True)
    new = f"{len(update.new_games)} new games ({', '.join(update.new_games)})" if update.new_games else "new games"
    moved = ", ".join(text for _, text in changes[:movers]) or "no notable changes"
    return f"{new}; {label}: {moved}"


def snapshots(season: int | None = None, forecast_dir: Path = FORECAST_DIR) -> tuple[int | None, list[list[dict]]]:
    """(season, snapshots oldest first), each snapshot being its odds rows.
    Defaults to the latest season with a forecast."""
    if season is None:
        files = sorted(forecast_dir.glob("*_odds.csv"))
        if not files:
            return None, []
        season = int(files[-1].name.split("_")[0])
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in _read(forecast_dir / f"{season}_odds.csv"):
        grouped.setdefault((row["snapshot_date"], row["games"]), []).append(row)
    return season, list(grouped.values())


def _prob(p: float | None) -> str | float:
    return "" if p is None else round(p, 4)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _append(path: Path, rows: list[dict], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)
