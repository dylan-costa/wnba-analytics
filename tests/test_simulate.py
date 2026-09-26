import random
from collections import Counter

import pytest

from wnba import simulate
from wnba.simulate import GameSimulator, play_bracket, play_series, rank_teams


class ScriptedSimulator:
    """Stands in for GameSimulator: records who hosted each game; the given team always wins."""

    def __init__(self, winner=None):
        self.winner = winner
        self.hosts = []

    def play(self, home, away):
        self.hosts.append(home)
        return self.winner if self.winner in (home, away) else min(home, away)


def test_simulated_games_match_elo_win_probability():
    rng = random.Random(0)
    sim = GameSimulator({1: 1600, 2: 1500}, home_advantage=0, rng=rng, k=0)  # k=0 keeps ratings fixed
    wins = sum(sim.play(1, 2) == 1 for _ in range(20_000))
    assert wins / 20_000 == pytest.approx(simulate.elo.win_prob(1600, 1500, 0), abs=0.01)


def test_simulated_games_update_ratings():
    sim = GameSimulator({1: 1500, 2: 1500}, home_advantage=0, rng=random.Random(1))
    winner = sim.play(1, 2)
    loser = 2 if winner == 1 else 1
    assert sim.ratings[winner] > 1500 > sim.ratings[loser]


def test_series_follows_home_pattern():
    sim = ScriptedSimulator(winner=None)  # lower team ID (the high seed here) always wins
    assert play_series(sim, 1, 2, best_of=5, pattern="HHLLH", high_wins=0, low_wins=2) == 1
    assert sim.hosts == [2, 2, 1]  # games 3 and 4 at the low seed, game 5 at the high seed


def test_finished_series_isnt_replayed():
    sim = ScriptedSimulator()
    assert play_series(sim, 1, 2, best_of=3, pattern="HLH", high_wins=0, low_wins=2) == 2
    assert sim.hosts == []


def test_bracket_pairs_one_eight_with_four_five():
    seeds = {s: 100 + s for s in range(1, 9)}  # team 101 is the 1 seed
    sim = ScriptedSimulator()  # lower team ID wins, so higher seeds always advance
    semis, finals, champion = play_bracket(sim, seeds, {})
    assert semis == [101, 104, 102, 103]
    assert finals == [101, 102]
    assert champion == [101]


def test_bracket_uses_series_already_played():
    seeds = {s: 100 + s for s in range(1, 9)}
    # The 8 seed has already won the first round against the 1 seed.
    series_wins = {frozenset((101, 108)): Counter({108: 2})}
    semis, _, _ = play_bracket(ScriptedSimulator(), seeds, series_wins)
    assert semis[0] == 108


def test_rank_teams_breaks_ties_by_record_among_tied_teams():
    wins = Counter({1: 20, 2: 20, 3: 25})
    losses = Counter({1: 20, 2: 20, 3: 15})
    head_to_head = Counter({(2, 1): 2, (1, 2): 1})
    assert rank_teams(wins, losses, head_to_head, random.Random(0)) == [3, 2, 1]


@pytest.mark.data
def test_simulate_current_playoffs_from_seeds(real_db):
    outlook = simulate.simulate_season(real_db, season=2026, sims=500, seed=1)
    assert outlook.remaining_regular_season_games == 0
    in_playoffs = [t for t in outlook.teams if t.seed]
    assert len(in_playoffs) == 8
    assert sum(t.stage_probs["Champion"] for t in outlook.teams) == pytest.approx(1)
    assert sum(t.stage_probs["Finals"] for t in outlook.teams) == pytest.approx(2)
    assert all(t.playoff_prob == 0 for t in outlook.teams if not t.seed)


@pytest.mark.data
def test_replay_past_season_from_midseason(real_db):
    outlook = simulate.simulate_season(real_db, season=2025, as_of="2025-07-15", sims=300, seed=1)
    assert outlook.remaining_regular_season_games > 100
    by_team = {t.abbreviation: t for t in outlook.teams}
    # Every team finishes with 44 games, and 8 teams make the playoffs per simulation.
    assert all(t.projected_wins + t.projected_losses == pytest.approx(44) for t in outlook.teams)
    assert sum(t.playoff_prob for t in outlook.teams) == pytest.approx(8)
    assert by_team["MIN"].wins == 19
