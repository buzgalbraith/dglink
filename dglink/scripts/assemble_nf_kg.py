from dglink import NodeSet, EdgeSet, get_wikis
from dglink.portals.nf_data_portal import get_all_nf_studies, get_publications
from dglink.portals.nf_data_portal.constants import WIKI_FIELDS, NF_STUDIES_BASE_URL
if __name__ == "__main__":
    # 1. load all studied from the nf disease portal 
    projects_ids = get_all_nf_studies()

    # 2. load the node and edge sets 
    node_set = NodeSet()
    edge_set = EdgeSet()
    node_set.load_node_set("dglink/resources/nodes.tsv")
    edge_set.load_edge_set("dglnk/resources/edges.tsv")

    # parse the project wikis
    node_set, edge_set = get_wikis(
                    node_set=node_set, edge_set=edge_set,
                    project_ids=projects_ids,
                    wiki_fields=WIKI_FIELDS,
                    studies_base_url=NF_STUDIES_BASE_URL
                    )
    # parse the nf data portal publications
    get_publications(node_set=node_set, edge_set=edge_set)
    # write out the nodes and eges
    node_set.write_node_set("dglink/resources/nodes.tsv")
    edge_set.write_edge_set("dglink/resources/edges.tsv")