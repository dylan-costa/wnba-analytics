"""Command-line entry point. Data: fetch, build, update. Stats: standings, leaders.
Models: ratings, predict, simulate, forecast, odds, backtest."""

import argparse
import math
import traceback
from contextlib import closing
from datetime import date, datetime

from wnba import db, elo, fetch, forecast, gitsync, predict, simulate
from wnba.config import API_SEASON_TYPES, DB_PATH, DEFAULT_SEASON_TYPES, FIRST_SEASON, UPDATE_LOG_PATH


def parse_seasons(values: list[str]) -> list[int]:
    """Accept years and ranges, e.g. ["1997-2000", "2024"] -> [1997, 1998, 1999, 2000, 2024]."""
    seasons = []
    for value in values:
        start, _, end = value.partition("-")
        seasons.extend(range(int(start), int(end or start) + 1))
    return sorted(set(seasons))


def cmd_fetch(args: argparse.Namespace) -> None:
    seasons = parse_seasons(args.seasons) if args.seasons else list(range(FIRST_SEASON, date.today().year + 1))
    fetch.fetch_seasons(seasons, args.season_types, force=args.force)


def cmd_build(args: argparse.Namespace) -> None:
    counts = db.build()
    print(f"Built {DB_PATH}")
    for table, count in counts.items():
        print(f"  {table}: {count:,}")


def cmd_update(args: argparse.Namespace) -> None:
    """Fetch new games and rebuild. Run daily by the scheduled task, so it logs
    every outcome to data/update.log (there's no console to print to)."""
    def log(message: str) -> None:
        UPDATE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(UPDATE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")

    try:
        fetched = fetch.fetch_seasons(list(range(FIRST_SEASON, date.today().year + 1)), list(DEFAULT_SEASON_TYPES))
        counts = db.build()
    except Exception:
        log(f"FAILED\n{traceback.format_exc()}")
        raise
    fetched_summary = ", ".join(
        f"{season} {season_type}: {n_team} team/{n_player} player rows"
        for (season, season_type), (n_team, n_player) in fetched.items()
    )
    message = f"ok: {counts['games']:,} games in db (fetched {fetched_summary or 'nothing'})"

    # A forecast problem shouldn't stop the new data from being saved and pushed.
    with closing(db.connect()) as conn:
        latest = conn.execute("SELECT MAX(game_date) FROM games").fetchone()[0]
        try:
            update = forecast.update_forecast(conn)
            message += f"; forecast: {forecast.summarize(update) if update else 'no new games, unchanged'}"
        except Exception:
            message += f"; forecast FAILED\n{traceback.format_exc()}"

    if args.push:
        message += f"; git: {gitsync.push_data(f'Update data through {latest}')}"
    log(message)
    print(message)


def cmd_standings(args: argparse.Namespace) -> None:
    season_type = "playoffs" if args.playoffs else "regular"
    with closing(db.connect()) as conn:
        rows = db.standings(conn, args.season, season_type)
    if not rows:
        print(f"No {season_type} games for {args.season}.")
        return
    print(f"{'Team':<26} {'W':>3} {'L':>3} {'Pct':>6} {'PPG':>6} {'OPPG':>6} {'Net':>6}")
    for r in rows:
        print(
            f"{r['name']:<26} {r['wins']:>3} {r['losses']:>3} {r['win_pct']:>6.3f} "
            f"{r['pts_per_game']:>6.1f} {r['opp_pts_per_game']:>6.1f} {r['net_rating']:>+6.1f}"
        )


def cmd_leaders(args: argparse.Namespace) -> None:
    season_type = "playoffs" if args.playoffs else "regular"
    with closing(db.connect()) as conn:
        rows = db.scoring_leaders(conn, args.season, season_type, args.limit)
    if not rows:
        print(f"No {season_type} games for {args.season}.")
        return
    print(f"{'Player':<26} {'Team':<5} {'G':>3} {'MPG':>5} {'PPG':>5} {'RPG':>5} {'APG':>5} {'TS%':>6}")
    for r in rows:
        print(
            f"{r['name']:<26} {r['team']:<5} {r['games']:>3} {r['minutes_per_game']:>5.1f} {r['pts_per_game']:>5.1f} "
            f"{r['reb_per_game']:>5.1f} {r['ast_per_game']:>5.1f} {r['ts_pct']:>6.3f}"
        )


def _pct(p: float | None) -> str:
    if p is None:
        return "-"
    return "<1%" if 0 < p < 0.005 else ">99%" if 0.995 <= p < 1 else f"{p:.0%}"


def _spread_text(abbr_home: str, abbr_away: str, home_spread: float) -> str:
    favorite, points = (abbr_home, home_spread) if home_spread >= 0 else (abbr_away, -home_spread)
    return f"{favorite} -{points:.1f}"


def cmd_ratings(args: argparse.Namespace) -> None:
    with closing(db.connect()) as conn:
        state = predict.model_state(conn)
        records = {
            r["team_id"]: (r["wins"], r["losses"])
            for r in conn.execute("SELECT team_id, wins, losses FROM team_season_stats WHERE season = ? AND season_type = 'regular'", (state.season,))
        }
    print(f"Elo ratings going into the next {state.season} game (home advantage {state.home_advantage:.0f} Elo points)")
    print(f"{'#':>2}  {'Team':<5} {'Elo':>5}  {'W-L':>5}")
    for rank, (team, rating) in enumerate(sorted(state.ratings.items(), key=lambda kv: -kv[1]), 1):
        w, l = records.get(team, (0, 0))
        print(f"{rank:>2}  {state.abbreviations[team]:<5} {rating:>5.0f}  {w:>2}-{l:<2}")


def cmd_predict(args: argparse.Namespace) -> None:
    with closing(db.connect()) as conn:
        state = predict.model_state(conn)
        if args.home:
            if not args.away:
                raise SystemExit("Give both teams: wnba predict HOME AWAY")
            games = [(None, "", state.team_id(args.home), state.team_id(args.away), 0)]
        else:
            games = [(g["game_date"], g["label"], g["home_team_id"], g["away_team_id"], g["if_necessary"]) for g in predict.upcoming_games(conn)]
    if not games:
        print("No upcoming games with both teams set. Try: wnba predict HOME AWAY")
        return
    print(f"{'Date':<10}  {'Game':<31} {'Matchup':<11} {'Home win':>8}  {'Spread':<10}")
    for game_date, label, home, away, if_necessary in games:
        p = predict.predict_game(state, home, away, neutral=args.neutral)
        abbr_home, abbr_away = state.abbreviations[home], state.abbreviations[away]
        label = f"{label} (if nec.)" if if_necessary else label
        matchup = f"{abbr_away} {'vs' if args.neutral else '@'} {abbr_home}"
        print(f"{game_date or '':<10}  {label:<31} {matchup:<11} {p.home_win_prob:>8.0%}  {_spread_text(abbr_home, abbr_away, p.home_spread):<10}")


def cmd_simulate(args: argparse.Namespace) -> None:
    with closing(db.connect()) as conn:
        outlook = simulate.simulate_season(conn, args.season, args.as_of, args.sims, args.seed)
    when = f"as of {outlook.as_of}" if outlook.as_of else "from today"
    print(f"{outlook.season} {when}: {outlook.remaining_regular_season_games} regular-season games left, {outlook.simulations:,} simulations")
    season_left = outlook.remaining_regular_season_games > 0
    header = f"{'Team':<5} {'Seed':>4} {'Elo':>5}  {'W-L':>5}"
    if season_left:
        header += f"  {'Proj W-L':>9}"
    if outlook.playoffs_simulated:
        header += f"  {'Playoffs':>8} {'Semis':>6} {'Finals':>6} {'Title':>6}"
    print(header)
    for t in outlook.teams:
        line = f"{t.abbreviation:<5} {t.seed or '':>4} {t.rating:>5.0f}  {t.wins:>2}-{t.losses:<2}"
        if season_left:
            line += f"  {t.projected_wins:>4.1f}-{t.projected_losses:<4.1f}"
        if outlook.playoffs_simulated:
            sp = t.stage_probs
            line += f"  {_pct(t.playoff_prob):>8} {_pct(sp['Semifinals']):>6} {_pct(sp['Finals']):>6} {_pct(sp['Champion']):>6}"
        print(line)
    if not outlook.playoffs_simulated:
        print(f"(Playoffs are only simulated for {simulate.PLAYOFF_FORMAT_SINCE}+, which use the current format.)")


def cmd_odds(args: argparse.Namespace) -> None:
    season, history = forecast.snapshots(args.season)
    if not history:
        print("No forecasts yet. They're saved by `wnba update` (or `wnba forecast`) when new games come in.")
        return

    def prob(value: str) -> str:
        return _pct(float(value)) if value != "" else "-"

    if args.team:
        team = args.team.upper()
        rows = [(snapshot[0]["through_date"], r) for snapshot in history for r in snapshot if r["team"] == team]
        if not rows:
            raise SystemExit(f"No {season} forecasts for {team}")
        print(f"{team} {season} forecast history")
        print(f"{'Through':<10}  {'W-L':>5} {'Elo':>5}  {'Playoffs':>8} {'Semis':>6} {'Finals':>6} {'Title':>6}")
        for through, r in rows:
            print(f"{through:<10}  {r['wins']:>2}-{r['losses']:<2} {float(r['elo']):>5.0f}  {prob(r['playoffs']):>8} "
                  f"{prob(r['semifinals']):>6} {prob(r['finals']):>6} {prob(r['champion']):>6}")
        return

    latest = history[-1]
    previous = {r["team"]: r for r in history[-2]} if len(history) > 1 else {}
    print(f"{season} forecast through {latest[0]['through_date']} ({len(history)} snapshots"
          + (f"; changes since {history[-2][0]['through_date']})" if previous else ")"))
    print(f"{'Team':<5} {'Seed':>4} {'W-L':>5} {'Elo':>5}  {'Playoffs':>8} {'Semis':>6} {'Finals':>6} {'Title':>6} {'Change':>7}")
    for r in latest:
        before = previous.get(r["team"])
        change = ""
        if before and r["champion"] != "" and before["champion"] != "":
            delta = float(r["champion"]) - float(before["champion"])
            change = f"{delta * 100:+.0f} pts" if round(delta * 100) else ""
        print(f"{r['team']:<5} {r['seed']:>4} {r['wins']:>2}-{r['losses']:<2} {float(r['elo']):>5.0f}  {prob(r['playoffs']):>8} "
              f"{prob(r['semifinals']):>6} {prob(r['finals']):>6} {prob(r['champion']):>6} {change:>7}")


def cmd_forecast(args: argparse.Namespace) -> None:
    with closing(db.connect()) as conn:
        update = forecast.update_forecast(conn, sims=args.sims)
    print(forecast.summarize(update) if update else "No new games since the last forecast; nothing to update.")


def cmd_backtest(args: argparse.Namespace) -> None:
    with closing(db.connect()) as conn:
        games = elo.load_games(conn)
    train, test = elo.TRAIN_SEASONS, range(elo.TRAIN_SEASONS.stop, date.today().year + 1)
    if args.tune:
        print(f"Tuning on {train.start}-{train.stop - 1} ({math.prod(len(v) for v in elo.TUNING_GRID.values())} combinations)...")
        for log_loss, params in elo.tune(games, train)[:5]:
            print(f"  log loss {log_loss:.4f}  {params}")
        print()
    rated, _ = elo.run(games)
    print(f"{'Seasons':<11} {'Games':<9} {'N':>5}  {'Log loss':>8} {'Baseline':>8} {'Brier':>6} {'Correct':>7}  {'Spread RMSE':>11}")
    for seasons in (train, test):
        for season_type in ("regular", "playoffs", None):
            subset = [g for g in rated if g.season in seasons and season_type in (None, g.season_type)]
            e = elo.evaluate(subset, elo.MARGIN_SD)
            print(f"{seasons.start}-{seasons.stop - 1:<6} {season_type or 'all':<9} {e.games:>5}  {e.log_loss:>8.4f} {e.baseline_log_loss:>8.4f} "
                  f"{e.brier:>6.3f} {e.accuracy:>7.1%}  {e.spread_rmse:>11.1f}")
    print(f"\nCalibration, {test.start}-{test.stop - 1} (predicted vs actual home win rate):")
    for predicted, actual, n in elo.calibration([g for g in rated if g.season in test]):
        print(f"  {predicted:>5.1%} -> {actual:>5.1%}  ({n} games)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wnba", description=__doc__)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("fetch", help="download game logs from stats.wnba.com into data/raw")
    p.add_argument("--seasons", nargs="+", metavar="YEAR", help="years or ranges, e.g. 2024 or 1997-2025 (default: all)")
    p.add_argument("--season-types", nargs="+", choices=list(API_SEASON_TYPES), default=list(DEFAULT_SEASON_TYPES))
    p.add_argument("--force", action="store_true", help="re-download files that already exist")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("build", help="rebuild data/wnba.db from the raw game logs")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("update", help="fetch new games and rebuild the database (what the daily task runs)")
    p.add_argument("--push", action="store_true", help="then commit changed files in data/raw and push them")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("standings", help="print a season's standings and team ratings")
    p.add_argument("season", type=int)
    p.add_argument("--playoffs", action="store_true")
    p.set_defaults(func=cmd_standings)

    p = sub.add_parser("leaders", help="print a season's top scorers")
    p.add_argument("season", type=int)
    p.add_argument("--playoffs", action="store_true")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_leaders)

    p = sub.add_parser("ratings", help="print current Elo ratings")
    p.set_defaults(func=cmd_ratings)

    p = sub.add_parser("predict", help="win probability and spread for upcoming games, or for HOME vs AWAY")
    p.add_argument("home", nargs="?", help="home team abbreviation, e.g. MIN")
    p.add_argument("away", nargs="?", help="away team abbreviation")
    p.add_argument("--neutral", action="store_true", help="no home-court advantage")
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("simulate", help="Monte Carlo odds for the rest of the season and the playoffs")
    p.add_argument("--season", type=int, help="default: the latest season")
    p.add_argument("--as-of", metavar="YYYY-MM-DD", help="replay a past season from this date")
    p.add_argument("--sims", type=int, default=10_000)
    p.add_argument("--seed", type=int, help="random seed, for repeatable results")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("forecast", help="save a forecast snapshot if there are new games (wnba update does this too)")
    p.add_argument("--sims", type=int, default=20_000)
    p.set_defaults(func=cmd_forecast)

    p = sub.add_parser("odds", help="latest saved forecast and how it changed, or one team's history")
    p.add_argument("team", nargs="?", help="team abbreviation, e.g. MIN, for its history")
    p.add_argument("--season", type=int)
    p.set_defaults(func=cmd_odds)

    p = sub.add_parser("backtest", help="score the Elo model's past predictions")
    p.add_argument("--tune", action="store_true", help="also re-run the parameter grid search")
    p.set_defaults(func=cmd_backtest)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
