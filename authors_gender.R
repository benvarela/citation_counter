# setwd("path/to/project/folder") I should not need this line, the WD is the CWD
source("HelperFunctions.R")
library(tidyverse)
library(parallel)
library(pbmcapply)
library(plyr)
library(rlist)
library(rjson)
library(pbmcapply)

# MODIFICATION: the apikey for gender-api.com needs to be read from the json file that we have. CHATGPT ASSIST
json_data <- fromJSON(file = "config.json")
gender_api_key <- json_data[["gender-api.com_apikey"]]

# MODIFICATION: Now, data is read from the citation_counter_output.csv, and formatted so that the R program can see if as it would appear otherwise. CHATGPT ASSIST
article.data <- read.csv("citation_counter_output.csv", stringsAsFactors = FALSE)
names(article.data)[names(article.data) == "first_last_author"] <- "AF"

# Read in dataset of common nicknames for variant matching
# E.g., to match Ray Dolan to Raymond Dolan
nicknames=as.matrix(read.csv("nicknames.csv",header=F))
nicknames=tolower(nicknames)

# Read in dataset of likely genders for nicknames
# Used to avoid matching e.g. Chris Smith & Christina Smith
nickname.gends=read.csv("nickname.gends.csv",header=T,stringsAsFactors=F)[,-1]

# Save number of cores on machine
# Note: Some of the functions in this step take a fair bit of compute power
# This file should ideally be performed by parallelizing over many cores
cores=detectCores()

# Separate out author names and find entries with initials
all_auth_names=lapply(as.list(article.data$AF),strsplit,split="; ")
unique_names=unique(unlist(all_auth_names))
allfirsts=unlist(pbmclapply(1:length(unique_names),get.all.given,
                            authlist=unique_names,mc.cores=cores))
alllasts=unlist(pbmclapply(1:length(unique_names),get.all.family,
                           authlist=unique_names,mc.cores=cores))
initials=unlist(lapply(allfirsts,is.initials))

# Match names with only initials to similar full names
# E.g., DS Bassett --> Danielle S Bassett
# Inspect the 'match.initials' function for more detail
# NOTE: This function may take some time (best on multiple cores)
newfirsts=unlist(pbmclapply(which(initials==T),match.initials,allfirsts,
                            alllasts,initials,mc.cores=cores))
allfirsts[initials==T]=newfirsts

# Find last names that repeat
lastname_occurrences=table(alllasts)
multiple_occurrences=names(lastname_occurrences[lastname_occurrences>1])

# Determine whether last names have potential variants on the same first name
# I.e., Raymond Dolan and Ray Dolan (vs. Raymond Dolan and Emily Dolan)
may_have_variants=do.call(rbind,pbmclapply(multiple_occurrences,find.variants,
                                           allfirsts,alllasts,mc.cores=cores))
may_have_variants=may_have_variants[may_have_variants[,1]==T,]

# Detect name variants and assign all instances to the most detailed version
# E.g., Ray Dolan, Raymond Dolan, & Ray J Dolan --> Raymond J Dolan
# Inspect 'match.variants.inner' for more detail
# NOTE: This function may take some time (best on multiple cores)
fn_matched=pbmclapply(which(alllasts%in%may_have_variants[,2]),
                      match.variants.outer,allfirsts,alllasts,
                      may_have_variants,nickname.gends,mc.cores=cores)
allfirsts_matched=allfirsts
allfirsts_matched[alllasts%in%may_have_variants[,2]]=unlist(fn_matched)

# Test out whether it worked as expected by comparing variants before/after
# Can substitute Dolan for any name in your dataset that had variants
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

# If you have already started this process and saved an interim file, read it
# If not, create a new file to store names and gender probabilities
# Note: This process takes a while, so you might have to pause and pick
# it back up every once in a while
if("df6_namegends.RData"%in%list.files()){
  load("df6_namegends.RData")
}else{
  all_auth_names=lapply(as.list(article.data$AF),strsplit,split="; ")
  first_names=pbmclapply(1:length(all_auth_names),get.all.given,
                         authlist=all_auth_names,mc.cores=cores)
  
  # Isolate first- and last-authors' first names
  first_last_auths=pbmclapply(first_names,get.first.last,mc.cores=cores)
  
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
  commonnames=read.csv("CommonNamesDatabase.csv",stringsAsFactors=F)[,-1]
  names_in_common=which(namegends$name%in%commonnames$name)
  in_common_data=pbmclapply(names_in_common,match.common,
                            namegends,commonnames,mc.cores=cores)
  namegends[names_in_common,]=do.call(rbind,in_common_data)
  
  # Save this new dataset to be filled in as you go
  save(namegends,file="df6_namegends.RData")
}

# Enter your API key here for gender-api.com
# Run 'sum(is.na(namegends$prob.m))' to see how many credits you'll need
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
  # Enter -1 if gender-api doesn't have any data for that name
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
  
  # Save the interim file so you can pick back up later if you decide to stop
  save(namegends,file="df6_namegends.RData")
  
  # Pause to space out pull requests
  time=round(runif(1,1,3),0)
  for(t in time:1){
    Sys.sleep(1)
    cat("Countdown:",t,"\n")
  }
}

# MODIFICATION: We take all the useful data and then output it over the citation_counter_output.csv. CHATGPT ASSIST
first_names_in_data <- unlist(lapply(strsplit(article.data$AF, "; "), function(x) {
  # Assuming first name is the first element in the split name (e.g., "First Last")
  first_name <- strsplit(x, ",")[[1]][2]
  return(first_name)
}))

# Add the first names as a new column in article.data
article.data$first_name <- first_names_in_data

# Now, join 'article.data' with 'namegends' based on the first names
article.data <- article.data %>%
  left_join(namegends, by = c("first_name" = "name"))  # Match on 'first_name'

# Remove the 'first_name' column after the join
article.data <- article.data %>%
  select(-first_name)  # This removes the 'first_name' column

# Now, keep only the 'AF' column, the gender probability columns, and any other unmodified columns
article.data <- article.data %>%
  select(AF, prob.m, prob.w, everything())  # Keeps AF, prob.m, prob.w, and all other columns that weren't changed

# Now, save the final data frame as a CSV
write.csv(article.data, "citation_counter_output.csv", row.names = FALSE)