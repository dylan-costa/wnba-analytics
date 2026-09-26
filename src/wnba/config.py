"""Filesystem locations and league constants."""

import os
from pathlib import Path

# The repo root, two levels above src/wnba/. Override with WNBA_DATA_DIR to keep
# data somewhere else.
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("WNBA_DATA_DIR", REPO_ROOT / "data"))
RAW_TEAM_GAMES_DIR = DATA_DIR / "raw" / "team_games"
RAW_PLAYER_GAMES_DIR = DATA_DIR / "raw" / "player_games"
RAW_SCHEDULE_DIR = DATA_DIR / "raw" / "schedule"
DB_PATH = DATA_DIR / "wnba.db"
UPDATE_LOG_PATH = DATA_DIR / "update.log"

FIRST_SEASON = 1997

# First digit of the stats API SEASON_ID (e.g. "22024") -> our season_type label.
SEASON_TYPE_BY_PREFIX = {
    "1": "preseason",
    "2": "regular",
    "3": "allstar",
    "4": "playoffs",
}

# Our season_type label -> the SeasonType query value the stats API expects.
API_SEASON_TYPES = {
    "preseason": "Pre Season",
    "regular": "Regular Season",
    "playoffs": "Playoffs",
}

# Preseason includes exhibitions against non-WNBA teams, so it's opt-in.
DEFAULT_SEASON_TYPES = ("regular", "playoffs")
