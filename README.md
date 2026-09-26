# wnba-analytics

A WNBA game data pipeline that feeds Monte Carlo simulations and game prediction models.

It downloads every game since the league's first season (1997) from the stats.wnba.com API, with team and player box scores, checks it, and loads it into a SQLite database. On top of that it rates every team with Elo, predicts games, and runs Monte Carlo simulations of the rest of the season and the playoffs.

**[Live forecast](https://dylan-costa.github.io/wnba-analytics/)**: title odds, next-game predictions, the model's live record, and how well it's calibrated. It's regenerated every morning.

**[Methodology](methodology/methodology.pdf)**: the math behind the ratings, predictions and simulations, with proofs, backtest results and a worked example (LaTeX source in `methodology/`).

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
wnba simulate                   # title odds
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

## Models

```bash
wnba ratings                    # current Elo ratings
wnba predict                    # upcoming games: home win probability and spread
wnba predict LVA MIN            # any matchup (home team first); add --neutral for no home court
wnba simulate                   # Monte Carlo odds for the rest of the season and the playoffs
wnba simulate --season 2025 --as-of 2025-07-15   # replay a past season from a date
wnba odds                       # latest saved forecast and the change since the one before
wnba odds MIN                   # one team's odds over time
wnba backtest                   # how well past predictions held up; --tune re-runs the grid search
```

**Elo ratings** (`elo.py`). Every team is rated after every game since 1997. The home team's win probability comes from the rating gap plus home-court advantage. After each game, ratings move by K = 30 times a margin-of-victory multiplier (FiveThirtyEight's NBA formula), so blowouts count more but favorites gain less for beating weak teams. Between seasons, ratings keep half their distance from the 1500 average; new teams start at 1300. Home advantage isn't fixed, because it has shrunk: from about +3 points (60% home wins) through 2019 to about +1.5 (54%) since. Each season uses the average home margin of the five seasons before it (43 Elo points for 2026). The 2020 bubble counts as neutral. Spreads come from the win probability, assuming final margins spread around the prediction with a standard deviation of 11 points.

The parameters were tuned on 1997–2018 and then checked on 2019–2026, which the tuning never saw:

| Seasons | Games | Log loss | Always pick home team | Correct picks | Spread RMSE |
|---|---|---|---|---|---|
| 1997–2018 (tuning) | 5,023 | 0.621 | 0.672 | 65.8% | 11.7 pts |
| 2019–2026 (held out) | 1,977 | 0.608 | 0.688 | 67.5% | 12.7 pts |

On the held-out seasons, predicted and actual win rates line up within about 2 points for home favorites. Home underdogs win a few points less often than predicted.

**Monte Carlo** (`simulate.py`). Each simulation plays every remaining game. The home team wins with the Elo probability, the margin is drawn around the spread, and ratings update after each simulated game, so a team that gets hot stays hot for the rest of that simulation. Games already played count as they happened, including playoff games in a series that's under way. Remaining regular-season games come from the league schedule. Playoff seeds come from the schedule once they're set; before that, each simulation seeds the top 8 by record, breaking ties by record among the tied teams and then at random. Playoffs use the current format (2025 onward): best-of-3 first round (higher seed hosts games 1 and 3), best-of-5 semifinals, best-of-7 finals, fixed bracket with 1/8 meeting 4/5. The daily update refreshes the schedule, so `wnba simulate` stays current through the playoffs.

**Forecast history** (`forecast.py`). Every `wnba update` checks for games played since the last forecast. If there are any, it re-runs the simulation (20,000 runs) and appends a snapshot to `data/forecasts/`, which is committed and pushed with the data. If there aren't, nothing is re-run. One result moves every team's odds, because it reshapes the bracket, so the whole league is re-simulated. The update log calls out the teams that just played plus the biggest movers:

```
forecast: 2 new games (NYL 80 @ MIN 85, DAL 77 @ GSV 90); title odds: MIN 21%->25%, GSV 27%->29%, NYL 4%->2%, DAL 5%->3%
```

- `{season}_odds.csv`: one row per team per snapshot, with record, Elo, and playoff, semifinal, finals and title odds.
- `{season}_games.csv`: the home win probability and spread for every upcoming game, recorded before it's played, so the model can later be scored on games it truly hadn't seen.

`wnba forecast` takes a snapshot by hand (same rule: only if there are new games).

**Website** (`website.py`). `wnba update` also regenerates `docs/index.html`, which GitHub Pages serves (Settings → Pages → Deploy from a branch → `main`, `/docs`). It's one static page with inline SVG charts and no build step. It has no timestamps, so it only changes when the data does. `wnba site` regenerates it by hand; to preview it locally, run `python -m http.server --directory docs`.

**Limits.** Elo only knows results. It can't see injuries, trades, or who's playing tonight, and it lags sudden changes. From mid-July 2025 it gave the eventual champion Aces a 3% title chance before their winning streak. Using player data to adjust for who's actually available is the natural next step.

## Daily updates

`wnba update` fetches the current season, rebuilds the database, saves a new forecast if any games were played (see Forecast history above), and appends the result to `data/update.log`. With `--push` it then commits any changed files in `data/raw`, `data/forecasts` and `docs` and pushes them to GitHub, so the repo stays current too. If the forecast step fails, the error is logged and the new data is still saved and pushed.

To run it automatically every morning on Windows:

```bash
.\scripts\schedule_daily_update.ps1              # daily at 9:00 AM, with --push
.\scripts\schedule_daily_update.ps1 -Time 11:30  # different time
.\scripts\schedule_daily_update.ps1 -NoPush      # update the local database only
```

The task catches up if the PC was off or asleep at that time and runs on battery. It uses `pythonw`, so no console window pops up. The API only lists final games, so a morning run picks up everything from the night before.

The automatic commits are deliberately cautious:

- Only files under `data/raw`, `data/forecasts` and `docs` are committed ("Update data through YYYY-MM-DD"), so anything else you're editing stays out of them.
- They only happen with `main` checked out. On another branch, that day's commit is skipped.
- Nothing is pushed if `main` has unpushed commits of your own; the log says to push manually.
- If a push fails (offline, say), the commit stays local and the next run pushes it.
- Nothing is committed if the build fails validation.

```bash
Get-Content data\update.log -Tail 5                                  # did it run? what did git do?
Start-ScheduledTask -TaskName "wnba-analytics daily update"          # run it now
Unregister-ScheduledTask -TaskName "wnba-analytics daily update"     # remove it
```

Since the task pushes to `main`, run `git pull` before starting work on another machine.

## Layout

```
data/raw/team_games/      raw API responses: one row per team per game, one CSV per season + season type (committed)
data/raw/player_games/    same, one row per player per game
data/raw/schedule/        the current season's schedule: upcoming games and playoff seeds
data/forecasts/           forecast history: odds and game predictions per snapshot (committed)
docs/                     the generated website, served by GitHub Pages (committed)
data/wnba.db              SQLite database built from data/raw (gitignored)
src/wnba/
  fetch.py                stats.wnba.com client
  db.py                   parse, validate and load raw data; query helpers
  schema.sql              tables and views
  elo.py                  Elo ratings, backtesting and tuning
  predict.py              game predictions from current ratings
  simulate.py             Monte Carlo season and playoff simulation
  forecast.py             saves a forecast snapshot when new games come in
  website.py              generates the static forecast site in docs/
  cli.py                  `wnba` command
  gitsync.py              commits and pushes new data after `wnba update --push`
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
| `schedule` | game | upcoming games from the league schedule (current season); undecided playoff matchups have NULL teams |
| `playoff_seeds` | season × seed | from the league schedule |
| `elo_games` | game | both teams' Elo before and after, home advantage, pre-game home win probability and spread |
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

1. Player-availability adjustments: shift a team's rating when key players are out
2. Richer game model (net rating, rest, travel) compared against Elo in the backtest
3. Benchmark against betting lines
