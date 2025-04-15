# This script should be run after create_team_tables.py as a sanity check
import sqlite3

def print_all_table_columns(cursor, limit):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    numToCheck = limit

    print("\nColumn names in each table:\n" + "-" * 40)
    for table in tables:
        if numToCheck != 0:
            table_name = table[0]
            print(f"\nTable: {table_name}")
            try:
                cursor.execute(f'PRAGMA table_info("{table_name}")')
                columns = cursor.fetchall()
                for col in columns:
                    print(f"- {col[1]} ({col[2]})")  # col[1] is name, col[2] is data type
            except sqlite3.Error as e:
                print(f"Error reading columns for {table_name}: {e}")
            numToCheck -= 1

# Connect to the existing database
conn = sqlite3.connect('../../wnba_stats.db')
cursor = conn.cursor()

# Fetch all table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

# Print them
print("Tables in the database:")
for table in tables:
    print(f"- {table[0]}")

# The second argument will dictate how many team tables with all of their columns will be 
# printed to the console
print_all_table_columns(cursor, 1)

conn.close()