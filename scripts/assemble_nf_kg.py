"""
this is a complete restructure of the assemble NF KG Method
"""

from dglink import NodeSet, EdgeSet, get_projects, get_tabular_data, write_graph
from dglink.portals.nf_data_portal import get_tabular_iterator, get_wikis, get_publications, get_tools, get_meta
from dglink.portals.nf_data_portal.constants import NODE_ATTRIBUTES, EDGE_ATTRIBUTES, NF_STUDIES_BASE_URL, WIKI_FIELDS, UNGROUNDED_FIELDS, GROUND_FIELDS


import logging
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    ## load the graph
    # node_set, edge_set = load_graph(
    #     resource_path="dglink/resources/graph/",
    #     node_name="nodes.tsv",
    #     edge_name="edges.tsv",
    # )
    ## make a new graph
    node_set = NodeSet(attributes=NODE_ATTRIBUTES)
    edge_set = EdgeSet(attributes=EDGE_ATTRIBUTES)
    ## get a full list of studies
    # project_ids = get_all_nf_studies()
    project_ids = [
    "syn2343195",  ## large project
    "syn5562324",  ## small project
    "syn27761862",  ## small project
    "syn4939874",  ## large project
    "syn4939876",  ## locked
    "syn4939906",  ## small
    "syn4939916",  ## locked
    "syn7217928",  ## large
    "syn8016635",  ## small
    "syn11638893",  ## locked
    "syn11817821",  ## large
    "syn21641813",  ## locked
    "syn21642027",  ## locked
    "syn21650493",  ## large
    "syn21984813",  ## large
    "syn23639889",  ## locked
    "syn51133914",  ## locked
    "syn52740594",  ## large
    ]
    ## add projects to KG as nodes
    node_set, edge_set = get_projects(
        project_ids=project_ids,
        node_set=node_set,
        edge_set=edge_set,
        studies_base_url=NF_STUDIES_BASE_URL,
        write_set=True,
    )
    # process the tabular data 
    tabular_iterator = get_tabular_iterator(project_list=project_ids)
    reports = get_tabular_data(
        group_identifiers=project_ids,
        node_set=node_set, 
        edge_set = edge_set,
        tabular_iterator=tabular_iterator
    )
    ## load in wikis
    node_set, edge_set = get_wikis(
        node_set=node_set,
        edge_set=edge_set,
        project_ids=project_ids,
        wiki_fields=WIKI_FIELDS,
        studies_base_url=NF_STUDIES_BASE_URL,
        write_set=True,
    )
    ## load in publications
    node_set, edge_set = get_publications(
        node_set=node_set, edge_set=edge_set, write_set=True
    )
    ## load in tools
    node_set, edge_set = get_tools(
        node_set=node_set, edge_set=edge_set, project_ids=project_ids, write_set=True
    )
    ## load in metadata
    node_set, edge_set = get_meta(
        project_ids=project_ids,
        node_set=node_set,
        edge_set=edge_set,
        ground_field=GROUND_FIELDS,
        ungrounded_field=UNGROUNDED_FIELDS,
        write_set=True,
    )
    ## write the graph
    write_graph(node_set=node_set, edge_set=edge_set)
