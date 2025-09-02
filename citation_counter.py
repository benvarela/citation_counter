'''
This file will search for and extract the citation count for a number of papers you provide in a csv. Please see README.txt to understand how to input into config.json. 

Last edited: 07/02/2025 (DD/MM/YYYY)
Author: Ben Varela

citation_counter expanded: last edited 21/02/2025 (DD/MM/YYYY)
Added functionality to extract additional paper characteristics, including author count, first and last authors and journal.
'''

#imports
import citation_counter_functions as f

#main block
if __name__ == '__main__':
    #Collect user input and make available in the code
    d = f.readjson()
    doi_series, title_series, full_dataframe = f.readcsv(d["csv_path"], d["colname_title"], d["colname_DOI"])
    els_client = f.instantiate_elsapy_client(d["elsevier_apikey"])
    data_dict = f.make_data_dictionary(doi_series)

    #Extract citation counts
    data_dict, warning_rows = f.get_elsevier_data(doi_series, title_series, els_client, data_dict)
    data_dict = f.get_semanticscholar_data(doi_series, title_series, data_dict, warning_rows)

    #Outputs, including a csv, and optionally a png.
    f.output_csv(data_dict, full_dataframe)