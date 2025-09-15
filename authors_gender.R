source("HelperFunctions.R")
library(plyr)
library(tidyverse)
library(rlist)
library(rjson)
library(stringi)

# Cache helper functions
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

# Suppress warnings for the whole block
suppressWarnings({

  cat("*** Starting extraction of first and last author genders! ***\n There are no progress messages printed during this process, although a message will be printed upon completion\n")
  
  # Load gender-api.com key
  json_data <- fromJSON(file = "config.json")
  gender_api_key <- json_data[["gender-api.com_apikey"]]

  # Read CSV as UTF-8
  article.data <- read.csv("citation_counter_output.csv", 
                           stringsAsFactors = FALSE, 
                           fileEncoding = "UTF-8")

  # Flatten all non-ASCII characters in the author column to ASCII
  article.data$firstlastauthor_openalex <- stri_trans_general(article.data$firstlastauthor_openalex, "Latin-ASCII")
  names(article.data)[names(article.data) == "firstlastauthor_openalex"] <- "AF"

  # Extract first and last author first names
  first_last_given_names <- lapply(strsplit(article.data$AF, "; "), function(authors){
    first_author <- strsplit(authors[1], ",")[[1]]
    first_given <- if(length(first_author) >= 2) trimws(tolower(first_author[2])) else NA
    last_author <- strsplit(authors[length(authors)], ",")[[1]]
    last_given <- if(length(last_author) >= 2) trimws(tolower(last_author[2])) else NA
    return(c(first_given, last_given))
  })

  first_last_df <- as.data.frame(do.call(rbind, first_last_given_names), stringsAsFactors = FALSE)
  colnames(first_last_df) <- c("first_given", "last_given")

  # Load existing cache
  cached_genders <- load_gender_cache()
  
  # Prepare unique names for gender lookup
  name_list <- unique(na.omit(c(first_last_df$first_given, first_last_df$last_given)))
  initials <- unlist(lapply(name_list, is.initials))

  namegends <- data.frame(
    name = trimws(tolower(name_list)),
    prob.m = rep(NA, length(name_list)),
    prob.w = rep(NA, length(name_list))
  )

  # Skip initials
  namegends$prob.m[initials] <- -1
  namegends$prob.w[initials] <- -1
  
  # Fill in from cache
  if (nrow(cached_genders) > 0) {
    cached_matches <- match(namegends$name, cached_genders$name)
    cached_idx <- which(!is.na(cached_matches))
    if (length(cached_idx) > 0) {
      namegends$prob.m[cached_idx] <- cached_genders$prob.m[cached_matches[cached_idx]]
      namegends$prob.w[cached_idx] <- cached_genders$prob.w[cached_matches[cached_idx]]
    }
  }

  # Fill in common names from pre-built database
  commonnames <- read.csv("name_csvs/CommonNamesDatabase.csv", stringsAsFactors = FALSE)[, -1]
  commonnames$name <- trimws(tolower(commonnames$name))
  names_in_common <- which(namegends$name %in% commonnames$name)
  if(length(names_in_common) > 0){
    in_common_data <- lapply(names_in_common, match.common, namegends, commonnames)
    namegends[names_in_common, ] <- do.call(rbind, in_common_data)
  }

  # Query gender-api for remaining names
  r <- which(is.na(namegends$prob.m))
  api_call_count <- 0
  
  # Report cache statistics
  cached_count <- sum(!is.na(namegends$prob.m) & namegends$prob.m != -1)
  common_count <- sum(!is.na(namegends$prob.m) & namegends$prob.m != -1) - nrow(cached_genders)
  remaining_count <- length(r)
  cat("Cache statistics:\n")
  cat("- Names loaded from cache:", nrow(cached_genders), "\n")
  cat("- Names found in common names database:", max(0, common_count), "\n") 
  cat("- Names remaining for API lookup:", remaining_count, "\n")
  
  for(i in r){
    this_name <- namegends$name[i]
    json_file <- paste0("https://gender-api.com/get?name=", this_name, "&key=", gender_api_key)
    json_data <- fromJSON(file = json_file)

    if(json_data$gender == "male"){
      namegends$prob.m[i] <- json_data$accuracy/100
      namegends$prob.w[i] <- 1 - json_data$accuracy/100
    } else if(json_data$gender == "female"){
      namegends$prob.w[i] <- json_data$accuracy/100
      namegends$prob.m[i] <- 1 - json_data$accuracy/100
    } else {
      namegends$prob.m[i] <- -1
      namegends$prob.w[i] <- -1
    }

    api_call_count <- api_call_count + 1
    
    # Save cache every 10 API calls
    if (api_call_count %% 10 == 0) {
      current_cache <- namegends[!is.na(namegends$prob.m), ]
      save_gender_cache(current_cache)
    }

    Sys.sleep(round(runif(1,1,3),0))
  }
  
  # Save final cache after all API calls
  final_cache <- namegends[!is.na(namegends$prob.m), ]
  save_gender_cache(final_cache)

  # Lookup function using match
  lookup_gender_prob <- function(name){
    if(is.na(name)) return(c(NA, NA))
    idx <- match(trimws(tolower(name)), namegends$name)
    if(is.na(idx)) return(c(NA, NA))
    return(c(namegends$prob.m[idx], namegends$prob.w[idx]))
  }

  # Apply lookup to first and last authors
  gender_probs <- t(apply(first_last_df, 1, function(name_pair){
    fg <- lookup_gender_prob(name_pair[1])
    lg <- lookup_gender_prob(name_pair[2])
    c(
      first_prob_m = fg[1],
      last_prob_m  = lg[1],
      first_prob_w = fg[2],
      last_prob_w  = lg[2]
    )
  }))

# Save results to article.data
  article.data$first_prob_male   <- gender_probs[, "first_prob_m"]
  article.data$first_prob_female <- gender_probs[, "first_prob_w"]
  article.data$last_prob_male    <- gender_probs[, "last_prob_m"]
  article.data$last_prob_female  <- gender_probs[, "last_prob_w"]

# Restore original column name
  names(article.data)[names(article.data) == "AF"] <- "firstlastauthor_openalex"

  # Write to CSV
  write.csv(article.data, "citation_counter_output.csv", row.names = FALSE)
  
  cat("*** Extraction of first and last author genders appended to citation_counter_output.csv! ***\n")
})