"""
This script will have a basic example of pulling code from the NCI General Commons (GC) with Gen3
"""

from dglink.portals.nci.gc import NciGeneralCommonsClient
from dglink.portals.nci.gc.constants import NCI_GC_CACHE_DIR, NCI_TABULAR_FILE_TYPES
import polars as pl
import os 


if __name__ == "__main__":
    client = NciGeneralCommonsClient(gen3_credential_file='nci_general_commons_credentials')
    print("Getting Studies")
    studies = client.get_all_studies()
    print("Getting files")
    records = []
    for study in studies:
        if study.get("study_access") != 'Open':
            continue
        print(study.get("study_name"))
        study_accession = study.get('phs_accession')
        study_files = client.get_study_files(study_accession, page_size=1000)
        records += study_files
    study_files_df = pl.from_dicts(records).filter(pl.col("file_type").is_in(NCI_TABULAR_FILE_TYPES))
    file_ids = study_files_df['file_id'].to_list()
    step_size = 250
    save_directory = os.path.join(NCI_GC_CACHE_DIR, 'files')
    for i in range(0, len(file_ids), step_size):
        batch_file_ids = file_ids[i: i + step_size]
        res = client.download_files(file_ids=batch_file_ids, save_directory=save_directory)
