"""Monte Carlo simulation of the rest of a season and the playoffs.

Each simulation plays every remaining game: the home team wins with the Elo
win probability, and the margin is drawn from a normal distribution around the
implied spread. Ratings update after every simulated game, so a team that gets
hot in one simulation stays hot for the rest of it; that spreads the outcomes
out the way real seasons do. Games already played are taken as they happened,
including playoff games in a series that's under way.
"""

import random
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from statistics import NormalDist

from wnba import elo
from wnba.predict import ModelState, model_state

# The current playoff format (2025-): the top 8 records make it, the bracket is
# fixed, and the higher seed hosts the games marked H.
PLAYOFF_FORMAT_SINCE = 2025
FIRST_ROUND = [(1, 8), (4, 5), (2, 7), (3, 6)]  # neighbouring series' winners meet in the semifinals
ROUNDS = [("First Round", 3, "HLH"), ("Semifinals", 5, "HHLLH"), ("Finals", 7, "HHLLHLH")]
STAGES = ["Semifinals", "Finals", "Champion"]  # reached by winning each round

_NORMAL = NormalDist()


class GameSimulator:
    """Plays simulated games for one simulation, updating its own copy of the ratings."""

    def __init__(self, ratings: dict[int, float], home_advantage: float, rng: random.Random,
                 k: float = elo.DEFAULT_PARAMS.k, margin_sd: float = elo.MARGIN_SD):
        self.ratings = dict(ratings)
        self.home_advantage = home_advantage
        self.rng = rng
        self.k = k
        self.margin_sd = margin_sd

    def play(self, home: int, away: int) -> int:
        """Play one game and return the winner's team ID."""
        home_elo, away_elo = self.ratings[home], self.ratings[away]
        p = elo.win_prob(home_elo, away_elo, self.home_advantage)
        margin = self.rng.gauss(self.margin_sd * _NORMAL.inv_cdf(p), self.margin_sd)  # P(margin > 0) == p
        home_margin = max(1, round(abs(margin))) * (1 if margin > 0 else -1)
        change = elo.rating_change(home_elo, away_elo, home_margin, self.k, self.home_advantage)
        self.ratings[home] = home_elo + change
        self.ratings[away] = away_elo - change
        return home if margin > 0 else away


def play_series(sim: GameSimulator, high: int, low: int, best_of: int, pattern: str, high_wins: int = 0, low_wins: int = 0) -> int:
    """Finish a series from its current score; `high` is the higher seed. Returns the winner."""
    needed = best_of // 2 + 1
    while high_wins < needed and low_wins < needed:
        game = high_wins + low_wins
        home, away = (high, low) if pattern[game] == "H" else (low, high)
        if sim.play(home, away) == high:
            high_wins += 1
        else:
            low_wins += 1
    return high if high_wins == needed else low


def play_bracket(sim: GameSimulator, seeds: dict[int, int], series_wins: dict[frozenset, Counter]) -> list[list[int]]:
    """Play the playoffs from the current state. `seeds` maps seed -> team;
    `series_wins` holds wins in games already played, by matchup. Returns the
    teams reaching each of STAGES."""
    seed_of = {team: seed for seed, team in seeds.items()}
    matchups = [(seeds[a], seeds[b]) for a, b in FIRST_ROUND]
    stages = []
    for _, best_of, pattern in ROUNDS:
        winners = []
        for a, b in matchups:
            high, low = sorted((a, b), key=seed_of.__getitem__)
            wins = series_wins.get(frozenset((high, low)), Counter())
            winners.append(play_series(sim, high, low, best_of, pattern, wins[high], wins[low]))
        stages.append(winners)
        matchups = list(zip(winners[::2], winners[1::2]))
    return stages


def rank_teams(wins: Counter, losses: Counter, head_to_head: Counter, rng: random.Random) -> list[int]:
    """Order teams by record, best first. Ties go to the better record in games
    among the tied teams (the league's first tiebreaker), then are drawn at
    random since the later tiebreakers need data a simulation doesn't have."""
    teams = list(wins.keys() | losses.keys())
    pct = {t: wins[t] / max(wins[t] + losses[t], 1) for t in teams}
    tiebreak = {t: rng.random() for t in teams}

    def tied_record(team: int) -> int:
        return sum(head_to_head[(team, other)] - head_to_head[(other, team)] for other in teams if other != team and pct[other] == pct[team])

    return sorted(teams, key=lambda t: (-pct[t], -tied_record(t), tiebreak[t]))


@dataclass
class TeamOutlook:
    team_id: int
    abbreviation: str
    rating: float
    wins: int  # so far
    losses: int
    projected_wins: float
    projected_losses: float
    playoff_prob: float | None  # None when the simulation doesn't cover the playoffs
    stage_probs: dict[str, float] = field(default_factory=dict)  # STAGES -> probability
    seed: int | None = None  # when the seeds are already set


@dataclass
class Outlook:
    season: int
    as_of: str | None
    simulations: int
    remaining_regular_season_games: int
    playoffs_simulated: bool
    teams: list[TeamOutlook]


def simulate_season(conn: sqlite3.Connection, season: int | None = None, as_of: str | None = None,
                    sims: int = 10_000, seed: int | None = None) -> Outlook:
    """Simulate the rest of `season` from the games played by `as_of` (default: now).

    Remaining regular-season games come from the league schedule for the
    current season, or from what was actually played after `as_of` when
    replaying a past season. The playoffs are simulated for seasons played
    under the current format.
    """
    state = model_state(conn, season, as_of)
    season = state.season
    played = [g for g in elo.load_games(conn, as_of) if g["season"] == season]
    remaining = _remaining_regular_season(conn, season, as_of)

    wins, losses, head_to_head = Counter(), Counter(), Counter()
    for g in played:
        if g["season_type"] == "regular":
            loser = g["away_team_id"] if g["winner_team_id"] == g["home_team_id"] else g["home_team_id"]
            wins[g["winner_team_id"]] += 1
            losses[loser] += 1
            head_to_head[(g["winner_team_id"], loser)] += 1
    for team in state.ratings:
        wins[team] += 0
        losses[team] += 0

    series_wins: dict[frozenset, Counter] = {}
    for g in played:
        if g["season_type"] == "playoffs" and not g["is_forfeit"]:
            series_wins.setdefault(frozenset((g["home_team_id"], g["away_team_id"])), Counter())[g["winner_team_id"]] += 1

    fixed_seeds = None
    if not remaining:
        fixed_seeds = dict(conn.execute("SELECT seed, team_id FROM playoff_seeds WHERE season = ?", (season,)).fetchall()) or None
    simulate_playoffs = season >= PLAYOFF_FORMAT_SINCE

    rng = random.Random(seed)
    total_wins, playoff_count = Counter(), Counter()
    stage_counts = {stage: Counter() for stage in STAGES}
    for _ in range(sims):
        sim = GameSimulator(state.ratings, state.home_advantage, rng)
        w, l, h2h = wins.copy(), losses.copy(), head_to_head.copy()
        for home, away in remaining:
            winner = sim.play(home, away)
            loser = away if winner == home else home
            w[winner] += 1
            l[loser] += 1
            h2h[(winner, loser)] += 1
        total_wins.update(w)
        if not simulate_playoffs:
            continue
        seeds = fixed_seeds or {i + 1: team for i, team in enumerate(rank_teams(w, l, h2h, rng)[:8])}
        playoff_count.update(seeds.values())
        for stage, teams in zip(STAGES, play_bracket(sim, seeds, series_wins)):
            stage_counts[stage].update(teams)

    seed_of = {team: s for s, team in (fixed_seeds or {}).items()}
    teams = []
    for team in state.ratings:
        games_total = wins[team] + losses[team] + sum(team in (h, a) for h, a in remaining)
        projected = total_wins[team] / sims
        teams.append(TeamOutlook(
            team_id=team,
            abbreviation=state.abbreviations[team],
            rating=state.ratings[team],
            wins=wins[team],
            losses=losses[team],
            projected_wins=projected,
            projected_losses=games_total - projected,
            playoff_prob=playoff_count[team] / sims if simulate_playoffs else None,
            stage_probs={stage: stage_counts[stage][team] / sims for stage in STAGES} if simulate_playoffs else {},
            seed=seed_of.get(team),
        ))
    teams.sort(key=lambda t: (-t.stage_probs.get("Champion", 0), -(t.playoff_prob or 0), -t.projected_wins, -t.rating))
    return Outlook(season, as_of, sims, len(remaining), simulate_playoffs, teams)


def _remaining_regular_season(conn: sqlite3.Connection, season: int, as_of: str | None) -> list[tuple[int, int]]:
    if as_of is not None:
        rows = conn.execute(
            "SELECT home_team_id, away_team_id FROM games WHERE season = ? AND season_type = 'regular' AND game_date > ? "
            "ORDER BY game_date, game_id",
            (season, as_of),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT home_team_id, away_team_id FROM schedule WHERE season = ? AND season_type = 'regular' "
            "ORDER BY game_date, game_id",
            (season,),
        ).fetchall()
    return [tuple(r) for r in rows]
