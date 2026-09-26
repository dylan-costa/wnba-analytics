"""Download team and player game logs from the stats.wnba.com API into data/raw.

Each (season, season_type) pair is saved as two CSVs in the API's own format:
data/raw/team_games/ (one row per team per game) and data/raw/player_games/
(one row per player per game; players who didn't play aren't listed). Raw
files are committed to the repo so the database can be rebuilt without hitting
the API, which is slow and rate-limited.
"""

import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

from wnba.config import API_SEASON_TYPES, RAW_PLAYER_GAMES_DIR, RAW_SCHEDULE_DIR, RAW_TEAM_GAMES_DIR

API_URL = "https://stats.wnba.com/stats"

_BOX_HEADERS = [
    "MIN", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT", "OREB", "DREB",
    "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS",
]
TEAM_LOG_HEADERS = [
    "SEASON_ID", "TEAM_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "GAME_ID", "GAME_DATE", "MATCHUP", "WL",
    *_BOX_HEADERS, "VIDEO_AVAILABLE",
]
PLAYER_LOG_HEADERS = [
    "SEASON_ID", "PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "GAME_ID",
    "GAME_DATE", "MATCHUP", "WL", *_BOX_HEADERS, "FANTASY_PTS", "VIDEO_AVAILABLE",
]
SCHEDULE_HEADERS = [
    "GAME_ID", "GAME_DATE", "GAME_STATUS", "HOME_TEAM_ID", "AWAY_TEAM_ID", "HOME_SEED", "AWAY_SEED",
    "GAME_LABEL", "GAME_SUB_LABEL", "IF_NECESSARY",
]

# The API drops connections that don't look like they come from wnba.com.
REQUEST_HEADERS = {
    "Host": "stats.wnba.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.wnba.com/",
    "Origin": "https://www.wnba.com",
    "Connection": "keep-alive",
}


def raw_path(raw_dir: Path, season: int, season_type: str) -> Path:
    return raw_dir / f"{season}_{season_type}.csv"


def _get_json(endpoint: str, params: dict, *, retries: int = 3, timeout: float = 45) -> dict:
    request = urllib.request.Request(f"{API_URL}/{endpoint}?{urllib.parse.urlencode(params)}", headers=REQUEST_HEADERS)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise RuntimeError(f"{endpoint} {params} failed after {retries} attempts: {e}") from e
            time.sleep(5 * attempt)


def _get(endpoint: str, params: dict) -> dict[str, list[dict]]:
    """Call a stats API endpoint and return its result sets as {name: [row dicts]}."""
    result_sets = _get_json(endpoint, params)["resultSets"]
    return {rs["name"]: [dict(zip(rs["headers"], row)) for row in rs["rowSet"]] for rs in result_sets}


def fetch_game_log(season: int, season_type: str, level: str) -> list[dict]:
    """Every team game (level="team") or player game (level="player") in a season."""
    params = {
        "Counter": 0,
        "Direction": "ASC",
        "LeagueID": "10",  # WNBA
        "PlayerOrTeam": {"team": "T", "player": "P"}[level],
        "Season": season,
        "SeasonType": API_SEASON_TYPES[season_type],
        "Sorter": "DATE",
    }
    return _get("leaguegamelog", params)["LeagueGameLog"]


def _box_minutes(value: str | int | None) -> int:
    """Box score minutes look like "37.000000:17" (minutes:seconds), or a plain
    number (often 0) in older games."""
    if not isinstance(value, str):
        return int(value or 0)
    minutes, _, seconds = value.partition(":")
    return round(float(minutes) + int(seconds or 0) / 60)


def fetch_box_score(game_id: str, season_id: str) -> tuple[list[dict], list[dict]] | None:
    """Build (team rows, player rows) in game log format for one game.

    Returns None if the game wasn't completed.
    """
    [summary] = _get("boxscoresummaryv2", {"GameID": game_id, "LeagueID": "10"})["GameSummary"]
    if summary["GAME_STATUS_TEXT"] != "Final":
        return None
    box = _get("boxscoretraditionalv2", {
        "GameID": game_id, "LeagueID": "10",
        "StartPeriod": 1, "EndPeriod": 10, "StartRange": 0, "EndRange": 28800, "RangeType": 0,
    })
    if len(box["TeamStats"]) != 2:
        return None

    game_date = summary["GAME_DATE_EST"][:10]
    team_rows = []
    for team, opp in (box["TeamStats"], box["TeamStats"][::-1]):
        is_home = team["TEAM_ID"] == summary["HOME_TEAM_ID"]
        row = {col: team.get(col) for col in TEAM_LOG_HEADERS}
        row.update({
            "SEASON_ID": season_id,
            "TEAM_NAME": f"{team['TEAM_CITY']} {team['TEAM_NAME']}",
            "GAME_DATE": game_date,
            "MATCHUP": f"{team['TEAM_ABBREVIATION']} {'vs.' if is_home else '@'} {opp['TEAM_ABBREVIATION']}",
            "WL": "W" if team["PTS"] > opp["PTS"] else "L",
            "MIN": _box_minutes(team["MIN"]),
            "TOV": team["TO"],
            "PLUS_MINUS": team["PTS"] - opp["PTS"],
            "VIDEO_AVAILABLE": 0,
        })
        team_rows.append(row)

    teams = {r["TEAM_ID"]: r for r in team_rows}
    player_rows = []
    for player in box["PlayerStats"]:
        if not player["MIN"]:  # DNP; the game log leaves these out too
            continue
        team = teams[player["TEAM_ID"]]
        row = {col: player.get(col) for col in PLAYER_LOG_HEADERS}
        row.update({
            "SEASON_ID": season_id,
            "TEAM_NAME": team["TEAM_NAME"],
            "GAME_DATE": game_date,
            "MATCHUP": team["MATCHUP"],
            "WL": team["WL"],
            "MIN": _box_minutes(player["MIN"]),
            "TOV": player["TO"],
            "PLUS_MINUS": None if player["PLUS_MINUS"] is None else int(player["PLUS_MINUS"]),
            "FANTASY_PTS": None,
            "VIDEO_AVAILABLE": 0,
        })
        player_rows.append(row)
    return team_rows, player_rows


def fetch_season(season: int, season_type: str, delay: float = 1.0) -> tuple[list[dict], list[dict]]:
    """Download (team rows, player rows) for one season, filling games the game logs omit.

    leaguegamelog silently leaves out a few games that the box score endpoints
    still have (e.g. the team log is missing 1020700070, NYL @ CON on
    2007-06-20). Regular-season game IDs are sequential, so gaps in the team log
    are games to look up; any game in the team log without player rows is too.
    """
    team_rows = fetch_game_log(season, season_type, "team")
    if not team_rows:
        return [], []
    time.sleep(delay)
    player_rows = fetch_game_log(season, season_type, "player")

    team_ids = {r["GAME_ID"] for r in team_rows}
    missing_team = set()
    if season_type == "regular":
        numbers = [int(game_id) for game_id in team_ids]
        missing_team = {str(n) for n in range(min(numbers), max(numbers) + 1)} - team_ids
    missing_player = (team_ids | missing_team) - {r["GAME_ID"] for r in player_rows}

    season_id = team_rows[0]["SEASON_ID"]
    for game_id in sorted(missing_team | missing_player):
        time.sleep(delay)
        box = fetch_box_score(game_id, season_id)
        if box is None:
            print(f"  no final box score for game {game_id}, skipped")
            continue
        if game_id in missing_team:
            team_rows += box[0]
        if game_id in missing_player:
            player_rows += box[1]
        print(f"  filled game {game_id} from its box score")

    # The player log occasionally has wrong numbers (1020000216 credits Vickie
    # Johnson with 17 points; the box score has 20). Where a game's player
    # points don't add up to the team scores, use the box score's player rows
    # if those do.
    for game_id in sorted(_points_mismatches(team_rows, player_rows)):
        time.sleep(delay)
        box = fetch_box_score(game_id, season_id)
        game_team_rows = [r for r in team_rows if r["GAME_ID"] == game_id]
        if box is not None and not _points_mismatches(game_team_rows, box[1]):
            player_rows = [r for r in player_rows if r["GAME_ID"] != game_id] + box[1]
            print(f"  replaced player rows for game {game_id} from its box score")
        else:
            print(f"  player points don't match the team score in game {game_id}; kept the game log rows")
    return team_rows, player_rows


def _points_mismatches(team_rows: list[dict], player_rows: list[dict]) -> set[str]:
    """Game IDs where some team's player points don't add up to its score."""
    player_totals = defaultdict(int)
    for r in player_rows:
        player_totals[(r["GAME_ID"], int(r["TEAM_ID"]))] += int(r["PTS"])
    return {r["GAME_ID"] for r in team_rows if player_totals[(r["GAME_ID"], int(r["TEAM_ID"]))] != int(r["PTS"])}


def fetch_schedule(season: int) -> list[dict]:
    """Every game on the season's schedule, played or not, in a flat format.

    Playoff games whose teams aren't decided yet have team IDs of 0. Seeds are
    only set for playoff games.
    """
    schedule = _get_json("scheduleleaguev2", {"LeagueID": "10", "Season": season})["leagueSchedule"]
    rows = []
    for game_date in schedule.get("gameDates", []):
        for g in game_date["games"]:
            home, away = g["homeTeam"], g["awayTeam"]
            rows.append({
                "GAME_ID": g["gameId"],
                "GAME_DATE": g["gameDateEst"][:10],
                "GAME_STATUS": g["gameStatus"],  # 1 scheduled, 2 in progress, 3 final
                "HOME_TEAM_ID": home["teamId"],
                "AWAY_TEAM_ID": away["teamId"],
                "HOME_SEED": home.get("seed") or "",
                "AWAY_SEED": away.get("seed") or "",
                "GAME_LABEL": g["gameLabel"],
                "GAME_SUB_LABEL": g["gameSubLabel"],
                "IF_NECESSARY": int(g["ifNecessary"] in (True, "true")),
            })
    return rows


def save_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    """Write rows sorted by date and IDs, so re-fetching unchanged data gives an identical file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sort_cols = [c for c in ("GAME_DATE", "GAME_ID", "TEAM_ID", "PLAYER_ID") if c in headers]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: tuple(int(r[c]) if c.endswith("ID") else r[c] for c in sort_cols)))


def fetch_seasons(
    seasons: list[int],
    season_types: list[str],
    *,
    force: bool = False,
    delay: float = 1.0,
    team_dir: Path = RAW_TEAM_GAMES_DIR,
    player_dir: Path = RAW_PLAYER_GAMES_DIR,
    schedule_dir: Path = RAW_SCHEDULE_DIR,
) -> dict[tuple[int, str], tuple[int, int]]:
    """Download game logs, skipping past seasons already on disk unless force=True.

    The current calendar year's season is always re-downloaded since it may
    still be in progress, along with its schedule (upcoming games and playoff
    seeds). Returns (team rows, player rows) saved per (season, season_type);
    seasons with no games yet are (0, 0) and not saved.
    """
    current_season = date.today().year
    saved = {}
    for season in seasons:
        for season_type in season_types:
            team_path = raw_path(team_dir, season, season_type)
            player_path = raw_path(player_dir, season, season_type)
            if team_path.exists() and player_path.exists() and not force and season < current_season:
                continue
            team_rows, player_rows = fetch_season(season, season_type, delay)
            if team_rows:
                save_csv(team_path, team_rows, TEAM_LOG_HEADERS)
                save_csv(player_path, player_rows, PLAYER_LOG_HEADERS)
            saved[(season, season_type)] = (len(team_rows), len(player_rows))
            print(f"{season} {season_type}: {len(team_rows)} team games, {len(player_rows)} player games")
            time.sleep(delay)

    if current_season in seasons:
        schedule = fetch_schedule(current_season)
        if schedule:
            save_csv(schedule_dir / f"{current_season}.csv", schedule, SCHEDULE_HEADERS)
        print(f"{current_season} schedule: {sum(r['GAME_STATUS'] != 3 for r in schedule)} games not yet final")
    return saved
