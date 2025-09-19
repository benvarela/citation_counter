# README
## Function
The citation_counter module outputs a set of metadata from a set of journal articles provided by the user by interfacing with the [Elsevier](https://dev.elsevier.com), [Semantic Scholar](https://www.semanticscholar.org/product/api), [Open Alex](https://docs.openalex.org/how-to-use-the-api/api-overview) and [Scimago](https://www.scimagojr.com) APIs.

## CSV file requirement (file input)
A csv file with the title and DOI of each journal article to extract metadata for is required.

## User setup
### Installations and virtual environment creation
If you have not yet, download the [Anaconda Distribution](https://www.anaconda.com/download). Then, in the terminal, execute the following commands. 
 ```
 conda env create -f environment.yml
 conda activate citation_env
 ``` 
They create a virtual environment with all the dependencies of citation_counter.py and authors_gender.R, and then activate this virtual environment. In sum, makes all the dependencies of citation_counter.py and authors_gender.R available to the current working directory.

Then, check that the R package 'parallel' is installed by executing the following command in **an R terminal** and reading through the list of installed packages
```
installed.packages()
``` 
If it is not, you will need to execute the following command in **an R terminal**
```
install.packages("parallel")
```

### Arguments entry into config.json
The user must input the following parameters, by creating a copy of 'config.example.json' and renaming it to 
'config.json'. The following parameters must be changed:

| Parameter | Explanation | Optional (Yes/No) |
| --------- | ----------- | ----------------- |
| ```csv_path```  | The relative path to your csv containing the DOI and title of all journal articles. See [here](https://www.codecademy.com/resources/docs/general/file-paths) if unsure how to write a file path. | No |
| ```elsevier_apikey```   | an API key for the Elsevier API. Obtain a new API key [here](https://dev.elsevier.com). | No |
| ```gender-api.com_apikey``` | an API key for gender-api.com. Obtain a new API key [here](gender-api.com). | Yes, if skip_gender is "", meaning gender extraction will proceed |
| ```colname_title``` | The exact column name that contains all the titles of your journal articles. | No |
| ```colname_DOI``` | The exact column name that contains all of the DOIs of your journal articles. | No |
| ```year``` | The current year | No | 
| ```retain_all_columns``` | Output csv called 'citation_counter_output.csv' will contain extracted metadata columns in addition to the columns in the input csv if value is set to "True". Otherwise, only extracted metadata will be in the output csv and the value of this parameter may be left as "". | Yes |
| ```no_cache``` | Caching of outputs from previous requests will be disabled if the value is set to "True". Caching stores these outputs so that successful requests in the past do not need to be repeated if the script is called again. Leaving the entry as "" will enable caching. | Yes |
| ```skip_gender``` | Inference of the genders of authors' first names not proceed if this parameter is set to "True". Otherwise, it will proceed if the value is left as "". | Yes |

### Notes
* No API key is required for semantic scholar.
* ```gender_apikey``` only needs to be specified if you wish to extract first and last author genders by running ```authors_gender.R```.
* Although an API key may be obtained for free for gender-api.com, only 100 requests per month are provided for free. Please see subsection Data extracted: ```authors_gender.R``` for more information on managing this.

## Running the program
In the terminal, execute the following command. Note that you must have previously activated the citation_env environment. Instructions for this are detailed under User setup / Installations and virtual environment creation.
```
python citation_counter.py
```
Updates will be printed to the terminal as the program runs. The results will be output in a csv called 'citation_counter_output.csv'.

## Data extracted: ```citation_counter.py```
The following table tabulates the set metadata output against the APIs used. Entries in the table are the column names used in the output csvs that contain the corresponding metadata from the corresponding API. 

| Metadata | Elsevier | Semantic Scholar | OpenAlex | Scimago |
| ------- | --------- | ---------------- | -------- | ------- |
| Citation count | ```citationcount_elsevier``` | ```citationcount_semanticscholar``` | ```citationcount_openalex``` | N/A |
| Works cited count | N/A | N/A | ```workscitedcount_openalex``` | N/A |
| FWCI | N/A | N/A | ```FWCI_openalex``` | N/A |
| Citation normalised percentage | N/A | N/A | ```citationnormalisedpercentile_openalex``` | N/A |
| Authors | N/A | ```authors_semanticscholar``` | ```authors_openalex``` | N/A |
| First and last author | N/A | N/A | ```firstlastauthor_openalex``` | N/A |
| Author count | N/A | ```authorcount_semanticscholar``` | ```authorcount_openalex``` | N/A |
| Author countries | N/A | N/A | ```authorcountries_openalex``` | N/A |
| Author institutions | N/A | N/A | ```institutions_openalex``` | N/A |
| Publishing location | ```journal_elsevier``` | ```journal_semanticscholar``` |```journal_openalex``` | N/A |
| Publishing location SJR | N/A | N/A | N/A | ```SJR_scimago``` |
| Publishing location H-index | N/A | N/A | N/A | ```Hindex_scimago``` |
| Publishing location Quartile | N/A | N/A | N/A | ```journalquartile_scimago``` |
| Published language | N/A | N/A | ```language_openalex``` | N/A |
| Grant institutions | N/A | N/A | ```grantinstitutions_openalex``` | N/A |
| Open access | N/A | N/A | ```openaccess_openalex``` | N/A |
| Retracted | N/A | N/A | ```retracted_openalex``` | N/A |

### Source code
Scimago data is accessed using a modified version of the following publically available GitHub https://github.com/Michael-E-Rose/SCImagoJournalRankIndicators. 

### Notes
* Author institutions is returned as a string ```"Institution1,type1,country1; Institution2..."```. Note the country and type institution is extractable in addition to the name of the institution
* Generally, all metadata fields that could hav mutiple entries are presented in comma separated strings: ```"Entry1, Entry2..."```.
* Author names are UTF-8 encoded, which is not the default encoding for .csv files. As a result, when opening the citation_counter_output.csv file, some author names with characters beyond ASCII style (the basic alphabet) will reder with unusual characters. Therefore, when programatically reading your csv file for data analysis, ensure the encoding is set to UTF-8.
* For more information on how OpenAlex extracts data on papers, access their detailed [technical documentation](https://docs.openalex.org/api-entities/works/work-object#grants) on 'Work' objects, the data representation of an extracted paper.

## Data extracted: ```authors_gender.R```
Using the data stored in ```firstlastauthor_openalex``` within citation_counter_output.csv, ```authors_gender.R``` adds four additional columns characterising the certainty that the first and last author's names are male or female names.

| Column | Description | Notes |
| ------ | ----------- | ----- |
| ```first_prob_m``` | Certainty that first author's first name is male, value in range 0 - 1 | ```first_prob_m``` and ```first_prob_f``` sum to 1 |
| ```first_prob_f``` | Certainty that first author's first name is female, value in range 0 - 1 | |
| ```last_prob_m``` | Certainty that last author's first name is male, value in range 0 - 1 | ```last_prob_m``` and ```last_prob_f``` sum to 1 |
| ```last_prob_f``` | Certainty that last author's first name is female, value in range 0 - 1 | |

### Method
A list of all unique first names in the ```firstlastauthor_openalex``` column of citation_counter_output.csv is created. All first names are searched within name_csvs/CommonNamesDatabase.csv, where names with known certainties are stored. If a name canot be found in name_csvs/CommonNamesDatabase.csv, then gender-api.com is queried with the first name in ASCII format. If a name cannot be assigned a gender with sufficient certainty, the associated probabilities, ```first_prob_m```/```first_prob_f``` or ```last_prob_m```/```last_prob_f``` are both assigned -1.

### Source code
This code is adapted from https://github.com/jdwor/gendercitation. 

### Notes
* gender-api.com allows users to create a API key for free, however, it is restricted to 100 free requests every month. For larger extractions, users may have to purchase additional credits.

## Missing data

### Handling of missing Title or DOI information for a paper
Where the title or DOI for a paper is not provided, data may no longer be able to be extracted from APIs. The below table specifies what information must be provided  for each API to be used to extract metadata. This criteria is independently assessed for each journal article. 
| API | Required information for use |
| --- | ---------------------------- |
| Elsevier | Title, DOI | 
| Semantic Scholar | DOI |
| OpenAlex | DOI |
The Scimago API is dependent on journal metadata being extracted from any of the above three APIs.

### Handling of missing metadata
Where metadata is missing, csv entries will be left blank, with the exception of Authors. Missing authors will be written as a string ```'X.,X.'```, as ```authors_gender.R``` recognises this as a missing entry. Furthermore, where author first names are missing, they are replaced witih the string ```'X.'```.

### Why was some metadata not extracted if I specified both the Title and DOI?
#### Elsevier
* Not all journal articles are available in the Elsevier API
* Titles with special characters can result in faulty searches of the Elsevier API database, even though the paper may be available 
* The Elsevier API can return imcomplete data in journal articles that are available

#### Semantic Scholar
* Not all journal articles are available in the Semantic Scholar API
* Some journal articles may exist in Semantic Scholar, but very rare errors may still be thrown preventing a very small subset of papers inaccessible through the API
* Some papers do not have any authors listed. [Example](https://www.semanticscholar.org/paper/EEG-Signal-Research-for-Identification-of-Epilepsy/140ee25d5ca5dbdf65dafc57f422f00366137bc8) (as of 03/09/25).
* Unfortunately, toward the later stages of development the performance of the Semantic Scholar API deteriorated significantly. Where a high proportion of papers could be extracted previously, Internal Server Errors are now being thrown, reducing metadata extraction efficiency from ~95% to ~10%. These changes were observed with identical code run at different times points throughout 2025, initially April-May, and later September.

#### OpenAlex
* Not all journal articles are available in the OpenAlex API
* Not all metadata field may be populated for every paper. For more information, review the [technical documentation](https://docs.openalex.org/api-entities/works/work-object#grants)

#### Scimago
* SJR values are only available for journals and book collections. Quartile values are dependent on an existing SJR value.
* Due to the method of look up, data is only found if the journal name extracted exactly matches the journal name stored in the Scimago database. Unfortunately, this is not guarunteed.