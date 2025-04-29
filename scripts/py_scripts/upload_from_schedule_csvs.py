# This script will parse the csv files at wnba_stats/ and write to each team's table
# with all applicable stats.  There may be some columns that won't be able to be 
# populated based off all the info from the schedule csv's.
import copy
import csv
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
    "Huston Comets",
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
    'AWAY_TEAM_NAME', 'AWAY_PTS', 'AWAY_FG_PCT', 'AWAY_FG3_PCT', 'Season'
]

class GameResults:
    def __init__(self, seasonYear, opponent, homePts, awayPts, homeFgPct, awayFgPct, homeThreePct,
                 awayThreePct, homePlusMinus, homeWin, numGamesPlayedAgainst):
        self.seasonYear = seasonYear
        self.opponent = opponent
        self.homePts = homePts
        self.awayPts = awayPts
        self.homeFgPct = homeFgPct
        self.awayFgPct = awayFgPct
        self.homeThreePct = homeThreePct
        self.awayThreePct = awayThreePct
        self.homePlusMinus = homePlusMinus
        self.homeWin = homeWin
        self.numGamesPlayedAgainst = numGamesPlayedAgainst

    def __str__(self):
        return (
            f"Season Year: {self.seasonYear}\n"
            f"Opponent: {self.opponent}\n"
            f"Home Points: {self.homePts}, Away Points: {self.awayPts}\n"
            f"Home FG%: {self.homeFgPct}, Away FG%: {self.awayFgPct}\n"
            f"Home 3PT%: {self.homeThreePct}, Away 3PT%: {self.awayThreePct}\n"
            f"Home Plus/Minus: {self.homePlusMinus}, Home Win: {self.homeWin}\n"
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

            results.append(record)

    return results

# This function will aggregate the slimmed down csv created from process_csv_data and create a map object where the 
# keys are the HOME_TEAM_NAME and the values are GameResults objects 
def createSeasonData(game_data):
    teamSeasonData = {}

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
            plus_minus = float(game.get('HOME_PLUS_MINUS', '0'))
        except ValueError:
            continue

        season_year = game.get('Season')

        # Convert W/L to 1 or 0
        wl = game.get('HOME_WL', '').strip().upper()
        win_val = 1 if wl == 'W' else 0

        new_result = GameResults(season_year, opponent, home_pts, away_pts, home_fg_pct,
                                 away_fg_pct, home_three_pct, away_three_pct,
                                 plus_minus, win_val, 1)

        # If the current Home team being considered does not have a key yet in the return map,
        # add a new entry for that Home team 
        if home_team not in teamSeasonData:
            teamSeasonData[home_team] = [new_result]
        else:
            existing_result = next(
                (gr for gr in teamSeasonData[home_team] if gr.opponent == opponent), None)

            if existing_result:
                existing_result.homePts += home_pts
                existing_result.awayPts += away_pts
                existing_result.homeFgPct += home_fg_pct
                existing_result.awayFgPct += away_fg_pct
                existing_result.homeThreePct += home_three_pct
                existing_result.awayThreePct += away_three_pct
                existing_result.homePlusMinus += plus_minus
                existing_result.homeWin += win_val
                existing_result.numGamesPlayedAgainst += 1
            else:
                teamSeasonData[home_team].append(new_result)

    return teamSeasonData

# This function will calculate the average stats for each home team 
# against each opponent.  Once this is done, insertion into the DB 
# can begin, see the 'uploadToDb' function below
def averageSeasonData(season_data):
    averaged_data = {}

    for team, game_results in season_data.items():
        averaged_results = []

        for result in game_results:
            games = result.numGamesPlayedAgainst
            if games == 0:
                continue  # avoid division by zero

            # Use deepcopy to avoid modifying the original object
            avg_result = copy.deepcopy(result)

            avg_result.homePts /= games
            avg_result.awayPts /= games
            avg_result.homeFgPct /= games
            avg_result.awayFgPct /= games
            avg_result.homeThreePct /= games
            avg_result.awayThreePct /= games
            avg_result.homePlusMinus /= games
            avg_result.homeWin /= games  # becomes win percentage

            averaged_results.append(avg_result)

        averaged_data[team] = averaged_results

    return averaged_data

# Function that will parse the averaged_season_data object and write all applicable data points per table name (HOME_TEAM_NAME)
# Currently, only Columns that keep track of stats recorded at home, i.e any column whose name is *_Home_Vs_ will have data 
# written to them.  Updates need to be made to update the away stats 
def uploadToDb(averaged_season_data):
    conn = sqlite3.connect("../../wnba_stats.db")
    cursor = conn.cursor()

    for team, game_results in averaged_season_data.items():
        table_name = team.replace(" ", "_")

        for result in game_results:
            opponent_key = result.opponent.replace(" ", "_")
            season_year = result.seasonYear

            # Build column values
            columns = {
                "Year": season_year,
                f"Avr_Win_Margin_Home_Vs_{opponent_key}": result.homePlusMinus,
                f"Avr_Pts_Scored_Home_Vs_{opponent_key}": result.homePts,
                f"Avr_Pts_Allowed_Home_Vs_{opponent_key}": result.awayPts,
                f"Three_Pt_Per_Home_Vs_{opponent_key}": result.homeThreePct,
                f"Fg_Per_Home_Vs_{opponent_key}": result.homeFgPct 
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
                print(f"Inserted data for {team} vs {result.opponent} ({result.seasonYear})")
            except sqlite3.OperationalError as e:
                print(f"Error inserting/updating {table_name}: {e}")

    conn.commit()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    print(f"Sample row from {table_name}:")
    for row in rows:
        print(row)
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
        # HOME_TEAM_NAME: 30, HOME_PTS: 32, HOME_FG_PCT: 35, HOME_FG3_PCT: 38, HOME_PLUS_MINUS: 50, HOME_WL: 51
        # AWAY_TEAM_NAME: 6, AWAY_PTS: 8, AWAY_FG_PCT: 11, AWAY_FG3_PCT: 14
        # Season Year, Number of Games Played Against Each Opponent
        print(f"\nProcessing {csv_filename}...")

        # The game_data var will hold a slimmed down version of the current csv being taken into consideration
        # We then need to further process the data to find the average metrics for the entirity of the season
        game_data = process_csv_data(csv_path, column_map)

        # This for loop will print the first 3 rows of the slimmed down csv that is stored in game_data
        # Use for a sanity check
        for game in game_data[:3]:
            print(game)

        # season_data will hold the aggregated data (each team's stats against each opponent throughout the season)
        season_data = createSeasonData(game_data)

        # averaged_season_data loops through the season_data object and calculates the averages of each team's stats
        # against each opponent. 
        averaged_season_data = averageSeasonData(season_data)

        # This for loop will print each team's average season stats against each opponent
        # Use for a sanity check
        for team, results in averaged_season_data.items():
            print(f"\nTeam: {team}")
            for game_result in results:
                print(game_result)
                print('-' * 40)
            print(f"\n")

        # Write data to database
        uploadToDb(averaged_season_data)