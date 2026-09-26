import pytest

from conftest import api_row, game_player_rows, game_rows, player_row, write_games, write_raw
from wnba import db, fetch
from wnba.cli import parse_seasons
from wnba.db import FORFEITS, check_player_games, pair_games, parse_player_game, parse_team_game


def test_parse_seasons():
    assert parse_seasons(["2024"]) == [2024]
    assert parse_seasons(["1997-1999", "2024", "1998"]) == [1997, 1998, 1999, 2024]


def test_parse_team_game():
    tg = parse_team_game(api_row("1022400001", 1, 2, False, 85, 80))
    assert tg["season"] == 2024
    assert tg["season_type"] == "regular"
    assert tg["is_home"] is False
    assert tg["pts"] == 85
    assert tg["minutes"] == 200


@pytest.mark.parametrize("season_id,expected", [("12024", "preseason"), ("42024", "playoffs")])
def test_parse_season_type(season_id, expected):
    assert parse_team_game(api_row("x", 1, 2, True, 80, 70, season_id=season_id))["season_type"] == expected


@pytest.mark.parametrize("raw_minutes", [0, 12])
def test_unrecorded_minutes_become_null(raw_minutes):
    assert parse_team_game(api_row("x", 1, 2, True, 80, 70, minutes=raw_minutes))["minutes"] is None


def test_pair_games_picks_winner_and_overtimes():
    rows = game_rows("g1", 1, 2, 88, 90, minutes=225)
    [game] = pair_games([parse_team_game(r) for r in rows])
    assert game["home"]["team_id"] == 1
    assert game["winner_team_id"] == 2
    assert game["overtimes"] == 1
    assert game["is_forfeit"] is False


def test_pair_games_rejects_missing_side():
    rows = game_rows("g1", 1, 2, 80, 70)[:1]
    with pytest.raises(ValueError, match="expected one home and one away"):
        pair_games([parse_team_game(r) for r in rows])


def test_pair_games_rejects_unknown_tie():
    rows = game_rows("g1", 1, 2, 0, 0, wl="")
    with pytest.raises(ValueError, match="not a known forfeit"):
        pair_games([parse_team_game(r) for r in rows])


def test_pair_games_rejects_wl_score_mismatch():
    rows = game_rows("g1", 1, 2, 80, 70, wl="L")
    with pytest.raises(ValueError, match="W/L disagrees"):
        pair_games([parse_team_game(r) for r in rows])


def test_pair_games_awards_known_forfeit(monkeypatch):
    monkeypatch.setitem(FORFEITS, "g1", 1)
    rows = game_rows("g1", 1, 2, 0, 0, wl="", minutes=0)
    [game] = pair_games([parse_team_game(r) for r in rows])
    assert game["winner_team_id"] == 1
    assert game["is_forfeit"] is True


def test_parse_player_game_allows_missing_plus_minus():
    pg = parse_player_game(player_row("g1", 101, "Alpha One", 1, 2, True, 20, plus_minus=""))
    assert (pg["player_id"], pg["team_id"], pg["pts"], pg["minutes"]) == (101, 1, 20, 30)
    assert pg["plus_minus"] is None
    assert parse_player_game(player_row("g1", 101, "Alpha One", 1, 2, True, 20, plus_minus="-7"))["plus_minus"] == -7


def _games(*specs):
    return pair_games([parse_team_game(r) for spec in specs for r in game_rows(*spec)])


def _players(*specs):
    return [parse_player_game(r) for spec in specs for r in game_player_rows(*spec)]


def test_check_player_games_accepts_consistent_rows():
    check_player_games(_games(("g1", 1, 2, 80, 70)), _players(("g1", 1, 2, 80, 70)))


def test_check_player_games_rejects_points_mismatch():
    with pytest.raises(ValueError, match="AAA players scored 79, team scored 80"):
        check_player_games(_games(("g1", 1, 2, 80, 70)), _players(("g1", 1, 2, 79, 70)))


def test_check_player_games_rejects_game_without_players():
    with pytest.raises(ValueError, match="players scored 0"):
        check_player_games(_games(("g1", 1, 2, 80, 70), ("g2", 1, 2, 80, 70)), _players(("g1", 1, 2, 80, 70)))


def test_check_player_games_rejects_duplicates():
    players = _players(("g1", 1, 2, 80, 70))
    with pytest.raises(ValueError, match="listed twice"):
        check_player_games(_games(("g1", 1, 2, 80, 70)), players + players[:1])


def test_build_writes_tables_and_views(tmp_path):
    team_dir, player_dir = write_games(tmp_path, "2024_regular.csv", [("g1", 1, 2, 80, 70), ("g2", 2, 1, 75, 91)])
    db_path = tmp_path / "wnba.db"

    counts = db.build(db_path=db_path, team_dir=team_dir, player_dir=player_dir, schedule_dir=tmp_path / "no_schedule")
    assert counts == {
        "franchises": 2, "team_seasons": 2, "games": 2, "team_games": 4, "players": 4, "player_games": 8,
        "schedule": 0, "elo_games": 2,
    }

    conn = db.connect(db_path)
    alpha, beta = db.standings(conn, 2024)
    assert (alpha["name"], alpha["wins"], alpha["losses"]) == ("Alpha Team", 2, 0)
    assert (alpha["home_wins"], alpha["away_wins"]) == (1, 1)
    assert alpha["pts_per_game"] == 85.5
    assert alpha["fg_pct"] == pytest.approx(30 / 70)
    assert alpha["net_rating"] == pytest.approx(-beta["net_rating"])

    # Alpha Two gets the odd point: 40 + 46 over two games.
    leader = db.scoring_leaders(conn, 2024)[0]
    assert (leader["name"], leader["team"], leader["games"], leader["pts_per_game"]) == ("Alpha Two", "AAA", 2, 43)
    away_game = conn.execute("SELECT is_home, win, opponent_team_id FROM player_games WHERE game_id = 'g2' AND player_id = 101").fetchone()
    assert tuple(away_game) == (0, 1, 2)
    conn.close()


def test_build_is_repeatable(tmp_path):
    team_dir, player_dir = write_games(tmp_path, "2024_regular.csv", [("g1", 1, 2, 80, 70)])
    db_path = tmp_path / "wnba.db"
    first = db.build(db_path=db_path, team_dir=team_dir, player_dir=player_dir, schedule_dir=tmp_path / "no_schedule")
    assert db.build(db_path=db_path, team_dir=team_dir, player_dir=player_dir, schedule_dir=tmp_path / "no_schedule") == first
    assert not (tmp_path / "wnba.db.tmp").exists()


def test_failed_build_keeps_existing_db(tmp_path):
    team_dir, player_dir = write_games(tmp_path, "2024_regular.csv", [("g1", 1, 2, 80, 70)])
    db_path = tmp_path / "wnba.db"
    db.build(db_path=db_path, team_dir=team_dir, player_dir=player_dir, schedule_dir=tmp_path / "no_schedule")

    write_raw(team_dir, "2024_playoffs.csv", game_rows("g2", 1, 2, 80, 70, wl="L", season_id="42024"))
    with pytest.raises(ValueError):
        db.build(db_path=db_path, team_dir=team_dir, player_dir=player_dir, schedule_dir=tmp_path / "no_schedule")
    assert db.connect(db_path).execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1


SCHEDULE_HEADERS = fetch.SCHEDULE_HEADERS


def schedule_row(game_id, home, away, home_seed="", away_seed="", label="First Round", sub_label="Game 1", date="2024-09-22"):
    return {
        "GAME_ID": game_id, "GAME_DATE": date, "GAME_STATUS": 1, "HOME_TEAM_ID": home, "AWAY_TEAM_ID": away,
        "HOME_SEED": home_seed, "AWAY_SEED": away_seed, "GAME_LABEL": label, "GAME_SUB_LABEL": sub_label, "IF_NECESSARY": 0,
    }


def test_build_loads_upcoming_schedule_seeds_and_ratings(tmp_path):
    team_dir, player_dir = write_games(tmp_path, "2024_regular.csv", [("1022400001", 1, 2, 80, 70)])
    schedule_dir = tmp_path / "schedule"
    write_raw(schedule_dir, "2024.csv", [
        schedule_row("1022400001", 1, 2, label="", sub_label=""),  # already played: left out
        schedule_row("1042400101", 1, 2, 1, 2),
        schedule_row("1042400201", 0, 0, label="Finals"),  # teams not decided yet
        schedule_row("1012400001", 1, 2, label="Preseason"),  # ignored
    ], SCHEDULE_HEADERS)
    db_path = tmp_path / "wnba.db"

    counts = db.build(db_path=db_path, team_dir=team_dir, player_dir=player_dir, schedule_dir=schedule_dir)

    assert (counts["schedule"], counts["elo_games"]) == (2, 1)
    conn = db.connect(db_path)
    upcoming = conn.execute("SELECT game_id, season, season_type, home_team_id, label FROM schedule ORDER BY game_id").fetchall()
    assert [tuple(r) for r in upcoming] == [
        ("1042400101", 2024, "playoffs", 1, "First Round Game 1"),
        ("1042400201", 2024, "playoffs", None, "Finals Game 1"),
    ]
    assert [tuple(r) for r in conn.execute("SELECT seed, team_id FROM playoff_seeds ORDER BY seed")] == [(1, 1), (2, 2)]
    home_win_prob, home_spread = conn.execute("SELECT home_win_prob, home_spread FROM elo_games").fetchone()
    assert home_win_prob > 0.5 and home_spread > 0  # equal new teams, so home court decides
    conn.close()


def test_build_rejects_inconsistent_seeds(tmp_path):
    team_dir, player_dir = write_games(tmp_path, "2024_regular.csv", [("1022400001", 1, 2, 80, 70)])
    schedule_dir = tmp_path / "schedule"
    write_raw(schedule_dir, "2024.csv", [
        schedule_row("1042400101", 1, 2, 1, 8),
        schedule_row("1042400102", 2, 1, 7, 1),
    ], SCHEDULE_HEADERS)
    with pytest.raises(ValueError, match="Inconsistent playoff seeds"):
        db.build(db_path=tmp_path / "wnba.db", team_dir=team_dir, player_dir=player_dir, schedule_dir=schedule_dir)
