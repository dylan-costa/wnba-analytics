"""Checks against the committed raw data: known records and whole-league invariants."""

import pytest

pytestmark = pytest.mark.data


def record(conn, season, abbreviation, season_type="regular"):
    row = conn.execute(
        "SELECT wins, losses FROM team_season_stats WHERE season = ? AND season_type = ? AND abbreviation = ?",
        (season, season_type, abbreviation),
    ).fetchone()
    return tuple(row)


@pytest.mark.parametrize(
    "season,abbreviation,expected",
    [
        (1997, "HOU", (18, 10)),
        (1998, "HOU", (27, 3)),
        (2023, "LVA", (34, 6)),
        (2024, "NYL", (32, 8)),
        # 2018 includes the Aces' forfeit loss at Washington.
        (2018, "LVA", (14, 20)),
        (2018, "WAS", (22, 12)),
    ],
)
def test_known_regular_season_records(real_db, season, abbreviation, expected):
    assert record(real_db, season, abbreviation) == expected


def test_wins_equal_losses_every_season(real_db):
    unbalanced = real_db.execute(
        "SELECT season, season_type FROM team_games GROUP BY season, season_type HAVING SUM(win) * 2 != COUNT(*)"
    ).fetchall()
    assert unbalanced == []


def test_every_game_has_two_consistent_sides(real_db):
    bad = real_db.execute(
        """
        SELECT g.game_id FROM games g
        JOIN team_games h ON h.game_id = g.game_id AND h.is_home
        JOIN team_games a ON a.game_id = g.game_id AND NOT a.is_home
        WHERE h.team_id != g.home_team_id OR a.team_id != g.away_team_id
           OR h.pts != g.home_pts OR a.pts != g.away_pts OR h.win + a.win != 1
        """
    ).fetchall()
    assert bad == []
    assert real_db.execute("SELECT COUNT(*) FROM team_games").fetchone()[0] == 2 * real_db.execute(
        "SELECT COUNT(*) FROM games"
    ).fetchone()[0]


def test_teams_play_equal_regular_seasons(real_db):
    """Every team plays the same number of regular-season games (the old CSVs failed this)."""
    uneven = real_db.execute(
        """
        SELECT season FROM team_season_stats WHERE season_type = 'regular'
        GROUP BY season HAVING MIN(games) != MAX(games)
        """
    ).fetchall()
    assert uneven == []


def test_relocated_franchises_share_an_id(real_db):
    names = {
        row[0]
        for row in real_db.execute(
            "SELECT DISTINCT ts.name FROM team_seasons ts JOIN franchises f USING (team_id) WHERE f.current_abbreviation = 'LVA'"
        )
    }
    assert names == {"Utah Starzz", "San Antonio Silver Stars", "San Antonio Stars", "Las Vegas Aces"}


def test_known_scoring_season(real_db):
    """A'ja Wilson's 2024 scoring title: 1,021 points in 38 games."""
    row = real_db.execute(
        "SELECT games, pts_per_game FROM player_season_stats "
        "WHERE season = 2024 AND season_type = 'regular' AND name = 'A''ja Wilson'"
    ).fetchone()
    assert row["games"] == 38
    assert round(row["pts_per_game"] * row["games"]) == 1021


def test_player_points_match_team_points(real_db):
    """Build checks this per game; this guards the loaded tables as a whole."""
    team_total, player_total = real_db.execute(
        """
        SELECT
            (SELECT SUM(pts) FROM team_games JOIN games USING (game_id) WHERE player_box = 'ok'),
            (SELECT SUM(pts) FROM player_games JOIN games USING (game_id) WHERE player_box = 'ok')
        """
    ).fetchone()
    assert team_total == player_total


def test_player_box_exceptions_are_rare(real_db):
    counts = dict(real_db.execute("SELECT player_box, COUNT(*) FROM games GROUP BY player_box").fetchall())
    assert counts["points_mismatch"] == 7
    assert counts["missing"] == 2


def test_every_played_game_has_players_on_both_teams(real_db):
    missing = real_db.execute(
        """
        SELECT tg.game_id, tg.team_id FROM team_games tg JOIN games g USING (game_id)
        WHERE g.player_box != 'missing'
          AND NOT EXISTS (SELECT 1 FROM player_games pg WHERE pg.game_id = tg.game_id AND pg.team_id = tg.team_id)
        """
    ).fetchall()
    assert missing == []
