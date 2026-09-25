import csv
import sqlite3
from pathlib import Path

import pytest

from wnba import db
from wnba.config import RAW_GAME_LOG_DIR

API_HEADERS = [
    "SEASON_ID", "TEAM_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "GAME_ID", "GAME_DATE", "MATCHUP", "WL",
    "MIN", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT", "OREB", "DREB",
    "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS", "VIDEO_AVAILABLE",
]

TEAMS = {1: ("AAA", "Alpha Team"), 2: ("BBB", "Beta Team")}


def api_row(game_id, team_id, opp_id, home, pts, opp_pts, *, season_id="22024", date="2024-06-01", wl=None, minutes=200):
    """A raw stats-API row for one team's side of a game, with plausible box stats."""
    abbr, name = TEAMS[team_id]
    opp_abbr = TEAMS[opp_id][0]
    if wl is None:
        wl = "W" if pts > opp_pts else "L"
    row = dict.fromkeys(API_HEADERS, 0)
    row.update({
        "SEASON_ID": season_id, "TEAM_ID": team_id, "TEAM_ABBREVIATION": abbr, "TEAM_NAME": name,
        "GAME_ID": game_id, "GAME_DATE": date, "MATCHUP": f"{abbr} vs. {opp_abbr}" if home else f"{abbr} @ {opp_abbr}",
        "WL": wl, "MIN": minutes, "PTS": pts, "PLUS_MINUS": pts - opp_pts,
        "FGM": 30, "FGA": 70, "FG3M": 8, "FG3A": 24, "FTM": 12, "FTA": 15,
        "OREB": 9, "DREB": 25, "REB": 34, "AST": 20, "STL": 7, "BLK": 4, "TOV": 14, "PF": 18,
    })
    return {k: str(v) for k, v in row.items()}


def game_rows(game_id, home_id, away_id, home_pts, away_pts, **kwargs):
    return [
        api_row(game_id, home_id, away_id, True, home_pts, away_pts, **kwargs),
        api_row(game_id, away_id, home_id, False, away_pts, home_pts, **kwargs),
    ]


def write_raw(raw_dir: Path, name: str, rows: list[dict]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    with open(raw_dir / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=API_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture(scope="session")
def real_db(tmp_path_factory) -> sqlite3.Connection:
    """The database built from the committed raw data, in a temp dir."""
    if not any(RAW_GAME_LOG_DIR.glob("*.csv")):
        pytest.skip("no raw data; run `wnba fetch`")
    db_path = tmp_path_factory.mktemp("db") / "wnba.db"
    db.build(db_path=db_path)
    conn = db.connect(db_path)
    yield conn
    conn.close()
