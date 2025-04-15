# This script will parse the csv files at wnba_stats/ and write to each team's table
# with all applicable stats.  There may be some columns that won't be able to be 
# populated based off all the info from the schedule csv's.
import csv
import os

def get_column_mapping(csv_file_path):
    # Reads the first line of a CSV file and returns a dict mapping
    # column names to their column numbers (0-indexed).
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        headers = next(reader)  # First line
        return {column_name: index for index, column_name in enumerate(headers)}
    
if __name__ == "__main__":
    # Path to the csv's (relative from this script)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    csv_dir = os.path.join(base_dir, 'wnba_stats', 'schedules', 'csv')

    # Get all CSV file paths
    csv_files = sorted([f for f in os.listdir(csv_dir) if f.endswith('.csv')])

    # Loop through each file and print the column mapping
    for csv_filename in csv_files:
        csv_path = os.path.join(csv_dir, csv_filename)
        column_map = get_column_mapping(csv_path)

        # For each CSV, need to read line by line and grab the following data points:
        # HOME_TEAM_NAME: 30, HOME_PTS: 32, HOME_FG_PCT: 35, HOME_FG3_PCT: 38, HOME_PLUS_MINUS: 50, HOME_WL: 51
        # 

        print(f"Column mapping for {csv_filename}:")
        print(column_map)
        print('-' * 50)