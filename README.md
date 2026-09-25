# wnba-analytics

A WNBA game data pipeline that feeds Monte Carlo simulations and game prediction models.

It downloads every game since the league's first season (1997) from the stats.wnba.com API, with team and player box scores, checks it, and loads it into a SQLite database.

## Quickstart

Requires Python 3.11+. The pipeline itself uses only the standard library.

Run these from the repo root:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

wnba build                      # build data/wnba.db from the committed raw data
wnba standings 2025             # sanity checks
wnba leaders 2025
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

## Daily updates

`wnba update` does both steps (fetch the current season, rebuild) and appends the result to `data/update.log`. To run it automatically every morning on Windows:

```bash
.\scripts\schedule_daily_update.ps1              # daily at 9:00 AM; add -Time 11:30 to change
```

The task catches up if the PC was off or asleep at that time and runs on battery. It uses `pythonw`, so no console window pops up. The API only lists final games, so a morning run picks up everything from the night before.

```bash
Get-Content data\update.log -Tail 5                                  # did it run?
Start-ScheduledTask -TaskName "wnba-analytics daily update"          # run it now
Unregister-ScheduledTask -TaskName "wnba-analytics daily update"     # remove it
```

Daily runs rewrite the current season's files in `data/raw/` when there are new games. Commit those files now and then so the repo's raw data stays current.

## Layout

```
data/raw/team_games/      raw API responses: one row per team per game, one CSV per season + season type (committed)
data/raw/player_games/    same, one row per player per game
data/wnba.db              SQLite database built from data/raw (gitignored)
src/wnba/
  fetch.py                stats.wnba.com client
  db.py                   parse, validate and load raw data; query helpers
  schema.sql              tables and views
  cli.py                  `wnba` command
  config.py               paths and constants
scripts/
  schedule_daily_update.ps1   registers the daily `wnba update` task (Windows)
tests/
```

## Database

| Table / view | Grain | Notes |
|---|---|---|
| `franchises` | franchise | `team_id` stays the same through relocations (Utah Starzz → San Antonio → Las Vegas Aces) |
| `team_seasons` | franchise × season | name and abbreviation used that season |
| `games` | game | home/away teams and scores, winner, overtimes, `season_type`, `player_box` (whether that game's player stats are complete) |
| `team_games` | team × game | full box score from one team's side, plus `opponent_team_id`, `is_home`, `win` |
| `players` | player | most recent name, first and last season |
| `player_games` | player × game | player box score (minutes, points, shooting, rebounds, assists, ..., plus-minus); players who didn't play aren't listed |
| `team_game_box` (view) | team × game | `team_games` with the opponent's box score and estimated possessions |
| `team_season_stats` (view) | team × season × season type | record, home/away splits, shooting, pace, offensive/defensive/net rating |
| `player_season_stats` (view) | player × team × season × season type | per-game averages, shooting splits, true shooting %; a traded player gets one row per team |
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

- **Missing games.** The team game log leaves out two regular-season games (`1020700070`, `1020900070`). Regular-season game IDs are sequential, so `wnba fetch` finds gaps and fills them from the box score endpoints. It does the same for any game that has team rows but no player rows.
- **Forfeit.** The Aces' 2018-08-03 forfeit at Washington is recorded 0–0 with no winner. It counts as a Washington win in standings (`games.is_forfeit = 1`) and is left out of scoring and shooting averages.
- **Minutes.** Team minutes weren't recorded for 1997–2004, so `team_games.minutes` and `games.overtimes` are NULL for those seasons. Player minutes are complete.
- **Plus-minus.** Player plus-minus starts in the mid-2000s and is NULL before that.
- **Player box scores that don't add up.** In 7 games from 1997–2000, the league's player box scores are 1–3 points off the official final score (the team scores match the line score). Those player rows are kept but marked `games.player_box = 'points_mismatch'`. One 2000 game (`1020000154`) has an unusable player box score, so its player rows are dropped (`player_box = 'missing'`, as for the 2018 forfeit). When the player game log is wrong but the box score adds up, `wnba fetch` uses the box score (e.g. `1020000216`). Filter on `player_box = 'ok'` when a model needs complete player data.
- **Commissioner's Cup final.** Not included, since it doesn't count toward the standings.

`wnba build` refuses to load data where a game is missing a side, the two sides disagree, the W/L doesn't match the score, or a team's player points don't add up to its score. It builds into a temp file first, so a failed build never replaces a good database.

## Roadmap

1. Team ratings (Elo, opponent-adjusted net rating) computed game by game
2. Game win-probability and margin model, backtested on past seasons
3. Monte Carlo season and playoff simulator on top of it
