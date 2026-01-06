"""
this is a complete restructure of the assemble NF KG Method
"""

from dglink.core.utils import get_projects_files
from dglink import NodeSet, EdgeSet, write_graph, get_projects
from dglink.core.tabular_data import get_tabular_data
from dglink.portals.nf_data_portal.nf_data_portal import get_all_nf_studies
from dglink.portals.nf_data_portal.constants import NF_DATA_PORTAL_CACHE_DIR, NODE_ATTRIBUTES, EDGE_ATTRIBUTES, NF_STUDIES_BASE_URL
from dglink.core.constants import TABULAR_FILE_TYPES
from dglink.portals.nf_data_portal import syn
import re
import polars as pl
import os



project_ids = [
"syn2343195",  ## large project
"syn5562324",  ## small project
]
def safe_download(syn_id):
    """safe download method to apply to dataframe"""
    try:
        entity = syn.get(syn_id, ifcollision="keep.local") ## keep local file if already downloaded ie do not re-download.
        return entity.path
    except Exception:
        return None
if __name__ == "__main__":
    ## get a full list of studies
    project_ids = get_all_nf_studies()
    ## crawl all projects
    project_files = get_projects_files(project_ids=project_ids, )
    ## filter for tabular projects
    file_types_pattern = f"({'|'.join(re.escape(s) for s in TABULAR_FILE_TYPES)})$"
    tabular_project_files = project_files.filter(
        pl.col("file_name").str.contains(file_types_pattern)
    )
    # download tabular files when possible (note that this file was saved TODO: look into if things are working )
    tabular_project_files = tabular_project_files.with_columns(
        file_path=pl.col('file_syn_id').map_elements(
            safe_download,
            return_dtype=pl.String
        )
    )
    ## assuming the above works ## 
    ## first save the result. 
    os.makedirs(
        NF_DATA_PORTAL_CACHE_DIR, 
        exist_ok=True
    )
    tabular_project_files.write_csv(
        os.path.join(
            NF_DATA_PORTAL_CACHE_DIR, 
            'tabular_file_paths.tsv'
        ), 
        separator='\t'
    )
    ## now filter for just files that were able to be downloaded
    downloaded_files = tabular_project_files.filter(pl.col("file_path").is_not_null()).select(
        ['project_syn_id','file_path', 'file_syn_id', ]
    ).rename(
        {'file_syn_id':'file_id', 'file_path':'file_paths'}
    )
    ## now lets group these by project id 
    project_files = downloaded_files.group_by("project_syn_id", maintain_order=True).agg(
    [pl.col("file_paths"), pl.col("file_id")]
    )
    ## then we can finally get the tabular iterator.
    tabular_iterator = project_files.iter_rows()
    
    ## now lets try to add the tabular datasets
    node_set = NodeSet(attributes=NODE_ATTRIBUTES)
    edge_set = EdgeSet(attributes=EDGE_ATTRIBUTES)
    node_set, edge_set = get_projects(
        project_ids=project_ids,
        node_set=node_set,
        edge_set=edge_set,
        studies_base_url=NF_STUDIES_BASE_URL,
        write_set=True,
    )
    reports = get_tabular_data(
        group_identifiers=project_ids,
        node_set=node_set, 
        edge_set = edge_set,
        tabular_iterator=tabular_iterator
    )

from dglink.portals.nci.gdc.utils import max_call_size
from dglink.portals.nci.gdc.constants import CASES_ENDPNT
res = max_call_size(CASES_ENDPNT)