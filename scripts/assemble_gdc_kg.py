"""
Assembles a knowledge graph by parsing the NCI General Data Commons (GDC) Portal https://general.datacommons.cancer.gov/#/
"""

from dglink import NodeSet, EdgeSet
from dglink.portals.nci.gdc import NODE_ATTRIBUTES, EDGE_ATTRIBUTES, get_case_hierarchy

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
    # get_case_hierarchy(
    #     node_set=node_set,
    #     edge_set=edge_set,
    #     number_cases=num_cases
    # )
    # get_case_hierarchy(
    #     node_set=node_set,
    #     edge_set=edge_set,
    #     # number_cases=num_cases
    # )
