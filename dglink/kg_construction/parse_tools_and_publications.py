"""Parses tools and publications used in each project from NF data Portal."""

import synapseclient
from pandas import isnull

syn = synapseclient.login()

all_project_ids = [
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


def get_tool_nodes():
    """returns a set with all tool nodes and a mapping from any name (or synonym) to its curie"""
    ## this table has all NF data portal tool meta data, it was generated from the programmatic export on the nf data portal website.
    query = syn.tableQuery("SELECT * FROM syn51730943")
    df = query.asDataFrame()
    ## make set to hold nodes, and mapping from names back to identifiers
    node_set = set()
    name_to_rid = dict()
    for row in df.itertuples():
        ## some tools do not have a curie, in this case we just use the plane text name as an identifier
        rrid = row.rrid if not isnull(row.rrid) else row.resourceName
        ## saving curie as id for node and tool as type but also keeping plane text name and type of tools as node attributes
        node_set.add((rrid, row.resourceName, row.resourceType, "tool"))
        ## update name mapping with primary name and synonyms
        name_to_rid[row.resourceName] = rrid
        for synonym in row.synonyms:
            name_to_rid[synonym] = rrid

    return node_set, name_to_rid


def get_tool_edges(project_ids: list, name_to_rid: dict):
    """parse file meta data for each project in a list of projects, to extract links between tools and projects.
    Simply checks if the name or (or synonym) of each tool is in the file individualID or any specimenID.
    """
    edge_set = set()
    for project_id in project_ids:
        query = syn.tableQuery(
            f"SELECT * FROM syn52702673 WHERE ( ( \"studyId\" LIKE '%{project_id.strip('syn')}%' ) ) AND ( resourceType IN ( 'analysis', 'experimentalData', 'results' ) )"
        )
        df = query.asDataFrame()
        for row in df.itertuples():
            for specimen in row.specimenID:
                if specimen in name_to_rid.keys():
                    edge_set.add((project_id, name_to_rid[specimen], "usesTool"))
            if row.individualID in name_to_rid.keys():
                edge_set.add((project_id, name_to_rid[row.individualID], "usesTool"))
    return edge_set


def get_publications():
    """pulls nodes for publications and adds edges from them to related studies from NF Data Portal"""
    query = syn.tableQuery("SELECT * FROM syn16857542")
    df = query.asDataFrame()
    ## make publication nodes and edges
    publication_node_set = set()
    publication_edge_set = set()
    for publication in df.itertuples():
        publication_node_set.add(
            (
                publication.title,
                publication.doi if not isnull(publication.doi) else "No DOI",
                publication.pmid,
                "publication",
            )
        )
        for study_id in publication.studyId:
            publication_edge_set.add((study_id, publication.title, "published"))
    return publication_node_set, publication_edge_set


if __name__ == "__main__":
    ## get a set of all tools formatted as neo4j nodes
    tool_node_set, name_to_rid = get_tool_nodes()
    tool_edge_set = get_tool_edges(project_ids=all_project_ids, name_to_rid=name_to_rid)

    ## get sets of all publications formatted as neo4j
    publication_node_set, publication_edge_set = get_publications()
    ## dump found nodes and edges.
    tool_nodes = [("curie:ID", "name", "tool_type", ":LABEL")] + list(tool_node_set)
    with open("dglink/resources/tool_nodes.tsv", "w") as f:
        for row in tool_nodes:
            f.write("\t".join(row) + "\n")

    tool_edges = [(":START_ID", ":END_ID", ":TYPE")] + list(tool_edge_set)
    with open("dglink/resources/tool_edges.tsv", "w") as f:
        for row in tool_edges:
            f.write("\t".join(row) + "\n")

    publication_nodes = [("curie:ID", "name", "tool_type", ":LABEL")] + list(
        publication_node_set
    )
    with open("dglink/resources/publication_nodes.tsv", "w") as f:
        for row in publication_nodes:
            f.write("\t".join(row) + "\n")

    publication_edges = [(":START_ID", ":END_ID", ":TYPE")] + list(publication_edge_set)
    with open("dglink/resources/publication_edges.tsv", "w") as f:
        for row in publication_edges:
            f.write("\t".join(row) + "\n")
