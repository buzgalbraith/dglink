from dglink import NodeSet, EdgeSet, write_graph
from dglink.core.constants import RESOURCE_PATH
from .constants import syn

from bioregistry import get_bioregistry_iri

import tqdm
import pandas 
import os 
import logging

logger = logging.getLogger(__name__)

def get_tools(
    node_set: NodeSet, edge_set: EdgeSet, project_ids: list, write_set: bool = False
):
    logger.info("Getting nodes for NF Data Portal tools")
    node_set, name_to_rid = get_tool_nodes(node_set=node_set)
    logger.info("Searching project metadata for NF Data Portal tools")
    edge_set = get_tool_edges(
        project_ids=project_ids, edge_set=edge_set, name_to_rid=name_to_rid
    )
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="tools",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set


def get_tool_nodes(node_set: NodeSet):
    """returns a set with all tool nodes and a mapping from any name (or synonym) to its curie"""
    ## this table has all NF data portal tool meta data, it was generated from the programmatic export on the nf data portal website.
    query = syn.tableQuery("SELECT * FROM syn51730943")
    df = query.asDataFrame()
    ## make set to hold nodes, and mapping from names back to identifiers
    name_to_rid = dict()
    for row in tqdm.tqdm(df.itertuples()):
        ## some tools do not have a curie, in this case we just use the plane text name as an identifier
        rrid = row.rrid if not pandas.isnull(row.rrid) else row.resourceName
        iri = ""
        if type(row.rrid) == str:
            tmp = row.rrid.split(":", maxsplit=1)
            iri = get_bioregistry_iri(tmp[0], tmp[1])

        ## saving curie as id for node and tool as type but also keeping plane text name and type of tools as node attributes
        node_set.update_nodes(
            {
                "curie:ID": rrid,
                ":LABEL": "tool",
                "name": row.resourceName,
                "tool_type": row.resourceType,
                "iri": iri,
                "source:string[]": "tools",
            },
        )
        ## update name mapping with primary name and synonyms
        name_to_rid[row.resourceName] = rrid
        for synonym in row.synonyms:
            name_to_rid[synonym] = rrid

    return node_set, name_to_rid


def get_tool_edges(project_ids: list, name_to_rid: dict, edge_set: EdgeSet):
    """parse file meta data for each project in a list of projects, to extract links between tools and projects.
    Simply checks if the name or (or synonym) of each tool is in the file individualID or any specimenID.
    """
    for project_id in tqdm.tqdm(project_ids):
        query = syn.tableQuery(
            f"SELECT * FROM syn52702673 WHERE ( ( \"studyId\" LIKE '%{project_id.strip('syn')}%' ) ) AND ( resourceType IN ( 'analysis', 'experimentalData', 'results' ) )"
        )
        df = query.asDataFrame()
        for row in df.itertuples():
            for specimen in row.specimenID:
                if specimen in name_to_rid.keys():
                    edge_set.update_edges(
                        {
                            ":START_ID": project_id,
                            ":END_ID": name_to_rid[specimen],
                            ":TYPE": "usesTool",
                            "source:string[]": "tools",
                        }
                    )
            if row.individualID in name_to_rid.keys():
                edge_set.update_edges(
                    {
                        ":START_ID": project_id,
                        ":END_ID": row.individualID,
                        ":TYPE": "usesTool",
                        "source:string[]": "tools",
                    }
                )
    return edge_set
