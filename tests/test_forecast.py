from datetime import date

import pytest

from conftest import write_games, write_raw
from wnba import db, forecast
from wnba.fetch import SCHEDULE_HEADERS


def schedule_row(game_id, home, away, game_date):
    return {
        "GAME_ID": game_id, "GAME_DATE": game_date, "GAME_STATUS": 1, "HOME_TEAM_ID": home, "AWAY_TEAM_ID": away,
        "HOME_SEED": "", "AWAY_SEED": "", "GAME_LABEL": "", "GAME_SUB_LABEL": "", "IF_NECESSARY": 0,
    }


@pytest.fixture
def season(tmp_path):
    """A 2024 season with one game played and two on the schedule; returns a
    function that rebuilds the database and returns a connection."""
    root = tmp_path / "raw"
    write_games(root, "2024_a.csv", [("1022400001", 1, 2, 80, 70)], date="2024-06-01")
    write_raw(root / "schedule", "2024.csv", [
        schedule_row("1022400001", 1, 2, "2024-06-01"),
        schedule_row("1022400002", 2, 1, "2024-06-03"),
        schedule_row("1022400003", 1, 2, "2024-06-05"),
    ], SCHEDULE_HEADERS)

    def rebuild():
        db_path = tmp_path / "wnba.db"
        db.build(db_path=db_path, team_dir=root / "team_games", player_dir=root / "player_games", schedule_dir=root / "schedule")
        return db.connect(db_path)

    rebuild.root = root
    return rebuild


def test_first_snapshot_then_nothing_until_new_games(season, tmp_path):
    forecasts = tmp_path / "forecasts"
    conn = season()

    first = forecast.update_forecast(conn, sims=200, forecast_dir=forecasts, today=date(2024, 6, 2), seed=1)
    assert first is not None and first.previous == {} and first.new_games == []
    assert {r["team"] for r in first.odds} == {"AAA", "BBB"}
    assert forecast.summarize(first).startswith("first 2024 forecast; projected wins:")
    games = (forecasts / "2024_games.csv").read_text().splitlines()
    assert len(games) == 3  # header + both upcoming games, predicted before they're played

    assert forecast.update_forecast(conn, sims=200, forecast_dir=forecasts, seed=1) is None
    conn.close()


def test_new_game_triggers_snapshot_and_summary(season, tmp_path):
    forecasts = tmp_path / "forecasts"
    conn = season()
    forecast.update_forecast(conn, sims=200, forecast_dir=forecasts, today=date(2024, 6, 2), seed=1)
    conn.close()

    write_games(season.root, "2024_b.csv", [("1022400002", 2, 1, 95, 60)], date="2024-06-03")
    conn = season()
    update = forecast.update_forecast(conn, sims=200, forecast_dir=forecasts, today=date(2024, 6, 4), seed=1)

    assert update.new_games == ["AAA 60 @ BBB 95"]
    assert update.teams_played == {"AAA", "BBB"}
    assert set(update.previous) == {"AAA", "BBB"}
    summary = forecast.summarize(update)
    assert summary.startswith("1 new games (AAA 60 @ BBB 95); projected wins:")
    assert "AAA" in summary and "BBB" in summary  # teams that played are always listed

    season_, history = forecast.snapshots(forecast_dir=forecasts)
    assert season_ == 2024
    assert [snapshot[0]["through_date"] for snapshot in history] == ["2024-06-01", "2024-06-03"]
    conn.close()
