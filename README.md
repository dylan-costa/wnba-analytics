# wnba-analytics

A WNBA game data pipeline that feeds Monte Carlo simulations and game prediction models.

It downloads every game since the league's first season (1997) from the stats.wnba.com API, checks it, and loads it into a SQLite database with one row per game and one row per team per game.

## Quickstart

Requires Python 3.11+. The pipeline itself uses only the standard library.

Run these from the repo root:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

wnba build                      # build data/wnba.db from the committed raw data
wnba standings 2025             # sanity check
pytest
```

On Windows, if PowerShell blocks `Activate.ps1` with "running scripts is disabled", run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip activating and call `.venv\Scripts\wnba.exe` directly.

The raw game logs are committed in `data/raw/`, so `wnba build` works offline. To pull new games:

```bash
wnba fetch                      # downloads seasons not on disk yet, and always refreshes the current season
wnba fetch --seasons 2024 --force
wnba fetch --seasons 1997-2026 --season-types regular playoffs preseason
wnba build
```

## Layout

```
data/raw/leaguegamelog/   raw API responses, one CSV per season + season type (committed)
data/wnba.db              SQLite database built from data/raw (gitignored)
src/wnba/
  fetch.py                stats.wnba.com client
  db.py                   parse, validate and load raw data; query helpers
  schema.sql              tables and views
  cli.py                  `wnba` command
  config.py               paths and constants
tests/
```

## Database

| Table / view | Grain | Notes |
|---|---|---|
| `franchises` | franchise | `team_id` stays the same through relocations (Utah Starzz → San Antonio → Las Vegas Aces) |
| `team_seasons` | franchise × season | name and abbreviation used that season |
| `games` | game | home/away teams and scores, winner, overtimes, `season_type` |
| `team_games` | team × game | full box score from one team's side, plus `opponent_team_id`, `is_home`, `win` |
| `team_game_box` (view) | team × game | `team_games` with the opponent's box score and estimated possessions |
| `team_season_stats` (view) | team × season × season type | record, home/away splits, shooting, pace, offensive/defensive/net rating |
| `head_to_head` (view) | team × opponent × season × season type | record and average margin |

`season_type` is `regular`, `playoffs`, or `preseason` (preseason only if you fetch it).

```sql
-- 2025 regular season, best net rating first
SELECT name, wins, losses, ROUND(net_rating, 1) AS net
FROM team_season_stats
WHERE season = 2025 AND season_type = 'regular'
ORDER BY net_rating DESC;
```

## Data notes

The stats API is mostly clean, but it has a few quirks that the pipeline handles:

- **Missing games.** `leaguegamelog` leaves out two regular-season games (`1020700070`, `1020900070`). Regular-season game IDs are sequential, so `wnba fetch` finds gaps and fills them from the box score endpoints.
- **Forfeit.** The Aces' 2018-08-03 forfeit at Washington is recorded 0–0 with no winner. It counts as a Washington win in standings (`games.is_forfeit = 1`) and is left out of scoring and shooting averages.
- **Minutes.** Minutes weren't recorded for 1997–2004, so `minutes` and `overtimes` are NULL for those seasons.
- **Commissioner's Cup final.** Not included, since it doesn't count toward the standings.

`wnba build` refuses to load data where a game is missing a side, the two sides disagree, or the W/L doesn't match the score. It builds into a temp file first, so a failed build never replaces a good database.

## Roadmap

1. Team ratings (Elo, opponent-adjusted net rating) computed game by game
2. Game win-probability and margin model, backtested on past seasons
3. Monte Carlo season and playoff simulator on top of it
