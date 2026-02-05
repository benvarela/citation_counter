source("HelperFunctions.R")
library(tidyverse)
# Conditional install+load for rjson
if (!requireNamespace("rjson", quietly = TRUE)) {
  cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
  cat("rjson package not found. Installing now...\n")
  cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")

  tryCatch({
    install.packages("rjson", repos = "https://cloud.r-project.org/")
    cat("rjson package installed successfully!\n\n")
  }, error = function(e) {
    cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
    cat("ERROR: Failed to automatically install rjson package\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    cat("Please install manually by running in R:\n")
    cat("    install.packages('rjson')\n\n")
    cat("Error details:", conditionMessage(e), "\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    stop("rjson package installation failed")
  })
}
library(rjson)

# Conditional install+load for stringi
if (!requireNamespace("stringi", quietly = TRUE)) {
  cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
  cat("stringi package not found. Installing now...\n")
  cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")

  tryCatch({
    install.packages("stringi", repos = "https://cloud.r-project.org/")
    cat("stringi package installed successfully!\n\n")
  }, error = function(e) {
    cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
    cat("ERROR: Failed to automatically install stringi package\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    cat("Please install manually by running in R:\n")
    cat("    install.packages('stringi')\n\n")
    cat("Error details:", conditionMessage(e), "\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    stop("stringi package installation failed")
  })
}
library(stringi)

# Conditional install+load for arrow (parquet support)
if (!requireNamespace("arrow", quietly = TRUE)) {
  cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
  cat("arrow package not found. Installing now...\n")
  cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")

  tryCatch({
    install.packages("arrow", repos = "https://cloud.r-project.org/")
    cat("arrow package installed successfully!\n\n")
  }, error = function(e) {
    cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
    cat("ERROR: Failed to automatically install arrow package\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    cat("Please install manually by running in R:\n")
    cat("    install.packages('arrow')\n\n")
    cat("Error details:", conditionMessage(e), "\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    stop("arrow package installation failed")
  })
}
library(arrow)

# Conditional install+load for openxlsx (xlsx support)
if (!requireNamespace("openxlsx", quietly = TRUE)) {
  cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
  cat("openxlsx package not found. Installing now...\n")
  cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")

  tryCatch({
    install.packages("openxlsx", repos = "https://cloud.r-project.org/")
    cat("openxlsx package installed successfully!\n\n")
  }, error = function(e) {
    cat("\n", paste(rep("=", 70), collapse = ""), "\n", sep = "")
    cat("ERROR: Failed to automatically install openxlsx package\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    cat("Please install manually by running in R:\n")
    cat("    install.packages('openxlsx')\n\n")
    cat("Error details:", conditionMessage(e), "\n")
    cat(paste(rep("=", 70), collapse = ""), "\n\n", sep = "")
    stop("openxlsx package installation failed")
  })
}
library(openxlsx)

# Cache helper functions (standalone copies)
load_gender_cache <- function() {
  cache_dir <- "data/cache"
  cache_file <- file.path(cache_dir, "gender-api-names.csv")

  if (!dir.exists(cache_dir)) {
    dir.create(cache_dir, recursive = TRUE)
  }

  if (file.exists(cache_file)) {
    cache_data <- read.csv(cache_file, stringsAsFactors = FALSE)
    cache_data$name <- trimws(tolower(cache_data$name))
    return(cache_data)
  } else {
    return(data.frame(name = character(0), prob.m = numeric(0), prob.w = numeric(0), stringsAsFactors = FALSE))
  }
}

save_gender_cache <- function(cache_data) {
  cache_dir <- "data/cache"
  cache_file <- file.path(cache_dir, "gender-api-names.csv")

  if (!dir.exists(cache_dir)) {
    dir.create(cache_dir, recursive = TRUE)
  }

  write.csv(cache_data, cache_file, row.names = FALSE)
}

suppressWarnings({

  cat("*** Starting per-author gender lookup ***\n")

  # Input: parquet file from command-line argument
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) < 1) {
    stop("Usage: Rscript authors_extended_gender.R <input.parquet>")
  }
  input_path <- args[1]

  if (!file.exists(input_path)) {
    stop(paste("Input file not found:", input_path))
  }

  author_data <- read_parquet(input_path)

  if (!"author_name" %in% colnames(author_data)) {
    stop("Input parquet must contain an 'author_name' column")
  }

  cat("Read", nrow(author_data), "rows from", input_path, "\n")

  # Transliterate author_name to ASCII and extract first name
  author_data$author_name_ascii <- stri_trans_general(as.character(author_data$author_name), "Latin-ASCII")

  first_names <- sapply(author_data$author_name_ascii, function(name) {
    if (is.na(name) || trimws(name) == "") return(NA_character_)
    tokens <- strsplit(trimws(name), "\\s+")[[1]]
    trimws(tolower(tokens[1]))
  }, USE.NAMES = FALSE)

  # Load gender-api.com key
  json_data <- fromJSON(file = "config.json")
  gender_api_key <- json_data[["gender-api.com_apikey"]]

  # Load existing cache
  cached_genders <- load_gender_cache()

  # Build unique name list for gender lookup
  name_list <- unique(na.omit(first_names))

  # Detect initials: single letter, single letter + dot, or is.initials() == TRUE
  initials <- sapply(name_list, function(n) {
    grepl("^[a-z]\\.?$", n) || is.initials(n)
  }, USE.NAMES = FALSE)

  namegends <- data.frame(
    name = name_list,
    prob.m = rep(NA, length(name_list)),
    prob.w = rep(NA, length(name_list)),
    stringsAsFactors = FALSE
  )

  # Skip initials
  namegends$prob.m[initials] <- -1
  namegends$prob.w[initials] <- -1

  # Tier 1: Fill from cache
  if (nrow(cached_genders) > 0) {
    cached_matches <- match(namegends$name, cached_genders$name)
    cached_idx <- which(!is.na(cached_matches))
    if (length(cached_idx) > 0) {
      namegends$prob.m[cached_idx] <- cached_genders$prob.m[cached_matches[cached_idx]]
      namegends$prob.w[cached_idx] <- cached_genders$prob.w[cached_matches[cached_idx]]
    }
  }

  # Count how many were resolved from cache (excluding initials)
  cache_resolved_count <- sum(!is.na(namegends$prob.m) & namegends$prob.m != -1)

  # Tier 2: Fill from CommonNamesDatabase
  commonnames <- read.csv("name_csvs/CommonNamesDatabase.csv", stringsAsFactors = FALSE)[, -1]
  commonnames$name <- trimws(tolower(commonnames$name))
  still_na <- which(is.na(namegends$prob.m))
  names_in_common <- still_na[namegends$name[still_na] %in% commonnames$name]
  if (length(names_in_common) > 0) {
    in_common_data <- lapply(names_in_common, match.common, namegends, commonnames)
    namegends[names_in_common, ] <- do.call(rbind, in_common_data)
  }

  # Count how many were resolved from common names
  common_resolved_count <- sum(!is.na(namegends$prob.m) & namegends$prob.m != -1) - cache_resolved_count

  # Report cache statistics
  remaining <- which(is.na(namegends$prob.m))
  total_api <- length(unique(namegends$name[remaining]))
  cat("Cache statistics:\n")
  cat("- Unique names to resolve:", length(name_list), "\n")
  cat("- Initials (skipped):", sum(initials), "\n")
  cat("- Resolved from common names:", common_resolved_count, "\n")
  cat("- Resolved from cache:", cache_resolved_count, "\n")
  cat("- Names remaining for API lookup:", length(remaining), "\n")
  cat("- Total unique names for API lookup:", total_api, "\n")

  # Prompt user before making API calls
#   if (length(remaining) > 0) {
#     answer <- readline(prompt = "Proceed with API lookup? (y/n): ")
#     if (!tolower(answer) %in% c("y", "yes")) {
#       stop("Aborted by user.")
#     }
#   }

  # Tier 3: Query gender-api.com for remaining names
  api_call_count <- 0
  for (i in remaining) {
    this_name <- namegends$name[i]
    json_file <- paste0("https://gender-api.com/get?name=", this_name, "&key=", gender_api_key)
    json_data <- fromJSON(file = json_file)

    if (json_data$gender == "male") {
      namegends$prob.m[i] <- json_data$accuracy / 100
      namegends$prob.w[i] <- 1 - json_data$accuracy / 100
    } else if (json_data$gender == "female") {
      namegends$prob.w[i] <- json_data$accuracy / 100
      namegends$prob.m[i] <- 1 - json_data$accuracy / 100
    } else {
      namegends$prob.m[i] <- -1
      namegends$prob.w[i] <- -1
    }

    api_call_count <- api_call_count + 1

    # Save cache every 10 API calls
    if (api_call_count %% 10 == 0) {
      # Merge new lookups into existing cache
      new_entries <- namegends[!is.na(namegends$prob.m), ]
      merged_cache <- rbind(cached_genders[!cached_genders$name %in% new_entries$name, ], new_entries)
      save_gender_cache(merged_cache)
    }

    Sys.sleep(round(runif(1, 1, 3), 0))
  }

  # Final cache update: merge new lookups with existing cache (append, don't overwrite)
  new_entries <- namegends[!is.na(namegends$prob.m), ]
  merged_cache <- rbind(cached_genders[!cached_genders$name %in% new_entries$name, ], new_entries)
  save_gender_cache(merged_cache)

  if (api_call_count > 0) {
    cat("Made", api_call_count, "gender-api.com calls\n")
  }

  # Map results back to per-row data
  name_idx <- match(first_names, namegends$name)
  author_data$prob_male <- namegends$prob.m[name_idx]
  author_data$prob_female <- namegends$prob.w[name_idx]

  # Remove intermediate column
  author_data$author_name_ascii <- NULL

  # Derive output paths from input filename
  base_name <- tools::file_path_sans_ext(input_path)
  output_parquet <- paste0(base_name, "_gender.parquet")
  output_xlsx <- paste0(base_name, "_gender.xlsx")

  write_parquet(author_data, output_parquet)
  cat("Wrote parquet:", output_parquet, "\n")

  write.xlsx(as.data.frame(author_data), output_xlsx, rowNames = FALSE)
  cat("Wrote xlsx:", output_xlsx, "\n")

  cat("*** Per-author gender lookup complete! ***\n")
})
