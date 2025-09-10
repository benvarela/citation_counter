source("HelperFunctions.R")
library(plyr)
library(tidyverse)
library(rlist)
library(rjson)
library(stringi)

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

    Sys.sleep(round(runif(1,1,3),0))
  }

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