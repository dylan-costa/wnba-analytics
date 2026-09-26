"""Fetch logic with the stats API stubbed out (no network)."""

import pytest

from wnba import fetch


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: None)


def _team(game_id, team_id, pts, season_id="22007"):
    return {"GAME_ID": game_id, "TEAM_ID": team_id, "PTS": pts, "SEASON_ID": season_id}


def _player(game_id, team_id, pts):
    return {"GAME_ID": game_id, "TEAM_ID": team_id, "PTS": pts}


def _stub_logs(monkeypatch, team_rows, player_rows):
    monkeypatch.setattr(fetch, "fetch_game_log", lambda season, season_type, level: list(
        {"team": team_rows, "player": player_rows}[level]
    ))


def test_fetch_season_fills_team_gaps_and_games_missing_players(monkeypatch, no_sleep):
    # Team log is missing game 3; player log is also missing game 2.
    _stub_logs(
        monkeypatch,
        [_team(g, t, 80) for g in ("1020700001", "1020700002", "1020700004") for t in (1, 2)],
        [_player(g, t, 80) for g in ("1020700001", "1020700003", "1020700004") for t in (1, 2)],
    )
    looked_up = []

    def fake_box_score(game_id, season_id):
        looked_up.append(game_id)
        return [dict(_team(game_id, t, 80), box=True) for t in (1, 2)], [dict(_player(game_id, t, 80), box=True) for t in (1, 2)]

    monkeypatch.setattr(fetch, "fetch_box_score", fake_box_score)

    team_rows, player_rows = fetch.fetch_season(2007, "regular")

    assert looked_up == ["1020700002", "1020700003"]
    # Game 3: team rows added, player rows kept from the log. Game 2: player rows added.
    assert [r["GAME_ID"] for r in team_rows if "box" in r] == ["1020700003"] * 2
    assert [r["GAME_ID"] for r in player_rows if "box" in r] == ["1020700002"] * 2


def test_fetch_season_replaces_player_rows_that_dont_add_up(monkeypatch, no_sleep):
    # Game 2's player log is 3 points short for team 1; its box score adds up.
    _stub_logs(
        monkeypatch,
        [_team(g, t, 81) for g in ("1020000001", "1020000002") for t in (1, 2)],
        [_player("1020000001", 1, 81), _player("1020000001", 2, 81), _player("1020000002", 1, 78), _player("1020000002", 2, 81)],
    )
    monkeypatch.setattr(fetch, "fetch_box_score", lambda game_id, season_id: (
        [], [dict(_player(game_id, t, 81), box=True) for t in (1, 2)]
    ))

    _, player_rows = fetch.fetch_season(2000, "regular")

    assert sorted((r["GAME_ID"], r["PTS"], "box" in r) for r in player_rows) == [
        ("1020000001", 81, False), ("1020000001", 81, False), ("1020000002", 81, True), ("1020000002", 81, True),
    ]


def test_fetch_season_keeps_player_rows_when_box_score_also_disagrees(monkeypatch, no_sleep):
    players = [_player("1029700001", 1, 73), _player("1029700001", 2, 60)]
    _stub_logs(monkeypatch, [_team("1029700001", 1, 70), _team("1029700001", 2, 60)], players)
    monkeypatch.setattr(fetch, "fetch_box_score", lambda game_id, season_id: ([], [dict(p, box=True) for p in players]))

    _, player_rows = fetch.fetch_season(1997, "regular")

    assert player_rows == players


def test_fetch_season_skips_gap_detection_for_playoffs(monkeypatch, no_sleep):
    rows = [_team(gid, t, 80, "42024") for gid in ("1042400101", "1042400201") for t in (1, 2)]
    monkeypatch.setattr(fetch, "fetch_game_log", lambda season, season_type, level: list(rows))
    monkeypatch.setattr(fetch, "fetch_box_score", lambda *args: pytest.fail("no box score lookups expected"))
    assert fetch.fetch_season(2024, "playoffs") == (rows, rows)


def test_box_score_matches_game_log_format(monkeypatch):
    def team(team_id, city, name, abbr, pts, tov):
        return {
            "GAME_ID": "1020700070", "TEAM_ID": team_id, "TEAM_NAME": name, "TEAM_ABBREVIATION": abbr,
            "TEAM_CITY": city, "MIN": "200.000000:00", "FGM": 28, "FGA": 64, "FG_PCT": 0.438, "FG3M": 7,
            "FG3A": 18, "FG3_PCT": 0.389, "FTM": 13, "FTA": 19, "FT_PCT": 0.684, "OREB": 10, "DREB": 22,
            "REB": 32, "AST": 13, "STL": 12, "BLK": 3, "TO": tov, "PF": 12, "PTS": pts, "PLUS_MINUS": 0.0,
        }

    def player(player_id, name, team_id, minutes, pts, plus_minus):
        return {
            "GAME_ID": "1020700070", "TEAM_ID": team_id, "TEAM_ABBREVIATION": "NYL", "PLAYER_ID": player_id,
            "PLAYER_NAME": name, "MIN": minutes, "FGM": 8, "FGA": 15, "FG3M": 2, "FG3A": 5, "FTM": 4, "FTA": 4,
            "OREB": 1, "DREB": 5, "REB": 6, "AST": 3, "STL": 1, "BLK": 0, "TO": 2, "PF": 3, "PTS": pts,
            "PLUS_MINUS": plus_minus,
        }

    responses = {
        "boxscoresummaryv2": {"GameSummary": [{
            "GAME_STATUS_TEXT": "Final", "HOME_TEAM_ID": 2, "GAME_DATE_EST": "2007-06-20T00:00:00",
        }]},
        "boxscoretraditionalv2": {
            "TeamStats": [team(1, "New York", "Liberty", "NYL", 76, 18), team(2, "Connecticut", "Sun", "CON", 73, 23)],
            "PlayerStats": [
                player(100937, "Shameka Christon", 1, "37.000000:17", 22, 4.0),
                player(200714, "Lindsay Bowen", 1, None, None, None),  # DNP
            ],
        },
    }
    monkeypatch.setattr(fetch, "_get", lambda endpoint, params: responses[endpoint])

    (away, home), players = fetch.fetch_box_score("1020700070", "22007")

    assert list(away) == fetch.TEAM_LOG_HEADERS
    assert away["TEAM_NAME"] == "New York Liberty"
    assert (away["MATCHUP"], home["MATCHUP"]) == ("NYL @ CON", "CON vs. NYL")
    assert (away["WL"], home["WL"]) == ("W", "L")
    assert (away["PLUS_MINUS"], home["PLUS_MINUS"]) == (3, -3)
    assert (away["MIN"], home["TOV"], away["GAME_DATE"]) == (200, 23, "2007-06-20")

    [christon] = players  # the DNP is dropped
    assert list(christon) == fetch.PLAYER_LOG_HEADERS
    assert (christon["TEAM_NAME"], christon["MATCHUP"], christon["WL"]) == ("New York Liberty", "NYL @ CON", "W")
    assert (christon["MIN"], christon["PTS"], christon["PLUS_MINUS"], christon["TOV"]) == (37, 22, 4, 2)


def test_box_score_skips_unfinished_games(monkeypatch):
    monkeypatch.setattr(fetch, "_get", lambda endpoint, params: {"GameSummary": [{"GAME_STATUS_TEXT": "7:00 pm ET"}]})
    assert fetch.fetch_box_score("1022600999", "22026") is None


def test_fetch_schedule_flattens_games(monkeypatch):
    team = lambda team_id, tricode, seed: {"teamId": team_id, "teamTricode": tricode, "seed": seed}
    response = {"leagueSchedule": {"gameDates": [{"games": [
        {"gameId": "1042600101", "gameDateEst": "2026-09-27T00:00:00Z", "gameStatus": 1, "ifNecessary": False,
         "gameLabel": "First Round", "gameSubLabel": "Game 1", "homeTeam": team(1611661324, "MIN", 1), "awayTeam": team(1611661313, "NYL", 8)},
        {"gameId": "1042600301", "gameDateEst": "2026-10-17T00:00:00Z", "gameStatus": 1, "ifNecessary": "true",
         "gameLabel": "WNBA Finals", "gameSubLabel": "Game 1", "homeTeam": team(0, None, None), "awayTeam": team(0, None, None)},
    ]}]}}
    monkeypatch.setattr(fetch, "_get_json", lambda endpoint, params: response)

    first_round, finals = fetch.fetch_schedule(2026)

    assert list(first_round) == fetch.SCHEDULE_HEADERS
    assert (first_round["GAME_DATE"], first_round["HOME_SEED"], first_round["AWAY_SEED"], first_round["IF_NECESSARY"]) == ("2026-09-27", 1, 8, 0)
    assert (finals["HOME_TEAM_ID"], finals["HOME_SEED"], finals["IF_NECESSARY"]) == (0, "", 1)
