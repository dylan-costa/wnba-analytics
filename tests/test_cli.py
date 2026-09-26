import sqlite3

import pytest

from wnba import cli


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "update.log"
    monkeypatch.setattr(cli, "UPDATE_LOG_PATH", path)
    return path


@pytest.fixture
def fake_db(monkeypatch):
    def connect():
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (game_date TEXT)")
        conn.execute("INSERT INTO games VALUES ('2026-09-27')")
        return conn

    monkeypatch.setattr(cli.db, "connect", connect)
    monkeypatch.setattr(cli.db, "build", lambda: {"games": 7001})
    monkeypatch.setattr(cli.fetch, "fetch_seasons", lambda seasons, types: {(2026, "playoffs"): (8, 80)})


def test_update_logs_success_and_forecast(log_path, fake_db, monkeypatch):
    monkeypatch.setattr(cli.forecast, "update_forecast", lambda conn: "an update")
    monkeypatch.setattr(cli.forecast, "summarize", lambda update: "1 new games (NYL 80 @ MIN 85); title odds: MIN 20%->24%")

    cli.main(["update"])

    assert log_path.read_text().strip().endswith(
        "ok: 7,001 games in db (fetched 2026 playoffs: 8 team/80 player rows); "
        "forecast: 1 new games (NYL 80 @ MIN 85); title odds: MIN 20%->24%"
    )


def test_update_survives_a_failed_forecast_and_still_pushes(log_path, fake_db, monkeypatch):
    def broken(conn):
        raise ValueError("simulation bug")

    pushed = []
    monkeypatch.setattr(cli.forecast, "update_forecast", broken)
    monkeypatch.setattr(cli.gitsync, "push_data", lambda message: pushed.append(message) or "committed and pushed")

    cli.main(["update", "--push"])

    log = log_path.read_text()
    assert "forecast FAILED" in log and "simulation bug" in log
    assert pushed == ["Update data through 2026-09-27"]
    assert log.strip().endswith("git: committed and pushed")


def test_update_logs_failure_and_skips_build(log_path, monkeypatch):
    def offline(seasons, types):
        raise RuntimeError("stats.wnba.com unreachable")

    monkeypatch.setattr(cli.fetch, "fetch_seasons", offline)
    monkeypatch.setattr(cli.db, "build", lambda: pytest.fail("build should not run after a failed fetch"))

    with pytest.raises(RuntimeError):
        cli.main(["update"])

    log = log_path.read_text()
    assert "FAILED" in log
    assert "stats.wnba.com unreachable" in log
