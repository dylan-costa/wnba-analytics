'''
Gets the totals of certain stats per season for each team
'''
import sqlite3
import math
# Connect to SQLite3 database (it will create the database file if it doesn't exist)
conn = sqlite3.connect("../../wnba_stats.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

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


def getAverage(team):
    table_name = team.replace(" ", "_")    
    print(f"Looping through the {table_name} table")


    # Step 1: Get all columns names
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = cursor.fetchall()
    column_names = [col[1] for col in columns_info]
    
    # Step 2: Identify columns needed to get season averages (case-insensitive)
    pts_home = [col for col in column_names if 'avr_pts_scored_home_vs' in col.lower()]
    pts_away = [col for col in column_names if 'avr_pts_scored_away_vs' in col.lower()]
    pts_allowed_home = [col for col in column_names if 'avr_pts_allowed_home_vs' in col.lower()]
    pts_allowed_away = [col for col in column_names if 'avr_pts_allowed_away_vs' in col.lower()]
    fg_home = [col for col in column_names if 'fg_per_home_vs' in col.lower()]
    fg_away = [col for col in column_names if 'fg_per_away_vs' in col.lower()]
    three_home = [col for col in column_names if 'three_pt_per_home_vs' in col.lower()]
    three_away = [col for col in column_names if 'three_pt_per_away_vs' in col.lower()]

    # Step 3: Select required columns and year for row identification
    selected_columns = (pts_home + pts_away + pts_allowed_home + pts_allowed_away + fg_home + fg_away + three_home + three_away + ['Year'])
    
    query = f"SELECT {', '.join(selected_columns)} FROM {table_name}"
    cursor.execute(query)
    rows = cursor.fetchall()
    
    '''
        Need to keep in mind that some teams didnt exist in certain years 
        - ratio of ratios/ratios
    '''


    # Each row is a different year 
    for row in rows:
        pts_home_values = [row[col] for col in pts_home if row[col] is not None]
        pts_away_values = [row[col] for col in pts_away if row[col] is not None]
        pts_allowed_home_values = [row[col] for col in pts_allowed_home if row[col] is not None]
        pts_allowed_away_values = [row[col] for col in pts_allowed_away if row[col] is not None]
        fg_home_values = [row[col] for col in fg_home if row[col] is not None]
        fg_away_values = [row[col] for col in fg_away if row[col] is not None]
        three_home_values = [row[col] for col in three_home if row[col] is not None]
        three_away_values = [row[col] for col in three_away if row[col] is not None]

        print(fg_home_values)
        
        avg_pts_home = math.floor(((sum(pts_home_values) / len(pts_home_values)) * 1000) / 1000) if pts_home_values else "NULL"
        avg_pts_away = math.floor(((sum(pts_away_values) / len(pts_away_values)) * 1000) / 1000)  if pts_away_values else "NULL"
        avg_pts_allowed_home = math.floor(((sum(pts_allowed_home_values) / len(pts_allowed_home_values)) * 1000) / 1000)  if pts_allowed_home_values else "NULL"
        avg_pts_allowed_away = math.floor(((sum(pts_allowed_away_values) / len(pts_allowed_away_values)) * 1000) / 1000)  if pts_allowed_away_values else "NULL"
        avg_fg_home = math.floor(((sum(fg_home_values) / len(fg_home_values)) * 1000) / 1000)  if fg_home_values else "NULL"
        avg_fg_away = math.floor(((sum(fg_away_values) / len(fg_away_values)) * 1000) / 1000)  if fg_away_values else "NULL"
        avg_three_home = math.floor(((sum(three_home_values) / len(three_home_values)) * 1000) / 1000)  if three_home_values else "NULL"
        avg_three_away = math.floor(((sum(three_away_values) / len(three_away_values)) * 1000) / 1000)  if three_away_values else "NULL"


        print(avg_fg_home)
        # Update the row
        cursor.execute(f"""
            UPDATE {table_name}
            SET
                Avr_Pts_Home = ?,
                Avr_Pts_Away = ?,
                Avr_Pts_Allowed_Home = ?,
                Avr_Pts_Allowed_Away = ?,
                Fg_Per_Home = ?,
                Fg_Per_Away = ?,
                Three_Pt_Per_Home = ?,
                Three_Pt_Per_Away = ?
            WHERE Year = ?
        """, (
            avg_pts_home,
            avg_pts_away,
            avg_pts_allowed_home,
            avg_pts_allowed_away,
            avg_fg_home,
            avg_fg_away,
            avg_three_home,
            avg_three_away,
            row['Year']
        ))

    
# main pipeline/controller
def main():
    for team in wnba_teams:
        getAverage(team)

    # Commit the changes to save them to the database
    conn.commit()
    # Close the connection
    conn.close()

# entry point
if __name__ == "__main__":
    main()


 