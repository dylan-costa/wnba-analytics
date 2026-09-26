"""Game predictions from the current Elo ratings."""

import sqlite3
from dataclasses import dataclass

from wnba import elo


@dataclass
class ModelState:
    """Elo ratings after every game up to a date, ready to predict games in `season`."""

    elo: elo.EloState
    season: int
    home_advantage: float
    ratings: dict[int, float]  # teams in `season`
    abbreviations: dict[int, str]

    def team_id(self, abbreviation: str) -> int:
        for team_id, abbr in self.abbreviations.items():
            if abbr == abbreviation.upper():
                return team_id
        raise ValueError(f"No team {abbreviation!r} in {self.season}; teams are {', '.join(sorted(self.abbreviations.values()))}")


def model_state(conn: sqlite3.Connection, season: int | None = None, as_of: str | None = None) -> ModelState:
    """Run Elo over games up to `as_of` (default: all) and return ratings for
    `season` (default: the latest season with games)."""
    _, state = elo.run(elo.load_games(conn, as_of))
    if season is None:
        season = conn.execute("SELECT MAX(season) FROM games WHERE ? IS NULL OR game_date <= ?", (as_of, as_of)).fetchone()[0]
    abbreviations = dict(conn.execute("SELECT team_id, abbreviation FROM team_seasons WHERE season = ?", (season,)).fetchall())
    if not abbreviations:
        raise ValueError(f"No games for {season} yet")
    return ModelState(state, season, state.home_advantage(season), state.ratings_for(season, abbreviations), abbreviations)


@dataclass
class Prediction:
    home_team_id: int
    away_team_id: int
    home_win_prob: float
    home_spread: float  # expected home margin in points


def predict_game(state: ModelState, home_team_id: int, away_team_id: int, neutral: bool = False) -> Prediction:
    p = elo.win_prob(state.ratings[home_team_id], state.ratings[away_team_id], 0.0 if neutral else state.home_advantage)
    return Prediction(home_team_id, away_team_id, p, elo.spread(p))


def upcoming_games(conn: sqlite3.Connection, limit: int = 12) -> list[sqlite3.Row]:
    """Scheduled games whose teams are known, soonest first."""
    return conn.execute(
        "SELECT * FROM schedule WHERE home_team_id IS NOT NULL AND away_team_id IS NOT NULL "
        "ORDER BY game_date, game_id LIMIT ?",
        (limit,),
    ).fetchall()
