# wnba_team_game_stats_by_season.R

library(wehoop)
library(dplyr)

# Set output directory
output_folder <- "~/Desktop/github/wnba/wnba_stats/schedules/csv"
dir.create(output_folder, recursive = TRUE, showWarnings = FALSE)

# Define seasons to fetch
seasons <- 2023:2024

for (season_year in seasons) {
  message(paste("Processing season:", season_year))
  
  # Get schedule and game IDs
  schedule <- espn_wnba_scoreboard(season = season_year)
  game_ids <- schedule$game_id
  
  # Fetch team stats for each game
  team_stats_list <- lapply(game_ids, function(id) {
    tryCatch({
      espn_wnba_team_box(game_id = id)
    }, error = function(e) {
      message(paste("Failed to load game ID:", id))
      return(NULL)
    })
  })
  
  # Remove NULLs and empty data frames
  team_stats_list <- Filter(function(x) {
    is.data.frame(x) && nrow(x) > 0
  }, team_stats_list)

  # Process and combine home/away stats per game
  if (length(team_stats_list) > 0) {
  season_data <- bind_rows(team_stats_list)

  if (is.data.frame(season_data)) {
    # Convert percentages if they exist (safely)
    if ("field_goal_pct" %in% names(season_data)) {
      season_data$field_goal_pct <- as.numeric(season_data$field_goal_pct) / 100
    }
    if ("three_point_field_goal_pct" %in% names(season_data)) {
      season_data$three_point_field_goal_pct <- as.numeric(season_data$three_point_field_goal_pct) / 100
    }

    # Separate home and away
    home_data <- season_data %>%
    filter(team_home_away == "home") %>%
    mutate(HOME_WL = if_else(team_winner, "W", "L")) %>%
    rename_with(~ paste0("HOME_", .), .cols = -game_id) %>%
    rename(
    HOME_TEAM_NAME = HOME_team_display_name,
    HOME_PTS = HOME_team_score,
    HOME_FG_PCT = HOME_field_goal_pct,
    HOME_FG3_PCT = HOME_three_point_field_goal_pct
    )

    away_data <- season_data %>%
    filter(team_home_away == "away") %>%
    select(-team_winner) %>%
    rename_with(~ paste0("AWAY_", .), .cols = -game_id) %>%
    rename(
    AWAY_TEAM_NAME = AWAY_team_display_name,
    AWAY_PTS = AWAY_team_score,
    AWAY_FG_PCT = AWAY_field_goal_pct,
    AWAY_FG3_PCT = AWAY_three_point_field_goal_pct
    )


    # Join on game_id
    merged_data <- left_join(home_data, away_data, by = "game_id") %>%
      mutate(Season = season_year, 
      HOME_PLUS_MINUS = HOME_PTS - AWAY_PTS,
      AWAY_PLUS_MINUS = AWAY_PTS - HOME_PTS
      ) %>%
      select(Season, everything())

    filename <- file.path(output_folder, paste0("wnba_stats_schedule_", season_year, ".csv"))
    write.csv(merged_data, filename, row.names = FALSE)
    message(paste("✅ Saved:", filename))
  } else {
    message(paste("⚠️ bind_rows did not return a data frame for season:", season_year))
  }
}
  message(paste("Saved CSV for season:", season_year))
}

