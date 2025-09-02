# README
## Function
The citation_counter module outputs a set of metadata from a set of journal articles provided by the user by interfacing with the [Elsevier](https://dev.elsevier.com), [Semantic Scholar](https://www.semanticscholar.org/product/api) and [Open Alex](https://docs.openalex.org/how-to-use-the-api/api-overview) APIs.

A csv file containing the set of journal papers to extract from, with each paper's title and DOI, is required.

## User setup
### Installations and virtual environment creation
If you have not yet, download the [Anaconda Distribution](https://www.anaconda.com/download) In the terminal, execute the following command:
 ```
 conda env create -f environment.yml
 ``` 
This creates a virtual environment with all the dependencies of citation_counter.py and authors_gender.R.

Then, activate the virtual environment by executing the command:
```conda actiavte citation_env``` 
This makes all the dependencies of citation_counter.py and authors_gender.R available to the current working directory.

Check that the R package 'parallel' is installed by executing in **an R terminal:** 
```installed.packages()``` 
If it is not, you will need to run ```install.packages("parallel")``` **in an R terminal**.

### Arguments entry into config.json
The user must input the following parameters, by editing the file 'config.json'

| Parameter | Explanation | Optional (Yes/No) |
| --------- | ----------- | ----------------- |
| csv_path  | relative to the working directory of the citation_counter.py file, the path to your csv containing the DOI and title of all journal articles. See [here](https://www.codecademy.com/resources/docs/general/file-paths) if unsure how to write a file path. | No |
| elsevier_apikey   | an API key for the Elsevier API. Obtain a new API key [here](https://dev.elsevier.com) | No |
| gender-api.com_apikey | an API key for gender-api.com. Obtain a new API key [here](gender-api.com). | Yes* (see: Notes) |
| colname_title | The exact column name that contains all the titles of your journal articles | No |
| colname_DOI | The exact column name that contains all of the DOIs of your journal articles | No |
| metadata_in_separate_csv | Whether the user wants metadata extracted to be output to a new csv (change value to "True"), or metadata columns to be appended to the csv file containing the information about each journal article (leave value as ""). | Yes |

### Notes
* No API key is required for semantic scholar.
* gender_apikey only needs to be specified if you wish to extract first and last author genders by running authors_gender.R.
* gender-api.com provides users with 100 free requests per month. Larger extractions will have to pay for additional credit.

## Data extracted
The following table tabulates the set metadata output against the APIs used. Entries in the table are the column names used in the output csvs that contain the corresponding metadata from the corresponding API.

*OpenAlex integration remains...*
