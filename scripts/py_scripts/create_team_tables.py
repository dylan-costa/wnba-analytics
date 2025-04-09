import sqlite3

# Connect to SQLite database (it will create the database if it doesn't exist)
conn = sqlite3.connect('wnba_stats.db')
cursor = conn.cursor()

# List of all current and historical WNBA teams
wnba_teams = [
    "Atlanta Dream",
    "Chicago Sky",
    "Connecticut Sun",
    "Indiana Fever",
    "New York Liberty",
    "Washington Mystics",
    "Dallas Wings",
    #"Golden State Valkyries",
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
    "Utah Starzz",
    "San Antonio Silver Stars",
    "San Antonio Stars",
    "Detroit Shock",
    "Tulsa Shock",
    "Orlando Miracle"
    # Add more teams if necessary, including past teams
]

# Template for creating a table with 34 configurable columns
column_template = [
    "column1 TEXT",
    "column2 INTEGER",
    "column3 REAL",
    "column4 TEXT",
    "column5 INTEGER",
    "column6 REAL",
    "column7 TEXT",
    "column8 INTEGER",
    "column9 REAL",
    "column10 TEXT",
    "column11 INTEGER",
    "column12 REAL",
    "column13 TEXT",
    "column14 INTEGER",
    "column15 REAL",
    "column16 TEXT",
    "column17 INTEGER",
    "column18 REAL",
    "column19 TEXT",
    "column20 INTEGER",
    "column21 REAL",
    "column22 TEXT",
    "column23 INTEGER",
    "column24 REAL",
    "column25 TEXT",
    "column26 INTEGER",
    "column27 REAL",
    "column28 TEXT",
    "column29 INTEGER",
    "column30 REAL",
    "column31 TEXT",
    "column32 INTEGER",
    "column33 REAL",
    "column34 TEXT"
]

# Function to create a table for each WNBA team
def create_tables():
    for team in wnba_teams:
        # Clean the team name to use as a table name (replace spaces with underscores)
        table_name = team.replace(" ", "_").replace("/", "_")  # Replace spaces and slashes
        
        # Create the SQL statement to create the table
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (" + ", ".join(column_template) + ");"
        
        try:
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