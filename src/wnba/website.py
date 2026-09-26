"""Static forecast website, written to docs/ and served by GitHub Pages.

One HTML page with inline SVG charts and a little JavaScript for tooltips,
generated entirely from the database and the forecast history. There are no
timestamps in it, so the same data always produces the same file and the daily
push only changes the site when something new happened.
"""

import html
import json
import math
import sqlite3
from datetime import date
from pathlib import Path

from wnba import elo, forecast, predict
from wnba.config import FORECAST_DIR, SITE_DIR

REPO_URL = "https://github.com/dylan-costa/wnba-analytics"


def build_site(conn: sqlite3.Connection, site_dir: Path = SITE_DIR, forecast_dir: Path = FORECAST_DIR) -> bool:
    """Write site_dir/index.html. Returns True if the page changed."""
    page = render(conn, forecast_dir)
    path = site_dir / "index.html"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / ".nojekyll").touch()  # serve the files as they are
    if path.exists() and path.read_text(encoding="utf-8") == page:
        return False
    path.write_text(page, encoding="utf-8")
    return True


def render(conn: sqlite3.Connection, forecast_dir: Path = FORECAST_DIR) -> str:
    season, history = forecast.snapshots(forecast_dir=forecast_dir)
    if not history:
        raise ValueError("No forecasts yet; run `wnba forecast` first")
    names = dict(conn.execute("SELECT abbreviation, name FROM team_seasons WHERE season = ?", (season,)).fetchall())
    latest = history[-1]
    through = latest[0]["through_date"]
    in_playoffs = any(r["seed"] for r in latest)

    rated, _ = elo.run(elo.load_games(conn))
    held_out = [g for g in rated if g.season >= elo.TRAIN_SEASONS.stop]
    backtest = elo.evaluate(held_out, elo.MARGIN_SD) if held_out else None
    live = _live_record(conn, forecast_dir / f"{season}_games.csv")

    sections = [
        _header(season, through, in_playoffs),
        _hero(latest, names, season),
        _kpis(backtest, held_out, rated, live) if held_out else "",
        _odds_table(latest, history, names, in_playoffs),
        _odds_history(latest, history, names),
        _upcoming(conn, season),
        _live_section(live),
        _accuracy_section(backtest, held_out) if held_out else "",
        _home_court_section(conn),
        _about(),
    ]
    return PAGE.format(title=f"WNBA Forecast {season}", body="\n".join(s for s in sections if s), css=CSS, js=JS)


# ---------- sections ----------

def _header(season: int, through: str, in_playoffs: bool) -> str:
    return (
        f'<header><p class="eyebrow">WNBA {season} {"Playoffs" if in_playoffs else "Season"}</p>'
        f"<h1>Who wins the {season} title?</h1>"
        f'<p class="lede">Elo ratings and 20,000 Monte Carlo simulations of the rest of the season, re-run every morning '
        f"when new results come in. Through games of {_long_date(through)}.</p></header>"
    )


def _hero(latest: list[dict], names: dict, season: int) -> str:
    rows = [r for r in latest if r["champion"] != ""]
    if not rows:
        return ""
    top = max(rows, key=lambda r: float(r["champion"]))
    p = float(top["champion"])
    text = f"won the {season} title" if p >= 1 else f"chance to win the {season} title, the best of any team"
    value = "Champions" if p >= 1 else _pct(p)
    return (
        f'<section class="hero"><p class="hero-team">{_e(names.get(top["team"], top["team"]))}</p>'
        f'<p class="hero-figure">{value}</p><p class="hero-caption">{text}</p></section>'
    )


def _kpis(backtest: elo.Evaluation, held_out: list, rated: list, live: dict) -> str:
    first, last = held_out[0].season, held_out[-1].season
    tiles = [
        ("Correct picks", f"{backtest.accuracy:.1%}", f"{backtest.games:,} games, {first}–{last}, not used for tuning"),
        ("Log loss", f"{backtest.log_loss:.3f}", f"vs {backtest.baseline_log_loss:.3f} always picking the home team (lower is better)"),
        ("Games rated", f"{len(rated):,}", f"every game since {rated[0].season}"),
    ]
    if live["games"]:
        tiles.append(("Live picks", f"{live['correct']}–{live['games'] - live['correct']}", "recorded before tip-off this season"))
    cells = "".join(
        f'<div class="tile"><p class="tile-label">{label}</p><p class="tile-value">{value}</p><p class="tile-note">{note}</p></div>'
        for label, value, note in tiles
    )
    return f'<section class="kpis">{cells}</section>'


def _odds_table(latest: list[dict], history: list[list[dict]], names: dict, in_playoffs: bool) -> str:
    previous = {r["team"]: r for r in history[-2]} if len(history) > 1 else {}
    season_left = any(float(r["projected_wins"]) != int(r["wins"]) for r in latest)
    rows = [r for r in latest if r["seed"]] if in_playoffs else latest
    has_title = any(r["champion"] != "" for r in rows)
    max_title = max((float(r["champion"]) for r in rows if r["champion"] != ""), default=0) or 1

    head = "<th>Seed</th>" if in_playoffs else ""
    head += '<th class="left">Team</th><th>W–L</th><th>Elo</th>'
    if season_left:
        head += "<th>Proj. W–L</th><th>Playoffs</th>"
    if has_title:
        head += '<th>Semifinals</th><th>Finals</th><th class="bar-col">Title</th>' + ("<th>Change</th>" if previous else "")

    body = []
    for r in rows:
        cells = f'<td>{r["seed"]}</td>' if in_playoffs else ""
        cells += f'<td class="left">{_e(names.get(r["team"], r["team"]))}</td><td>{r["wins"]}–{r["losses"]}</td><td>{float(r["elo"]):.0f}</td>'
        if season_left:
            cells += f'<td>{float(r["projected_wins"]):.1f}–{float(r["projected_losses"]):.1f}</td><td>{_pct(_f(r["playoffs"]))}</td>'
        if has_title:
            title = float(r["champion"])
            out = in_playoffs and title == 0 and float(r["finals"]) == 0
            bar = f'<span class="bar" style="width:{title / max_title * 100:.1f}%"></span>' if title > 0 else ""
            change = ""
            if r["team"] in previous and previous[r["team"]]["champion"] != "":
                delta = round((title - float(previous[r["team"]]["champion"])) * 100)
                change = f'<span class="delta">{"▲" if delta > 0 else "▼"} {abs(delta)}</span>' if delta else ""
            cells += (
                f'<td>{_pct(_f(r["semifinals"]))}</td><td>{_pct(_f(r["finals"]))}</td>'
                f'<td class="bar-col"><div class="bar-cell"><span class="bar-track">{bar}</span>'
                f'<span class="bar-value">{"Out" if out else _pct(title)}</span></div></td>'
                + (f"<td>{change}</td>" if previous else "")
            )
        body.append(f"<tr>{cells}</tr>")

    note = f"Change is in percentage points since the forecast through {_long_date(history[-2][0]['through_date'])}." if previous else ""
    return (
        f'<section class="card"><h2>{"Playoff odds" if in_playoffs else "Season odds"}</h2>'
        f'<p class="sub">Share of simulations in which each team reaches each round. {note}</p>'
        f'<div class="table-wrap"><table class="odds"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div></section>'
    )


def _odds_history(latest: list[dict], history: list[list[dict]], names: dict) -> str:
    teams = [r["team"] for r in sorted(latest, key=lambda r: -_f(r["champion"], 0)) if r["seed"] or _f(r["champion"], 0) > 0]
    if not teams or latest[0]["champion"] == "":
        return ""
    dates = [snapshot[0]["through_date"] for snapshot in history]
    series = {t: [_f({r["team"]: r for r in snapshot}.get(t, {}).get("champion"), None) for snapshot in history] for t in teams}
    top = max((v for values in series.values() for v in values if v is not None), default=0.1)
    y_max = min(1.0, math.ceil(top * 10 + 0.5) / 10)
    labels = [_short_date(d) for d in dates]

    panels = []
    for t in teams:
        chart = _line_chart(
            list(zip(labels, series[t])), width=280, height=130, y_max=y_max, y_ticks=[0, y_max / 2, y_max],
            label=f"{names.get(t, t)} title odds by forecast date", small=True,
        )
        now = series[t][-1]
        panels.append(f'<div class="panel"><p class="panel-title"><span>{_e(names.get(t, t))}</span><span class="panel-value">{_pct(now)}</span></p>{chart}</div>')

    table_rows = "".join(f"<tr><td class='left'>{_long_date(d)}</td>" + "".join(f"<td>{_pct(series[t][i])}</td>" for t in teams) + "</tr>" for i, d in enumerate(dates))
    table = f"<thead><tr><th class='left'>Through</th>{''.join(f'<th>{t}</th>' for t in teams)}</tr></thead><tbody>{table_rows}</tbody>"
    few = " The lines grow as results come in; each point is one day's forecast." if len(dates) < 3 else ""
    return (
        '<section class="card"><h2>Title odds over time</h2>'
        f'<p class="sub">One panel per team, all on the same scale.{few}</p>'
        f'<div class="multiples">{"".join(panels)}</div>{_data_table(table)}</section>'
    )


def _upcoming(conn: sqlite3.Connection, season: int) -> str:
    games = predict.upcoming_games(conn, limit=8)
    if not games:
        return ""
    state = predict.model_state(conn, season)
    rows = []
    for g in games:
        p = predict.predict_game(state, g["home_team_id"], g["away_team_id"])
        home, away = state.abbreviations[g["home_team_id"]], state.abbreviations[g["away_team_id"]]
        favorite, prob = (home, p.home_win_prob) if p.home_win_prob >= 0.5 else (away, 1 - p.home_win_prob)
        label = g["label"] + (" · if necessary" if g["if_necessary"] else "")
        rows.append(
            f'<tr><td class="left">{_short_date(g["game_date"])}</td><td class="left">{_e(label)}</td><td class="left">{away} @ {home}</td>'
            f'<td class="bar-col"><div class="bar-cell"><span class="bar-track meter"><span class="bar" style="width:{prob * 100:.0f}%"></span></span>'
            f'<span class="bar-value">{favorite} {prob:.0%}</span></div></td>'
            f"<td>{favorite} −{abs(p.home_spread):.1f}</td></tr>"
        )
    return (
        '<section class="card"><h2>Next games</h2>'
        '<p class="sub">Favorite and win probability from current Elo ratings, including home court.</p>'
        '<div class="table-wrap"><table><thead><tr><th class="left">Date</th><th class="left">Game</th><th class="left">Matchup</th>'
        f'<th class="bar-col">Favorite</th><th>Spread</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>'
    )


def _live_record(conn: sqlite3.Connection, games_csv: Path) -> dict:
    """Score the predictions recorded before each game against its result."""
    last_pick = {}
    for row in forecast._read(games_csv):
        last_pick[row["game_id"]] = row  # later snapshots are closer to tip-off
    results = []
    for game_id, pick in last_pick.items():
        g = conn.execute("SELECT game_date, home_pts, away_pts, is_forfeit FROM games WHERE game_id = ?", (game_id,)).fetchone()
        if g is None or g["is_forfeit"]:
            continue
        p = float(pick["home_win_prob"])
        home_won = g["home_pts"] > g["away_pts"]
        results.append({**pick, "home_pts": g["home_pts"], "away_pts": g["away_pts"], "correct": (p >= 0.5) == home_won,
                        "log_loss": -math.log(p if home_won else 1 - p)})
    results.sort(key=lambda r: (r["game_date"], r["game_id"]), reverse=True)
    return {
        "games": len(results),
        "correct": sum(r["correct"] for r in results),
        "log_loss": sum(r["log_loss"] for r in results) / len(results) if results else None,
        "results": results,
    }


def _live_section(live: dict) -> str:
    intro = ('<section class="card"><h2>Live record</h2><p class="sub">Every prediction on this page is saved before the game '
             "is played, so this is the model scored on games it had never seen.")
    if not live["games"]:
        return intro + " Results will appear here once games are played.</p></section>"
    rows = []
    for r in live["results"][:12]:
        favorite, prob = (r["home"], float(r["home_win_prob"])) if float(r["home_win_prob"]) >= 0.5 else (r["away"], 1 - float(r["home_win_prob"]))
        mark = '<span class="status good">✓ Correct</span>' if r["correct"] else '<span class="status bad">✗ Missed</span>'
        rows.append(
            f'<tr><td class="left">{_short_date(r["game_date"])}</td><td class="left">{_e(r["label"])}</td>'
            f'<td class="left">{r["away"]} {r["away_pts"]} @ {r["home"]} {r["home_pts"]}</td><td>{favorite} {prob:.0%}</td><td class="left">{mark}</td></tr>'
        )
    return (
        intro + f' So far: {live["correct"]} of {live["games"]} correct, log loss {live["log_loss"]:.3f}.</p>'
        '<div class="table-wrap"><table><thead><tr><th class="left">Date</th><th class="left">Game</th><th class="left">Result</th>'
        f'<th>Pick</th><th class="left"></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>'
    )


def _accuracy_section(backtest: elo.Evaluation, held_out: list) -> str:
    points = elo.calibration(held_out)
    first, last = held_out[0].season, held_out[-1].season
    chart = _calibration_chart(points)
    table = "<thead><tr><th>Predicted home win</th><th>Actual</th><th>Games</th></tr></thead><tbody>" + "".join(
        f"<tr><td>{p:.0%}</td><td>{a:.0%}</td><td>{n:,}</td></tr>" for p, a, n in points) + "</tbody>"
    return (
        '<section class="card"><h2>Is the model calibrated?</h2>'
        f'<p class="sub">Parameters were tuned on 1997–{elo.TRAIN_SEASONS.stop - 1} only. On the {backtest.games:,} games from {first}–{last}, '
        "games are grouped by the predicted home win chance; a well-calibrated model sits on the diagonal.</p>"
        f"{chart}{_data_table(table)}</section>"
    )


def _home_court_section(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT season, AVG(home_pts > away_pts) FROM games WHERE season_type = 'regular' AND NOT is_forfeit GROUP BY season ORDER BY season"
    ).fetchall()
    points = [(str(s), None if s in elo.NEUTRAL_SEASONS else w) for s, w in rows]
    notes = {i: "2020 bubble" for i, (s, _) in enumerate(rows) if s in elo.NEUTRAL_SEASONS}
    chart = _line_chart(points, width=720, height=260, y_min=0.45, y_max=0.7, y_ticks=[0.45, 0.5, 0.55, 0.6, 0.65, 0.7],
                        label="Home team regular-season win rate by season", ref_y=0.5, x_every=4, notes=notes)
    before = [w for s, w in rows if s < 2020]
    after = [w for s, w in rows if s > 2020]
    if not before or not after:
        return ""
    table = "<thead><tr><th class='left'>Season</th><th>Home win rate</th></tr></thead><tbody>" + "".join(
        f"<tr><td class='left'>{s}</td><td>{'bubble, no home games' if w is None else f'{w:.1%}'}</td></tr>" for s, w in points) + "</tbody>"
    return (
        '<section class="card"><h2>Home court is shrinking</h2>'
        f'<p class="sub">Home teams won {sum(before) / len(before):.0%} of regular-season games from {rows[0][0]} to 2019, '
        f"and {sum(after) / len(after):.0%} since 2021 (2020 was played in a bubble). A model with a fixed home advantage "
        "overrates home teams now, so this one sets each season's home advantage from the seasons just before it.</p>"
        f"{chart}{_data_table(table)}</section>"
    )


def _about() -> str:
    return f"""<section class="card about"><h2>How it works</h2>
<ul>
<li><strong>Data.</strong> Every WNBA game since 1997 (team and player box scores) from the league's stats API, validated and loaded into SQLite. The build checks that every game has two consistent sides and that player points add up to team scores.</li>
<li><strong>Ratings.</strong> Elo, updated after every game with a margin-of-victory multiplier, regressed halfway to the mean between seasons, with a home advantage that adapts as it changes.</li>
<li><strong>Simulation.</strong> Each of 20,000 runs plays out every remaining game from the win probabilities, with ratings updating inside the run, using the real schedule and playoff bracket. Series already under way start from their actual score.</li>
<li><strong>Automation.</strong> A scheduled job fetches new results every morning, rebuilds the database, re-runs the forecast if anything changed, and republishes this page.</li>
</ul>
<p class="source">Built with Python and SQLite. Data: stats.wnba.com. <a href="{REPO_URL}">Source code on GitHub</a>.</p>
</section>"""


# ---------- charts ----------

def _line_chart(points: list[tuple[str, float | None]], *, width: int, height: int, y_max: float, y_ticks: list[float],
                label: str, y_min: float = 0.0, ref_y: float | None = None, x_every: int | None = None, small: bool = False,
                notes: dict[int, str] | None = None) -> str:
    """A single-series line chart as inline SVG. None values leave gaps; `notes`
    puts a short label at an x position (e.g. explaining a gap)."""
    left, right, top, bottom = (40 if small else 44), (12 if small else 44), 10, (24 if small else 28)
    plot_w, plot_h = width - left - right, height - top - bottom
    n = len(points)

    def x(i: int) -> float:
        return left + (plot_w / 2 if n == 1 else i * plot_w / (n - 1))

    def y(v: float) -> float:
        return top + plot_h * (1 - (v - y_min) / (y_max - y_min))

    parts = []
    for tick in y_ticks:
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 6}" y="{y(tick) + 4:.1f}" text-anchor="end">{tick:.0%}</text>')
    if ref_y is not None:
        parts.append(f'<line class="ref" x1="{left}" x2="{width - right}" y1="{y(ref_y):.1f}" y2="{y(ref_y):.1f}"/>')

    every = x_every or max(1, math.ceil(n / 4))
    for i, (x_label, _) in enumerate(points):
        if i == n - 1 or (i % every == 0 and n - 1 - i >= every / 2):  # skip ticks that would crowd the last one
            anchor = "middle" if 0 < i < n - 1 or n == 1 else ("start" if i == 0 else "end")
            parts.append(f'<text class="tick" x="{x(i):.1f}" y="{height - 6}" text-anchor="{anchor}">{_e(x_label)}</text>')

    segments, current = [], []
    for i, (_, v) in enumerate(points):
        if v is None:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(f"{x(i):.1f},{y(v):.1f}")
    if current:
        segments.append(current)
    for seg in segments:
        if len(seg) > 1:
            parts.append(f'<polyline class="line" points="{" ".join(seg)}"/>')

    last = max((i for i, (_, v) in enumerate(points) if v is not None), default=None)
    if last is not None:
        parts.append(f'<circle class="dot" cx="{x(last):.1f}" cy="{y(points[last][1]):.1f}" r="4"/>')
        if not small:
            parts.append(f'<text class="end-label" x="{x(last) + 8:.1f}" y="{y(points[last][1]) + 4:.1f}">{points[last][1]:.0%}</text>')
    for i, note in (notes or {}).items():
        parts.append(f'<text class="note" x="{x(i):.1f}" y="{top + plot_h - 8:.1f}" text-anchor="middle">{_e(note)}</text>')

    data = {
        "labels": [p[0] for p in points],
        "values": [None if p[1] is None else round(p[1], 4) for p in points],
        "xs": [round(x(i), 1) for i in range(n)],
        "ys": [None if p[1] is None else round(y(p[1]), 1) for p in points],
        "top": top, "bottom": height - bottom, "crosshair": True,
    }
    return _svg(width, height, label, parts, data, css_class="chart small" if small else "chart")


def _calibration_chart(points: list[tuple[float, float, int]]) -> str:
    width, height, left, right, top, bottom = 420, 320, 48, 16, 12, 40
    plot_w, plot_h = width - left - right, height - top - bottom

    def x(v: float) -> float:
        return left + v * plot_w

    def y(v: float) -> float:
        return top + (1 - v) * plot_h

    parts = []
    for tick in (0, 0.25, 0.5, 0.75, 1):
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 6}" y="{y(tick) + 4:.1f}" text-anchor="end">{tick:.0%}</text>')
        parts.append(f'<text class="tick" x="{x(tick):.1f}" y="{height - 22}" text-anchor="middle">{tick:.0%}</text>')
    parts.append(f'<line class="ref" x1="{x(0):.1f}" y1="{y(0):.1f}" x2="{x(1):.1f}" y2="{y(1):.1f}"/>')
    parts.append(f'<text class="axis-label" x="{left + plot_w / 2:.1f}" y="{height - 4}" text-anchor="middle">Predicted home win chance</text>')
    parts.append(f'<text class="axis-label" x="12" y="{top + plot_h / 2:.1f}" text-anchor="middle" transform="rotate(-90 12 {top + plot_h / 2:.1f})">Actual</text>')
    for p, a, _ in points:
        parts.append(f'<circle class="dot" cx="{x(p):.1f}" cy="{y(a):.1f}" r="5"/>')
    data = {
        "labels": [f"Predicted {p:.0%} · {n:,} games" for p, _, n in points],
        "values": [round(a, 4) for _, a, _ in points],
        "xs": [round(x(p), 1) for p, _, _ in points],
        "ys": [round(y(a), 1) for _, a, _ in points],
        "top": top, "bottom": height - bottom, "crosshair": False,
    }
    return _svg(width, height, "Calibration: predicted vs actual home win rate", parts, data, css_class="chart calibration")


def _svg(width: int, height: int, label: str, parts: list[str], data: dict, css_class: str = "chart") -> str:
    hover = (f'<line class="crosshair" x1="0" x2="0" y1="{data["top"]}" y2="{data["bottom"]}"/>'
             '<circle class="hover-dot" r="5" cx="-10" cy="-10"/>')
    return (
        f'<svg class="{css_class}" viewBox="0 0 {width} {height}" role="img" tabindex="0" aria-label="{_e(label)}" '
        f"data-chart='{_e(json.dumps(data, separators=(',', ':')))}'>{''.join(parts)}{hover}</svg>"
    )


def _data_table(inner: str) -> str:
    return f'<details><summary>Show the data</summary><div class="table-wrap"><table>{inner}</table></div></details>'


# ---------- formatting ----------

def _e(text) -> str:
    return html.escape(str(text), quote=True)


def _f(value, default=None):
    return default if value in ("", None) else float(value)


def _pct(p: float | None) -> str:
    if p is None:
        return "–"
    if 0 < p < 0.005:
        return "<1%"
    if 0.995 <= p < 1:
        return ">99%"
    return f"{p:.0%}"


def _short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def _long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="Daily WNBA playoff odds from Elo ratings and Monte Carlo simulation.">
<style>{css}</style>
</head>
<body>
<main>
{body}
</main>
<div id="tip" class="tip" role="status" aria-live="polite" hidden><strong></strong><span></span></div>
<script>{js}</script>
</body>
</html>
"""

CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --accent: #2a78d6; --accent-track: #e3eefb; --good: #006300; --bad: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --accent: #3987e5; --accent-track: #1f2f45; --good: #0ca30c; --bad: #e66767;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 960px; margin: 0 auto; padding: 40px 16px 64px; }
header { margin-bottom: 24px; }
.eyebrow { margin: 0; color: var(--ink-2); font-size: 14px; font-weight: 600; letter-spacing: 0.02em; text-transform: uppercase; }
h1 { margin: 4px 0 8px; font-size: clamp(28px, 5vw, 40px); line-height: 1.15; }
.lede { margin: 0; color: var(--ink-2); max-width: 640px; }
h2 { margin: 0 0 4px; font-size: 20px; }
.sub { margin: 0 0 16px; color: var(--ink-2); font-size: 14px; max-width: 680px; }
.card, .hero, .tile { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
.card { padding: 20px; margin-top: 16px; }
.hero { padding: 24px 20px; }
.hero-team { margin: 0; font-size: 18px; font-weight: 600; }
.hero-figure { margin: 0; font-size: 64px; font-weight: 600; line-height: 1.1; }
.hero-caption { margin: 0; color: var(--ink-2); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 12px; }
.tile { padding: 16px; }
.tile-label { margin: 0; color: var(--ink-2); font-size: 14px; }
.tile-value { margin: 2px 0; font-size: 28px; font-weight: 600; }
.tile-note { margin: 0; color: var(--muted); font-size: 13px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }
th { color: var(--ink-2); font-weight: 600; font-size: 13px; }
th, td { padding: 8px 10px; text-align: right; white-space: nowrap; border-bottom: 1px solid var(--grid); }
th.left, td.left { text-align: left; }
tbody tr:last-child td { border-bottom: none; }
.bar-col { width: 32%; }
.bar-cell { display: flex; align-items: center; gap: 8px; }
.bar-track { flex: 1; height: 10px; min-width: 60px; }
.bar-track.meter { background: var(--accent-track); border-radius: 4px; }
.bar-track.meter .bar { border-radius: 4px; }
.bar { display: block; height: 100%; background: var(--accent); border-radius: 0 4px 4px 0; min-width: 2px; }
.bar-value { min-width: 64px; text-align: right; }
.delta { color: var(--ink-2); font-size: 13px; }
.status { font-weight: 600; }
.status.good { color: var(--good); }
.status.bad { color: var(--bad); }
.multiples { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.panel { border: 1px solid var(--grid); border-radius: 8px; padding: 10px 10px 4px; }
.panel-title { display: flex; justify-content: space-between; margin: 0 0 4px; font-size: 14px; font-weight: 600; }
.panel-value { color: var(--ink-2); font-variant-numeric: tabular-nums; }
svg.chart { display: block; width: 100%; height: auto; overflow: visible; }
svg.calibration { max-width: 460px; }
svg.chart:focus { outline: 2px solid var(--accent); outline-offset: 4px; border-radius: 4px; }
.grid { stroke: var(--grid); stroke-width: 1; }
.ref { stroke: var(--axis); stroke-width: 1; }
.tick, .axis-label, .note { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.chart.small .tick { font-size: 14px; }
.end-label { fill: var(--ink-2); font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.axis-label { font-size: 12px; }
.line { fill: none; stroke: var(--accent); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.dot { fill: var(--accent); stroke: var(--surface); stroke-width: 2; }
.crosshair { stroke: var(--axis); stroke-width: 1; visibility: hidden; }
.hover-dot { fill: var(--accent); stroke: var(--surface); stroke-width: 2; visibility: hidden; }
svg.active .crosshair, svg.active .hover-dot { visibility: visible; }
details { margin-top: 12px; font-size: 14px; }
summary { cursor: pointer; color: var(--ink-2); }
details table { margin-top: 8px; }
.about ul { margin: 8px 0; padding-left: 20px; color: var(--ink-2); font-size: 15px; }
.about li { margin-bottom: 8px; }
.about strong { color: var(--ink); }
.source { margin: 12px 0 0; font-size: 14px; color: var(--ink-2); }
a { color: var(--accent); }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 6px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,0.12); display: flex; flex-direction: column; }
.tip strong { font-size: 15px; font-variant-numeric: tabular-nums; }
.tip span { color: var(--ink-2); }
@media (max-width: 600px) { .hero-figure { font-size: 48px; } .card { padding: 16px; } }
"""

JS = """
(function () {
  const tip = document.getElementById('tip');
  const [tipValue, tipLabel] = [tip.querySelector('strong'), tip.querySelector('span')];
  const pct = v => v === null ? 'No data' : (v > 0 && v < 0.005 ? '<1%' : Math.round(v * 100) + '%');
  document.querySelectorAll('svg[data-chart]').forEach(svg => {
    const d = JSON.parse(svg.dataset.chart);
    const cross = svg.querySelector('.crosshair'), dot = svg.querySelector('.hover-dot');
    const points = d.xs.map((x, i) => i).filter(i => d.values[i] !== null);
    let current = null;
    function show(i, clientX, clientY) {
      current = i;
      svg.classList.add('active');
      cross.setAttribute('x1', d.xs[i]); cross.setAttribute('x2', d.xs[i]);
      cross.style.display = d.crosshair ? '' : 'none';
      dot.setAttribute('cx', d.xs[i]); dot.setAttribute('cy', d.ys[i]);
      tipValue.textContent = pct(d.values[i]);
      tipLabel.textContent = d.labels[i];
      tip.hidden = false;
      const box = svg.getBoundingClientRect();
      const scale = box.width / svg.viewBox.baseVal.width;
      const px = clientX ?? box.left + d.xs[i] * scale, py = clientY ?? box.top + d.ys[i] * scale;
      tip.style.left = Math.min(px + window.scrollX + 12, window.scrollX + document.documentElement.clientWidth - tip.offsetWidth - 8) + 'px';
      tip.style.top = (py + window.scrollY - tip.offsetHeight - 12) + 'px';
    }
    function hide() { current = null; svg.classList.remove('active'); tip.hidden = true; }
    svg.addEventListener('pointermove', e => {
      const box = svg.getBoundingClientRect();
      const x = (e.clientX - box.left) * svg.viewBox.baseVal.width / box.width;
      const i = points.reduce((best, j) => Math.abs(d.xs[j] - x) < Math.abs(d.xs[best] - x) ? j : best, points[0]);
      if (i !== undefined) show(i, e.clientX, e.clientY);
    });
    svg.addEventListener('pointerleave', hide);
    svg.addEventListener('blur', hide);
    svg.addEventListener('focus', () => points.length && show(points[points.length - 1]));
    svg.addEventListener('keydown', e => {
      if (!points.length || !['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      e.preventDefault();
      const k = Math.max(0, Math.min(points.length - 1, points.indexOf(current ?? points[points.length - 1]) + (e.key === 'ArrowRight' ? 1 : -1)));
      show(points[k]);
    });
  });
})();
"""
