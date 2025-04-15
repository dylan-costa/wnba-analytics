import sqlite3

# Connect to SQLite3 database (it will create the database file if it doesn't exist)
conn = sqlite3.connect('wnba_stats.db')  # Change the database name if needed
cursor = conn.cursor()

# make a dictionary that maps the years in the wnba to the team (including this year which will have no data currently)
# key : value ex. Golden State Valkyries : [2025]
history = {
    "Atlanta Dream" : [2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Chicago Sky" : [2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Connecticut Sun" : [2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025], 
    "Indiana Fever" : [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "New York Liberty" : [1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Washington Mystics" : [1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Dallas Wings" : [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Golden State Valkyries" : [2025],
    "Los Angeles Sparks" : [1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Minnesota Lynx" : [1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Phoenix Mercury" : [1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Seattle Storm" : [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Cleveland Rockers" : [1997, 1998, 1999, 2000, 2001, 2002, 2003],
    "Charlotte Sting" : [1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006],
    "Huston Comets" : [1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008],
    "Sacramento Monarchs" : [1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009],
    "Miami Sol" : [2000, 2001, 2002],
    "Portland Fire" : [2000, 2001, 2002],
    "Las Vegas Aces" : [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "Utah Starzz" : [1997, 1998, 1999, 2000, 2001, 2002],
    "San Antonio Silver Stars" : [2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013],
    "San Antonio Stars" : [2014, 2015, 2016, 2017],
    "Detroit Shock" : [1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009],
    "Tulsa Shock" : [2010, 2011, 2012, 2013, 2014, 2015],
    "Orlando Miracle" : [1999, 2000, 2001, 2002]
}


def add_rows():
    for team, years in history.items():
        # go to its table and add x rows to it
        table_name = team.replace(" ", "_")
        print(f"Adding rows to the {table_name} table")
        try:
        # Execute the SQL statement
            cursor.executemany(f"INSERT INTO {table_name} (Year) VALUES (?)", [(year,) for year in years])
            print(f"Rows for {team} added successfully.")
        except sqlite3.Error as e:
            print(f"Error adding rows to table for {team}: {e}")
            
# Commit the changes to save them to the database
add_rows()
conn.commit()

# Close the connection
conn.close()
