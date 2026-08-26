"""
Assemble DGLink KG over NHLBI BioData Catalyst data portal 
"""
from dglink import NodeSet, EdgeSet, write_graph
from dglink.portals.nhlbi.bdc import NhlbiBioDataCatalystClient ,get_metadata_graph, NODE_ATTRIBUTES, EDGE_ATTRIBUTES, download_tabular_files, get_tabular_iterator
from dglink.core.tabular_data import get_tabular_data

if __name__ == "__main__":
    node_set = NodeSet(NODE_ATTRIBUTES)
    edge_set = EdgeSet(EDGE_ATTRIBUTES)
    client = NhlbiBioDataCatalystClient(credential_file='/Users/buzgalbraith/.gen3/credentials.json')
    all_projects = client.get_all_projects()

    node_set, edge_set = get_metadata_graph(client=client, edge_set=edge_set, node_set=node_set)

    download_tabular_files(client=client, project_list=all_projects)

    study_ids, tabular_iterator = get_tabular_iterator(project_list = all_projects)
    get_tabular_data(
        group_identifiers=study_ids,
        node_set=node_set,
        edge_set=edge_set,
        tabular_iterator=tabular_iterator,
        quality_check_method="heuristic",
    )

    write_graph(node_set=node_set, edge_set=edge_set)