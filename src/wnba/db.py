"""Build the SQLite database from the raw game logs, and query it."""

import csv
import os
import sqlite3
from collections import defaultdict
from importlib.resources import files
from pathlib import Path

from wnba.config import DB_PATH, RAW_GAME_LOG_DIR, SEASON_TYPE_BY_PREFIX

# Games the API lists as 0-0 with no winner because one team forfeited.
# game_id -> team_id awarded the win.
FORFEITS = {
    # 2018-08-03 LVA @ WAS: the Aces refused to play after a ~25-hour travel delay.
    "1021800162": 1611661322,  # Washington Mystics
}

REGULATION_MINUTES = 200  # 5 players x 40 minutes
OVERTIME_MINUTES = 25  # 5 players x 5 minutes

# team_games column -> raw API column
BOX_COLUMNS = {
    "fgm": "FGM", "fga": "FGA", "fg3m": "FG3M", "fg3a": "FG3A", "ftm": "FTM", "fta": "FTA",
    "oreb": "OREB", "dreb": "DREB", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK",
    "tov": "TOV", "pf": "PF",
}


def parse_team_game(row: dict[str, str]) -> dict:
    """Convert one raw API row (one team's side of one game) into a flat record."""
    minutes = int(row["MIN"])
    return {
        "game_id": row["GAME_ID"],
        "team_id": int(row["TEAM_ID"]),
        "name": row["TEAM_NAME"],
        "abbreviation": row["TEAM_ABBREVIATION"],
        "season": int(row["SEASON_ID"][1:]),
        "season_type": SEASON_TYPE_BY_PREFIX[row["SEASON_ID"][0]],
        "game_date": row["GAME_DATE"],
        "is_home": " vs. " in row["MATCHUP"],
        "wl": row["WL"],
        "pts": int(row["PTS"]),
        # Minutes weren't recorded before 2005; the API reports 0 or 12 instead.
        "minutes": minutes if minutes >= REGULATION_MINUTES else None,
        **{col: int(row[api_col]) for col, api_col in BOX_COLUMNS.items()},
    }


def read_raw_team_games(raw_dir: Path = RAW_GAME_LOG_DIR) -> list[dict]:
    records = []
    for path in sorted(raw_dir.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            records.extend(parse_team_game(row) for row in csv.DictReader(f))
    return records


def pair_games(team_games: list[dict]) -> list[dict]:
    """Group team rows into games, checking that every game is consistent.

    Raises ValueError listing every problem found, rather than loading bad data.
    """
    by_game = defaultdict(list)
    for tg in team_games:
        by_game[tg["game_id"]].append(tg)

    games, problems = [], []
    for game_id, sides in by_game.items():
        if len(sides) != 2 or sides[0]["is_home"] == sides[1]["is_home"]:
            problems.append(f"{game_id}: expected one home and one away row, got {len(sides)} rows")
            continue
        home, away = sorted(sides, key=lambda s: not s["is_home"])
        if (home["season"], home["season_type"], home["game_date"]) != (away["season"], away["season_type"], away["game_date"]):
            problems.append(f"{game_id}: home and away rows disagree on season or date")
            continue

        if game_id in FORFEITS:
            winner, is_forfeit = FORFEITS[game_id], True
        elif home["pts"] == away["pts"]:
            problems.append(f"{game_id}: tied {home['pts']}-{away['pts']} and not a known forfeit")
            continue
        else:
            winner, is_forfeit = (home if home["pts"] > away["pts"] else away)["team_id"], False
            if (home["wl"] == "W") != (winner == home["team_id"]):
                problems.append(f"{game_id}: API W/L disagrees with the score")
                continue

        games.append({
            "game_id": game_id,
            "season": home["season"],
            "season_type": home["season_type"],
            "game_date": home["game_date"],
            "home": home,
            "away": away,
            "winner_team_id": winner,
            "is_forfeit": is_forfeit,
            "overtimes": (home["minutes"] - REGULATION_MINUTES) // OVERTIME_MINUTES if home["minutes"] else None,
        })

    if problems:
        raise ValueError(f"{len(problems)} bad games in raw data:\n" + "\n".join(problems))
    return sorted(games, key=lambda g: (g["game_date"], g["game_id"]))


def _write(conn: sqlite3.Connection, games: list[dict]) -> None:
    conn.executescript(files("wnba").joinpath("schema.sql").read_text(encoding="utf-8"))

    team_seasons = {}
    for g in games:
        for side in (g["home"], g["away"]):
            team_seasons[(g["season"], side["team_id"])] = (side["name"], side["abbreviation"])

    franchises = {}
    for (season, team_id), (name, abbreviation) in sorted(team_seasons.items()):
        first = franchises.get(team_id, {}).get("first_season", season)
        franchises[team_id] = {"name": name, "abbreviation": abbreviation, "first_season": first, "last_season": season}

    conn.executemany(
        "INSERT INTO franchises VALUES (?, ?, ?, ?, ?)",
        [(tid, f["name"], f["abbreviation"], f["first_season"], f["last_season"]) for tid, f in franchises.items()],
    )
    conn.executemany(
        "INSERT INTO team_seasons VALUES (?, ?, ?, ?)",
        [(season, tid, name, abbr) for (season, tid), (name, abbr) in team_seasons.items()],
    )
    conn.executemany(
        "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (g["game_id"], g["season"], g["season_type"], g["game_date"],
             g["home"]["team_id"], g["away"]["team_id"], g["home"]["pts"], g["away"]["pts"],
             g["winner_team_id"], g["overtimes"], g["is_forfeit"])
            for g in games
        ],
    )

    columns = [
        "game_id", "team_id", "opponent_team_id", "season", "season_type", "game_date",
        "is_home", "win", "is_forfeit", "pts", "opp_pts", "minutes", *BOX_COLUMNS,
    ]
    conn.executemany(
        f"INSERT INTO team_games ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        [
            (g["game_id"], side["team_id"], opp["team_id"], g["season"], g["season_type"], g["game_date"],
             side["is_home"], side["team_id"] == g["winner_team_id"], g["is_forfeit"],
             side["pts"], opp["pts"], side["minutes"], *(side[c] for c in BOX_COLUMNS))
            for g in games
            for side, opp in ((g["home"], g["away"]), (g["away"], g["home"]))
        ],
    )


def build(db_path: Path = DB_PATH, raw_dir: Path = RAW_GAME_LOG_DIR) -> dict[str, int]:
    """Rebuild the database from scratch out of the raw game logs.

    Writes to a temporary file and swaps it in at the end, so a failed build
    never leaves a half-written database behind. Returns row counts per table.
    """
    team_games = read_raw_team_games(raw_dir)
    if not team_games:
        raise FileNotFoundError(f"No raw game logs in {raw_dir}. Run `wnba fetch` first.")
    games = pair_games(team_games)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp_path)
    try:
        with conn:
            _write(conn, games)
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("franchises", "team_seasons", "games", "team_games")
        }
    except BaseException:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp_path, db_path)
    return counts


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"No database at {db_path}. Run `wnba build` first.")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def standings(conn: sqlite3.Connection, season: int, season_type: str = "regular") -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM team_season_stats WHERE season = ? AND season_type = ? "
        "ORDER BY win_pct DESC, net_rating DESC",
        (season, season_type),
    ).fetchall()
