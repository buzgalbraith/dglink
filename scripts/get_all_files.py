from dglink.core.experimental_data import get_project_files
from dglink.portals.nf_data_portal import get_all_nf_studies
from synapseutils import walk
import os
import pandas
import tqdm

if __name__ == "__main__":
    projects_ids = get_all_nf_studies()
    all_files = []
    for project_syn_id in tqdm.tqdm(projects_ids):
        ## set file_types to None so we check all types of files
        project_files = get_project_files(
            project_syn_id=project_syn_id, file_types=None
        )
        for obs in project_files:
            all_files.append(
                {
                    "syn_id": obs[1],
                    "file_path": obs[0],
                    "extension": os.path.splitext(obs[0])[1],
                }
            )
    ## write to tsv
    files_df = pandas.DataFrame.from_records(all_files)
    files_df.to_csv("file_types.tsv", sep="\t", index=False)
