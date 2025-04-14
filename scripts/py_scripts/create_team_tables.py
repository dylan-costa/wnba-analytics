import os
import sqlite3

# Connect to SQLite database (it will create the database if it doesn't exist)
db_path = '../../wnba_stats.db'

# Delete the existing database file if it exists
if os.path.exists(db_path):
    #os.remove(db_path)
    print(f"Database file already exists at {os.path.abspath(db_path)}, please manually delete the .db file to recreate.")

print(f"Connecting to database at: {os.path.abspath(db_path)}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Set of all current and historical WNBA teams
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

# A set that holds all data points we care about against each team
against_all_teams_data_points = {
    "Win_Loss_Vs_",
    "Avr_Win_Margin_Home_Vs_",
    "Avr_Win_Margin_Away_Vs_",
    "Avr_Pts_Scored_Home_Vs_",
    "Avr_Pts_Scored_Away_Vs_",
    "Avr_Pts_Allowed_Home_Vs_",
    "Avr_Pts_Allowed_Away_Vs_",
    "Fg_Per_Home_Vs_",
    "Fg_Per_Away_Vs_",
    "Three_Pt_Per_Home_Vs_",
    "Three_Pt_Per_Away_Vs_"
}

# Template for creating a table with 34 configurable columns
base_columns = [
    "Year INTEGER",
    "Win_Loss_Szn REAL",
    "Avr_Pts_Home REAL" ,
    "Avr_Pts_Away REAL",
    "Avr_Pts_Allowed_Home REAL",
    "Avr_Pts_Allowed_Away REAL",
    "Fg_Per_Home REAL",
    "Fg_Per_Away REAL",
    "Three_Pt_Per_Home REAL",
    "Three_Pt_Per_Away REAL"
]

# Function to create a table for each WNBA team
def create_tables():
    for team in sorted(wnba_teams):
        # Clean the team name to use as a table name (replace spaces with underscores)
        table_name = team.replace(" ", "_").replace("/", "_")  # Replace spaces and slashes
        
        # Copy the base columns into a new list
        column_template = base_columns.copy()

        # Iterate through each team in the team set and add all data points from against_all_teams_data_points
        # for each team (11 data points * 22 teams = 242 additional columns added to the 9 base columns)
        for opponent in wnba_teams:
            if opponent != team:
                opponent_clean = opponent.replace(" ", "_").replace("/", "_")
                for point in against_all_teams_data_points:
                    column_template.append(f"{point}{opponent_clean} REAL")

        # Create the SQL statement to create the table
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (" + ", ".join(column_template) + ");"

        try:
            print(f"\n--- Creating table for: {team} ---")
            print(f"Table name: {table_name}")
            print(f"Total columns: {len(column_template)}")
            print(f"SQL:\n{create_table_sql}\n")
            # Execute the SQL statement
            cursor.execute(create_table_sql)
            print(f"Table for {team} created successfully.")
        except sqlite3.Error as e:
            print(f"Error creating table for {team}: {e}")

# Call the function to create the tables
create_tables()

# Commit changes and close the connection
conn.commit()
conn.close()