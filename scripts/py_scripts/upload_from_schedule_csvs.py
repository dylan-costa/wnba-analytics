# This script will parse the csv files at wnba_stats/ and write to each team's table
# with all applicable stats.  There may be some columns that won't be able to be 
# populated based off all the info from the schedule csv's.
import copy
import csv
import math
import os
import sqlite3
from dataclasses import dataclass

# The fields we're interested in keeping track of from the schedule csv's at ~/wnba_stats/schedules/csv 
TRACKED_COLUMNS = [
    'HOME_TEAM_NAME', 'HOME_PTS', 'HOME_FG_PCT', 'HOME_FG3_PCT', 'HOME_PLUS_MINUS', 'HOME_WL',
    'AWAY_TEAM_NAME', 'AWAY_PTS', 'AWAY_FG_PCT', 'AWAY_FG3_PCT', 'AWAY_PLUS_MINUS', 'AWAY_WL', 'Season'
]

class GameResults:
    def __init__(self, seasonYear, homeTeam, opponent, homePts, awayPts, homeFgPct, awayFgPct, homeThreePct,
                 awayThreePct, homePlusMinus, awayPlusMinus, homeWin, awayWin, numGamesPlayedAgainst):
        self.seasonYear = seasonYear
        self.homeTeam = homeTeam
        self.opponent = opponent
        self.homePts = homePts
        self.awayPts = awayPts
        self.homeFgPct = homeFgPct
        self.awayFgPct = awayFgPct
        self.homeThreePct = homeThreePct
        self.awayThreePct = awayThreePct
        self.homePlusMinus = homePlusMinus
        self.awayPlusMinus = awayPlusMinus
        self.homeWin = homeWin
        self.awayWin = awayWin
        self.numGamesPlayedAgainst = numGamesPlayedAgainst

    def __str__(self):
        return (
            f"Season Year: {self.seasonYear}\n"
            f"Home Team: {self.homeTeam}\n"
            f"Opponent: {self.opponent}\n"
            f"Home Points: {self.homePts}, Away Points: {self.awayPts}\n"
            f"Home FG%: {self.homeFgPct}, Away FG%: {self.awayFgPct}\n"
            f"Home 3PT%: {self.homeThreePct}, Away 3PT%: {self.awayThreePct}\n"
            f"Home Plus/Minus: {self.homePlusMinus}, Home Win: {self.homeWin}\n"
            f"Home Plus/Minus: {self.awayPlusMinus}, Home Win: {self.awayWin}\n"
            f"Games Played Against Opponent: {self.numGamesPlayedAgainst}"
        )
    
class TeamResults:
    def __init__(self, teamBeingConsidered, opponent, year, ptsForTeamBeingConsidered, ptsForOppBeingConsidered,fgPctForTeamBeingConsidered, threePctForTeamBeingConsidered,
                 plusMinusForTeamBeingConsidered, winForTeamBeingConsidered, numGamesPlayedAgainst):
        self.teamBeingConsidered = teamBeingConsidered
        self.opponent = opponent
        self.year = year
        self.ptsForTeamBeingConsidered = ptsForTeamBeingConsidered
        self.ptsForOppBeingConsidered = ptsForOppBeingConsidered
        self.fgPctForTeamBeingConsidered = fgPctForTeamBeingConsidered
        self.threePctForTeamBeingConsidered = threePctForTeamBeingConsidered
        self.plusMinusForTeamBeingConsidered = plusMinusForTeamBeingConsidered
        self.winForTeamBeingConsidered = winForTeamBeingConsidered
        self.numGamesPlayedAgainst = numGamesPlayedAgainst

    def __str__(self):
        return (
            f"Team Being Considered: {self.teamBeingConsidered}\n"
            f"Opponent: {self.opponent}\n"
            f"Season Year: {self.year}\n"
            f"Points The Team Being Considered Scored: {self.ptsForTeamBeingConsidered}\n"
            f"Points The Opponent Scored: {self.ptsForOppBeingConsidered}\n"
            f"FG% for The Team Being Considered: {self.fgPctForTeamBeingConsidered}\n"
            f"3PT% for The Team Being Considered: {self.threePctForTeamBeingConsidered}\n"
            f"Plus/Minus of The Team Being Considered: {self.plusMinusForTeamBeingConsidered}\n"
            f"Num Wins or W/L Ratio for the Team Being Considered: {self.winForTeamBeingConsidered}\n"
            f"Games Played Against Opponent: {self.numGamesPlayedAgainst}"
        )

# This function's only purpose was to get the TRACKED_COLUMNS list above
def get_column_mapping(csv_file_path):
    # Reads the first line of a CSV file and returns a dict mapping
    # column names to their column numbers (0-indexed).
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        headers = next(reader)  # First line
        return {column_name: index for index, column_name in enumerate(headers)}

# This function will take a csv and basically create a simplified, slimmed down 
# version that only contains the columns we want to track
def process_csv_data(csv_file_path, column_map):
    results = []

    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header (column names)

        for row in reader:
            record = {}
            for col in TRACKED_COLUMNS:
                idx = column_map.get(col)
                if idx is not None and idx < len(row):
                    record[col] = row[idx]

            # Handle missing HOME_PLUS_MINUS in some of the CSV's
            home_pm = record.get('HOME_PLUS_MINUS', '').strip()
            if home_pm == '':
                try:
                    # Pull and convert values safely
                    away_pts = int(record.get('AWAY_PTS', '0'))
                    home_pts = int(record.get('HOME_PTS', '0'))
                    record['HOME_PLUS_MINUS'] = str(home_pts - away_pts)
                except ValueError:
                    # Skip if values can't be converted to int
                    record['HOME_PLUS_MINUS'] = '0'

            # Handle missing AWAY_PLUS_MINUS in some of the CSV's
            away_pm = record.get('AWAY_PLUS_MINUS', '').strip()
            if away_pm == '':
                try:
                    # Pull and convert values safely
                    away_pts = int(record.get('AWAY_PTS', '0'))
                    home_pts = int(record.get('HOME_PTS', '0'))
                    record['AWAY_PLUS_MINUS'] = str(away_pts - home_pts)
                except ValueError:
                    # Skip if values can't be converted to int
                    record['AWAY_PLUS_MINUS'] = '0'

            results.append(record)

    return results

# This function will aggregate the slimmed down csv created from process_csv_data and create a map object where the 
# keys are the HOME_TEAM_NAME and the values are GameResults objects 
def createSeasonData(game_data):
    homeTeamSeasonData = {}
    awayTeamSeasonData = {}
    ptsScoredHome = {}
    ptsScoredAway = {}
    ptsAllowedHome = {}
    ptsAllowedAway = {}
    fgPerHome = {}
    fgPerAway = {}
    threePtPerHome = {}
    threePtPerAway = {}
    winsAndGamesPlayed = {}

    # Get the Home and Away teams from the current row being considered in the game_data object
    for game in game_data:
        home_team = game.get('HOME_TEAM_NAME')
        opponent = game.get('AWAY_TEAM_NAME')
        if not home_team or not opponent:
            continue

        try:
            home_pts = float(game.get('HOME_PTS', '0'))
            away_pts = float(game.get('AWAY_PTS', '0'))
            home_fg_pct = float(game.get('HOME_FG_PCT', '0'))
            away_fg_pct = float(game.get('AWAY_FG_PCT', '0'))
            home_three_pct = float(game.get('HOME_FG3_PCT', '0'))
            away_three_pct = float(game.get('AWAY_FG3_PCT', '0'))
            home_plus_minus = float(game.get('HOME_PLUS_MINUS', '0'))
            away_plus_minus = float(game.get('AWAY_PLUS_MINUS', '0'))
        except ValueError:
            continue

        season_year = game.get('Season')

        # Convert W/L to 1 or 0
        hwl = game.get('HOME_WL', '').strip().upper()
        home_win_val = 1 if hwl == 'W' else 0
        awl = game.get('AWAY_WL', '').strip().upper()
        away_win_val = 1 if awl == 'W' else 0

        new_result = GameResults(season_year, home_team, opponent, home_pts, away_pts, home_fg_pct,
                                 away_fg_pct, home_three_pct, away_three_pct,
                                 home_plus_minus, away_plus_minus, home_win_val, away_win_val, 1)
        
        new_home_result = TeamResults(
                            new_result.homeTeam,
                            new_result.opponent,
                            new_result.seasonYear,
                            new_result.homePts,
                            new_result.awayPts,
                            new_result.homeFgPct,
                            new_result.homeThreePct,
                            new_result.homePlusMinus,
                            new_result.homeWin,
                            new_result.numGamesPlayedAgainst)
        
        new_away_result = TeamResults(
                            new_result.opponent,
                            new_result.homeTeam,
                            new_result.seasonYear,
                            new_result.awayPts,
                            new_result.homePts,
                            new_result.awayFgPct,
                            new_result.awayThreePct,
                            new_result.awayPlusMinus,
                            new_result.awayWin,
                            new_result.numGamesPlayedAgainst)

        # If the current Home team being considered does not have a key yet in the return map,
        # add a new entry for that Home team 
        if home_team not in homeTeamSeasonData:
            homeTeamSeasonData[home_team] = [new_home_result]
        else:
            existing_result = next(
                (gr for gr in homeTeamSeasonData[home_team] if gr.opponent == opponent), None)

            if existing_result:
                existing_result.ptsForTeamBeingConsidered += home_pts
                existing_result.ptsForOppBeingConsidered += away_pts
                existing_result.fgPctForTeamBeingConsidered += home_fg_pct
                existing_result.threePctForTeamBeingConsidered += home_three_pct
                existing_result.plusMinusForTeamBeingConsidered += home_plus_minus
                existing_result.winForTeamBeingConsidered += home_win_val
                existing_result.numGamesPlayedAgainst += 1
            else:
                homeTeamSeasonData[home_team].append(new_home_result)    

        # If the current Away team being considered does not have a key yet in the return map,
        # add a new entry for that Away team
        if opponent not in awayTeamSeasonData:
            awayTeamSeasonData[opponent] = [new_away_result]
        else:
            existing_result = next(
                (gr for gr in awayTeamSeasonData[opponent] if gr.opponent == home_team), None)

            if existing_result:
                existing_result.ptsForTeamBeingConsidered += away_pts
                existing_result.ptsForOppBeingConsidered += home_pts
                existing_result.fgPctForTeamBeingConsidered += away_fg_pct
                existing_result.threePctForTeamBeingConsidered += away_three_pct
                existing_result.plusMinusForTeamBeingConsidered += away_plus_minus
                existing_result.winForTeamBeingConsidered += away_win_val
                existing_result.numGamesPlayedAgainst += 1
            else:
                awayTeamSeasonData[opponent].append(new_away_result)

        # Store total points scored at home and away for each team and total games
        if home_team not in ptsScoredHome:
            ptsScoredHome[home_team] = [home_pts, 1]
        else:
            ptsScoredHome[home_team][0] += home_pts
            ptsScoredHome[home_team][1] += 1

        if opponent not in ptsScoredAway:
            ptsScoredAway[opponent] = [away_pts, 1]
        else:
            ptsScoredAway[opponent][0] += away_pts
            ptsScoredAway[opponent][1] += 1

        # Store total points allowed at home and away for each team and total games
        if home_team not in ptsAllowedHome:
            ptsAllowedHome[home_team] = [away_pts, 1]
        else:
            ptsAllowedHome[home_team][0] += away_pts
            ptsAllowedHome[home_team][1] += 1

        if opponent not in ptsAllowedAway:
            ptsAllowedAway[opponent] = [home_pts, 1]
        else:
            ptsAllowedAway[opponent][0] += home_pts
            ptsAllowedAway[opponent][1] += 1

        # Store home and away fg percentage and total games
        if home_team not in fgPerHome:
            fgPerHome[home_team] = [home_fg_pct, 1]
        else:
            fgPerHome[home_team][0] += home_fg_pct
            fgPerHome[home_team][1] += 1

        if opponent not in fgPerAway:
            fgPerAway[opponent] = [away_fg_pct, 1]
        else:
            fgPerAway[opponent][0] += away_fg_pct
            fgPerAway[opponent][1] += 1

        # Store home and away three pt. percentage and total games
        if home_team not in threePtPerHome:
            threePtPerHome[home_team] = [home_three_pct, 1]
        else:
            threePtPerHome[home_team][0] += home_three_pct
            threePtPerHome[home_team][1] += 1

        if opponent not in threePtPerAway:
            threePtPerAway[opponent] = [away_three_pct, 1]
        else:
            threePtPerAway[opponent][0] += away_three_pct
            threePtPerAway[opponent][1] += 1

        # Store the number of wins and number of games played for each team in a season
        if home_team not in winsAndGamesPlayed:
            winsAndGamesPlayed[home_team] = [home_win_val, 1]
        else:
            winsAndGamesPlayed[home_team][0] += home_win_val
            winsAndGamesPlayed[home_team][1] += 1

        if opponent not in winsAndGamesPlayed:
            winsAndGamesPlayed[opponent] = [away_win_val, 1]
        else:
            winsAndGamesPlayed[opponent][0] += away_win_val
            winsAndGamesPlayed[opponent][1] += 1


    return homeTeamSeasonData, awayTeamSeasonData, ptsScoredHome, ptsScoredAway, ptsAllowedHome, ptsAllowedAway, fgPerHome, fgPerAway, threePtPerHome, threePtPerAway, winsAndGamesPlayed

# This function will calculate the average stats for each home team 
# against each opponent.  Once this is done, insertion into the DB 
# can begin, see the 'uploadToDb' function below
def averageSeasonData(home_season_data, away_season_data, ptsScoredHome, ptsScoredAway, ptsAllowedHome, ptsAllowedway, fgPerHome, fgPerAway, threePtPerHome, threePtPerAway, wl_season_data):
    home_averaged_data = {}
    away_averaged_data = {}
    pts_scored_home_average_data = {}
    pts_scored_away_average_data = {}
    pts_allowed_home_average_data = {}
    pts_allowed_away_average_data = {}
    fg_per_home_average_data = {}
    fg_per_away_average_data = {}
    three_pt_per_home_average_data = {}
    three_pt_per_away_average_data = {}
    wl_ratio_data = {}

    for team, game_results in home_season_data.items():
        averaged_results = []

        for result in game_results:
            games = result.numGamesPlayedAgainst
            if games == 0:
                continue  # avoid division by zero

            # Use deepcopy to avoid modifying the original object
            avg_result = copy.deepcopy(result)

            avg_result.ptsForTeamBeingConsidered /= games
            avg_result.ptsForOppBeingConsidered /= games
            avg_result.fgPctForTeamBeingConsidered /= games
            avg_result.threePctForTeamBeingConsidered /= games
            avg_result.plusMinusForTeamBeingConsidered /= games
            avg_result.winForTeamBeingConsidered /= games  # becomes win percentage

            averaged_results.append(avg_result)

        home_averaged_data[team] = averaged_results

    for team, game_results in away_season_data.items():
        averaged_results = []

        for result in game_results:
            games = result.numGamesPlayedAgainst
            if games == 0:
                continue  # avoid division by zero

            # Use deepcopy to avoid modifying the original object
            avg_result = copy.deepcopy(result)

            avg_result.ptsForTeamBeingConsidered /= games
            avg_result.ptsForOppBeingConsidered /= games
            avg_result.fgPctForTeamBeingConsidered /= games
            avg_result.threePctForTeamBeingConsidered /= games
            avg_result.plusMinusForTeamBeingConsidered /= games
            avg_result.winForTeamBeingConsidered /= games  # becomes win percentage

            averaged_results.append(avg_result)

        away_averaged_data[team] = averaged_results

    # Find the average points scored at home for all teams for the season
    for team in ptsScoredHome:
        points_home = ptsScoredHome[team][0] / ptsScoredHome[team][1]
        pts_scored_home_average_data[team] = points_home

    # Find the average points scored away for all teams for the season
    for team in ptsScoredAway:
        points_away = ptsScoredAway[team][0] / ptsScoredAway[team][1]
        pts_scored_away_average_data[team] = points_away

    # Find the average points allowed at home for all teams for the season
    for team in ptsAllowedHome:
        points_allowed_home = ptsAllowedHome[team][0] / ptsAllowedHome[team][1]
        pts_allowed_home_average_data[team] = points_allowed_home

    # Find the average points allowed away for all teams for the season
    for team in ptsAllowedway:
        points_allowed_away = ptsAllowedway[team][0] / ptsAllowedway[team][1]
        pts_allowed_away_average_data[team] = points_allowed_away

    # Find the average FG percentage at home for all teams for the season
    for team in fgPerHome:
        fg_per_home = fgPerHome[team][0] / fgPerHome[team][1]
        fg_per_home_average_data[team] = fg_per_home

    # Find the average FG percentage away for all teams for the season
    for team in fgPerAway:
        fg_per_away = fgPerAway[team][0] / fgPerAway[team][1]
        fg_per_away_average_data[team] = fg_per_away

    # Find the average 3 point percentage at home for all teams for the season
    for team in threePtPerHome:
        three_pt_per_home = threePtPerHome[team][0] / threePtPerHome[team][1]
        three_pt_per_home_average_data[team] = three_pt_per_home

    # Find the average 3 point percentage away for all teams for the season
    for team in threePtPerAway:
        three_pt_per_away = threePtPerAway[team][0] / threePtPerAway[team][1]
        three_pt_per_away_average_data[team] = three_pt_per_away

    # Find the season W/L Ratio for all teams
    for team in wl_season_data:
        wl_ratio = wl_season_data[team][0] / wl_season_data[team][1]
        wl_ratio_data[team] = wl_ratio

    return home_averaged_data, away_averaged_data, pts_scored_home_average_data, pts_scored_away_average_data, pts_allowed_home_average_data, pts_allowed_away_average_data, fg_per_home_average_data, fg_per_away_average_data, three_pt_per_home_average_data, three_pt_per_away_average_data, wl_ratio_data

# Function that will parse the averaged_season_data object and write all applicable data points per table name (HOME_TEAM_NAME)
# Currently, only Columns that keep track of stats recorded at home, i.e any column whose name is *_Home_Vs_ will have data 
# written to them.  Updates need to be made to update the away stats 
def uploadToDb(home_averaged_season_data, away_averaged_season_data, pts_scored_home_average_season_data, pts_scored_away_average_season_data, pts_allowed_home_average_season_data, pts_allowed_away_average_season_data, fg_per_home_average_seasson_data, fg_per_away_average_season_data, three_pt_per_home_average_season_data, three_pt_per_away_average_season_data, wl_ratio_data):
    sznYear = 0
    conn = sqlite3.connect("../../wnba_stats.db")
    cursor = conn.cursor()

    # Handle the home data
    for team, game_results in home_averaged_season_data.items():
        table_name = team.replace(" ", "_")

        for result in game_results:
            opponent_key = result.opponent.replace(" ", "_")
            season_year = result.year
            sznYear = season_year

            # Build column values
            columns = {
                "Year": season_year,
                f"Avr_Pts_Scored_Home_Vs_{opponent_key}": (math.floor(result.ptsForTeamBeingConsidered * 1000) / 1000),
                f"Avr_Pts_Allowed_Home_Vs_{opponent_key}": (math.floor(result.ptsForOppBeingConsidered * 1000) / 1000),
                f"Avr_Fg_Per_Home_Vs_{opponent_key}": (math.floor(result.fgPctForTeamBeingConsidered * 1000) / 1000),
                f"Avr_Three_Pt_Per_Home_Vs_{opponent_key}": (math.floor(result.threePctForTeamBeingConsidered * 1000) / 1000),
                f"Avr_Win_Margin_Home_Vs_{opponent_key}": (math.floor(result.plusMinusForTeamBeingConsidered * 1000) / 1000),
                f"Win_Loss_Home_Vs_{opponent_key}": (math.floor(result.winForTeamBeingConsidered * 1000) / 1000)
            }

            # Ensure all columns exist
            for col in columns:
                if col == "Year":
                    continue
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} REAL")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # Check if the row for this year and opponent already exists
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = ?", (season_year,))
            exists = cursor.fetchone()[0] > 0

            if exists:
                # UPDATE
                set_clause = ", ".join(f"{col} = ?" for col in columns if col != "Year")
                values = [val for col, val in columns.items() if col != "Year"]
                values.append(season_year)  # WHERE clause value
                sql = f"UPDATE {table_name} SET {set_clause} WHERE Year = ?"
            else:
                # INSERT
                col_names = ", ".join(columns.keys())
                placeholders = ", ".join("?" for _ in columns)
                values = list(columns.values())
                sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

            try:
                cursor.execute(sql, values)
                #print(f"Inserted data for {team} vs {result.opponent} ({result.year})")
            except sqlite3.OperationalError as e:
                print(f"Error inserting/updating {table_name}: {e}")

    # Handle the away data
    for team, game_results in away_averaged_season_data.items():
        table_name = team.replace(" ", "_")

        for result in game_results:
            opponent_key = result.opponent.replace(" ", "_")
            season_year = result.year

            # Build column values
            columns = {
                "Year": season_year,
                f"Avr_Pts_Scored_Away_Vs_{opponent_key}": (math.floor(result.ptsForTeamBeingConsidered * 1000) / 1000),
                f"Avr_Pts_Allowed_Away_Vs_{opponent_key}": (math.floor(result.ptsForOppBeingConsidered * 1000) / 1000),
                f"Avr_Fg_Per_Away_Vs_{opponent_key}": (math.floor(result.fgPctForTeamBeingConsidered * 1000) / 1000),
                f"Avr_Three_Pt_Per_Away_Vs_{opponent_key}": (math.floor(result.threePctForTeamBeingConsidered * 1000) / 1000),
                f"Avr_Win_Margin_Away_Vs_{opponent_key}": (math.floor(result.plusMinusForTeamBeingConsidered * 1000) / 1000),
                f"Win_Loss_Away_Vs_{opponent_key}": (math.floor(result.winForTeamBeingConsidered * 1000) / 1000)
            }

            # Ensure all columns exist
            for col in columns:
                if col == "Year":
                    continue
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} REAL")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # Check if the row for this year and opponent already exists
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = ?", (season_year,))
            exists = cursor.fetchone()[0] > 0

            if exists:
                # UPDATE
                set_clause = ", ".join(f"{col} = ?" for col in columns if col != "Year")
                values = [val for col, val in columns.items() if col != "Year"]
                values.append(season_year)  # WHERE clause value
                sql = f"UPDATE {table_name} SET {set_clause} WHERE Year = ?"
            else:
                # INSERT
                col_names = ", ".join(columns.keys())
                placeholders = ", ".join("?" for _ in columns)
                values = list(columns.values())
                sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

            try:
                cursor.execute(sql, values)
                #print(f"Inserted data for {team} vs {result.opponent} ({result.year})")
            except sqlite3.OperationalError as e:
                print(f"Error inserting/updating {table_name}: {e}")

    # Handle the average points scored at home for each team
    for team, avg_pts in pts_scored_home_average_season_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Avr_Pts_Home column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Avr_Pts_Home REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Avr_Pts_Home row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Avr_Pts_Home = {math.floor(avg_pts * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Avr_Pts_Home for {table_name}: {e}")

    # Handle the average points scored away for each team
    for team, avg_pts in pts_scored_away_average_season_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Avr_Pts_Away column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Avr_Pts_Away REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Avr_Pts_Away row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Avr_Pts_Away = {math.floor(avg_pts * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Avr_Pts_Away for {table_name}: {e}")

    # Handle the average points allowed at home for each team
    for team, avg_pts_allowed in pts_allowed_home_average_season_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Avr_Pts_Allowed_Home column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Avr_Pts_Allowed_Home REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Avr_Pts_Allowed_Home row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Avr_Pts_Allowed_Home = {math.floor(avg_pts_allowed * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Avr_Pts_Allowed_Home for {table_name}: {e}")

    # Handle the average points allowed away for each team
    for team, avg_pts_allowed in pts_allowed_away_average_season_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Avr_Pts_Allowed_Away column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Avr_Pts_Allowed_Away REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Avr_Pts_Allowed_Away row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Avr_Pts_Allowed_Away = {math.floor(avg_pts_allowed * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Avr_Pts_Allowed_Away for {table_name}: {e}")

    # Handle the season FG percentages at home for each team
    for team, fg_per in fg_per_home_average_seasson_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Fg_Per_Home column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Fg_Per_Home REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Fg_Per_Home row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Fg_Per_Home = {math.floor(fg_per * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Fg_Per_Home for {table_name}: {e}")

    # Handle the season FG percentages away for each team
    for team, fg_per in fg_per_away_average_season_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Fg_Per_Away column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Fg_Per_Away REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Fg_Per_Away row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Fg_Per_Away = {math.floor(fg_per * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Fg_Per_Away for {table_name}: {e}")

    # Handle the season 3 point percentages at home for each team
    for team, three_pt_fg_per in three_pt_per_home_average_season_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Three_Pt_Per_Home column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Three_Pt_Per_Home REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Three_Pt_Per_Home row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Three_Pt_Per_Home = {math.floor(three_pt_fg_per * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Three_Pt_Per_Home for {table_name}: {e}")

    # Handle the season 3 point percentages away for each team
    for team, three_pt_fg_per in three_pt_per_away_average_season_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Three_Pt_Per_Away column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Three_Pt_Per_Away REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Three_Pt_Per_Away row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Three_Pt_Per_Away = {math.floor(three_pt_fg_per * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating Three_Pt_Per_Away for {table_name}: {e}")

    # Handle the season win/loss ratio for each team
    for team, wl_ratio in wl_ratio_data.items():
        table_name = team.replace(" ", "_")

        # Ensure the Win_Loss_Szn column exists
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN Win_Loss_Szn REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Check if there's already a Win_Loss_Szn row (we'll use Year = 0 to flag it)
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE Year = {sznYear}")
        exists = cursor.fetchone()[0] > 0

        if exists:
            sql = f"UPDATE {table_name} SET Win_Loss_Szn = {math.floor(wl_ratio * 1000) / 1000} WHERE Year = {sznYear}"

        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"Error inserting/updating WL_Ratio for {table_name}: {e}")


    conn.commit()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    #print(f"Sample row from {table_name}:")
    # for row in rows:
    #     print(row)

    conn.close()
    
# Main jawn
if __name__ == "__main__":
    # Path to the csv's (relative from this script)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    csv_dir = os.path.join(base_dir, 'wnba_stats', 'schedules', 'csv')

    # Get all CSV file paths
    csv_files = sorted([f for f in os.listdir(csv_dir) if f.endswith('.csv')])

    # Loop through each file and get the column mapping
    for csv_filename in csv_files:
        csv_path = os.path.join(csv_dir, csv_filename)
        column_map = get_column_mapping(csv_path)

        # For each CSV, need to read line by line and grab the following data points (numbers represent the column no.):
        # HOME_TEAM_NAME: 30, HOME_PTS: 32, HOME_FG_PCT: 35, HOME_FG3_PCT: 38, HOME_PLUS_MINUS: 50, HOME_WL: 51,
        # AWAY_TEAM_NAME: 6, AWAY_PTS: 8, AWAY_FG_PCT: 11, AWAY_FG3_PCT: 14, AWAY_PLUS_MINUS: 26, AWAY_WL: 27
        # Season Year, Number of Games Played Against Each Opponent
        print(f"\nProcessing {csv_filename}...")

        # The game_data var will hold a slimmed down version of the current csv being taken into consideration
        # We then need to further process the data to find the average metrics for the entirity of the season
        game_data = process_csv_data(csv_path, column_map)

        # This for loop will print the first 3 rows of the slimmed down csv that is stored in game_data
        # Use for a sanity check
        for entry in game_data:
            print(entry)
            print("\n")

        # season_data will hold the aggregated data (each team's stats against each opponent throughout the season)
        home_season_data, away_season_data, ptsScoredHome, ptsScoredAway, ptsAllowedHome, ptsAllowedway, fgPerHome, fgPerAway, threePtPerHome, threePtPerAway, wl_season_data = createSeasonData(game_data)

        # for entry in home_season_data:
        #     print(entry)
        #     for value in home_season_data[entry]:
        #         print(value)
        #     print("\n")
        # print('--------------------------------')
        # for entry in away_season_data:
        #     print(entry)
        #     for value in away_season_data[entry]:
        #         print(value)
        #     print("\n")
        print('--------------------------------')
        print('Sum of Points scored at home for each team:')
        for entry in ptsScoredHome:
            print(f"{entry}")
            for value in ptsScoredHome[entry]:
                print(f"\t{value}")
            print("\n")
        print('--------------------------------')
        print('Sum of Points scored away for each team:')
        for entry in ptsScoredAway:
            print(f"{entry}")
            for value in ptsScoredAway[entry]:
                print(f"\t{value}")
            print("\n")
        print('--------------------------------')
        print('Sum of Points allowed at home for each team:')
        for entry in ptsAllowedHome:
            print(f"{entry}")
            for value in ptsAllowedHome[entry]:
                print(f"\t{value}")
            print("\n")
        print('--------------------------------')
        print('Sum of Points allowed away for each team:')
        for entry in ptsAllowedway:
            print(f"{entry}")
            for value in ptsAllowedway[entry]:
                print(f"\t{value}")
            print("\n")
        # print('--------------------------------')
        # print('Sum of FG percentages at home:')
        # for entry in fgPerHome:
        #     print(f"{entry}")
        #     for value in fgPerHome[entry]:
        #         print(f"\t{value}")
        #     print("\n")
        # print('--------------------------------')
        # print('Sum of FG percentages away:')
        # for entry in fgPerAway:
        #     print(f"{entry}")
        #     for value in fgPerAway[entry]:
        #         print(f"\t{value}")
        #     print("\n")
        # print('--------------------------------')
        # print('Sum of 3 point FG percentages at home:')
        # for entry in threePtPerHome:
        #     print(f"{entry}")
        #     for value in threePtPerHome[entry]:
        #         print(f"\t{value}")
        #     print("\n")
        # print('--------------------------------')
        # print('Sum of FG percentages away:')
        # for entry in threePtPerAway:
        #     print(f"{entry}")
        #     for value in threePtPerAway[entry]:
        #         print(f"\t{value}")
        #     print("\n")
        # print('--------------------------------')
        # print("W/L ")
        # for entry in wl_season_data:
        #     print(f"{entry}")
        #     for value in wl_season_data[entry]:
        #         print(f"\t{value}")
        #     print("\n")

        # averaged_season_data loops through the season_data object and calculates the averages of each team's stats
        # against each opponent. 
        home_averaged_season_data, away_averaged_season_data, pts_scored_home_average_season_data, pts_scored_away_average_season_data, pts_allowed_home_average_season_data, pts_allowed_away_average_season_data, fg_per_home_average_seasson_data, fg_per_away_average_season_data, three_pt_per_home_average_season_data, three_pt_per_away_average_season_data, wl_ratio_data = averageSeasonData(home_season_data, away_season_data, ptsScoredHome, ptsScoredAway, ptsAllowedHome, ptsAllowedway, fgPerHome, fgPerAway, threePtPerHome, threePtPerAway, wl_season_data)

        # print('--------------------------------')
        # for entry in home_averaged_season_data:
        #     print(entry)
        #     for value in home_averaged_season_data[entry]:
        #         print(value)
        #     print("\n")
        # print('--------------------------------')
        # for entry in away_averaged_season_data:
        #     print(entry)
        #     for value in away_averaged_season_data[entry]:
        #         print(value)
        #     print("\n")
        print('--------------------------------')
        print('Average points scored at home for each team:')
        for entry in pts_scored_home_average_season_data:
            print(entry)
            print(f"\t{pts_scored_home_average_season_data[entry]}")
            print("\n")
        print('--------------------------------')
        print('Average points scored away for each team:')
        for entry in pts_scored_away_average_season_data:
            print(entry)
            print(f"\t{pts_scored_away_average_season_data[entry]}")
            print("\n")
        print('--------------------------------')
        print('Average points allowed at home for each team:')
        for entry in pts_allowed_home_average_season_data:
            print(entry)
            print(f"\t{pts_allowed_home_average_season_data[entry]}")
            print("\n")
        print('--------------------------------')
        print('Average points allowed away for each team:')
        for entry in pts_allowed_away_average_season_data:
            print(entry)
            print(f"\t{pts_allowed_away_average_season_data[entry]}")
            print("\n")
        # print('--------------------------------')
        # print('Average FG percentages at home for the season:')
        # for entry in fg_per_home_average_seasson_data:
        #     print(entry)
        #     print(f"\t{fg_per_home_average_seasson_data[entry]}")
        #     print("\n")
        # print('--------------------------------')
        # print('Average FG percentages away for the season:')
        # for entry in fg_per_away_average_season_data:
        #     print(entry)
        #     print(f"\t{fg_per_away_average_season_data[entry]}")
        #     print("\n")
        # print('--------------------------------')
        # print('Average 3 point FG percentages at home for the season:')
        # for entry in three_pt_per_home_average_season_data:
        #     print(entry)
        #     print(f"\t{three_pt_per_home_average_season_data[entry]}")
        #     print("\n")
        # print('--------------------------------')
        # print('Average 3 point FG percentages away for the season:')
        # for entry in three_pt_per_away_average_season_data:
        #     print(entry)
        #     print(f"\t{three_pt_per_away_average_season_data[entry]}")
        #     print("\n")
        # print('--------------------------------')
        # print('W/L ratios for the season:')
        # for entry in wl_ratio_data:
        #     print(entry)
        #     print(f"\t{wl_ratio_data[entry]}")
        #     print("\n")


        # Write data to database
        uploadToDb(home_averaged_season_data, away_averaged_season_data, pts_scored_home_average_season_data, pts_scored_away_average_season_data, pts_allowed_home_average_season_data, pts_allowed_away_average_season_data, fg_per_home_average_seasson_data, fg_per_away_average_season_data, three_pt_per_home_average_season_data, three_pt_per_away_average_season_data, wl_ratio_data)
