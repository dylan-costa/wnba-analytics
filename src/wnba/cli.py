"""Command-line entry point: `wnba fetch`, `wnba build`, `wnba update`, `wnba standings`."""

import argparse
import traceback
from contextlib import closing
from datetime import date, datetime

from wnba import db, fetch
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
    fetched_summary = ", ".join(f"{season} {season_type}: {n}" for (season, season_type), n in fetched.items())
    log(f"ok: {counts['games']:,} games in db (fetched {fetched_summary or 'nothing'})")
    print(f"Updated {DB_PATH}: {counts['games']:,} games")


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
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("standings", help="print a season's standings and team ratings")
    p.add_argument("season", type=int)
    p.add_argument("--playoffs", action="store_true")
    p.set_defaults(func=cmd_standings)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
