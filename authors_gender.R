source("HelperFunctions.R")
library(plyr)
library(tidyverse)
library(rlist)
library(rjson)

# MODIFICATION: the apikey for gender-api.com needs to be read from the json file that we have. CHATGPT ASSIST
json_data <- fromJSON(file = "config.json")
gender_api_key <- json_data[["gender-api.com_apikey"]]

# MODIFICATION: Now, data is read from the citation_counter_output.csv, and formatted so that the R program can see if as it would appear otherwise. CHATGPT ASSIST
article.data <- read.csv("citation_counter_output.csv", stringsAsFactors = FALSE)
names(article.data)[names(article.data) == "first_last_author"] <- "AF"

# Read in dataset of common nicknames for variant matching
nicknames=as.matrix(read.csv("name_csvs/nicknames.csv",header=F))
nicknames=tolower(nicknames)

# Read in dataset of likely genders for nicknames
nickname.gends=read.csv("name_csvs/nickname.gends.csv",header=T,stringsAsFactors=F)[,-1]

# Separate out author names and find entries with initials. The expected format is "LastName,Firstname; LastName..." (I think, need to confirm this)
all_auth_names=lapply(as.list(article.data$AF),strsplit,split="; ")
unique_names=unique(unlist(all_auth_names))
allfirsts=unlist(lapply(1:length(unique_names),get.all.given,
                        authlist=unique_names))
alllasts=unlist(lapply(1:length(unique_names),get.all.family,
                       authlist=unique_names))
initials=unlist(lapply(allfirsts,is.initials))

# Match names with only initials to similar full names
newfirsts=unlist(lapply(which(initials==T),match.initials,allfirsts,
                        alllasts,initials))
allfirsts[initials==T]=newfirsts

# Find last names that repeat
lastname_occurrences=table(alllasts)
multiple_occurrences=names(lastname_occurrences[lastname_occurrences>1])

# Determine whether last names have potential variants on the same first name
may_have_variants=do.call(rbind,lapply(multiple_occurrences,find.variants,
                                       allfirsts,alllasts))
may_have_variants=may_have_variants[may_have_variants[,1]==T,]

# Detect name variants and assign all instances to the most detailed version
fn_matched=lapply(which(alllasts%in%may_have_variants[,2]),
                  match.variants.outer,allfirsts,alllasts,
                  may_have_variants,nickname.gends)
allfirsts_matched=allfirsts
allfirsts_matched[alllasts%in%may_have_variants[,2]]=unlist(fn_matched)

# Test out whether it worked as expected by comparing variants before/after
sort(allfirsts[alllasts=="Dolan"])
sort(allfirsts_matched[alllasts=="Dolan"])

# Concatenate first and last names
unique_names_matched=paste0(alllasts,", ",allfirsts_matched)
updated=which(unique_names!=unique_names_matched)
to_change=cbind(unique_names,unique_names_matched)[updated,]

# Replace article.data names with matched names
auth_vec=unlist(all_auth_names)
auth_vec=mapvalues(auth_vec, from=to_change[,1], to=to_change[,2])
all_auth_names=list.flatten(relist(auth_vec, skeleton=all_auth_names))
article.data$AF=unlist(lapply(all_auth_names,paste,collapse="; "))

# MODIFICATION: removed the saving/loading of the dataframe here.
all_auth_names=lapply(as.list(article.data$AF),strsplit,split="; ")
first_names=lapply(1:length(all_auth_names),get.all.given,
                   authlist=all_auth_names)

# Isolate first- and last-authors' first names
first_last_auths=lapply(first_names,get.first.last)

# Get unique first names for gender estimation
name_list=unique(unlist(first_last_auths))
initials=unlist(lapply(name_list,is.initials))

# Create dataset for names and predicted genders
namegends=data.frame(name=name_list,
                     prob.m=rep(NA,length(name_list)),
                     prob.w=rep(NA,length(name_list)))

# Make name variable chr type
namegends$name=as.character(namegends$name)

# Insert "-1" for initials, so you don't waste gender credits on them
namegends$prob.m[initials==T]=-1
namegends$prob.w[initials==T]=-1

# Fill in some data using pre-built common names database
commonnames=read.csv("name_csvs/CommonNamesDatabase.csv",stringsAsFactors=F)[,-1]
names_in_common=which(namegends$name%in%commonnames$name)
in_common_data=lapply(names_in_common,match.common,
                      namegends,commonnames)
namegends[names_in_common,]=do.call(rbind,in_common_data)

# Enter your API key here for gender-api.com
gender_api_key = gender_api_key

# Determine which names have yet to be queried from gender-api
r=which(is.na(namegends$prob.m))

# For the remaining unqueried names...
for(i in r){
  
  # Isolate name to be queried
  this_name=namegends$name[i]
  
  # Pull json data from gender-api
  json_file=paste0("https://gender-api.com/get?name=",this_name,
                   "&key=",gender_api_key)
  json_data=fromJSON(file=json_file)
  
  # Save gender probabilities to the namegends dataset
  if(json_data$gender=="male"){
    namegends$prob.m[i]=json_data$accuracy/100
    namegends$prob.w[i]=1-json_data$accuracy/100
  }else if(json_data$gender=="female"){
    namegends$prob.w[i]=json_data$accuracy/100
    namegends$prob.m[i]=1-json_data$accuracy/100
  }else{
    namegends$prob.w[i]=-1
    namegends$prob.m[i]=-1
  }
  
  # Pause to space out pull requests
  time=round(runif(1,1,3),0)
  for(t in time:1){
    Sys.sleep(1)
    cat("Pausing to space out gender-api.com requests...","\n")
  }
}

# MODIFICATION: CHATGPT assisted code, to get this into a nice exportable csv.
namegends$name <- trimws(tolower(namegends$name))
first_last_given_names <- lapply(strsplit(article.data$AF, "; "), function(authors) {
  # First author
  first_author <- strsplit(authors[1], ",")[[1]]
  first_given <- if (length(first_author) >= 2) trimws(tolower(first_author[2])) else NA
  
  # Last author
  last_author <- strsplit(authors[length(authors)], ",")[[1]]
  last_given <- if (length(last_author) >= 2) trimws(tolower(last_author[2])) else NA
  
  return(c(first_given, last_given))
})

first_last_df <- as.data.frame(do.call(rbind, first_last_given_names), stringsAsFactors = FALSE)
colnames(first_last_df) <- c("first_given", "last_given")

lookup_gender_prob <- function(name) {
  if (is.na(name)) return(c(NA, NA))
  row <- namegends[namegends$name == name, ]
  if (nrow(row) == 0) return(c(NA, NA))
  return(c(row$prob.m, row$prob.w))
}

gender_probs <- t(apply(first_last_df, 1, function(name_pair) {
  fg <- lookup_gender_prob(name_pair[1])
  lg <- lookup_gender_prob(name_pair[2])
  c(
    first_prob_m = fg[1],
    last_prob_m  = lg[1],
    first_prob_w = fg[2],
    last_prob_w  = lg[2]
  )
}))

article.data$first_prob_male <- as.numeric(gender_probs[, "first_prob_m"])
article.data$first_prob_female <- as.numeric(gender_probs[, "first_prob_w"])
article.data$last_prob_male  <- as.numeric(gender_probs[, "last_prob_m"])
article.data$last_prob_female  <- as.numeric(gender_probs[, "last_prob_w"])
names(article.data)[names(article.data) == "AF"] <- "first_last_author"

write.csv(article.data, "citation_counter_output.csv", row.names = FALSE)
cat("\n", file = "citation_counter_output.csv", append = TRUE)