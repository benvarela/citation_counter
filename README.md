# README
## Function
The citation_counter module outputs a set of metadata from a set of journal articles provided by the user by interfacing with the [Elsevier](https://dev.elsevier.com), [Semantic Scholar](https://www.semanticscholar.org/product/api) and [Open Alex](https://docs.openalex.org/how-to-use-the-api/api-overview) APIs.

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
The user must input the following parameters, by editing the file 'config.json'

| Parameter | Explanation | Optional (Yes/No) |
| --------- | ----------- | ----------------- |
| ```csv_path```  | The relative path to your csv containing the DOI and title of all journal articles. See [here](https://www.codecademy.com/resources/docs/general/file-paths) if unsure how to write a file path. | No |
| ```elsevier_apikey```   | an API key for the Elsevier API. Obtain a new API key [here](https://dev.elsevier.com). | No |
| ```gender-api.com_apikey``` | an API key for gender-api.com. Obtain a new API key [here](gender-api.com). | Yes* (see: Notes) |
| ```colname_title``` | The exact column name that contains all the titles of your journal articles. | No |
| ```colname_DOI``` | The exact column name that contains all of the DOIs of your journal articles. | No |
| ```retain_all_columns``` | Output csv called 'citation_counter_output.csv' will contain extracted metadata columns in addition to the columns in the input csv if value is set to "True". Otherwise, only extracted metadata will be in the output csv and the value of this parameter may be left as "". | Yes |

### Notes
* No API key is required for semantic scholar.
* ```gender_apikey``` only needs to be specified if you wish to extract first and last author genders by running authors_gender.R.
* gender-api.com provides users with 100 free requests per month. Larger extractions will have to pay for additional credit.

## Running the program
In the terminal, execute the following command. Note that you must have previously activated the citation_env environment. Instructions for this are detailed under User setup / Intallations and virtual environment creation.
```
python citation_counter.py
```
Updates will be printed to the terminal as the program runs. The results will be output in a csv called 'citation_counter_output.csv'.

## Data extracted
The following table tabulates the set metadata output against the APIs used. Entries in the table are the column names used in the output csvs that contain the corresponding metadata from the corresponding API. 

| Metadata | Elsevier | Semantic Scholar | OpenAlex |
| ------- | -------- | ---------------- | -------- |
| Citation count | ```citationcount_elsevier``` | ```citationcount_semanticscholar``` | ```citationcount_openalex``` |
| Works cited count | N/A | N/A | ```workscitedcount_openalex``` |
| FWCI | N/A | N/A | ```FWCI_openalex``` |
| Citation normalised percentage | N/A | N/A | ```citationnormalisedpercentile_openalex``` |
| Authors | N/A | ```authors_semanticscholar``` | ```authors_openalex``` |
| Author count | N/A | ```authorcount_semanticscholar``` | ```authorcount_openalex``` |
| Author countries | N/A | N/A | ```authorcountries_openalex``` |
| Author institutions | N/A | N/A | ```institutions_openalex``` |
| Publishing location | ```journal_elsevier``` | ```journal_semanticscholar``` | ```journal_openalex``` |
| Published language | N/A | N/A | ```language_openalex``` |
| Grant institutions | N/A | N/A | ```grantinstitutions_openalex``` |
| Open access | N/A | N/A | ```openaccess_openalex``` |
| Retracted | N/A | N/A | ```retracted_openalex``` |

### Notes
* Author institutions is returned as a string ```"Institution1,type1,country1; Institution2..."```. Note the country and type institution is extractable in addition to the name of the institution
* Generally, all metadata fields that could hav mutiple entries are presented in comma separated strings: ```"Entry1, Entry2..."```.
* For more information on how OpenAlex extracts data on papers, access their detailed [technical documentation](https://docs.openalex.org/api-entities/works/work-object#grants) on 'Work' objects, the data representation of an extracted paper.


## Missing data

### Handling of missing Title or DOI information for a paper
Where the title or DOI for a paper is not provided, data may no longer be able to be extracted from APIs. The below table specifies what information must be provided  for each API to be used to extract metadata. This criteria is independently assessed for each journal article. 
| API | Required information for use |
| --- | ---------------------------- |
| Elsevier | Title, DOI | 
| Semantic Scholar | DOI |
| OpenAlex | DOI |

### Handling of missing metadata
Where metadata is missing, csv entries will be left blank, with the exception of Authors. Missing authors will be written as a string ```'X.,X.'```, as this format interfaces well with gender-api.com. Furthermore, where author first names are missing, they are replaced witih the string ```'X.'```.

### Why was some metadata not extracted if I specified both the Title and DOI?
#### Elsevier
* Not all journal articles are available in the Elsevier API
* Titles with special characters can result in faulty searches of the Elsevier API database, even though the paper may be available 
* The Elsevier API can return imcomplete data in journal articles that are available

#### Semantic Scholar
* Not all journal articles are available in the Semantic Scholar API
* Some journal articles may exist in Semantic Scholar, but very rare errors may still be thrown preventing a very small subset of papers inaccessible through the API
* Some papers do not have any authors listed. [Example](https://www.semanticscholar.org/paper/EEG-Signal-Research-for-Identification-of-Epilepsy/140ee25d5ca5dbdf65dafc57f422f00366137bc8) (as of 03/09/25).

#### OpenAlex
* Not all journal articles are available in the OpenAlex API
* Not all metadata field may be populated for every paper. For more information, review the [technical documentation](https://docs.openalex.org/api-entities/works/work-object#grants)