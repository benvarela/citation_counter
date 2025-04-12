'''
Functions required for citation_counter.py. See function descriptor for more information about each one.

Last edited: 21/02/2025 (DD/MM/YYYY)
Author: Ben Varela
'''

#imports
import json
import pandas as pd
from elsapy.elsclient import ElsClient
from elsapy.elssearch import ElsSearch
from elsapy.elsdoc import FullDoc
from semanticscholar import SemanticScholar
import matplotlib.pyplot as plt
import numpy as np
import sys

# Only apply to Darwin systems (macOS)
if sys.platform == 'darwin':
    # CODE FROM CHATGPT TO SUPPRESS MESSAGE: 'Backend MacOSX is interactive backend. Turning interactive mode on.' Comes from Matplotlib for some reason.
    sys.stderr = open('/dev/null', 'w')  # Redirect stderr to null
plt.switch_backend('Agg')  # Use a non-interactive backend
sys.stderr = sys.__stderr__  # Restore stderr

def readbool(parameter_name: str, json_dict: dict) -> bool:
    ''' 
    Used within the readjson() function below

    Converts the user input for the boolean parameters of config.json to a boolean

    INPUTS: parameter_name: str key to the field in the json file, json_dict: the dictionary output from reading the json file
    OUTPUTS: return_value: bool the boolean entered by the user as a python bool
'''
    if json_dict[parameter_name].lower() == "false":
        return_value = False #Just in case the user entered "False". the bool() function would return True in this case
    else:
        return_value = bool(json_dict[parameter_name])
    return return_value

def readjson() -> tuple[str, str, str, str, bool, bool, bool, bool, bool, bool]:
    '''
    This function reads the file config.json, in order to output its information to the code body

    INPUTS: None
    OUTPUTS: csv_path path to the csv containing DOIs and Title for each paper, elsevier_apikey the user's elsevier API key, colname_title column name that contains title information, colname_DOI column name that contains DOI information, create_separate_csv bool whether user wants to create a separate csv with citation counts or append to the original, output_citation_data_full whether the user wants all the citation counts that can be found looking through both APIs, instead of searching Elsevier and then Semantic Scholar for whatever is left
    '''
    #Open the json file
    try:
        with open("config.json") as con_file:
            con = json.load(con_file)
    except Exception as e:
        print("ERROR: Make sure there is a file name config.json in this folder. More information:\n")
        raise
    
    #Extract values

    #Essential parameters
    csv_path = con['csv_path']
    elsevier_apikey = con['elsevier_apikey']
    colname_title = con['colname_title']
    colname_DOI = con['colname_DOI']

    #Data-to-extract parameters
    extract_citation_count = readbool("extract_citation_count", con)
    extract_first_last_author = readbool("extract_first_last_author", con)
    extract_author_count = readbool("extract_author_count", con)
    extract_journal = readbool("extract_journal", con)

    #Optional parameters
    create_separate_csv = readbool("create_separate_csv", con)
    output_citation_data_full = readbool("output_citation_data_full", con)
    
    data = (csv_path, elsevier_apikey, colname_title, colname_DOI,                                          #Essential parameters
            extract_citation_count, extract_first_last_author, extract_author_count, extract_journal,       #Data-to-extract parameters
            create_separate_csv, output_citation_data_full)                                                 #Optional parameters

    #Communicate to user what inputs are
    print("\n** Inputs read! Your inputs are: **")

    print("csv_path: {}".format(csv_path))
    print("elsevier_apikey: {}".format(elsevier_apikey))
    print("colname_title: {}".format(colname_title))
    print("colname_DOI: {}".format(colname_DOI))

    print("extract_citation_count: {}".format(extract_citation_count))
    print("extract_first_last_author: {}".format(extract_first_last_author))
    print("extract_author_count: {}".format(extract_author_count))
    print("extract_journal: {}".format(extract_journal))

    print("create_separate_csv: {}".format(create_separate_csv))
    print("output_citation_data_full: {}".format(output_citation_data_full))
    print("")

    return data

def readcsv(csv_path: str, colname_title: str, colname_DOI: str) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    '''
    Returns the columns containing paper titles and DOIs as pd.Series objects

    INPUTS: csv_path path to the csv, colname_title column name of column with titles, colname_DOI column name of column with DOIs
    OUTPUTS: DOIs pd.Series containing all DOIs, Titles pd.Series containin all titles.
    '''
    # Extract pd.Series object of the Titles and DOIs of all papers in the user provided csv
    try:
        with open(csv_path) as csv_data:
            encode = 'unicode_escape'
            all_user_data = pd.read_csv(csv_path, encoding=encode)
            all_user_data.fillna(0, inplace=True)

            # Check if the first column contains the UTF-8BOM character
            if all_user_data.columns[0] == 'ï»¿':
                # If it does, reload the CSV with the correct encoding
                encode = 'utf-8'
                print("Found a file with UTF-8 encoding. Reloading CSV with this encoding.")
                all_user_data = pd.read_csv(csv_path, encoding=encode)
                all_user_data.fillna(0, inplace=True)

            # Check if the first row contains the column headers
            if colname_DOI not in all_user_data.columns or colname_title not in all_user_data.columns:
                # It doesn't, so check the second row. If they are not in the second row the program will error.
                print("Headers were not found in the first row, checking if second row contains headers.")
                all_user_data = pd.read_csv(csv_path, encoding=encode, skiprows=1)
                all_user_data.fillna(0, inplace=True)
            
            DOIs = all_user_data[colname_DOI]
            Titles = all_user_data[colname_title]
    except Exception as e:
        print("ERROR: Something went wrong when interacting with your csv. Either the path is incorrect, one of the column name titles you entered was incorrect, or a combination of the above. Here's more information:\n")
        raise

    # Communcate to user successful extraction
    print("** Successfully read Title and DOI information from your provided CSV **\n")

    return DOIs, Titles, all_user_data

def instantiate_elsapy_client(elsevier_apikey: str) -> ElsClient:
    '''
    Instantiates the elsapy client and returns it if it is functional, using the elsevier API key

    INPUTS: elsevier_apikey the user's elsevier API key
    OUTPUTS: client ElsClient object to be used to interface with the Elsevier API
    '''
    #Instantiate the client object and test it
    client = ElsClient(elsevier_apikey)
    try:
        doc_srch = ElsSearch("TITLE({})".format("Tensor-based Uncorrelated Multilinear Discriminant Analysis for Epileptic Seizure Prediction"), 'scopus')
        doc_srch.execute(client)
    except Exception as e:
        print("ERROR: There was a problem setting up a connection with your API key. Please check it's correct. More information:\n")
        raise
    
    #Confirm success to the user
    print("** Connection established succesfully using the provided elsevier API key **\n")

    return client

def make_data_dictionary(doi_series: pd.Series) -> dict:
    '''
    Uses the length of doi_series to instantiate a dictionary where the paper data will be stored as the program proceeds. All entries begin as None.

    INPUTS: None
    OUTPUTS: Dictionary to store paper data. You can view the format in the code below
    '''
    data_dict = {}
    for i in range(len(doi_series)):
        data_dict[i] = {"elsevier_citation_count": None, 
                       "semanticscholar_citation_count": None,
                       "first_last_author": None,
                       "author_count": None,
                       "journal": None
                       }
    return data_dict

def print_progress(i: int, proportion: float, total: int, database: str) -> float:
    '''
    This function is used in get_elsevier_data and get_semanticscholar_data

    This function manages the printing of the progress statements to the terminal for the user.

    INPUTS: i: int the paper number of the current paper, proportion: the current propotion completed rounded down to the 0.1, total: int the total number of papers, database: str what database is currently being used, ie. Elsevier or Semantic Scholar
    OUTPUTS: proportion is overwritten if the function changes it
    '''
    if round((i+1)/total, 8) >= round(proportion, 8):
            if round(proportion, 8) == 1:
                end_char = '!\n'
            else:
                end_char = '...'
            print("Completed {}% with {}{}".format(round(proportion*100, 3), database, end_char))
            proportion += 0.1
    
    return proportion

def get_elsevier_data(doi_series: pd.Series, title_series: pd.Series, els_client: ElsClient, data_dict: dict) -> tuple[dict, list]:
    '''
    This function will search for each paper using their title, and confirming both the title and DOI match, extract the citation count and journal data, and store it in data_dict.

    INPUTS: doi_series contains all DOIs, title_series contains all titles, els_client the elsapy ElsClient object, data_dict dictionary of current citation counts
    OUTPUTS: data_dict updated with paper data
    '''
    #Variables for the progress statements to be printed to terminal
    total = len(data_dict)
    proportion = 0.1

    #List to collect all rows where a warning was recorded. Warnings are recorded because one or both of the row entries for DOI and/or Title are missing.
    warning_rows = []

    #Message that the elsevier extraction is beginning
    print("** Extraction of data with Elsevier API is now beginning **")
    print("A message will be printed below every time a 10% portion of the total papers to analyse is completed.")

    for i in range(len(data_dict)):
        #Extract title and DOI. Check they both exist
        doi = doi_series[i]
        title = title_series[i]
        if not doi or not title:
            print("WARNING: In row {} (excluding the header row) of your spreadsheet, either the title or DOI entry is missing. Please check this. For now, the program has skipped the paper.".format(i+1))
            warning_rows.append(i)
            continue

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
                    data_dict[i]['elsevier_citation_count'] = int(result['citedby-count'])
                #Get journal
                if 'prism:publicationName' in result.keys():
                    data_dict[i]['journal'] = result['prism:publicationName']

        proportion = print_progress(i, proportion, total, 'Elsevier')


    return data_dict, warning_rows

def reformat_author_names(first: str, last: str) -> str:
    '''
    This function takes the two author names, in the format [First] [Last], and reformats them into one string, such that the format is [Last_1st],[First_1st];[Last_last],[First_last]
    This has been done in particular to interface well with the R code that classifies the names according to gender. The github of the main branch is here: https://github.com/jdwor/gendercitation

    This function is used in the following: get_semanticscholar_data function

    INPUTS: first: str the first author's name as a string in format [First] [Last], last: str the last author's name as a string in format [First] [Last]
    OUTPUTS: names: str reformatted names as [Last_1st],[First_1st];[Last_last],[First_last]
    '''
    auth1 = first.split(sep = ' ')
    authl = last.split(sep = ' ')
    a1 = [0, 0]
    al = [0, 0]
    # Check through to make sure the names exist, replace with X. if not
    try:
        a1[0] = auth1[0]
    except IndexError:
        a1[0] = 'X.'
    try:
        a1[1] = auth1[1]
    except IndexError:
        a1[1] = 'X.'    
    try:
        al[0] = authl[0]
    except IndexError:
        al[0] = 'X.'    
    try:
        al[1] = authl[1]
    except IndexError:
        al[1] = 'X.'
    # Concatenate all together
    names = a1[1] + ', ' + a1[0] + '; ' + al[1] + ', ' + al[0]
    return names

def get_semanticscholar_data(doi_series: pd.Series, title_series: pd.Series, data_dict: dict, output_citation_data_full: bool, warning_rows: list) -> dict:
    '''
    Extracts citation count, journal and author information for all required papers using the Semantic Scholar API, adding them to data_dict.

    INPUTS: doi_series pd.Series object containing all DOIs, title_series pd.Series object containing all paper Titles, data_dict dictionary containing all citation counts, output_citation_data_full: bool whether papers with an elsevier citation should also have a semantic scholar citation extrated, warning_rows the list of row indices that were skipped by get_elsevier_counts()
    OUTPUTS: data_dict the dictionary containing all paper data 
    '''
    #Message that the semnatic scholar extraction is beginning
    print("** Extraction of data with Semantic Scholar API is now beginning **")
    print("A message will be printed below every time a 10% portion of the total papers to analyse is completed.")
    print("Rows previously identified with a warning, because they did not contain one or both entries of DOI and/or Title for a paper will be skipped again.")
    
    #Instantiate the SemanticScholar object
    sch = SemanticScholar()        

    #Variables for the progress statements to be printed to terminal
    total = len(data_dict)
    proportion = 0.1

    for i in range(len(data_dict)):
        ## Checking whether citation count and journal data is needed, and whether a warning occurred
        #Determine whether semantic scholar citation count is needed. Dependent on 
        semanticscholar_count_needed = True
        if not output_citation_data_full and data_dict[i]["elsevier_citation_count"] != None:
            semanticscholar_count_needed = False

        #Determine whether the journal is yet to be found
        journal_needed = True
        if data_dict[i]['journal'] != None:
            journal_needed = False

        #If there was a warning due to poor data entry, set no_warning to False to skip the paper
        no_warning = True
        if i in warning_rows:
            no_warning = False

        ## Extracting the data points
        if no_warning:
            #Extract title and DOI
            doi = doi_series[i]
            title = title_series[i] 

            #Extract paper result with semantic scholar, skip if an error is thrown when retrieving it
            try:
                paper_result = sch.get_paper(doi)
            except:
                proportion = print_progress(i, proportion, total, 'Semantic Scholar')
                continue
            
            #Extract citation count. Method is looking at the papers author1 has published, and matching according to title. Take max citation count. JUSTIFICATION FOR THIS PROCESS: This is more complicated than the semanticscholar documentation may suggest. Semantic scholar can give two copies of the same paper, with different citation counts, eg: 'Local Transformed Features for Epileptic Seizure Detection in EEG Signal.' Type that into https://www.semanticscholar.org and see what you get. This is managed by taking the first author, seeing all the papers they're authored on, and then taking the one with a matching title and greatest citation count.
            if semanticscholar_count_needed:    
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
                    data_dict[i]['semanticscholar_citation_count'] = citation_count
            
            #Extract journal information
            if journal_needed:
                if paper_result['venue']:
                    data_dict[i]['journal'] = paper_result['venue']
            
            #Extract author information
            if paper_result['authors']:
                authors = paper_result['authors']

                #Extract first and last authors
                first_author = authors[0]['name']
                last_author = authors[-1]['name']
                names = reformat_author_names(first_author, last_author)
                data_dict[i]['first_last_author'] = names

                #Extract the number of authors
                num_authors = len(authors)
                data_dict[i]['author_count'] = num_authors

        #Progress statements to be printed to the terminal
        proportion = print_progress(i, proportion, total, 'Semantic Scholar')

    return data_dict

def output_csv(data_dict: dict, all_user_data: pd.DataFrame, create_separate_csv: bool) -> None:
    '''
    Outputs results into a csv. This is either appended to the user's original csv of data if create_separate_csv is False, otherwise, a new csv is created with the citation data.
    There are also some statistics output about what percentage of papers results could be found for, for each of the data fields.

    INPUTS: data_dict dictionary of all data, all_user_data pd.DataFrame of all the user data entered in the start as a csv, create_separate_csv a bool determining whether a separate csv is output with the data or not. See function description for more information.
    OUTPUTS: None. Outputs 'citation_counter_output.csv' to the current folder.
    '''
    #Instantiate citation data as data frame
    data = pd.DataFrame(data_dict)
    data = data.T

    if create_separate_csv:
        #Output immediately if create separate csv
        data.to_csv("citation_counter_output.csv", header = True, index = False)
    else:
        #Otherwise, add citation data columns to user dataframe and output this
        all_user_data['Elsevier citation count'] = data['elsevier_citation_count']
        all_user_data['Semantic Scholar citation count'] = data['semanticscholar_citation_count']
        all_user_data['First Last authors'] = data['first_last_author']
        all_user_data['Author count'] = data['author_count']
        all_user_data['Journal'] = data['journal']
        all_user_data.to_csv("citation_counter_output.csv", header = True, index = False)

    #Calculate the percentages of extraction for each of the data fields, and store it in percentages. Ordered the same as the fields appearing in the dictionary. Since if there's no data there's None, a quick nested for loop gets the job done here.
    percentages = {}
    for field in data_dict[0].keys():
        total = 0
        for i in range(len(data_dict)):
            if data_dict[i][field] != None:
                total += 1
        percent = (total/len(data_dict)) * 100
        percentages[field] = round(percent, 3)

    #Printing of the percentages
    print("** Extraction efficacy summary **\n")
    print("Note that if you did not request full citation data, percentage of citations extracted is the sum of 'elsevier_citation_count' and 'semanticscholar_citation_count'")
    for percent in percentages.items():
        field = percent[0]
        perc = percent[1]
        print('{}: {}%'.format(field, perc))
    print('')

    print("** 'citation_counter_output.csv' has been successfully output! **\n")

    return None

def output_png(data_dict: dict) -> None:
    '''
    Outputs a scatterplot of the elsevier citation counts compared to the semantic scholar citation counts with some summary statistics.

    INPUTS: data_dict, dictionary of all citation data
    OUTPUTS: None. Outputs 'citation_counter_visual_summary.png' to the current folder
    '''
    #Create a numpy array for the elsevier citation counts and one for semantic scholar citation counts for all rows with both a elsevier and semantic scholar citation count exists
    citation_data = pd.DataFrame(data_dict).T
    citation_data = citation_data.dropna()
    el_cits = citation_data['elsevier_citation_count'].to_numpy()
    ss_cits = citation_data['semanticscholar_citation_count'].to_numpy()

    # Couple of calculations
    diff = el_cits - ss_cits
    mean = round(np.mean(diff), 1)
    sd = round(np.std(diff), 1)
    q1 = np.percentile(diff, 25)
    q3 = np.percentile(diff, 75)
    iqr = q3 - q1
    
    #plotting
    plt.plot(ss_cits, el_cits, 'bo', alpha = 0.5)
    plt.xlabel('Semantic scholar citation counts')
    plt.ylabel('Elsevier citation counts')
    plt.title("Elsevier citation counts plotted against Semantic Scholar citation counts")
    plt.figtext(0.89, 0.13, 'Mean difference (Els. - S.S.): {}\nSTDEV difference: {}\nIQR: {}'.format(mean, sd, iqr), ha="right", fontsize=10)
    plt.plot(ss_cits, ss_cits, 'r-', label = 'Els. = S.S line')
    plt.legend()
    plt.savefig('citation_counter_visual_summary.png') 

    #Communicate successful plot creation
    print("** 'citation_counter_visual_summary.png' successfully output! **\n")

    return None