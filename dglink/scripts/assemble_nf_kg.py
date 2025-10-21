from dglink import get_wikis, load_graph, write_graph, get_meta, get_projects, write_graph_and_artifacts_default
from dglink.portals.nf_data_portal import get_all_nf_studies, get_publications, get_tools
from dglink.portals.nf_data_portal.constants import WIKI_FIELDS, NF_STUDIES_BASE_URL, GROUND_FIELDS, UNGROUNDED_FIELDS
import logging 
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # 1. load all studied from the nf disease portal
    logger.info("loading NF Data portal studies list")
    # node_set, edge_set = merge_resource_sets()
    projects_ids = get_all_nf_studies()
    # 2. load the node and edge sets if exist
    node_set, edge_set = load_graph(
        resource_path="dglink/resources/graph/", node_name="nodes.tsv", edge_name="edges.tsv"
    )
    node_set, edge_set = get_projects(
        project_ids=projects_ids, 
        node_set=node_set, 
        edge_set=edge_set, 
        studies_base_url=NF_STUDIES_BASE_URL,
    )

    # # 3. parse the project wikis
    node_set, edge_set = get_wikis(
        node_set=node_set,
        edge_set=edge_set,
        project_ids=projects_ids,
        wiki_fields=WIKI_FIELDS,
        studies_base_url=NF_STUDIES_BASE_URL,
    )
    # # 4. parse the nf data portal publications
    node_set, edge_set = get_publications(node_set=node_set, edge_set=edge_set)
    # # 5. get tool edges 
    # logger.info("Adding NF Data Portal Tools registry to KG")
    node_set, edge_set = get_tools(
        node_set=node_set, 
        edge_set=edge_set,
        project_ids=projects_ids[:5]
    )
    node_set, edge_set = get_meta(
        project_ids=projects_ids,
        node_set=node_set,
        edge_set=edge_set,
        ground_field=GROUND_FIELDS, 
        ungrounded_field=UNGROUNDED_FIELDS
    )
    # 5. write the graph for neo4j reading
    write_graph_and_artifacts_default(
        node_set=node_set,
        edge_set=edge_set,
        resource_path="dglink/resources/graph",
        node_name = "nodes.tsv",
        edge_name = "edges.tsv"
    )
