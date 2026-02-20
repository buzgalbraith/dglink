"""
Assembles a knowledge graph by parsing the NCI General Data Commons (GDC) Portal https://general.datacommons.cancer.gov/#/
"""

from dglink import NodeSet, EdgeSet, write_graph
from dglink.portals.nci.gdc import (
    NODE_ATTRIBUTES,
    EDGE_ATTRIBUTES,
    get_case_hierarchy,
    download_tabular_files,
)
from dglink.portals.nci.gdc.utils import get_tabular_iterator
from dglink.core.tabular_data import get_tabular_data

num_cases = 5  ## number of cases to process at max
batch_size = 500  ## number of cases to process at one
target_case_id = "9b2c325c-1f03-43c7-ad5c-b49c6d205635"  ## uuid of target case
case_ids = [
    target_case_id,
    "0e9262d1-5aa8-4528-9aee-2815afcd23cd",
    "0ee53efd-b992-4aeb-a091-8dd1bd32da6e",
]
if __name__ == "__main__":
    ## set up a new node and edge set
    node_set = NodeSet(attributes=NODE_ATTRIBUTES)
    edge_set = EdgeSet(attributes=EDGE_ATTRIBUTES)
    get_case_hierarchy(
        node_set=node_set,
        edge_set=edge_set,
        case_list=case_ids,
        batch_length=batch_size,
    )
    download_tabular_files(case_list=case_ids)
    case_to_files = get_tabular_iterator(case_list=case_ids)
    reports = get_tabular_data(
        group_identifiers=case_ids,
        node_set=node_set,
        edge_set=edge_set,
        tabular_iterator=case_to_files,
        quality_check_method="ml_schema_match",
        # quality_check_method='heuristic'
    )
    write_graph(node_set=node_set, edge_set=edge_set)
