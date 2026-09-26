from datetime import date

from test_forecast import season  # noqa: F401  (fixture)
from conftest import write_games
from wnba import forecast, website


def test_site_renders_and_only_changes_with_new_data(season, tmp_path):  # noqa: F811
    forecasts, site = tmp_path / "forecasts", tmp_path / "site"
    conn = season()
    forecast.update_forecast(conn, sims=200, forecast_dir=forecasts, today=date(2024, 6, 2), seed=1)

    assert website.build_site(conn, site_dir=site, forecast_dir=forecasts) is True
    page = (site / "index.html").read_text(encoding="utf-8")
    assert "Alpha Team" in page and "Beta Team" in page
    assert "Results will appear here once games are played" in page
    assert (site / ".nojekyll").exists()
    assert website.build_site(conn, site_dir=site, forecast_dir=forecasts) is False  # same data, same page
    conn.close()

    # Game 2 was predicted in the first snapshot; once it's played, it's scored.
    write_games(season.root, "2024_b.csv", [("1022400002", 2, 1, 95, 60)], date="2024-06-03")
    conn = season()
    forecast.update_forecast(conn, sims=200, forecast_dir=forecasts, today=date(2024, 6, 4), seed=1)
    assert website.build_site(conn, site_dir=site, forecast_dir=forecasts) is True
    page = (site / "index.html").read_text(encoding="utf-8")
    assert "So far: " in page and "of 1 correct" in page
    assert "AAA 60 @ BBB 95" in page
    conn.close()


def test_live_record_scores_the_last_prediction_before_each_game(season, tmp_path):  # noqa: F811
    forecasts = tmp_path / "forecasts"
    write_games(season.root, "2024_b.csv", [("1022400002", 2, 1, 95, 60)], date="2024-06-03")
    conn = season()
    games_csv = forecasts / "2024_games.csv"
    forecast._append(games_csv, [
        {"snapshot_date": "2024-06-01", "game_id": "1022400002", "game_date": "2024-06-03", "label": "", "home": "BBB",
         "away": "AAA", "home_win_prob": 0.3, "home_spread": -4.0},
        {"snapshot_date": "2024-06-02", "game_id": "1022400002", "game_date": "2024-06-03", "label": "", "home": "BBB",
         "away": "AAA", "home_win_prob": 0.6, "home_spread": 2.0},
    ], forecast.GAME_HEADERS)

    live = website._live_record(conn, games_csv)

    assert (live["games"], live["correct"]) == (1, 1)  # the later 60% pick counts, and BBB won
    conn.close()
