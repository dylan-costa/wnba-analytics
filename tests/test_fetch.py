"""Fetch logic with the stats API stubbed out (no network)."""

from wnba import fetch


def test_fill_missing_games_looks_up_id_gaps(monkeypatch):
    looked_up = []

    def fake_box_score_rows(game_id, season_id):
        looked_up.append(game_id)
        return [{"GAME_ID": game_id, "SEASON_ID": season_id}] * 2

    monkeypatch.setattr(fetch, "fetch_box_score_rows", fake_box_score_rows)
    rows = [{"GAME_ID": gid, "SEASON_ID": "22007"} for gid in ("1020700001", "1020700002", "1020700004")]

    filled = fetch.fill_missing_games(rows, delay=0)

    assert looked_up == ["1020700003"]
    assert len(filled) == 5


def test_box_score_rows_match_game_log_format(monkeypatch):
    def team(team_id, city, name, abbr, pts, tov):
        return {
            "GAME_ID": "1020700070", "TEAM_ID": team_id, "TEAM_NAME": name, "TEAM_ABBREVIATION": abbr,
            "TEAM_CITY": city, "MIN": "200.000000:00", "FGM": 28, "FGA": 64, "FG_PCT": 0.438, "FG3M": 7,
            "FG3A": 18, "FG3_PCT": 0.389, "FTM": 13, "FTA": 19, "FT_PCT": 0.684, "OREB": 10, "DREB": 22,
            "REB": 32, "AST": 13, "STL": 12, "BLK": 3, "TO": tov, "PF": 12, "PTS": pts, "PLUS_MINUS": 0.0,
        }

    responses = {
        "boxscoresummaryv2": {"GameSummary": [{
            "GAME_STATUS_TEXT": "Final", "HOME_TEAM_ID": 2, "GAME_DATE_EST": "2007-06-20T00:00:00",
        }]},
        "boxscoretraditionalv2": {"TeamStats": [
            team(1, "New York", "Liberty", "NYL", 76, 18),
            team(2, "Connecticut", "Sun", "CON", 73, 23),
        ]},
    }
    monkeypatch.setattr(fetch, "_get", lambda endpoint, params: responses[endpoint])

    away, home = fetch.fetch_box_score_rows("1020700070", "22007")

    assert list(away) == fetch.GAME_LOG_HEADERS
    assert away["TEAM_NAME"] == "New York Liberty"
    assert away["MATCHUP"] == "NYL @ CON"
    assert home["MATCHUP"] == "CON vs. NYL"
    assert (away["WL"], home["WL"]) == ("W", "L")
    assert (away["PLUS_MINUS"], home["PLUS_MINUS"]) == (3, -3)
    assert away["MIN"] == 200
    assert home["TOV"] == 23
    assert away["GAME_DATE"] == "2007-06-20"


def test_box_score_rows_skip_unfinished_games(monkeypatch):
    monkeypatch.setattr(fetch, "_get", lambda endpoint, params: {"GameSummary": [{"GAME_STATUS_TEXT": "7:00 pm ET"}]})
    assert fetch.fetch_box_score_rows("1022600999", "22026") == []
