'''
Functions required for citation_counter.py. See function descriptor for information on function, inputs and outputs.
'''

#imports
import json
import pandas as pd
from pathlib import Path
from elsapy.elsclient import ElsClient
from elsapy.elssearch import ElsSearch
from elsapy.elsdoc import FullDoc
from semanticscholar import SemanticScholar
import numpy as np

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
                "metadata_in_separate_csv": str
                    Either "" or "True".
            }

    Raises
    ------
    FileNotFoundError
        If `config.json` does not exist.
    ValueError
        If `metadata_in_separate_csv` has an invalid value.
    """

    #Open the json file
    try:
        with open("config.json") as con_file:
            con = json.load(con_file)
    except Exception as e:
        print("ERROR: Make sure there is a file name config.json in this folder. More information:\n")
        raise

    #Check appropriate input for metadata_in_separate_csv
    v = con["metadata_in_separate_csv"]
    if v not in ("", "True"):
        raise ValueError(f"Invalid value for metadata_in_separate_csv: {v!r}. Expected '' or 'True'.")
    
    # Extract values and store in dictinoary to return
    data = {
    "csv_path": con["csv_path"],
    "elsevier_apikey": con["elsevier_apikey"],
    "colname_title": con["colname_title"],
    "colname_DOI": con["colname_DOI"],
    "metadata_in_separate_csv": con["metadata_in_separate_csv"],
    }

    # User communication
    print("\n** Inputs read! Your inputs are: **")
    print("csv_path: {}".format(data["csv_path"]))
    print("elsevier_apikey: {}".format(data["elsevier_apikey"]))
    print("colname_title: {}".format(data["colname_title"]))
    print("colname_DOI: {}".format(data["colname_DOI"]))
    print("metadata_in_separate_csv: {}".format(data["metadata_in_separate_csv"]))
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
                        "authors_semanticscholar": None,
                        "authorcount_semanticscholar": None,
                        "journal_elsevier": None,
                        "journal_semanticscholar": None
                       }
        
    return data_dict, full_dataframe

def instantiate_elsapy_client(elsevier_apikey: str) -> ElsClient:
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

def print_progress(i: int, proportion: float, total: int, database: str) -> float:
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
            print("Completed {}% with {}{}".format(round(proportion*100, 3), database, end_char))
            proportion += 0.1
    
    return proportion

def get_elsevier_data(elsevier_apikey: str, data_dict: dict) -> dict:
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
    #Instantiate the elsevier client
    els_client = instantiate_elsapy_client(elsevier_apikey)

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
            continue
        
        ## Using the title and DOI informatino to extract citation count and journal
        #Having brackets in the title causes a syntax error to be thrown sometimes. They are removed
        def remove_chars(string, chars_to_remove):
            return ''.join(char for char in string if char not in chars_to_remove)
        title = remove_chars(title, '()')

        #Search for a paper with a title check by ensuring the DOI matches. When errors arise, papers are skipped (due to special characters in the title). 
        search = ElsSearch("TITLE({})".format(title), 'scopus')
        try:
            search.execute(els_client)
        except:
            proportion = print_progress(i, proportion, total, 'Elsevier')
            continue

        #Use the ElsSearch and FullDoc to extract citation count and journal. Author information can't be found reliably, due to how poor AbsDoc and Fulldoc perform.
        for result in search.results:
            if 'prism:doi' in result.keys():
                if result['prism:doi'] == doi:
                    #Get citation count
                    data_dict[i]['citationcount_elsevier'] = int(result['citedby-count'])
                    #Get journal
                    if 'prism:publicationName' in result.keys():
                        data_dict[i]['journal_elsevier'] = result['prism:publicationName']

        proportion = print_progress(i, proportion, total, 'Elsevier')

    return data_dict

def reformat_author_names(authors: list) -> str:
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
    return ";".join(formatted)

def get_semanticscholar_data(data_dict: dict) -> dict:
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
    
    #Instantiate the SemanticScholar object
    sch = SemanticScholar()        

    #Variables for the progress statements to be printed to terminal, using print_progress()
    total = len(data_dict)
    proportion = 0.1

    for i in range(len(data_dict)):
        ## Check DOI, skip iteration if not present.
        doi = data_dict[i]['DOI']
        if doi == "":
            continue

        ## Extraction of data
        #Extract paper result with semantic scholar, skip if an error is thrown when retrieving it
        try:
            paper_result = sch.get_paper(doi)
        except:
            proportion = print_progress(i, proportion, total, 'Semantic Scholar')
            continue
        
        #Extract citation count. Method is looking at the papers author1 has published, and matching according to title. Take max citation count. JUSTIFICATION FOR THIS PROCESS: This is more complicated than the semanticscholar documentation may suggest. Semantic scholar can give two copies of the same paper, with different citation counts, eg: 'Local Transformed Features for Epileptic Seizure Detection in EEG Signal.' Type that into https://www.semanticscholar.org and see what you get. This is managed by taking the first author, seeing all the papers they're authored on, and then taking the one with a matching title and greatest citation count.        
        citation_count = None
        authors = paper_result['authors']
        #Some papers, erroneously, may not have a listed author in Semantic Scholar, eg: https://www.semanticscholar.org/paper/EEG-Signal-Research-for-Identification-of-Epilepsy/140ee25d5ca5dbdf65dafc57f422f00366137bc8
        #If there are authors:
        if authors:
            author1_papers = sch.get_author_papers(authors[0]['authorId'], limit = 1000)
            for author1_paper in author1_papers.raw_data:
                if 'DOI' in author1_paper['externalIds'].keys():                                # A couple things to note here. Because sometimes the titles extracted have strange characters, I'm only checking to see if the DOI.lower() matches. .lower() is needed because sometimes pre-prints have a letter of lower case and they get chosen instead of the peer-reviewed published paper, which has the citations.
                    if author1_paper['externalIds']['DOI'].lower() == doi.lower():
                        if citation_count != None:
                            citation_count = max(citation_count, author1_paper['citationCount'])
                        else:
                            citation_count = author1_paper['citationCount']
        #If there aren't any authors, assume no paper duplication problems:
        if citation_count == None:
            citation_count = paper_result['citationCount']
        #Save the citation count
        if citation_count != None:
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
            authors = reformat_author_names(authors)
            data_dict[i]['authors_semanticscholar'] = authors

        #Progress statements to be printed to the terminal
        proportion = print_progress(i, proportion, total, 'Semantic Scholar')

    return data_dict

def output_csv(data_dict: dict, all_user_data: pd.DataFrame, create_separate_csv: bool) -> None:
    """
    Write citation and metadata results to a CSV file.

    Parameters
    ----------
    data_dict : dict
        Dictionary of all extracted data.
    all_user_data : pandas.DataFrame
        Original user CSV data.
    create_separate_csv : bool
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

    if create_separate_csv:
        #Output immediately if create separate csv
        data.to_csv("citation_counter_output.csv", header = True, index = False)
    else:
        #Otherwise, add citation data columns to user dataframe and output this
        all_user_data['citationcount_elsevier'] = data['citationcount_elsevier']
        all_user_data['citationcount_semanticscholar'] = data['citationcount_semanticscholar']
        all_user_data['authors_semanticscholar'] = data['authors_semanticscholar']
        all_user_data['authorcount_semanticscholar'] = data['authorcount_semanticscholar']
        all_user_data['journal_elsevier'] = data['journal_elsevier']
        all_user_data['journal_semanticscholar'] = data['journal_semanticscholar']
        all_user_data.to_csv("citation_counter_output.csv", header = True, index = False)

    # Communicate to user successful output of the csv
    print("** 'citation_counter_output.csv' has been successfully output! **\n")

    return None