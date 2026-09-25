import csv
import sqlite3
from pathlib import Path

import pytest

from wnba import db
from wnba.config import RAW_PLAYER_GAMES_DIR, RAW_TEAM_GAMES_DIR
from wnba.fetch import PLAYER_LOG_HEADERS, TEAM_LOG_HEADERS

TEAMS = {1: ("AAA", "Alpha Team"), 2: ("BBB", "Beta Team")}
# Two players per team; team points are split between them.
ROSTERS = {1: [(101, "Alpha One"), (102, "Alpha Two")], 2: [(201, "Beta One"), (202, "Beta Two")]}


def _matchup(team_id, opp_id, home):
    return f"{TEAMS[team_id][0]} {'vs.' if home else '@'} {TEAMS[opp_id][0]}"


def api_row(game_id, team_id, opp_id, home, pts, opp_pts, *, season_id="22024", date="2024-06-01", wl=None, minutes=200):
    """A raw stats-API row for one team's side of a game, with plausible box stats."""
    abbr, name = TEAMS[team_id]
    if wl is None:
        wl = "W" if pts > opp_pts else "L"
    row = dict.fromkeys(TEAM_LOG_HEADERS, 0)
    row.update({
        "SEASON_ID": season_id, "TEAM_ID": team_id, "TEAM_ABBREVIATION": abbr, "TEAM_NAME": name,
        "GAME_ID": game_id, "GAME_DATE": date, "MATCHUP": _matchup(team_id, opp_id, home),
        "WL": wl, "MIN": minutes, "PTS": pts, "PLUS_MINUS": pts - opp_pts,
        "FGM": 30, "FGA": 70, "FG3M": 8, "FG3A": 24, "FTM": 12, "FTA": 15,
        "OREB": 9, "DREB": 25, "REB": 34, "AST": 20, "STL": 7, "BLK": 4, "TOV": 14, "PF": 18,
    })
    return {k: str(v) for k, v in row.items()}


def player_row(game_id, player_id, name, team_id, opp_id, home, pts, *, season_id="22024", date="2024-06-01", minutes=30, plus_minus=""):
    abbr, team_name = TEAMS[team_id]
    row = dict.fromkeys(PLAYER_LOG_HEADERS, 0)
    row.update({
        "SEASON_ID": season_id, "PLAYER_ID": player_id, "PLAYER_NAME": name, "TEAM_ID": team_id,
        "TEAM_ABBREVIATION": abbr, "TEAM_NAME": team_name, "GAME_ID": game_id, "GAME_DATE": date,
        "MATCHUP": _matchup(team_id, opp_id, home), "WL": "", "MIN": minutes, "PTS": pts,
        "FGM": 15, "FGA": 35, "FG3M": 4, "FG3A": 12, "FTM": 6, "FTA": 8, "REB": 17, "AST": 10,
        "PLUS_MINUS": plus_minus, "FANTASY_PTS": "",
    })
    return {k: str(v) for k, v in row.items()}


def game_rows(game_id, home_id, away_id, home_pts, away_pts, **kwargs):
    return [
        api_row(game_id, home_id, away_id, True, home_pts, away_pts, **kwargs),
        api_row(game_id, away_id, home_id, False, away_pts, home_pts, **kwargs),
    ]


def game_player_rows(game_id, home_id, away_id, home_pts, away_pts, *, season_id="22024", date="2024-06-01"):
    rows = []
    for team_id, opp_id, home, pts in ((home_id, away_id, True, home_pts), (away_id, home_id, False, away_pts)):
        (id1, name1), (id2, name2) = ROSTERS[team_id]
        for pid, name, share in ((id1, name1, pts // 2), (id2, name2, pts - pts // 2)):
            rows.append(player_row(game_id, pid, name, team_id, opp_id, home, share, season_id=season_id, date=date))
    return rows


def write_raw(raw_dir: Path, name: str, rows: list[dict], headers: list[str] = TEAM_LOG_HEADERS) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    with open(raw_dir / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_games(root: Path, name: str, games: list[tuple], **kwargs) -> tuple[Path, Path]:
    """Write consistent team + player raw files for (game_id, home, away, home_pts, away_pts) tuples."""
    team_dir, player_dir = root / "team_games", root / "player_games"
    write_raw(team_dir, name, [r for g in games for r in game_rows(*g, **kwargs)])
    write_raw(player_dir, name, [r for g in games for r in game_player_rows(*g, **kwargs)], PLAYER_LOG_HEADERS)
    return team_dir, player_dir


@pytest.fixture(scope="session")
def real_db(tmp_path_factory) -> sqlite3.Connection:
    """The database built from the committed raw data, in a temp dir."""
    if not any(RAW_TEAM_GAMES_DIR.glob("*.csv")) or not any(RAW_PLAYER_GAMES_DIR.glob("*.csv")):
        pytest.skip("no raw data; run `wnba fetch`")
    db_path = tmp_path_factory.mktemp("db") / "wnba.db"
    db.build(db_path=db_path)
    conn = db.connect(db_path)
    yield conn
    conn.close()
