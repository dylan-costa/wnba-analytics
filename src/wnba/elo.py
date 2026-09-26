"""Elo team ratings, updated game by game since 1997.

Win probability comes from the rating gap plus home-court advantage. After each
game both teams move by K times a margin-of-victory multiplier (the
FiveThirtyEight NBA formula), so blowouts count more than close games but
big favorites gain less from beating weak teams. Between seasons ratings
regress toward the mean; teams that didn't play the previous season
(expansion teams, or Portland returning in 2026) start below average.

Home advantage isn't fixed: it fell from about +3 points (60% home wins)
before 2020 to about +1.5 (54%) since. Each season uses the average home
margin over the few seasons before it, so it adapts without peeking at the
season being predicted.
"""

import math
import sqlite3
from dataclasses import dataclass, field
from statistics import NormalDist

# 2020 was played in a bubble at IMG Academy, so nobody had home court.
NEUTRAL_SEASONS = {2020}

# Standard deviation of the final margin around the predicted spread, in points.
# Fitted by `wnba backtest`; spread = MARGIN_SD * inverse-normal(win probability).
MARGIN_SD = 11.0

_NORMAL = NormalDist()


@dataclass(frozen=True)
class EloParams:
    k: float = 30.0
    carryover: float = 0.5  # share of a team's distance from the mean kept into the next season
    new_team_rating: float = 1300.0
    home_advantage_seasons: int = 5  # prior seasons averaged to set each season's home advantage
    initial_home_advantage: float = 75.0  # Elo points, for 1997 when there's no history
    mean: float = 1500.0


# Parameters are tuned on these seasons; later seasons are held out to check them.
TRAIN_SEASONS = range(1997, 2019)

# Chosen by `wnba backtest --tune`: best log loss on TRAIN_SEASONS, then
# checked on 2019 onward (see the README for the numbers).
DEFAULT_PARAMS = EloParams()


def margin_to_elo(margin: float, margin_sd: float = MARGIN_SD) -> float:
    """Elo edge equivalent to an expected margin in points."""
    p = _NORMAL.cdf(margin / margin_sd)
    return 400 * math.log10(p / (1 - p))


def win_prob(home_elo: float, away_elo: float, home_advantage: float) -> float:
    """Probability the home team wins; pass home_advantage=0 for a neutral site."""
    return 1 / (1 + 10 ** (-(home_elo - away_elo + home_advantage) / 400))


def spread(home_win_prob: float, margin_sd: float = MARGIN_SD) -> float:
    """Expected home margin in points implied by a win probability."""
    return margin_sd * _NORMAL.inv_cdf(home_win_prob)


def rating_change(home_elo: float, away_elo: float, home_margin: int, k: float, home_advantage: float) -> float:
    """Points the home team gains (and the away team loses) from a result."""
    home_won = home_margin > 0
    edge = home_elo - away_elo + home_advantage
    winner_edge = edge if home_won else -edge
    mov_multiplier = (abs(home_margin) + 3) ** 0.8 / (7.5 + 0.006 * winner_edge)
    return k * mov_multiplier * ((1.0 if home_won else 0.0) - win_prob(home_elo, away_elo, home_advantage))


@dataclass
class RatedGame:
    game_id: str
    season: int
    season_type: str
    home_team_id: int
    away_team_id: int
    home_margin: int
    home_elo_pre: float
    away_elo_pre: float
    home_advantage: float
    home_win_prob: float
    home_elo_post: float
    away_elo_post: float


@dataclass
class EloState:
    """Ratings after the games run so far, able to answer 'what would this
    team be rated going into a game in season S'."""

    params: EloParams = DEFAULT_PARAMS
    ratings: dict[int, float] = field(default_factory=dict)
    last_season: dict[int, int] = field(default_factory=dict)
    # season -> [sum of home margins, games], neutral seasons excluded
    home_margins: dict[int, list[float]] = field(default_factory=dict)

    def rating(self, team_id: int, season: int) -> float:
        """Rating going into a game in `season`, applying the between-season
        regression if the team hasn't played yet that season."""
        last = self.last_season.get(team_id)
        if last == season:
            return self.ratings[team_id]
        if last == season - 1:
            p = self.params
            return p.mean + p.carryover * (self.ratings[team_id] - p.mean)
        return self.params.new_team_rating

    def ratings_for(self, season: int, team_ids) -> dict[int, float]:
        return {team_id: self.rating(team_id, season) for team_id in team_ids}

    def home_advantage(self, season: int) -> float:
        """Home advantage in Elo points for games in `season` (0 if neutral)."""
        if season in NEUTRAL_SEASONS:
            return 0.0
        prior = sorted(s for s in self.home_margins if s < season)[-self.params.home_advantage_seasons:]
        if not prior:
            return self.params.initial_home_advantage
        total = sum(self.home_margins[s][0] for s in prior)
        games = sum(self.home_margins[s][1] for s in prior)
        return margin_to_elo(total / games)

    def record_game(self, season: int, home: int, away: int, home_elo: float, away_elo: float, change: float, home_margin: int) -> None:
        self.ratings[home], self.ratings[away] = home_elo + change, away_elo - change
        self.last_season[home] = self.last_season[away] = season
        if season not in NEUTRAL_SEASONS:
            totals = self.home_margins.setdefault(season, [0.0, 0])
            totals[0] += home_margin
            totals[1] += 1


def run(games, params: EloParams = DEFAULT_PARAMS) -> tuple[list[RatedGame], EloState]:
    """Rate games in order. `games` are dicts (or sqlite Rows) with game_id,
    season, season_type, home_team_id, away_team_id, home_pts, away_pts and
    is_forfeit. Forfeits don't change ratings."""
    state = EloState(params)
    rated = []
    season_hca: dict[int, float] = {}
    for g in games:
        if g["is_forfeit"]:
            continue
        season, home, away = g["season"], g["home_team_id"], g["away_team_id"]
        if season not in season_hca:  # fixed for the whole season, from earlier seasons only
            season_hca[season] = state.home_advantage(season)
        hca = season_hca[season]
        home_elo, away_elo = state.rating(home, season), state.rating(away, season)
        margin = g["home_pts"] - g["away_pts"]
        change = rating_change(home_elo, away_elo, margin, params.k, hca)
        rated.append(RatedGame(
            g["game_id"], season, g["season_type"], home, away, margin, home_elo, away_elo, hca,
            win_prob(home_elo, away_elo, hca), home_elo + change, away_elo - change,
        ))
        state.record_game(season, home, away, home_elo, away_elo, change, margin)
    return rated, state


def load_games(conn: sqlite3.Connection, through_date: str | None = None) -> list[sqlite3.Row]:
    """Games in the order they were played, optionally only up to a date."""
    return conn.execute(
        "SELECT game_id, season, season_type, game_date, home_team_id, away_team_id, home_pts, away_pts, "
        "winner_team_id, is_forfeit FROM games WHERE ? IS NULL OR game_date <= ? ORDER BY game_date, game_id",
        (through_date, through_date),
    ).fetchall()


@dataclass
class Evaluation:
    games: int
    log_loss: float
    brier: float
    accuracy: float
    baseline_log_loss: float  # always predicting these games' overall home win rate
    margin_sd: float  # fitted spread scale (see MARGIN_SD)
    spread_rmse: float


def evaluate(rated: list[RatedGame], margin_sd: float | None = None) -> Evaluation:
    """Score pre-game predictions against results. Fits the margin scale on
    these games unless one is given."""
    n = len(rated)
    eps = 1e-12
    outcomes = [1.0 if g.home_margin > 0 else 0.0 for g in rated]
    probs = [min(max(g.home_win_prob, eps), 1 - eps) for g in rated]
    home_rate = sum(outcomes) / n
    z = [_NORMAL.inv_cdf(p) for p in probs]
    if margin_sd is None:
        margin_sd = sum(g.home_margin * zi for g, zi in zip(rated, z)) / sum(zi * zi for zi in z)
    return Evaluation(
        games=n,
        log_loss=-sum(y * math.log(p) + (1 - y) * math.log(1 - p) for y, p in zip(outcomes, probs)) / n,
        brier=sum((p - y) ** 2 for y, p in zip(outcomes, probs)) / n,
        accuracy=sum((p > 0.5) == (y == 1.0) for y, p in zip(outcomes, probs)) / n,
        baseline_log_loss=-(home_rate * math.log(home_rate) + (1 - home_rate) * math.log(1 - home_rate)),
        margin_sd=margin_sd,
        spread_rmse=math.sqrt(sum((g.home_margin - margin_sd * zi) ** 2 for g, zi in zip(rated, z)) / n),
    )


def calibration(rated: list[RatedGame], buckets: int = 10) -> list[tuple[float, float, int]]:
    """(mean predicted home win prob, actual home win rate, games) per probability bucket."""
    groups: dict[int, list[RatedGame]] = {}
    for g in rated:
        groups.setdefault(min(int(g.home_win_prob * buckets), buckets - 1), []).append(g)
    return [
        (sum(g.home_win_prob for g in gs) / len(gs), sum(g.home_margin > 0 for g in gs) / len(gs), len(gs))
        for _, gs in sorted(groups.items())
    ]


TUNING_GRID = {
    "k": [20, 25, 30],
    "carryover": [0.4, 0.5, 0.6, 0.7],
    "new_team_rating": [1300, 1350, 1400, 1450],
    "home_advantage_seasons": [1, 2, 3, 5],
}


def tune(games, train_seasons: range = TRAIN_SEASONS, grid: dict[str, list] = TUNING_GRID) -> list[tuple[float, EloParams]]:
    """Grid-search parameters by log loss on `train_seasons`. Returns
    (log loss, params) pairs, best first. Ratings still run over every game so
    early seasons warm up the ratings; only the scoring is restricted."""
    results = []
    for k in grid["k"]:
        for carryover in grid["carryover"]:
            for new_team in grid["new_team_rating"]:
                for window in grid["home_advantage_seasons"]:
                    params = EloParams(k=k, carryover=carryover, new_team_rating=new_team, home_advantage_seasons=window)
                    rated, _ = run(games, params)
                    results.append((evaluate([g for g in rated if g.season in train_seasons]).log_loss, params))
    return sorted(results, key=lambda r: r[0])
