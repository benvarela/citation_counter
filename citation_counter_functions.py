'''
Functions required for citation_counter.py. See function descriptor for information on function, inputs and outputs.
'''

#imports
import json
from typing import Optional
import httpx
import subprocess
import shutil
import pandas as pd
import time
from io import StringIO
import requests
from pathlib import Path
from elsapy.elsclient import ElsClient
from elsapy.elssearch import ElsSearch
from semanticscholar import SemanticScholar
import pyalex as pa
from semanticscholar.Paper import Paper
from semanticscholar.SemanticScholarException import ObjectNotFoundException
from results_cache import ResultsCache

## Functions used within main functions, called in citation_counter.py

def checkjsonbool(v: str, paramter: str) -> None:
    """
    Validate that a string value corresponds to an expected JSON-style boolean.

    This function checks whether the provided string `v` is either an empty
    string ("") or the literal "True". If the value does not match either of
    these options, a ValueError is raised.

    Parameters
    ----------
    v : str
        The string value to validate.
    paramter : str
        The name of the parameter being validated. Used in the error
        message if validation fails.

    Raises
    ------
    ValueError
        If `v` is not equal to "" or "True".
    """
    if v not in ("", "True"):
        raise ValueError(f"Invalid value for '{str}': {v!r}. Expected '' or 'True'.")

def print_progress(i: int, proportion: float, total: int, database: str, c_hits: Optional[int] = None) -> float:
    """
    Print progress updates during data extraction.

    Parameters
    ----------
    i : int
        Index of the current paper.
    proportion : float
        Current completion proportion (increments in steps of 0.1).
    total : int
        Total number of papers.
    database : str
        Name of the database being queried (e.g., "Elsevier" or "Semantic Scholar").
    c_hits : int or None
        Number of papers hit in the cache (Optional).

    Returns
    -------
    float
        Updated proportion value.
    """
    if round((i+1)/total, 8) >= round(proportion, 8):
        if round(proportion, 8) == 1:
            end_char = '!\n'
        else:
            end_char = '...'
        if c_hits:
            print("Completed {}% ({}/{} from cache) with {}{}".format(round(proportion*100, 3), str(c_hits), str(i),
                                                                  database, end_char))
        else:
            print("Completed {}% with {}{}".format(round(proportion * 100, 3), database, end_char))
        proportion += 0.1
    
    return proportion

def instantiateclient_elsevier(elsevier_apikey: str) -> ElsClient:
    """
    Instantiate an `ElsClient` object for the Elsevier API.

    Parameters
    ----------
    elsevier_apikey : str
        User's Elsevier API key.

    Returns
    -------
    ElsClient
        Client object for interacting with the Elsevier API.

    Raises
    ------
    Exception
        If a connection cannot be established using the provided API key.
    """
    #Instantiate the client object and test it
    client = ElsClient(elsevier_apikey)
    try:
        doc_srch = ElsSearch("TITLE({})".format("Tensor-based Uncorrelated Multilinear Discriminant Analysis for Epileptic Seizure Prediction"), 'scopus')
        doc_srch.execute(client)
    except Exception as e:
        print("ERROR: There was a problem setting up a connection with your API key. Please check it's correct. More information:\n")
        raise
    
    #Communicate success to the user
    print("** Connection established succesfully using the provided elsevier API key **\n")

    return client    

def cleantitle_elsevier(string, chars_to_remove):
    """
    Remove specified characters from a string.

    Parentheses are removed before querying Elsevier API, can cause bad requests

    Parameters
    ----------
    string : str
        The input string (e.g., paper title) to clean.
    chars_to_remove : str
        String containing all characters to remove from `string`.

    Returns
    -------
    str
        The cleaned string with all specified characters removed.
    """
    return ''.join(char for char in string if char not in chars_to_remove)

def reformatauthors_semanticscholar(authors: list) -> str:
    """
    Reformat author names into "[Last],[First];[Last],[First]..." string.

    Parameters
    ----------
    authors : list of str
        Each string is an author's name in format "[First] [Last]".

    Returns
    -------
    str
        Semicolon-delimited string of names in format "[Last],[First];...".

    Notes
    -----
    If a name is missing or malformed, placeholder "X." is used for the first name or last name as appropriate.
    """
    ## Instantiate and fill out a list of author first and last names
    formatted = []
    for author in authors:
        # Check whether author name existed, replace with 'X.' if it didn't to interface well with gender-api.com assessment of names
        names = author.split()
        try: 
            first = names[0] 
        except IndexError: 
            first = 'X.' 
        try: 
            last = names[-1]
            # If only one name was listed, then this was the last name. The first name needs to be re-written as X.
            if last == first:
                first = 'X.'
        except IndexError: 
            last = 'X.'
        formatted.append(f"{last},{first}")
    
    ## Join list of author names with semicolons and return
    return "; ".join(formatted)

def getauthorpapers_semanticscholar(sch, author_id: str, initial_limit: int = 1000, retries: int = 3,
                                    cache: Optional[ResultsCache] = None):
    """
    Safely fetch author papers from Semantic Scholar API with retries
    and progressively smaller limits if the request times out.

    Parameters
    ----------
    sch : SemanticScholar
        An instance of the SemanticScholar client.
    author_id : str
        Semantic Scholar authorId to fetch papers for.
    initial_limit : int, optional
        Starting number of papers to request (default 1000).
    retries : int, optional
        Number of retry attempts before giving up (default 3).
    cache : ResultsCache, optional
        ResultsCache instance to store the results of requests made.

    Returns
    -------
    list or None
        List of author papers if successful, or None if request fails.
    """
    if cache is not None:
        if cache.has(author_id):
            return cache.get(author_id)
    limit = initial_limit
    for attempt in range(retries):
        try:
            result = sch.get_author_papers(author_id, limit=limit)
            cache.set(author_id, result)
            return result
        except Exception as e:
            limit = max(100, limit // 2)
    return None

def reformatauthor_openalex(author: str) -> str:
    """
    Clean and reformat an author name into "Last,First" format.

    Parameters
    ----------
    author : str
        Author name as returned by OpenAlex (e.g., "First Last",
        "First Middle Last", or sometimes just a single token).

    Returns
    -------
    str
        Reformatted author name in "Last,First" format.
        - Middle names are ignored.
        - If only one token is provided, it is treated as the last name
          and the first name is replaced with "X.".
        - If the input is empty, returns "X.,X.".
    """
    tokens = author.split()

    if not tokens:  # completely empty string
        return "X.,X."

    if len(tokens) == 1:
        return f"{tokens[0]},X."

    first, last = tokens[0], tokens[-1]
    return f"{last},{first}"

def reformatjournal_scimago(journal: str) -> str:
    """
    Remove all punctuation andn spaces from a journal name and return it in lower case.

    Standardisation helps with rigid look up in scimago pd.Dataframe.

    Parameters
    ----------
    journal : str
        Input string that may contain punctuation, commas, or mixed case characters.

    Returns
    -------
    str
        A processed version of the input string with all punctuation removed 
        and all letters converted to lower case.
    """
    # Return None if None was passed
    if journal is None:
        return None
    # Else, remove all punctuation and convert to lower case
    else:
        clean = str()
        for letter in journal:
            if letter.isalnum():
                clean += letter
        return clean.lower()

def manageNan_scimago(value: pd.Series):
    """
    Convert a pandas Series containing a single value to a Python scalar, replacing NaN with None.
    Includes handling for missing or duplicate journal entries.

    Parameters
    ----------
    value : pd.Series
        A pandas Series expected to contain exactly one element.

    Returns
    -------
    result : object
        The scalar value contained in the Series, or None if the value is NaN.
    """
    # Handling for missing journal, or duplicate journal, and extract as scalar
    if value.empty:
        return None
    if len(value) > 1:
        value = value.iloc[0]
    else:
        value = value.item()

    # Return None or scalar as appropriate
    return None if (pd.isna(value) or value == '-') else value

def addjournalinfo_scimago(df: pd.DataFrame, data_dict: dict, i: int, journals: dict, journal: str) -> dict:
    """
    Add Scimago journal metrics (SJR, H-index, and quartile) to a data dictionary entry.

    This function looks up a journal in a DataFrame containing Scimago metrics, extracts
    the SJR, H-Index and Quartile, and stores the information in a dictionary entry corresponding to the
    given index.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing Scimago journal data with columns 'Title', 'SJR', 'h-index', and 'field'.
    data_dict : dict
        Dictionary of article or journal entries where metrics will be added.
    i : int
        Index in `data_dict` corresponding to the entry to update.
    journals : dict
        Dictionary mapping input journal names to the canonical names in `df`.
    journal : str
        Name of the journal to look up.

    Returns
    -------
    data_dict : dict
        The updated dictionary with added fields:
        - 'SJR_openalex': SJR value or None
        - 'Hindex_openalex': H-index value or None
        - 'journalquartile_scimago': Quartile string ('Q1'-'Q4') if SJR exists

    Notes
    -----
    - If no SJR or H-index is found for the journal, the corresponding dictionary entries
      will be None.
    - Quartiles are determined according to the SJR percentile boundaries of the journal's field.
    - Relies on `manageNan_scimago` to safely handle missing values in the DataFrame.
    """
    # Lookup name of the journal, given a match was found
    dfjournalname = journals[journal]

    ## Extraction of the SJR and H-index if a journal name match is found
    data_dict[i]['SJR_scimago'] = manageNan_scimago(df[df['Title'] == dfjournalname]['SJR'])
    data_dict[i]['Hindex_scimago'] = manageNan_scimago(df[df['Title'] == dfjournalname]['H index'])
    data_dict[i]['journalquartile_scimago'] = manageNan_scimago(df[df['Title'] == dfjournalname]['SJR Best Quartile'])

    return data_dict

def collectyear_scimago(year):
    """
    Fetch SCImago Journal Rank (SJR) data for a specific year.

    Parameters
    ----------
    year : int
        Year for which SCImago Journal Rank data is requested.

    Returns
    -------
    pandas.DataFrame or None
        DataFrame containing columns:
        - 'Title' : str
            Journal title.
        - 'SJR' : float
            SCImago Journal Rank value.
        - 'SJR Best Quartile' : str
            Best quartile classification (Q1–Q4).
        - 'H index' : int
            Journal's H-index.
        Returns None if data could not be downloaded or parsed.
    """
    # Access the csv data from a particular year
    url = f"https://www.scimagojr.com/journalrank.php?year={year}&out=xls"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to download data for year {year}: {e}")
        return None

    # Read CSV from response, take the relevant columns, clean SJR 
    df = pd.read_csv(StringIO(response.text), delimiter=';', dtype={5: str, 'Issn': str, 8: str})
    df = df[['Title', "SJR", "SJR Best Quartile", "H index"]]
    df['SJR'] = df['SJR'].str.replace(',', '.').astype('float')

    return df

def collectall_scimago(end_year, start_year = 1999, delay=1) -> pd.DataFrame:
    """
    Fetch and aggregate SCImago Journal Rank (SJR) data across multiple years.

    Parameters
    ----------
    end_year : int
        The latest year to include in the dataset (inclusive).
    start_year : int, optional
        The earliest year to include in the dataset (exclusive).
        Default is 1999.
    delay : int or float, optional
        Delay in seconds between successive requests to avoid overloading the server.
        Default is 1.

    Returns
    -------
    pandas.DataFrame
        Concatenated DataFrame of SJR data for all years in the specified range.
        If a journal appears in multiple years, only the most recent entry is kept.
        Columns include:
        - 'Title' : str
        - 'SJR' : float
        - 'SJR Best Quartile' : str
        - 'H index' : int
    """
    years = range(end_year, start_year, -1)
    all_scimago = pd.DataFrame(columns=["Title", "SJR", "SJR Best Quartile", "H index"])

    for year in years:
        # Add yearly data to the dictionary, only adding if Title of source has not yet been included in the dictionary
        temp = collectyear_scimago(year)
        temp = temp[~temp['Title'].isin(all_scimago['Title'])]
        if all_scimago.empty:
            all_scimago = temp
        else:
            all_scimago = pd.concat([all_scimago, temp], ignore_index=True)

        # Pause
        time.sleep(delay)

    return all_scimago

## Main functions

def readjson() -> dict:
    """
    Read configuration values from `config.json`.

    Returns
    -------
    dict
        Dictionary with the following structure::

            {
                "csv_path": str
                    Path to the CSV file(s).
                "elsevier_apikey": str
                    Elsevier API key.
                "colname_title": str
                    Column name containing titles.
                "colname_DOI": str
                    Column name containing DOIs.
                "year": int
                    The current year
                "retain_all_columns": str
                    Either "" or "True".
                "no_cache": str
                    Either "" or "True".
                "skip_gender": str
                    Either "" or "True".
            }

    Raises
    ------
    FileNotFoundError
        If `config.json` does not exist.
    ValueError
        If `retain_all_columns` has an invalid value.
    """

    #Open the json file
    try:
        with open("config.json") as con_file:
            con = json.load(con_file)
    except Exception as e:
        print("ERROR: Make sure there is a file name config.json in this folder. More information:\n")
        raise

    # Check appropriate input for boolean inputs, and the numeric input of year
    for bool_parameter in ['retain_all_columns', 'no_cache', 'skip_gender']:
        checkjsonbool(con[bool_parameter], bool_parameter)
    if not con["year"].isnumeric():
        raise ValueError(f"Invalid value for 'year': {con['year']}. Expected a number.")
    else:
        con['year'] = int(con['year'])

    # Extract values and store in dictionary to return. Should have really used a function and loop for these.
    data = {}
    for key in con.keys():
        data[key] = con[key]

    # User communication
    print("\n** Inputs read! Your inputs are: **")
    for key in data.keys():
        print(f'{key}: {data[key]}')
    print("")

    return data

def readcsv(csv_path: str, colname_title: str, colname_DOI: str) -> tuple[dict, pd.DataFrame]:
    """
    Read a CSV file and extract metadata, DOIs, and titles.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file.
    colname_title : str
        Column name containing paper titles.
    colname_DOI : str
        Column name containing DOIs.

    Returns
    -------
    tuple of (dict, pandas.DataFrame)
        - dict : Dictionary containing DOI, title, and metadata fields for each paper.
        - DataFrame : The full user-provided CSV loaded into a pandas DataFrame.

    Raises
    ------
    Exception
        If the CSV file cannot be read or the specified columns are not found.
    """
    ## Extract pd.Series object of the Titles and DOIs of all papers in the user provided csv
    try:
        csv_file = Path(csv_path)

        # Try with default encoding first
        encode = "unicode_escape"
        full_dataframe = pd.read_csv(csv_file, encoding=encode)

        # Handle UTF-8 BOM in first column
        if full_dataframe.columns[0] == "ï»¿":
            encode = "utf-8"
            print("Found a file with UTF-8 BOM. Reloading CSV with UTF-8 encoding.")
            full_dataframe = pd.read_csv(csv_file, encoding=encode)

        # Handle case where headers are not in first row
        header_row = 1
        if colname_DOI not in full_dataframe.columns or colname_title not in full_dataframe.columns:
            print("Headers not found in first row, retrying with skiprows=1.")
            full_dataframe = pd.read_csv(csv_file, encoding=encode, skiprows=1)
            header_row = 2
            
        DOIs = full_dataframe[colname_DOI]
        Titles = full_dataframe[colname_title]
    except Exception as e:
        print("ERROR: Something went wrong when interacting with your csv. Please ensure your csv path is correct, and that you've correctly entered your title and DOI column headers. These headers must also be in the first or second row of your csv. Here's more information to help figure out what went wrong:\n")
        raise

    ## Communcate to user successful extraction
    print("** Successfully read Title and DOI information from your provided CSV **\n")

    ## Reformat the pd.Series object to be contained within a dictionary
    # Convert missing values to empty strings
    DOIs = DOIs.fillna("")
    Titles = Titles.fillna("")

    data_dict = {}
    first_warning = True
    for i in range(len(DOIs)):
        # Check whether this row has DOI and title information. Communicate to user if it doesn't
        if DOIs[i] == "" or Titles[i] == "":
            if first_warning:
                print("WARNING: rows detected that do not contain both DOI and Title data. Please refer to README.md to understand how this will limit program output.")
                first_warning = False
            print(f"In row {i+header_row+1} data was missing. DOI: {DOIs[i]}, Title: {Titles[i]}")

        data_dict[i] = {"DOI": DOIs[i],
                        "Title": Titles[i],
                        "citationcount_elsevier": None, 
                        "citationcount_semanticscholar": None, 
                        "citationcount_openalex": None,
                        "authors_semanticscholar": None,                # Authors are listed in string format 'LastName,Firstname; LastName...'
                        "authors_openalex": None,                       # ^
                        "authorcount_semanticscholar": None,
                        "authorcount_openalex": None,
                        "firstlastauthor_openalex": None,
                        "journal_elsevier": None,
                        "journal_semanticscholar": None,
                        "journal_openalex": None,
                        "institutions_openalex": None,                  # All unique institutions listed in string format 'Institution1,type1,country1; Institution2...'
                        "authorcountries_openalex": None,               # All unique countries listed in string format 'Country1, Country2...'
                        "openaccess_openalex": None,
                        "FWCI_openalex": None,
                        "citationnormalisedpercentile_openalex": None,
                        "workscitedcount_openalex": None,
                        "retracted_openalex": None,
                        "SJR_scimago": None,
                        "Hindex_scimago": None,
                        "journalquartile_scimago": None
                       }
        
    return data_dict, full_dataframe

def get_elsevier_data(elsevier_apikey: str, data_dict: dict, no_cache: bool = False) -> dict:
    """
    Retrieve citation counts and journal data from the Elsevier API.

    Parameters
    ----------
    elsevier_apikey : str
        Elsevier API key.
    data_dict : dict
        Dictionary containing DOI and title metadata.

    Returns
    -------
    dict
        Updated dictionary with citation counts and journal data added.
    """
    #Instantiate the elsevier client and cache
    els_client = instantiateclient_elsevier(elsevier_apikey)
    cache = ResultsCache("elsevier", cache_disabled=no_cache)
    c_hits = 0

    #Initialisation of variables for the progress statements to be printed to terminal, using print_progress()
    total = len(data_dict)
    proportion = 0.1

    #Message that the elsevier extraction is beginning
    print("** Extraction of data with Elsevier API is now beginning **")
    print("A message will be printed below every time a 10% portion of the total papers to analyse is completed.")

    for i in range(len(data_dict)):
        ## Extract title and DOI. Both must exist for the following code to work. Skip this loop iteration if either was not in the user csv
        doi = data_dict[i]["DOI"]
        title = data_dict[i]["Title"]
        if doi == "" or title == "":
            proportion = print_progress(i, proportion, total, 'Elsevier', c_hits)
            continue

        ## Check cache first
        if cache.has(doi):
            search = cache.get(doi)
            c_hits += 1
        else:
            # Start new search
            ## Using the title and DOI informatino to extract citation count and journal
            title = cleantitle_elsevier(title, '()')

            #Search for a paper with a title check by ensuring the DOI matches. When errors arise, papers are skipped (due to special characters in the title).
            search = ElsSearch("TITLE({})".format(title), 'scopus')
            try:
                search.execute(els_client)
            except:
                proportion = print_progress(i, proportion, total, 'Elsevier', c_hits)
                continue

        #Cache the search object after successful execution
        cache.set(doi, search)

        #Use ElsSearch to extract citation count and journal. Author information can't be found reliably, due to how poor AbsDoc and Fulldoc perform.
        for result in search.results:
            if 'prism:doi' in result.keys():
                if result['prism:doi'] == doi:
                    #Get citation count
                    data_dict[i]['citationcount_elsevier'] = int(result.get('citedby-count')) if result.get('citedby-count') else None
                    #Get journal
                    if 'prism:publicationName' in result.keys():
                        data_dict[i]['journal_elsevier'] = result.get('prism:publicationName')

        proportion = print_progress(i, proportion, total, 'Elsevier', c_hits)

    cache.save_to_disk()
    return data_dict

def get_semanticscholar_data(data_dict: dict, no_cache: bool = False) -> dict:
    """
    Retrieve citation counts, journal information, and author metadata from the Semantic Scholar API.

    Parameters
    ----------
    data_dict : dict
        Dictionary containing DOI, title, and existing metadata.

    Returns
    -------
    dict
        Updated dictionary with semantic scholar citation counts, journal, and author data added.
    """
    #Message that the semnatic scholar extraction is beginning
    print("** Extraction of data with Semantic Scholar API is now beginning **")
    print("A message will be printed below every time a 10% portion of the total papers to analyse is completed.")
    print("Rows previously identified with a warning, because they did not contain one or both entries of DOI and/or Title for a paper will be skipped again.")

    # Recent version of SemanticScholar doesn't like the publicationVenue arg or references so skip them
    backup_fields_to_query = Paper.FIELDS.copy()
    fields_to_remove = ['references',
        'references.abstract',
        'references.authors',
        'references.citationCount',
        'references.citationStyles',
        'references.corpusId',
        'references.externalIds',
        'references.fieldsOfStudy',
        'references.influentialCitationCount',
        'references.isOpenAccess',
        'references.journal',
        'references.openAccessPdf',
        'references.paperId',
        'references.publicationDate',
        'references.publicationTypes',
        'references.publicationVenue',
        'references.referenceCount',
        'references.s2FieldsOfStudy',
        'references.title',
        'references.url',
        'references.venue',
        'references.year']
    for field in fields_to_remove:
        backup_fields_to_query.remove(field)

    #Instantiate the SemanticScholar object and cache
    sch = SemanticScholar()
    cache = ResultsCache("semanticscholar", cache_disabled=no_cache)
    cache_authors = ResultsCache("semanticscholar_authors", cache_disabled=no_cache)
    c_hits = 0

    #Variables for the progress statements to be printed to terminal, using print_progress()
    total = len(data_dict)
    proportion = 0.1

    for i in range(len(data_dict)):
        ## Check DOI, skip iteration if not present.
        doi = data_dict[i]['DOI']
        if doi == "":
            proportion = print_progress(i, proportion, total, 'Semantic Scholar', c_hits)
            continue

        ## Check cache first
        if cache.has(doi):
            paper_result = cache.get(doi)
            c_hits += 1
        else:
            ## Extraction of data
            #Extract paper result with semantic scholar, skip if an error is thrown when retrieving it
            try:
                paper_result = sch.get_paper(doi)
            except Exception as e:
                try:
                    # Tries to query without missing fields
                    paper_result = sch.get_paper(doi, fields=backup_fields_to_query)
                except ObjectNotFoundException as e:
                    proportion = print_progress(i, proportion, total, 'Semantic Scholar', c_hits)
                    continue
                except httpx.ReadTimeout as e:
                    proportion = print_progress(i, proportion, total, 'Semantic Scholar', c_hits)
                    print("WARNING: Semantic Scholar API request timed out. Check your internet connection.")
                    continue
                except Exception as e:
                    proportion = print_progress(i, proportion, total, 'Semantic Scholar', c_hits)
                    import traceback
                    traceback.print_exc()
                    continue
            
            #Cache the paper_result after successful retrieval
            cache.set(doi, paper_result)
        
        #Extract citation count. Method is looking at the papers author1 has published, and matching according to title. Take max citation count. JUSTIFICATION FOR THIS PROCESS: This is more complicated than the semanticscholar documentation may suggest. Semantic scholar can give two copies of the same paper, with different citation counts, eg: 'Local Transformed Features for Epileptic Seizure Detection in EEG Signal.' Type that into https://www.semanticscholar.org and see what you get. This is managed by taking the first author, seeing all the papers they're authored on, and then taking the one with a matching title and greatest citation count.        
        citation_count = None
        authors = paper_result['authors']
        #Some papers, erroneously, may not have a listed author in Semantic Scholar, eg: https://www.semanticscholar.org/paper/EEG-Signal-Research-for-Identification-of-Epilepsy/140ee25d5ca5dbdf65dafc57f422f00366137bc8
        #If there are authors, check through author1 papers to manage paper duplication problems leading to erroneous citation counts:
        if authors:
            author1_papers = getauthorpapers_semanticscholar(sch, authors[0]['authorId'], cache=cache_authors)
            for author1_paper in author1_papers.raw_data:
                if 'DOI' in author1_paper['externalIds'].keys():                                # A couple things to note here. Because sometimes the titles extracted have strange characters, I'm only checking to see if the DOI.lower() matches. .lower() is needed because sometimes pre-prints have a letter of lower case and they get chosen instead of the peer-reviewed published paper, which has the citations.
                    if author1_paper['externalIds']['DOI'].lower() == doi.lower():
                        if citation_count != None:
                            citation_count = max(citation_count, author1_paper['citationCount'])
                        else:
                            citation_count = author1_paper['citationCount']
        #If there aren't any authors, assume no paper duplication problems:
        else:
            citation_count = paper_result['citationCount']
        #Save the citation count
        data_dict[i]['citationcount_semanticscholar'] = citation_count
    
        #Extract journal information
        if paper_result['venue']:
            data_dict[i]['journal_semanticscholar'] = paper_result['venue']
        
        #Extract author information, including authors and author count
        if paper_result['authors']:
            authors = paper_result['authors']
            authors = [a['name'] for a in paper_result['authors']]
            num_authors = len(authors)
            data_dict[i]['authorcount_semanticscholar'] = num_authors
            authors = reformatauthors_semanticscholar(authors)
            data_dict[i]['authors_semanticscholar'] = authors
        else:
            data_dict[i]['authors_semanticscholar'] = 'X.,X.'

        #Progress statements to be printed to the terminal
        proportion = print_progress(i, proportion, total, 'Semantic Scholar', c_hits)

    cache.save_to_disk()
    cache_authors.save_to_disk()
    return data_dict

def get_openalex_data(data_dict: dict, no_cache: bool = False) -> dict:
    """
    Extracts citation, authorship, and publication metadata for each paper in
    the dataset using the OpenAlex API.

    Parameters
    ----------
    data_dict : dict
        Dictionary of paper metadata. Must include at least 'DOI' for each paper.

    Returns
    -------
    dict
        Updated dictionary containing additional OpenAlex-derived metadata.
    """
    # Initialisation of variables for progress updates and cache
    cache = ResultsCache("openalex", cache_disabled=no_cache)
    c_hits = 0
    total = len(data_dict)
    proportion = 0.1

    print("** Extraction of data with OpenAlex API is now beginning **")
    print("A message will be printed below every time a 10% portion of the "
          "total papers to analyse is completed.")

    # Iterate over all papers
    for i in range(len(data_dict)):
        DOI = data_dict[i]["DOI"]

        # Skip paper if no DOI stored
        if DOI == "":
            proportion = print_progress(i, proportion, total, 'OpenAlex', c_hits)
            continue

        ## Check cache first
        if cache.has(DOI):
            w = cache.get(DOI)
            c_hits += 1
        else:
            # Attempt to query OpenAlex by DOI
            try:
                DOI_link = 'https://doi.org/' + DOI
                w = pa.Works()[DOI_link]
                # Cache the successful result
                cache.set(DOI, w)
            except Exception:
                data_dict[i]['authors_openalex'] = "X.,X."
                data_dict[i]["firstlastauthor_openalex"] = "X.,X.; X.,X."
                proportion = print_progress(i, proportion, total, 'OpenAlex', c_hits)
                continue

        ## Author associated data
        authors = []
        first = 'X.,X.'
        last = 'X.,X.'
        countries = set()
        institutions = set()

        for authorship in w.get('authorships', []):
            # Author name
            name = reformatauthor_openalex(
                (authorship.get('author') or {})
                .get('display_name') or "X.,X."
            )
            authors.append(name)

            # First and last authors
            position = authorship.get('author_position')
            if position == 'first':
                first = name
            elif position == 'last':
                last = name

            # Countries
            for country in authorship.get('countries', []) or []:
                countries.add(country)

            # Institutions
            for institution in authorship.get('institutions', []) or []:
                ins = f"{institution.get('display_name')},{institution.get('type')},{institution.get('country_code')}"
                institutions.add(ins)

        data_dict[i]["authorcountries_openalex"] = ", ".join(list(countries)) if countries else None
        data_dict[i]["institutions_openalex"] = "; ".join(list(institutions)) if institutions else None
        data_dict[i]["authorcount_openalex"] = len(authors) if authors else None
        data_dict[i]["authors_openalex"] = "; ".join(authors) if authors else None
        data_dict[i]["firstlastauthor_openalex"] = first + "; " + last

        ## Citing information
        data_dict[i]["citationcount_openalex"] = w.get('cited_by_count')
        data_dict[i]["workscitedcount_openalex"] = len(w.get('referenced_works') or [])
        data_dict[i]["FWCI_openalex"] = w.get('fwci')
        citation_normalised_percentile = w.get('citation_normalized_percentile') or {}
        data_dict[i]["citationnormalisedpercentile_openalex"] = citation_normalised_percentile.get('value')

        ## Publishing information
        primary_location = w.get('primary_location') or {}
        source = primary_location.get('source') or {}
        data_dict[i]["journal_openalex"] = source.get('display_name')
        openaccess = w.get('open_access') or {}
        data_dict[i]["openaccess_openalex"] = openaccess.get('is_oa')
        data_dict[i]["retracted_openalex"] = w.get('is_retracted')

        proportion = print_progress(i, proportion, total, 'OpenAlex', c_hits)

    cache.save_to_disk()
    return data_dict

def get_scimago_data(data_dict: dict, year: int, no_cache: bool = False) -> dict:
    """
    Retrieve and enrich journal metadata from the SCImago Journal Rank (SJR) database.

    This function downloads the most recent SCImago statistics, subsets them for the 
    specified year minus one, computes quartile thresholds for each field, and attempts 
    to enrich each journal entry in `data_dict` with its SJR, h-index, and quartile. 
    Journals are matched using cleaned versions of their names across multiple sources 
    (Elsevier, Semantic Scholar, OpenAlex).

    Parameters
    ----------
    data_dict : dict
        Dictionary of extracted metadata for a set of journals. Each entry must include
        journal names from at least one source under keys such as 
        ``'journal_elsevier'``, ``'journal_semanticscholar'``, or ``'journal_openalex'``.
    year : int
        The reference year for filtering SCImago data. The function uses statistics from
        ``year - 1`` (e.g., if year=2024, the function loads 2023 data).
    no_cache : bool, optional
        If True, disables use of the local cache and forces retrieval of fresh data.
        Default is False.

    Returns
    -------
    dict
        Updated `data_dict` where available journals have been enriched with:
        
        - ``SJR_openalex`` : float or None
            SCImago Journal Rank (SJR) score.
        - ``Hindex_openalex`` : float or None
            Journal h-index.
        - ``journalquartile_scimago`` : str or None
            Quartile classification ('Q1', 'Q2', 'Q3', 'Q4') based on field-specific 
            percentile thresholds.
    """
    # Initialisation of variables for progress updates and cache
    #cache = ResultsCache("openalex", cache_disabled=no_cache)
    #c_hits = 0
    total = len(data_dict)
    proportion = 0.1

    ## User communication
    print("** Extraction of data with Scimago API is now beginning **")
    print("A message will be printed below every time a 10% portion of the "
          "total papers to analyse is completed.")

    ## Import the most recent Scimago statistics as a pd.Dataframe
    print("Pulling Scimago data from online, collating into a dataframe...")
    df = collectall_scimago(year - 1)
    print("Scimago data retrieved!")

    ## Create a list of the stored journals. Clean strings are the keys, values are the original strings for lookup
    journals = {}
    for journal in df['Title']:
        journals[reformatjournal_scimago(journal)] = journal

    ## For each journal/source attempt to review the SJR and h-index
    for i in range(len(data_dict)):
        # Extract and standardise the associated journal
        el_journal = reformatjournal_scimago(data_dict[i]['journal_elsevier'])
        ss_journal = reformatjournal_scimago(data_dict[i]['journal_semanticscholar'])
        oa_journal = reformatjournal_scimago(data_dict[i]['journal_openalex'])

        # Check whether there is a matching journal stored in the elsevier journal field
        if el_journal in journals.keys():
            data_dict = addjournalinfo_scimago(df, data_dict, i, journals, el_journal)
        elif oa_journal in journals.keys():
            data_dict = addjournalinfo_scimago(df, data_dict, i, journals, oa_journal)
        elif ss_journal in journals.keys():
            data_dict = addjournalinfo_scimago(df, data_dict, i, journals, ss_journal)

        proportion = print_progress(i, proportion, total, 'OpenAlex')

    return data_dict

def output_csv(data_dict: dict, all_user_data: pd.DataFrame, retain_all_columns: bool) -> None:
    """
    Write citation and metadata results to a CSV file.

    Parameters
    ----------
    data_dict : dict
        Dictionary of all extracted data.
    all_user_data : pandas.DataFrame
        Original user CSV data.
    retain_all_columns : bool
        If True, output results into a new CSV file. Otherwise, append results to the original user data.

    Returns
    -------
    None

    Notes
    -----
    The output file is always saved as `citation_counter_output.csv` 
    in the current working directory.
    """
    #Instantiate citation data as data frame
    data = pd.DataFrame(data_dict)
    data = data.T

    if not retain_all_columns:
        #Output immediately if create separate csv
        data.to_csv("citation_counter_output.csv", header = True, index = False, encoding = 'utf-8')
    else:
        #Otherwise, add citation data columns to user dataframe and output this
        for col in data.columns:
            all_user_data[col] = data[col]
        all_user_data.to_csv("citation_counter_output.csv", header = True, index = False, encoding = 'utf-8')

    # Communicate to user successful output of the csv
    print("** 'citation_counter_output.csv' has been successfully output! **\n")

    return None

def execute_gender_script():
    # Check if Rscript is available
    if shutil.which("Rscript") is None:
        print("WARNING: Rscript not found. Skipping gender analysis.")
        print("To install R, visit: https://www.r-project.org/")
    else:
        try:
            print("** Running gender analysis script in background. Output will be displayed upon completion... **")
            result = subprocess.run(["Rscript", "authors_gender.R"],
                                    capture_output=True, text=True)
            
            # Print the R script output
            if result.stdout:
                print(result.stdout)
            
            if result.returncode == 0:
                print("** Gender analysis completed successfully **")
            else:
                print(f"WARNING: Gender script failed with return code {result.returncode}")
                if result.stderr:
                    print(f"Error output: {result.stderr}")
        except Exception as e:
            print(f"WARNING: Failed to run gender script: {e}")