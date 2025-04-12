Hello!

This is a module to extract data for any set of papers you provide.
You may first run citation_counter.py. It first attempts to find the paper using the Elsevier API, and that failing, looks for the paper with the Semantic Scholar API. The data fields extractable is listed below, under the sub-heading 'Data-to-extract'.
If this is successful, you can then choose to run authors_gender.R This will act on the csv output of ciation_counter.py (named citation_counter_output.py), and output two additional columns, indicating the probabilities of the names of the first or last authors being male or female (as defined by assigned at birth)

Things you need to be able to use this:
- A csv file, containing columns that contain the title and DOI of all papers you want citation counts for. IMPORTANT: Ensure all columns are the same length and contain data. Errors will occur otherwise. 
- An API key for the Elsevier database. If you don't have one, you can get one here: https://dev.elsevier.com. You don't need one for semantic scholar.
- An API key for gender-api.com, if you want to run authors_gender.R. This can be acquired from gender-api.com

If you have these things, you can proceed with the following actions to use the module.

Creation of a virtual environment:
- Run the following: conda env create -f environment.yml. This creates a virtual environment with the dependencies of citation_counter.py and authors_gender.R. You must have conda installed for this to work
- Check that the R package 'parallel' is installed by running installed.packages() in an R terminal. If it is not, you will need to run install.packages("parallel"). Parallel is a default R package, so if you have R downloaded, you should have this package already.

Configuration file you need to edit:
- config.json is in this folder. Please open it and enter the following pieces of information:

    Essential:
    - csv_path: str. Contains the path to your csv file.
    - elsevier_apikey: str. Your Elsevier API key
    - gender-api.com_apikey: str. Your gender-api.com API key
    - colname_title: str and colname_DOI: str. The column names in your file that contain the title and DOIs for your papers, respectively.

    Data-to-extract:
    - extract_citation_count: bool. Change the value to "True" if desired, otherwise leave as ""
    - extract_first_last_author: bool. <as above>
    - extract_author_count: bool. <as above>
    - extract_journal: bool. <as above>

    Optional:
    - create_separate_csv: bool. Change the value to "True" if you would like a separate csv file containing the data extracted. Leaving this as "" means the csv columns this module outputs will be appended to a copy of the csv you provide.
    - output_citation_data_full: bool. Change the value to "True" if you would like both citation counts from Elsevier and Semantic Scholar to be recorded when available, instead of only searching Semantic Scholar when the paper cannot be located in Elsevier. This will slow down the execution time of the program, but allows you to compare the results of the two databases. A summarising figure is output as well. Otherwise, leave as "".


Once that's done, you should be able to run citation_coutner.py and then authors_gender.R as you wish!

Output notes:
The data csv is output to the working directory, with the name 'citation_counter_output.csv,' and if output_citation_data_full is "True", a png will be output called "citation_counter_visual_summary.png"
The open source module 'elsapy' is used to interface with the Elsevier API. This module outputs dump.json, a folder called 'logs' and a folder called 'data'. These can be deleted and do not affect the function of the elsapy module.
Once 'citation_counter_output.csv' is output to the working directory, authors_gender.R is able to be run. It will add the gender probability columns to the csv file.

This module was authored by Benjamin Varela. It uses open source modules 'elsapy' and 'semanticscholar'. Last edited 09/04/2025 (DD/MM/YYYY)