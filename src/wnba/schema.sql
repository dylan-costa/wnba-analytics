-- One row per franchise. team_id is the stats.wnba.com TEAM_ID, which stays the
-- same when a franchise relocates or renames (Utah Starzz -> San Antonio -> Las
-- Vegas Aces), so it doubles as the franchise key.
CREATE TABLE franchises (
    team_id              INTEGER PRIMARY KEY,
    current_name         TEXT    NOT NULL,
    current_abbreviation TEXT    NOT NULL,
    first_season         INTEGER NOT NULL,
    last_season          INTEGER NOT NULL
);

-- The name and abbreviation a franchise played under in each season.
CREATE TABLE team_seasons (
    season       INTEGER NOT NULL,
    team_id      INTEGER NOT NULL REFERENCES franchises (team_id),
    name         TEXT    NOT NULL,
    abbreviation TEXT    NOT NULL,
    PRIMARY KEY (season, team_id)
);

-- One row per game.
CREATE TABLE games (
    game_id        TEXT    PRIMARY KEY,
    season         INTEGER NOT NULL,
    season_type    TEXT    NOT NULL CHECK (season_type IN ('preseason', 'regular', 'allstar', 'playoffs')),
    game_date      TEXT    NOT NULL,  -- YYYY-MM-DD
    home_team_id   INTEGER NOT NULL REFERENCES franchises (team_id),
    away_team_id   INTEGER NOT NULL REFERENCES franchises (team_id),
    home_pts       INTEGER NOT NULL,
    away_pts       INTEGER NOT NULL,
    winner_team_id INTEGER NOT NULL REFERENCES franchises (team_id),
    overtimes      INTEGER,           -- NULL where minutes weren't recorded (1997-2004)
    is_forfeit     INTEGER NOT NULL DEFAULT 0
);

-- One row per team per game: the box score from that team's side. Season,
-- season_type, date and is_forfeit are copied from games for easy filtering.
-- Percentages aren't stored; compute them from makes and attempts.
CREATE TABLE team_games (
    game_id          TEXT    NOT NULL REFERENCES games (game_id),
    team_id          INTEGER NOT NULL REFERENCES franchises (team_id),
    opponent_team_id INTEGER NOT NULL REFERENCES franchises (team_id),
    season           INTEGER NOT NULL,
    season_type      TEXT    NOT NULL,
    game_date        TEXT    NOT NULL,
    is_home          INTEGER NOT NULL,
    win              INTEGER NOT NULL,
    is_forfeit       INTEGER NOT NULL,
    pts              INTEGER NOT NULL,
    opp_pts          INTEGER NOT NULL,
    minutes          INTEGER,  -- team player-minutes: 200 regulation, +25 per OT
    fgm INTEGER, fga INTEGER, fg3m INTEGER, fg3a INTEGER, ftm INTEGER, fta INTEGER,
    oreb INTEGER, dreb INTEGER, reb INTEGER, ast INTEGER, stl INTEGER, blk INTEGER,
    tov INTEGER, pf INTEGER,
    PRIMARY KEY (game_id, team_id)
);

CREATE INDEX idx_games_season ON games (season, season_type);
CREATE INDEX idx_team_games_team ON team_games (team_id, season, season_type);

-- Each team game with the opponent's box score alongside and estimated
-- possessions (average of both teams' FGA - OREB + TOV + 0.44 * FTA).
-- Forfeits are excluded since they have no box score.
CREATE VIEW team_game_box AS
SELECT
    t.*,
    o.fgm AS opp_fgm, o.fga AS opp_fga, o.fg3m AS opp_fg3m, o.fg3a AS opp_fg3a,
    o.ftm AS opp_ftm, o.fta AS opp_fta, o.oreb AS opp_oreb, o.dreb AS opp_dreb,
    o.reb AS opp_reb, o.ast AS opp_ast, o.stl AS opp_stl, o.blk AS opp_blk,
    o.tov AS opp_tov, o.pf AS opp_pf,
    0.5 * ((t.fga - t.oreb + t.tov + 0.44 * t.fta) + (o.fga - o.oreb + o.tov + 0.44 * o.fta)) AS possessions
FROM team_games t
JOIN team_games o ON o.game_id = t.game_id AND o.team_id = t.opponent_team_id
WHERE NOT t.is_forfeit;

-- Season totals and rates per team. W/L includes forfeits; everything else
-- comes from games with a box score.
CREATE VIEW team_season_stats AS
WITH records AS (
    SELECT
        season, season_type, team_id,
        COUNT(*)                            AS games,
        SUM(win)                            AS wins,
        SUM(1 - win)                        AS losses,
        SUM(CASE WHEN is_home THEN win END)     AS home_wins,
        SUM(CASE WHEN is_home THEN 1 - win END) AS home_losses,
        SUM(CASE WHEN NOT is_home THEN win END)     AS away_wins,
        SUM(CASE WHEN NOT is_home THEN 1 - win END) AS away_losses
    FROM team_games
    GROUP BY season, season_type, team_id
),
box AS (
    SELECT
        season, season_type, team_id,
        AVG(pts)                          AS pts_per_game,
        AVG(opp_pts)                      AS opp_pts_per_game,
        AVG(pts - opp_pts)                AS margin_per_game,
        1.0 * SUM(fgm) / SUM(fga)         AS fg_pct,
        1.0 * SUM(fg3m) / SUM(fg3a)       AS fg3_pct,
        1.0 * SUM(ftm) / SUM(fta)         AS ft_pct,
        (SUM(fgm) + 0.5 * SUM(fg3m)) / SUM(fga) AS efg_pct,
        AVG(possessions)                  AS pace,
        100.0 * SUM(pts) / SUM(possessions)     AS off_rating,
        100.0 * SUM(opp_pts) / SUM(possessions) AS def_rating
    FROM team_game_box
    GROUP BY season, season_type, team_id
)
SELECT
    r.season, r.season_type, r.team_id, ts.name, ts.abbreviation,
    r.games, r.wins, r.losses, 1.0 * r.wins / r.games AS win_pct,
    r.home_wins, r.home_losses, r.away_wins, r.away_losses,
    b.pts_per_game, b.opp_pts_per_game, b.margin_per_game,
    b.fg_pct, b.fg3_pct, b.ft_pct, b.efg_pct,
    b.pace, b.off_rating, b.def_rating, b.off_rating - b.def_rating AS net_rating
FROM records r
JOIN team_seasons ts ON ts.season = r.season AND ts.team_id = r.team_id
LEFT JOIN box b ON b.season = r.season AND b.season_type = r.season_type AND b.team_id = r.team_id;

-- Record and scoring for each team against each opponent in a season.
CREATE VIEW head_to_head AS
SELECT
    season, season_type, team_id, opponent_team_id,
    COUNT(*)                                        AS games,
    SUM(win)                                        AS wins,
    SUM(1 - win)                                    AS losses,
    AVG(CASE WHEN NOT is_forfeit THEN pts END)            AS pts_per_game,
    AVG(CASE WHEN NOT is_forfeit THEN opp_pts END)        AS opp_pts_per_game,
    AVG(CASE WHEN NOT is_forfeit THEN pts - opp_pts END)  AS margin_per_game
FROM team_games
GROUP BY season, season_type, team_id, opponent_team_id;
