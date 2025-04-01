# Call this script by typing "R" into your terminal, hit enter,
# then type 'source("path_to_script/hello_world_wehoop.R")' and hit enter

# Load the "wehoop" library
library(wehoop)
library(tictoc)

# Optionally, you can check if the package loaded successfully
print("The wehoop package has been installed and loaded!")

tictoc::tic()
progressr::with_progress({
  wnba_pbp <- wehoop::wnba_schedule(league_id = '10', season = most_recent_wnba_season())
  View(wnba_pbp)
})
tictoc::toc()