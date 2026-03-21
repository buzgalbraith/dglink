## this package ##
from dglink.portals.nci.gc.constants import NCI_GC_CACHE_DIR, NCI_TABULAR_FILE_TYPES, NODE_ATTRIBUTES, EDGE_ATTRIBUTES
from dglink.portals.nci.gc import nciGeneralCommonsClient
from dglink.core.tabular_data import get_tabular_data
from dglink import load_graph, write_graph

## second party ## 
import polars as pl 


## first party ## 
from pathlib import Path

## initiate ##
client = nciGeneralCommonsClient('nci_general_commons_credentials')
study_files_path = Path(NCI_GC_CACHE_DIR).joinpath("study_to_files.tsv")
# node_set = NodeSet(attributes=NODE_ATTRIBUTES)
# edge_set  = EdgeSet(attributes=EDGE_ATTRIBUTES)
node_set, edge_set = load_graph(NODE_ATTRIBUTES, EDGE_ATTRIBUTES, "nci_gc_graph")


if __name__ == "__main__":
    ## get study_ids names ## 
    # study_ids = [x.get("phs_accession") for x in client.get_all_studies(only_open=True)]
    
    ## load in tabular iterator ## 
    study_to_files_df = pl.read_csv(
        study_files_path, 
        separator='\t'
    )
    tabular_study_files_to_process = study_to_files_df.filter(pl.col("file_type").is_in(NCI_TABULAR_FILE_TYPES) & pl.col("path").is_not_null())
    tabular_files = tabular_study_files_to_process.select(
        ['phs_accession','path', 'file_id', ]
    ).rename(
        {'path':'file_paths', 'file_id' : 'file_ids'}
    )
    study_files = tabular_files.group_by("phs_accession", maintain_order=True).agg(
    [pl.col("file_paths"), pl.col("file_ids")]
    )
    ## TODO: Remove testing ## 
    study_ids = study_files['phs_accession'].unique().to_list()
    tabular_iterator = study_files.iter_rows()

    ## process the files ## 
    reports = get_tabular_data(
        group_identifiers=study_ids,
        node_set=node_set, 
        edge_set = edge_set,
        tabular_iterator=tabular_iterator,
        # quality_check_method='llm_schema_match',
        # model='gpt-oss:20b',
        # provider = 'ollama',
    )
    write_graph(node_set, edge_set, resource_path='./nci_gc_graph', pascalify=True)
