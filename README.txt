Hello!

This is a module to extract data for any set of papers you provide.
It first attempts to find the paper using the Elsevier API, and that failing, looks for the paper with the Semantic Scholar API. The data fields extractable is listed below, under the sub-heading 'Data-to-extract'.


Things you need to be able to use this:
- A csv file, containing columns that contain the title and DOI of all papers you want citation counts for. IMPORTANT: Ensure all columns are the same length and contain data. Errors will occur otherwise. 
- An API key for the Elsevier database. If you don't have one, you can get one here: https://dev.elsevier.com. You don't need one for semantic scholar.

If you have both of these things, you can proceed with the following actions to use the module.

Creation of a virtual environment:
- A requirements.txt file is provided for this

Configuration file you need to edit:
- config.json is in this folder. Please open it and enter the following pieces of information:

    Essential:
    - csv_path: str. Contains the path to your csv file.
    - elsevier_apikey: str. Your Elsevier API key
    - colname_title: str and colname_DOI: str. The column names in your file that contain the title and DOIs for your papers, respectively.

    Data-to-extract:
    - extract_citation_count: bool. Change the value to "True" if desired, otherwise leave as ""
    - extract_first_last_author: bool. <as above>
    - extract_author_count: bool. <as above>
    - extract_journal: bool. <as above>

    Optional:
    - create_separate_csv: bool. Change the value to "True" if you would like a separate csv file containing the data extracted. Leaving this as "" means the csv columns this module outputs will be appended to a copy of the csv you provide.
    - output_citation_data_full: bool. Change the value to "True" if you would like both citation counts from Elsevier and Semantic Scholar to be recorded when available, instead of only searching Semantic Scholar when the paper cannot be located in Elsevier. This will slow down the execution time of the program, but allows you to compare the results of the two databases. A summarising figure is output as well. Otherwise, leave as "".


Once that's done, open citation_counter.py and run!

Output notes:
The data csv is output to the working directory, with the name 'citation_counter_output.csv,' and if output_citation_data_full is "True", a png will be output called "citation_counter_visual_summary.png"
The open source module 'elsapy' is used to interface with the Elsevier API. This module outputs dump.json, a folder called 'logs' and a folder called 'data'. These can be deleted and do not affect the function of the elsapy module.

This module was authored by Benjamin Varela. It uses open source modules 'elsapy' and 'semanticscholar'. Last edited 07/02/2025 (DD/MM/YYYY)