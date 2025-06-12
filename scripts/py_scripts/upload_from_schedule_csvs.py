# This script will parse the csv files at wnba_stats/ and write to each team's table
# with all applicable stats.  There may be some columns that won't be able to be 
# populated based off all the info from the schedule csv's.
import copy
import csv
import math
import os
import sqlite3
from dataclasses import dataclass

# Set of all current and historical WNBA teams
# TODO: Since this list appears in a few scripts now, we might want this list to be in its own
# file that we then import by the scripts that require it
wnba_teams = {
    "Atlanta Dream",
    "Chicago Sky",
    "Connecticut Sun",
    "Indiana Fever",
    "New York Liberty",
    "Washington Mystics",
    "Dallas Wings",
    "Los Angeles Sparks",
    "Minnesota Lynx",
    "Phoenix Mercury",
    "Seattle Storm",
    "Cleveland Rockers",
    "Charlotte Sting",
    "Houston Comets",
    "Sacramento Monarchs",
    "Miami Sol",
    "Portland Fire",
    "Las Vegas Aces",
    "Utah Starzz",
    "San Antonio Silver Stars",
    "San Antonio Stars",
    "Detroit Shock",
    "Tulsa Shock",
    "Orlando Miracle",
    "Golden State Valkyries"
}

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
        self.plusMinusForTeamBeingConsidered = float(plusMinusForTeamBeingConsidered)
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


    return homeTeamSeasonData, awayTeamSeasonData, winsAndGamesPlayed

# This function will calculate the average stats for each home team 
# against each opponent.  Once this is done, insertion into the DB 
# can begin, see the 'uploadToDb' function below
def averageSeasonData(home_season_data, away_season_data, wl_season_data):
    home_averaged_data = {}
    away_averaged_data = {}
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

    # Find the season W/L Ratio for all teams
    for team in wl_season_data:
        wl_ratio = wl_season_data[team][0] / wl_season_data[team][1]
        wl_ratio_data[team] = wl_ratio

    return home_averaged_data, away_averaged_data, wl_ratio_data

# Function that will parse the averaged_season_data object and write all applicable data points per table name (HOME_TEAM_NAME)
# Currently, only Columns that keep track of stats recorded at home, i.e any column whose name is *_Home_Vs_ will have data 
# written to them.  Updates need to be made to update the away stats 
def uploadToDb(home_averaged_season_data, away_averaged_season_data, wl_ratio_data):
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
        home_season_data, away_season_data, wl_season_data = createSeasonData(game_data)

        for entry in home_season_data:
            print(entry)
            for value in home_season_data[entry]:
                print(value)
            print("\n")
        print('--------------------------------')
        for entry in away_season_data:
            print(entry)
            for value in away_season_data[entry]:
                print(value)
            print("\n")
        print('--------------------------------')
        for entry in wl_season_data:
            print(entry)
            for value in wl_season_data[entry]:
                print(value)
            print("\n")

        # averaged_season_data loops through the season_data object and calculates the averages of each team's stats
        # against each opponent. 
        home_averaged_season_data, away_averaged_season_data, wl_ratio_data = averageSeasonData(home_season_data, away_season_data, wl_season_data)

        print('--------------------------------')
        for entry in home_averaged_season_data:
            print(entry)
            for value in home_averaged_season_data[entry]:
                print(value)
            print("\n")
        print('--------------------------------')
        for entry in away_averaged_season_data:
            print(entry)
            for value in away_averaged_season_data[entry]:
                print(value)
            print("\n")
        print('--------------------------------')
        for entry in wl_ratio_data:
            print(entry)
            print(wl_ratio_data[entry])
            print("\n")

        # Write data to database
        uploadToDb(home_averaged_season_data, away_averaged_season_data, wl_ratio_data)
