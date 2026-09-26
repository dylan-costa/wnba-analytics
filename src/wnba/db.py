"""Build the SQLite database from the raw game logs, and query it."""

import csv
import os
import sqlite3
from collections import defaultdict
from importlib.resources import files
from pathlib import Path

from wnba import elo
from wnba.config import DB_PATH, RAW_PLAYER_GAMES_DIR, RAW_SCHEDULE_DIR, RAW_TEAM_GAMES_DIR, SEASON_TYPE_BY_PREFIX

# Games the API lists as 0-0 with no winner because one team forfeited.
# game_id -> team_id awarded the win.
FORFEITS = {
    # 2018-08-03 LVA @ WAS: the Aces refused to play after a ~25-hour travel delay.
    "1021800162": 1611661322,  # Washington Mystics
}

# Games whose player box scores in the league's own data don't add up to the
# official final score (the team totals here match the line score). The player
# rows are the only ones that exist and are off by 1-3 points, so they're kept.
PLAYER_POINTS_MISMATCHES = {
    "1029700003", "1029700007", "1029700019", "1029700070",  # 1997
    "1029800015", "1029800017",  # 1998
    "1020000131",  # 2000
}
# Games whose player box score is too incomplete to use; their player rows are dropped.
PLAYER_BOX_UNUSABLE = {
    "1020000154",  # 2000-07-12 CLE @ ORL: 5 players per team listed, scoring 14 and 1 of 74-72
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


def parse_player_game(row: dict[str, str]) -> dict:
    """Convert one raw API row (one player in one game) into a flat record."""
    return {
        "game_id": row["GAME_ID"],
        "player_id": int(row["PLAYER_ID"]),
        "name": row["PLAYER_NAME"],
        "team_id": int(row["TEAM_ID"]),
        "season": int(row["SEASON_ID"][1:]),
        "minutes": int(row["MIN"]),
        "pts": int(row["PTS"]),
        **{col: _optional_int(row[api_col]) for col, api_col in BOX_COLUMNS.items()},
        "plus_minus": _optional_int(row["PLUS_MINUS"]),
    }


def _optional_int(value: str) -> int | None:
    return int(value) if value != "" else None


def read_schedule(schedule_dir: Path) -> list[dict]:
    """Regular-season and playoff games from the schedule files ({season}.csv)."""
    rows = []
    for path in sorted(schedule_dir.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                season_type = SEASON_TYPE_BY_PREFIX.get(row["GAME_ID"][2])
                if season_type not in ("regular", "playoffs"):
                    continue  # preseason, All-Star, Commissioner's Cup final
                rows.append({
                    "game_id": row["GAME_ID"],
                    "season": int(path.stem),
                    "season_type": season_type,
                    "game_date": row["GAME_DATE"],
                    "home_team_id": int(row["HOME_TEAM_ID"]) or None,
                    "away_team_id": int(row["AWAY_TEAM_ID"]) or None,
                    "home_seed": _optional_int(row["HOME_SEED"]),
                    "away_seed": _optional_int(row["AWAY_SEED"]),
                    "label": f"{row['GAME_LABEL']} {row['GAME_SUB_LABEL']}".strip(),
                    "if_necessary": int(row["IF_NECESSARY"]),
                })
    return rows


def playoff_seeds(schedule: list[dict]) -> dict[tuple[int, int], int]:
    """(season, seed) -> team_id from playoff schedule rows. Raises ValueError
    if a team shows up with two different seeds."""
    seeds, team_seed = {}, {}
    for g in schedule:
        for team_id, seed in ((g["home_team_id"], g["home_seed"]), (g["away_team_id"], g["away_seed"])):
            if g["season_type"] != "playoffs" or not team_id or seed is None:
                continue
            if team_seed.setdefault((g["season"], team_id), seed) != seed or seeds.setdefault((g["season"], seed), team_id) != team_id:
                raise ValueError(f"Inconsistent playoff seeds in the {g['season']} schedule (game {g['game_id']})")
    return seeds


def read_raw(raw_dir: Path, parse) -> list[dict]:
    records = []
    for path in sorted(raw_dir.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            records.extend(parse(row) for row in csv.DictReader(f))
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


def player_box_status(game: dict) -> str:
    if game["is_forfeit"] or game["game_id"] in PLAYER_BOX_UNUSABLE:
        return "missing"
    if game["game_id"] in PLAYER_POINTS_MISMATCHES:
        return "points_mismatch"
    return "ok"


def check_player_games(games: list[dict], player_games: list[dict]) -> None:
    """Check player rows against the games: every player is on one of the two
    teams, and each team's player points add up to its score (apart from the
    known exceptions above).

    Raises ValueError listing every problem found.
    """
    games_by_id = {g["game_id"]: g for g in games}
    team_pts = defaultdict(int)
    seen = set()
    problems = []
    for pg in player_games:
        game = games_by_id.get(pg["game_id"])
        if game is None:
            problems.append(f"{pg['game_id']}: player {pg['player_id']} is in a game with no team rows")
            continue
        if pg["team_id"] not in (game["home"]["team_id"], game["away"]["team_id"]):
            problems.append(f"{pg['game_id']}: player {pg['player_id']} isn't on either team")
            continue
        if (pg["game_id"], pg["player_id"]) in seen:
            problems.append(f"{pg['game_id']}: player {pg['player_id']} listed twice")
            continue
        seen.add((pg["game_id"], pg["player_id"]))
        team_pts[(pg["game_id"], pg["team_id"])] += pg["pts"]

    for game in games:
        if game["is_forfeit"] or game["game_id"] in PLAYER_POINTS_MISMATCHES | PLAYER_BOX_UNUSABLE:
            continue
        for side in (game["home"], game["away"]):
            player_total = team_pts.get((game["game_id"], side["team_id"]), 0)
            if player_total != side["pts"]:
                problems.append(
                    f"{game['game_id']}: {side['abbreviation']} players scored {player_total}, team scored {side['pts']}"
                )

    if problems:
        raise ValueError(f"{len(problems)} bad player rows in raw data:\n" + "\n".join(problems))


def _write_schedule_and_ratings(conn: sqlite3.Connection, games: list[dict], schedule: list[dict]) -> None:
    played = {g["game_id"] for g in games}
    conn.executemany(
        "INSERT INTO schedule VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (s["game_id"], s["season"], s["season_type"], s["game_date"], s["home_team_id"], s["away_team_id"],
             s["label"], s["if_necessary"])
            for s in schedule if s["game_id"] not in played
        ],
    )
    conn.executemany(
        "INSERT INTO playoff_seeds VALUES (?, ?, ?)",
        [(season, seed, team_id) for (season, seed), team_id in playoff_seeds(schedule).items()],
    )

    rated, _ = elo.run({
        "game_id": g["game_id"], "season": g["season"], "season_type": g["season_type"],
        "home_team_id": g["home"]["team_id"], "away_team_id": g["away"]["team_id"],
        "home_pts": g["home"]["pts"], "away_pts": g["away"]["pts"], "is_forfeit": g["is_forfeit"],
    } for g in games)
    conn.executemany(
        "INSERT INTO elo_games VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (r.game_id, r.home_elo_pre, r.away_elo_pre, r.home_advantage, r.home_win_prob,
             elo.spread(r.home_win_prob), r.home_elo_post, r.away_elo_post)
            for r in rated
        ],
    )


def _write(conn: sqlite3.Connection, games: list[dict], player_games: list[dict]) -> None:
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
        "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (g["game_id"], g["season"], g["season_type"], g["game_date"],
             g["home"]["team_id"], g["away"]["team_id"], g["home"]["pts"], g["away"]["pts"],
             g["winner_team_id"], g["overtimes"], g["is_forfeit"], player_box_status(g))
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

    players = {}
    for pg in sorted(player_games, key=lambda pg: pg["season"]):
        first = players.get(pg["player_id"], {}).get("first_season", pg["season"])
        players[pg["player_id"]] = {"name": pg["name"], "first_season": first, "last_season": pg["season"]}
    conn.executemany(
        "INSERT INTO players VALUES (?, ?, ?, ?)",
        [(pid, p["name"], p["first_season"], p["last_season"]) for pid, p in players.items()],
    )

    games_by_id = {g["game_id"]: g for g in games}
    columns = [
        "game_id", "player_id", "team_id", "opponent_team_id", "season", "season_type", "game_date",
        "is_home", "win", "minutes", "pts", *BOX_COLUMNS, "plus_minus",
    ]
    rows = []
    for pg in player_games:
        g = games_by_id[pg["game_id"]]
        is_home = pg["team_id"] == g["home"]["team_id"]
        opponent_id = (g["away"] if is_home else g["home"])["team_id"]
        rows.append((
            pg["game_id"], pg["player_id"], pg["team_id"], opponent_id, g["season"], g["season_type"], g["game_date"],
            is_home, pg["team_id"] == g["winner_team_id"], pg["minutes"], pg["pts"],
            *(pg[c] for c in BOX_COLUMNS), pg["plus_minus"],
        ))
    conn.executemany(f"INSERT INTO player_games ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})", rows)


def build(
    db_path: Path = DB_PATH,
    team_dir: Path = RAW_TEAM_GAMES_DIR,
    player_dir: Path = RAW_PLAYER_GAMES_DIR,
    schedule_dir: Path = RAW_SCHEDULE_DIR,
) -> dict[str, int]:
    """Rebuild the database from scratch out of the raw game logs.

    Writes to a temporary file and swaps it in at the end, so a failed build
    never leaves a half-written database behind. Returns row counts per table.
    """
    team_games = read_raw(team_dir, parse_team_game)
    player_games = [pg for pg in read_raw(player_dir, parse_player_game) if pg["game_id"] not in PLAYER_BOX_UNUSABLE]
    if not team_games or not player_games:
        raise FileNotFoundError(f"No raw game logs in {team_dir} or {player_dir}. Run `wnba fetch` first.")
    games = pair_games(team_games)
    check_player_games(games, player_games)
    schedule = read_schedule(schedule_dir)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp_path)
    try:
        with conn:
            _write(conn, games, player_games)
            _write_schedule_and_ratings(conn, games, schedule)
        conn.execute("ANALYZE")  # table statistics so SQLite picks good indexes
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("franchises", "team_seasons", "games", "team_games", "players", "player_games", "schedule", "elo_games")
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


def scoring_leaders(conn: sqlite3.Connection, season: int, season_type: str = "regular", limit: int = 10) -> list[sqlite3.Row]:
    """Top scorers by points per game, among players who played at least half
    their team's games (the league's scoring-title threshold is similar)."""
    return conn.execute(
        """
        SELECT ps.* FROM player_season_stats ps
        JOIN team_season_stats ts USING (season, season_type, team_id)
        WHERE ps.season = ? AND ps.season_type = ? AND ps.games * 2 >= ts.games
        ORDER BY ps.pts_per_game DESC
        LIMIT ?
        """,
        (season, season_type, limit),
    ).fetchall()
