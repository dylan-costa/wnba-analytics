import pytest

from wnba import cli


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "update.log"
    monkeypatch.setattr(cli, "UPDATE_LOG_PATH", path)
    return path


def test_update_logs_success(log_path, monkeypatch):
    monkeypatch.setattr(cli.fetch, "fetch_seasons", lambda seasons, types: {(2026, "regular"): (660, 6000)})
    monkeypatch.setattr(cli.db, "build", lambda: {"games": 7001})

    cli.main(["update"])

    assert log_path.read_text().strip().endswith("ok: 7,001 games in db (fetched 2026 regular: 660 team/6000 player rows)")


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
