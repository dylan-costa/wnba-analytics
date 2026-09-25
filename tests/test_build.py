import pytest

from conftest import api_row, game_rows, write_raw
from wnba import db
from wnba.cli import parse_seasons
from wnba.db import FORFEITS, pair_games, parse_team_game


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


def test_build_writes_tables_and_views(tmp_path):
    raw_dir = tmp_path / "raw"
    write_raw(raw_dir, "2024_regular.csv", game_rows("g1", 1, 2, 80, 70) + game_rows("g2", 2, 1, 75, 90))
    db_path = tmp_path / "wnba.db"

    counts = db.build(db_path=db_path, raw_dir=raw_dir)
    assert counts == {"franchises": 2, "team_seasons": 2, "games": 2, "team_games": 4}

    conn = db.connect(db_path)
    alpha, beta = db.standings(conn, 2024)
    assert (alpha["name"], alpha["wins"], alpha["losses"]) == ("Alpha Team", 2, 0)
    assert (alpha["home_wins"], alpha["away_wins"]) == (1, 1)
    assert alpha["pts_per_game"] == 85
    assert alpha["fg_pct"] == pytest.approx(30 / 70)
    assert alpha["net_rating"] == pytest.approx(-beta["net_rating"])
    conn.close()


def test_build_is_repeatable(tmp_path):
    raw_dir = tmp_path / "raw"
    write_raw(raw_dir, "2024_regular.csv", game_rows("g1", 1, 2, 80, 70))
    db_path = tmp_path / "wnba.db"
    first = db.build(db_path=db_path, raw_dir=raw_dir)
    assert db.build(db_path=db_path, raw_dir=raw_dir) == first
    assert not (tmp_path / "wnba.db.tmp").exists()


def test_failed_build_keeps_existing_db(tmp_path):
    raw_dir = tmp_path / "raw"
    write_raw(raw_dir, "2024_regular.csv", game_rows("g1", 1, 2, 80, 70))
    db_path = tmp_path / "wnba.db"
    db.build(db_path=db_path, raw_dir=raw_dir)

    write_raw(raw_dir, "2024_playoffs.csv", game_rows("g2", 1, 2, 80, 70, wl="L", season_id="42024"))
    with pytest.raises(ValueError):
        db.build(db_path=db_path, raw_dir=raw_dir)
    assert db.connect(db_path).execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
