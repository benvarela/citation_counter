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
    stop("Usage: Rscript authors_extended_gender.R <input.parquet> [include_all]")
  }
  input_path <- args[1]
  include_all <- length(args) >= 2 && tolower(args[2]) == "include_all"

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

  # By default, only look up first and last authors
  if (!include_all) {
    is_first <- if ("first_author" %in% colnames(author_data)) author_data$first_author == TRUE else FALSE
    is_last  <- if ("last_author" %in% colnames(author_data))  author_data$last_author == TRUE  else FALSE
    keep <- is_first | is_last
    cat("Filtering to first/last authors:", sum(keep), "of", nrow(author_data), "rows\n")
    first_names[!keep] <- NA_character_
  } else {
    cat("include_all: looking up all", nrow(author_data), "authors\n")
  }

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

  # Tier 1: Fill from cache (but skip -1, -1 entries to allow re-querying)
  if (nrow(cached_genders) > 0) {
    cached_matches <- match(namegends$name, cached_genders$name)
    cached_idx <- which(!is.na(cached_matches))
    if (length(cached_idx) > 0) {
      # Only use cache entries that are not -1, -1 (which may indicate previous API errors)
      for (idx in cached_idx) {
        cache_row <- cached_matches[idx]
        cached_prob_m <- cached_genders$prob.m[cache_row]
        cached_prob_w <- cached_genders$prob.w[cache_row]

        # Skip if both values are -1 (previous error/unknown, should be re-queried)
        if (cached_prob_m == -1 && cached_prob_w == -1) {
          next
        }

        namegends$prob.m[idx] <- cached_prob_m
        namegends$prob.w[idx] <- cached_prob_w
      }
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
  consecutive_401_count <- 0
  consecutive_400_count <- 0
  failed_401_names <- character(0)
  failed_400_names <- character(0)

  # Progress tracking
  total_to_query <- length(remaining)
  start_time <- Sys.time()
  processed_count <- 0

  for (i in remaining) {
    processed_count <- processed_count + 1
    this_name <- namegends$name[i]
    json_file <- paste0("https://gender-api.com/get?name=", this_name, "&key=", gender_api_key)

    # Try to fetch gender data with error handling
    api_result <- tryCatch({
      fromJSON(file = json_file)
    }, error = function(e) {
      # Network/HTTP errors - log and skip
      error_msg <- conditionMessage(e)
      cat("Warning: API error for name '", this_name, "': ", error_msg, "\n", sep = "")
      return(list(error = "other"))
    })

    # Check for API errors in the JSON response (errno field)
    if (!is.null(api_result$errno)) {
      errno <- api_result$errno
      errmsg <- if (!is.null(api_result$errmsg)) api_result$errmsg else "unknown error"

      # errno 30 = limit reached
      if (errno == 30) {
        api_result$error <- "401"
      }
      # errno 20-29 are typically bad request / invalid input errors
      else if (errno >= 20 && errno < 30) {
        api_result$error <- "400"
      }
      # Other errors
      else {
        cat("Warning: API error ", errno, " for name '", this_name, "': ", errmsg, "\n", sep = "")
        api_result$error <- "other"
      }
    }

    # Handle limit exceeded (errno 30)
    if (!is.null(api_result$error) && api_result$error == "401") {
      consecutive_401_count <- consecutive_401_count + 1
      failed_401_names <- c(failed_401_names, this_name)
      cat("API limit exceeded (401) for name '", this_name, "' (", consecutive_401_count, " consecutive)\n", sep = "")

      # Check if we've hit 10 consecutive 401 errors
      if (consecutive_401_count >= 10) {
        cat("\n")
        cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")
        cat("ERROR: API credits exceeded\n")
        cat("Received 10 consecutive 401 errors from gender-api.com\n")
        cat("The names ", paste(failed_401_names, collapse = ", "), " could not be retrieved from Gender API. Gender limit may have been exceeded\n", sep = "")
        cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")

        # Save cache before exiting
        new_entries <- namegends[!is.na(namegends$prob.m), ]
        merged_cache <- rbind(cached_genders[!cached_genders$name %in% new_entries$name, ], new_entries)
        save_gender_cache(merged_cache)

        stop("API credits exceeded")
      }

      # Skip this name (leave as NA)
      next
    }

    # Handle 400 errors (bad request)
    if (!is.null(api_result$error) && api_result$error == "400") {
      consecutive_400_count <- consecutive_400_count + 1
      failed_400_names <- c(failed_400_names, this_name)
      cat("Bad request (400) for name '", this_name, "' (", consecutive_400_count, " consecutive)\n", sep = "")

      # Check if we've hit 10 consecutive 400 errors
      if (consecutive_400_count >= 10) {
        cat("\n")
        cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")
        cat("ERROR: Server request error\n")
        cat("Received 10 consecutive 400 errors from gender-api.com\n")
        cat("The names ", paste(failed_400_names, collapse = ", "), " could not be retrieved from Gender API. An error occurred with submitting to the server\n", sep = "")
        cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")

        # Save cache before exiting
        new_entries <- namegends[!is.na(namegends$prob.m), ]
        merged_cache <- rbind(cached_genders[!cached_genders$name %in% new_entries$name, ], new_entries)
        save_gender_cache(merged_cache)

        stop("Server request error")
      }

      # Skip this name (leave as NA)
      next
    }

    # Handle other errors - skip name
    if (!is.null(api_result$error)) {
      next
    }

    # Reset consecutive error counters on successful API call
    consecutive_401_count <- 0
    consecutive_400_count <- 0
    json_data <- api_result

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

    # Calculate and display progress every 5 successful API calls
    if (api_call_count %% 5 == 0) {
      elapsed_time <- as.numeric(difftime(Sys.time(), start_time, units = "secs"))
      rate <- api_call_count / elapsed_time

      # Determine display format (it/s or s/it)
      if (rate >= 1) {
        rate_str <- sprintf("%.2f it/s", rate)
      } else {
        rate_str <- sprintf("%.2f s/it", 1 / rate)
      }

      # Calculate ETA
      remaining_items <- total_to_query - processed_count
      eta_seconds <- remaining_items / rate
      eta_str <- if (eta_seconds < 60) {
        sprintf("%.0fs", eta_seconds)
      } else if (eta_seconds < 3600) {
        sprintf("%.0fm %.0fs", floor(eta_seconds / 60), eta_seconds %% 60)
      } else {
        sprintf("%.0fh %.0fm", floor(eta_seconds / 3600), (eta_seconds %% 3600) / 60)
      }

      cat("Progress: ", processed_count, "/", total_to_query,
          " (", sprintf("%.1f%%", 100 * processed_count / total_to_query),
          ") | ", rate_str, " | ETA: ", eta_str, "\n", sep = "")
    }

    # Save cache every 10 API calls
    if (api_call_count %% 10 == 0) {
      # Merge new lookups into existing cache
      new_entries <- namegends[!is.na(namegends$prob.m), ]
      merged_cache <- rbind(cached_genders[!cached_genders$name %in% new_entries$name, ], new_entries)
      save_gender_cache(merged_cache)
    }

    Sys.sleep(round(runif(1, 1, 3), 0))
  }

  # Display final progress summary
  if (api_call_count > 0) {
    total_elapsed <- as.numeric(difftime(Sys.time(), start_time, units = "secs"))
    avg_rate <- api_call_count / total_elapsed
    rate_str <- if (avg_rate >= 1) {
      sprintf("%.2f it/s", avg_rate)
    } else {
      sprintf("%.2f s/it", 1 / avg_rate)
    }
    cat("Completed ", api_call_count, " API calls in ",
        sprintf("%.1fs", total_elapsed), " (", rate_str, ")\n", sep = "")
  }

  # After loop completes, check if any errors occurred and exit with appropriate message
  if (length(failed_401_names) > 0) {
    cat("\n")
    cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")
    cat("The names ", paste(failed_401_names, collapse = ", "), " could not be retrieved from Gender API. Gender limit may have been exceeded\n", sep = "")
    cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")

    # Save cache before exiting
    new_entries <- namegends[!is.na(namegends$prob.m), ]
    merged_cache <- rbind(cached_genders[!cached_genders$name %in% new_entries$name, ], new_entries)
    save_gender_cache(merged_cache)

    stop("API limit exceeded")
  }

  if (length(failed_400_names) > 0) {
    cat("\n")
    cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")
    cat("The names ", paste(failed_400_names, collapse = ", "), " could not be retrieved from Gender API. An error occurred with submitting to the server\n", sep = "")
    cat(paste(rep("=", 70), collapse = ""), "\n", sep = "")

    # Save cache before exiting
    new_entries <- namegends[!is.na(namegends$prob.m), ]
    merged_cache <- rbind(cached_genders[!cached_genders$name %in% new_entries$name, ], new_entries)
    save_gender_cache(merged_cache)

    stop("Server request error")
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
