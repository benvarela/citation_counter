'''
Run this file to extract metadata on journal articles in provided csv. Please see README.md to understand pre-requesites of use.
'''

#imports
import citation_counter_functions as f
import sys
from pathlib import Path

#main block
if __name__ == '__main__':
    #Collect user input, instantiate data dictionary
    d = f.readjson()

    # Check if openpyxl is required and available for xlsx files
    file_path = Path(d["csv_path"])
    if file_path.suffix.lower() == '.xlsx':
        try:
            import openpyxl
        except ImportError:
            print("\n" + "="*70)
            print("ERROR: openpyxl is required to read Excel (.xlsx) files")
            print("="*70)
            print("\nTo install openpyxl, run:")
            print("    pip install openpyxl")
            print("\nOr install it with conda:")
            print("    conda install openpyxl")
            print("\nAfter installation, please run the program again.")
            print("="*70 + "\n")
            sys.exit(1)

    data_dict, full_dataframe, file_extension = f.readcsv(d["csv_path"], d["colname_title"], d["colname_DOI"])

    #Interface with each API
    data_dict = f.get_elsevier_data(d["elsevier_apikey"], data_dict, d["no_cache"])
    data_dict = f.get_semanticscholar_data(data_dict, d["no_cache"])
    data_dict = f.get_openalex_data(data_dict, d["no_cache"])
    data_dict = f.get_scimago_data(data_dict, d["year"], d["no_cache"])

    #Output file (csv or xlsx)
    f.output_csv(data_dict, full_dataframe, d["retain_all_columns"], file_extension)

    # Run the gender script
    if not d["skip_gender"]:
        f.execute_gender_script()
