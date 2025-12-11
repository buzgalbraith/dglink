from dglink import load_graph, write_graph, get_projects, get_wikis
from dglink.portals.ad_knowledge_portal import (
    get_all_ad_studies,
    get_program_project_study_hierarchy,
    get_publications,
    get_metadata_ad_knowledge_portal,
)
from dglink.portals.ad_knowledge_portal.constants import (
    AD_BASE_STUDY_URL,
    WIKI_FIELDS,
    UNGROUNDED_FIELDS,
    GROUND_FIELDS,
)


if __name__ == "__main__":
    node_set, edge_set = load_graph()
    projects_ids = get_all_ad_studies()
    node_set, edge_set = get_program_project_study_hierarchy(
        node_set=node_set, edge_set=edge_set
    )

    node_set, edge_set = get_projects(
        project_ids=projects_ids,
        node_set=node_set,
        edge_set=edge_set,
        studies_base_url=AD_BASE_STUDY_URL,
        write_set=True,
    )
    node_set, edge_set = get_wikis(
        node_set=node_set,
        edge_set=edge_set,
        project_ids=projects_ids,
        wiki_fields=WIKI_FIELDS,
        studies_base_url=AD_BASE_STUDY_URL,
        write_set=True,
    )
    node_set, edge_set = get_publications(
        node_set=node_set,
        edge_set=edge_set,
        write_set=True,
    )
    node_set, edge_set = get_metadata_ad_knowledge_portal(
        node_set=node_set,
        edge_set=edge_set,
        write_set=True,
    )
    write_graph(node_set=node_set, edge_set=edge_set)
