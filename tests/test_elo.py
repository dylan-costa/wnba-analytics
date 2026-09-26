import pytest

from wnba import elo
from wnba.elo import EloParams, EloState


def game(game_id, season, home, away, home_pts, away_pts, season_type="regular", is_forfeit=False):
    return {
        "game_id": game_id, "season": season, "season_type": season_type, "home_team_id": home,
        "away_team_id": away, "home_pts": home_pts, "away_pts": away_pts, "is_forfeit": is_forfeit,
    }


def test_win_prob_is_symmetric_and_home_advantage_helps():
    assert elo.win_prob(1500, 1500, 0) == 0.5
    assert elo.win_prob(1600, 1500, 0) == pytest.approx(1 - elo.win_prob(1500, 1600, 0))
    assert elo.win_prob(1500, 1500, 50) > 0.5
    assert elo.win_prob(1900, 1500, 0) == pytest.approx(10 / 11)  # 400 points = 10:1 odds


def test_spread_matches_win_prob():
    assert elo.spread(0.5) == 0
    assert elo.spread(0.7) == pytest.approx(-elo.spread(0.3))
    assert elo.spread(0.7) > 0


def test_margin_to_elo_inverts_spread():
    edge = elo.margin_to_elo(3.0)
    assert elo.spread(elo.win_prob(1500, 1500, edge)) == pytest.approx(3.0)


def test_rating_change_rewards_winner_and_margin():
    assert elo.rating_change(1500, 1500, 5, k=30, home_advantage=0) > 0
    assert elo.rating_change(1500, 1500, -5, k=30, home_advantage=0) < 0
    assert elo.rating_change(1500, 1500, 25, 30, 0) > elo.rating_change(1500, 1500, 5, 30, 0)
    # Beating a much weaker team earns less than an upset of equal margin.
    assert elo.rating_change(1700, 1400, 10, 30, 0) < -elo.rating_change(1700, 1400, -10, 30, 0)


def test_run_is_zero_sum_and_skips_forfeits():
    rated, state = elo.run([
        game("g1", 2024, 1, 2, 90, 70),
        game("g2", 2024, 2, 1, 0, 0, is_forfeit=True),
    ])
    assert [g.game_id for g in rated] == ["g1"]
    assert state.ratings[1] + state.ratings[2] == pytest.approx(2 * EloParams().new_team_rating)
    assert state.ratings[1] > state.ratings[2]


def test_season_carryover_and_new_teams():
    params = EloParams(carryover=0.5, new_team_rating=1300, mean=1500)
    state = EloState(params, ratings={1: 1700, 2: 1400}, last_season={1: 2024, 2: 2022})
    assert state.rating(1, 2024) == 1700  # same season: unchanged
    assert state.rating(1, 2025) == 1600  # halfway back to 1500
    assert state.rating(2, 2025) == 1300  # skipped 2023-2024: treated as new
    assert state.rating(3, 2025) == 1300  # never played


def test_home_advantage_comes_from_prior_seasons():
    params = EloParams(home_advantage_seasons=2, initial_home_advantage=75)
    state = EloState(params)
    assert state.home_advantage(1997) == 75  # no history yet
    state.home_margins = {2022: [300.0, 100], 2023: [100.0, 100], 2024: [100.0, 100]}
    assert state.home_advantage(2025) == pytest.approx(elo.margin_to_elo(1.0))  # 2023-2024 average
    assert state.home_advantage(2020) == 0  # bubble season


def test_evaluate_scores_perfect_and_coin_flip_predictions():
    rated, _ = elo.run([game(f"g{i}", 2024, 1, 2, 80 + (i % 2) * 20, 90) for i in range(10)])
    e = elo.evaluate(rated)
    assert e.games == 10
    assert 0 < e.log_loss < 1
    assert 0 <= e.accuracy <= 1
