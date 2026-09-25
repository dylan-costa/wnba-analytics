"""Download team game logs from the stats.wnba.com API into data/raw.

Each (season, season_type) pair is saved as one CSV exactly as the API returns
it: one row per team per game. Raw files are committed to the repo so the
database can be rebuilt without hitting the API, which is slow and rate-limited.
"""

import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from wnba.config import API_SEASON_TYPES, RAW_GAME_LOG_DIR

API_URL = "https://stats.wnba.com/stats"

GAME_LOG_HEADERS = [
    "SEASON_ID", "TEAM_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "GAME_ID", "GAME_DATE", "MATCHUP", "WL",
    "MIN", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT", "OREB", "DREB",
    "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS", "VIDEO_AVAILABLE",
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


def raw_game_log_path(season: int, season_type: str, raw_dir: Path = RAW_GAME_LOG_DIR) -> Path:
    return raw_dir / f"{season}_{season_type}.csv"


def _get(endpoint: str, params: dict, *, retries: int = 3, timeout: float = 45) -> dict[str, list[dict]]:
    """Call a stats API endpoint and return its result sets as {name: [row dicts]}."""
    request = urllib.request.Request(f"{API_URL}/{endpoint}?{urllib.parse.urlencode(params)}", headers=REQUEST_HEADERS)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result_sets = json.load(response)["resultSets"]
            return {rs["name"]: [dict(zip(rs["headers"], row)) for row in rs["rowSet"]] for rs in result_sets}
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise RuntimeError(f"{endpoint} {params} failed after {retries} attempts: {e}") from e
            time.sleep(5 * attempt)


def fetch_game_log(season: int, season_type: str) -> list[dict]:
    """Every team game (one row per team per game) in one season and season type."""
    params = {
        "Counter": 0,
        "Direction": "ASC",
        "LeagueID": "10",  # WNBA
        "PlayerOrTeam": "T",
        "Season": season,
        "SeasonType": API_SEASON_TYPES[season_type],
        "Sorter": "DATE",
    }
    return _get("leaguegamelog", params)["LeagueGameLog"]


def fetch_box_score_rows(game_id: str, season_id: str) -> list[dict]:
    """Build game log rows for one game from the box score endpoints.

    Returns [] if the game wasn't completed.
    """
    [summary] = _get("boxscoresummaryv2", {"GameID": game_id, "LeagueID": "10"})["GameSummary"]
    if summary["GAME_STATUS_TEXT"] != "Final":
        return []
    box = _get("boxscoretraditionalv2", {
        "GameID": game_id, "LeagueID": "10",
        "StartPeriod": 1, "EndPeriod": 10, "StartRange": 0, "EndRange": 28800, "RangeType": 0,
    })["TeamStats"]
    if len(box) != 2:
        return []

    rows = []
    for team, opp in (box, box[::-1]):
        is_home = team["TEAM_ID"] == summary["HOME_TEAM_ID"]
        row = {col: team.get(col) for col in GAME_LOG_HEADERS}
        row.update({
            "SEASON_ID": season_id,
            "TEAM_NAME": f"{team['TEAM_CITY']} {team['TEAM_NAME']}",
            "GAME_DATE": summary["GAME_DATE_EST"][:10],
            "MATCHUP": f"{team['TEAM_ABBREVIATION']} {'vs.' if is_home else '@'} {opp['TEAM_ABBREVIATION']}",
            "WL": "W" if team["PTS"] > opp["PTS"] else "L",
            "MIN": int(float(team["MIN"].split(":")[0])),  # "200.000000:00"
            "TOV": team["TO"],
            "PLUS_MINUS": team["PTS"] - opp["PTS"],
            "VIDEO_AVAILABLE": 0,
        })
        rows.append(row)
    return rows


def fill_missing_games(rows: list[dict], delay: float = 1.0) -> list[dict]:
    """Add regular-season games that leaguegamelog leaves out.

    leaguegamelog silently omits a few games (e.g. 1020700070, NYL @ CON on
    2007-06-20) that the box score endpoints still have. Regular-season game IDs
    are sequential, so any gap in the sequence is a game to look up.
    """
    ids = {int(r["GAME_ID"]) for r in rows}
    missing = sorted(set(range(min(ids), max(ids) + 1)) - ids)
    season_id = rows[0]["SEASON_ID"]
    added = []
    for game_id in missing:
        time.sleep(delay)
        game_rows = fetch_box_score_rows(str(game_id), season_id)
        print(f"  filled missing game {game_id}" if game_rows else f"  game {game_id} not completed, skipped")
        added.extend(game_rows)
    return rows + added


def save_game_log(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GAME_LOG_HEADERS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["GAME_DATE"], r["GAME_ID"], r["TEAM_ID"])))


def fetch_seasons(
    seasons: list[int],
    season_types: list[str],
    *,
    force: bool = False,
    delay: float = 1.0,
    raw_dir: Path = RAW_GAME_LOG_DIR,
) -> dict[tuple[int, str], int]:
    """Download game logs, skipping past seasons already on disk unless force=True.

    The current calendar year's season is always re-downloaded since it may
    still be in progress. Returns the number of team-game rows saved per
    (season, season_type); seasons with no games yet are 0 and not saved.
    """
    current_season = date.today().year
    saved = {}
    for season in seasons:
        for season_type in season_types:
            path = raw_game_log_path(season, season_type, raw_dir)
            if path.exists() and not force and season < current_season:
                continue
            rows = fetch_game_log(season, season_type)
            if rows and season_type == "regular":
                rows = fill_missing_games(rows, delay)
            if rows:
                save_game_log(path, rows)
            saved[(season, season_type)] = len(rows)
            print(f"{season} {season_type}: {len(rows)} team games")
            time.sleep(delay)
    return saved
