'''
Gets the totals of certain stats per season for each team
'''
import sqlite3
# Connect to SQLite3 database (it will create the database file if it doesn't exist)
conn = sqlite3.connect("wnba_stats.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

wnba_teams = {
    #"Atlanta Dream"
    # "Chicago Sky",
    # "Connecticut Sun",
    # "Indiana Fever",
    # "New York Liberty",
    # "Washington Mystics",
    # "Dallas Wings",
    # "Los Angeles Sparks",
    # "Minnesota Lynx",
    # "Phoenix Mercury",
    # "Seattle Storm",
    # "Cleveland Rockers",
    # "Charlotte Sting",
    # "Houston Comets",
    # "Sacramento Monarchs",
    # "Miami Sol",
    # "Portland Fire",
    # "Las Vegas Aces",
    # "Utah Starzz",
    # "San Antonio Silver Stars",
    # "San Antonio Stars",
    # "Detroit Shock",
    # "Tulsa Shock",
    # "Orlando Miracle",
    # "Golden State Valkyries"
}


def getAverage(team):
    table_name = team.replace(" ", "_")    
    print(f"Looping through the {table_name} table")


    # Step 1: Get all columns names
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = cursor.fetchall()
    column_names = [col[1] for col in columns_info]
    
    # Step 2: Identify columns needed to get season averages (case-insensitive)
    win_loss = [col for col in column_names if 'win_loss_vs' in col.lower()]
    pts_home = [col for col in column_names if 'avr_pts_scored_home_vs' in col.lower()]
    pts_away = [col for col in column_names if 'avr_pts_scored_away_vs' in col.lower()]
    pts_allowed_home = [col for col in column_names if 'avr_pts_allowed_home_vs' in col.lower()]
    pts_allowed_away = [col for col in column_names if 'avr_pts_allowed_away_vs' in col.lower()]
    fg_home = [col for col in column_names if 'fg_per_home_vs' in col.lower()]
    fg_away = [col for col in column_names if 'fg_per_away_vs' in col.lower()]
    three_home = [col for col in column_names if 'three_pt_per_home_vs' in col.lower()]
    three_away = [col for col in column_names if 'three_pt_per_away_vs' in col.lower()]

    # Step 3: Select required columns and year for row identification
    selected_columns = (win_loss + pts_home + pts_away + pts_allowed_home + pts_allowed_away + fg_home + fg_away + three_home + three_away + ['Year'])
    
    query = f"SELECT {', '.join(selected_columns)} FROM {table_name}"
    cursor.execute(query)
    rows = cursor.fetchall()
    
    '''
        Need to keep in mind that some teams didnt exist in certain years 
        - ratio of ratios/ratios
    '''


    # Each row is a different year 
    for row in rows:
        win_loss_values = [row[col] for col in win_loss if row[col] is not None]
        pts_home_values = [row[col] for col in pts_home if row[col] is not None]
        pts_away_values = [row[col] for col in pts_away if row[col] is not None]
        pts_allowed_home_values = [row[col] for col in pts_allowed_home if row[col] is not None]
        pts_allowed_away_values = [row[col] for col in pts_allowed_away if row[col] is not None]
        fg_home_values = [row[col] for col in fg_home if row[col] is not None]
        fg_away_values = [row[col] for col in fg_away if row[col] is not None]
        three_home_values = [row[col] for col in three_home if row[col] is not None]
        three_away_values = [row[col] for col in three_away if row[col] is not None]

        #avg_win_loss = sum(point_values) / len(point_columns) if point_columns else 0
        avg_pts_home = sum(pts_home_values) / len(pts_home) if pts_home else 0
        avg_pts_away = sum(pts_away_values) / len(pts_away) if pts_away else 0
        avg_pts_allowed_home = sum(pts_allowed_home_values) / len(pts_allowed_home) if pts_allowed_home else 0
        avg_pts_allowed_away = sum(pts_allowed_away_values) / len(pts_allowed_away) if pts_allowed_away else 0
        avg_fg_home= sum(fg_home_values) / len(fg_home) if fg_home else 0
        avg_fg_away = sum(fg_away_values) / len(fg_away) if fg_away else 0
        avg_three_home = sum(three_home_values) / len(three_home) if pts_home else 0
        avg_three_away = sum(three_away_values) / len(three_away) if pts_away else 0

        # Update the row
        '''
        cursor.execute("""
            UPDATE {table_name}
            SET average_points = ?, average_assists = ?
            WHERE rowid = ?
        """, (avg_points, avg_assists, row['Year']))
        '''

    
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


 