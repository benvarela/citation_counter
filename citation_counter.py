'''
Run this file to extract metadata on journal articles in provided csv. Please see README.md to understand pre-requesites of use. 
'''

#imports
import citation_counter_functions as f

#main block
if __name__ == '__main__':
    #Collect user input and make available in the code
    d = f.readjson()
    data_dict, full_dataframe = f.readcsv(d["csv_path"], d["colname_title"], d["colname_DOI"])

    #Interface with each API
    data_dict  = f.get_elsevier_data(d["elsevier_apikey"], data_dict)
    data_dict = f.get_semanticscholar_data(data_dict)
    data_dict = f.get_openalex_data(data_dict)

    #Outputs, including a csv, and optionally a png.
    f.output_csv(data_dict, full_dataframe, d["metadata_in_separate_csv"])