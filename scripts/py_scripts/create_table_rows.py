import sqlite3

# Connect to SQLite3 database (it will create the database file if it doesn't exist)
conn = sqlite3.connect('wnba_stats.db')  # Change the database name if needed
cursor = conn.cursor()

# make a dictionary that maps how many years a team has played to the team (including this year which will have no date currently)
# key : value ex. new york liberty : 29
history = {
    "Atlanta Dream" : 18,
    "Chicago Sky" : 20,
    "Connecticut Sun" : 23, 
    "Indiana Fever" : 26,
    "New York Liberty" : 29,
    "Washington Mystics" : 28,
    "Dallas Wings" : 10,
    "Golden State Valkyries" : 1,
    "Los Angeles Sparks" : 29,
    "Minnesota Lynx" : 27,
    "Phoenix Mercury" : 29,
    "Seattle Storm" : 26,
    #"Cleveland Rockers",
    #"Charlotte Sting",
    #"Huston Comets",
    #"Sacramento Monarchs",
    #"Miami Sol",
    #"Portland Fire",
    "Las Vegas Aces" : 29,
    "Utah Starzz" : 6,
    "San Antonio Silver Stars" : 11,
    "San Antonio Stars" : 4,
    "Detroit Shock" : 12,
    "Tulsa Shock" : 6,
    "Orlando Miracle" : 4
    # add any new teams
}

# Get all column names (excluding primary key if autoincrement)
# all the columns will be the same for each team
cursor.execute("PRAGMA table_info(Dallas_Wings)")
columns_info = cursor.fetchall()
column_names = [col[1] for col in columns_info if col[5] == 0]  # col[5] == 1 means it's PK

# for team in keys
def add_rows():
    for team in history:
        # go to its table and add x rows to it
        table_name = team.replace(" ", "_").replace("/", "_") 
        for _ in range(history[team]):
            insert_rows_sql = f"INSERT INTO {table_name} ({", ".join(column_names)}) VALUES ({", ".join(["None"] * len(column_names))})"
        
    try:
        # Execute the SQL statement
        cursor.execute(insert_rows_sql)
        print(f"Rows for {team} added successfully.")
    except sqlite3.Error as e:
        print(f"Error adding rows to table for {team}: {e}")

# Commit the changes to save them to the database
add_rows()
conn.commit()

print("Rows inserted successfully.")

# Close the connection
conn.close()
