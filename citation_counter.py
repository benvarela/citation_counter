'''
Run this file to extract metadata on journal articles in provided csv. Please see README.md to understand pre-requesites of use. 
'''

#imports
import argparse
import citation_counter_functions as f

#main block
if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Extract information on journal articles from a CSV file')
    parser.add_argument('--no-cache', action='store_true', help='Skip using the cache for API results')
    parser.add_argument('--skip-gender', action='store_true', help='Skip the R script for author genders')
    args = parser.parse_args()
    #Collect user input, instantiate data dictionary
    d = f.readjson()
    data_dict, full_dataframe = f.readcsv(d["csv_path"], d["colname_title"], d["colname_DOI"])

    #Interface with each API
    data_dict = f.get_elsevier_data(d["elsevier_apikey"], data_dict, args.no_cache)
    data_dict = f.get_semanticscholar_data(data_dict, args.no_cache)
    data_dict = f.get_openalex_data(data_dict, args.no_cache)
    data_dict = f.get_scimago_data(data_dict, d["year"], args.no_cache)

    #Output csv
    f.output_csv(data_dict, full_dataframe, d["metadata_in_separate_csv"])

    # Run the gender script
    if not args.skip_gender:
        f.execute_gender_script()
