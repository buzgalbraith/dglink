from dglink.core.constants import DGLINK_CACHE, syn, RESOURCE_PATH
from pathlib import Path
import os
import logging
import pandas
from dglink.core.utils import write_graph
from dglink.core.nodes import NodeSet
from dglink.core.edges import EdgeSet
from bioregistry import get_bioregistry_iri
import tqdm

logger = logging.getLogger(__name__)


def download_all_nf_studies():
    """
    Saves a list of all studies on the NF Data Portal
    """
    os.makedirs(Path(DGLINK_CACHE), exist_ok=True)
    query = syn.tableQuery("SELECT * FROM syn52694652")
    df = query.asDataFrame()
    df.to_csv(f"{DGLINK_CACHE}/all_nf_studies.tsv", sep="\t", index=False)


def get_all_nf_studies():
    """
    Checks the list of all studies on the NF Data Portal exists and makes it if not. Returns all nf study ids as a list.
    """
    nf_studies_path = f"{DGLINK_CACHE}/all_nf_studies.tsv"
    if not os.path.exists(nf_studies_path):
        logger.info("NF Data Portal studies list not found.")
        logger.info("Pulling NF Data Portal studies list")
        download_all_nf_studies()
        logger.info(f"NF Data Portal studies list saved to {nf_studies_path}")
    return pandas.read_csv(nf_studies_path, sep="\t")["studyId"].to_list()


def get_publications(node_set: NodeSet, edge_set: EdgeSet, write_set:bool = False):
    """pulls nodes for publications and adds edges from them to related studies from NF Data Portal"""
    query = syn.tableQuery("SELECT * FROM syn16857542")
    df = query.asDataFrame()
    ## make publication nodes and edges
    for publication in tqdm.tqdm(df.itertuples()):
        node_set.update_nodes(
            {
                "curie:ID": publication.pmid,
                ":LABEL": "publication",
                "name": publication.title,
                "DOI": (
                    publication.doi if not pandas.isnull(publication.doi) else "No DOI"
                ),
                "source:string[]": "publications",
            },
        )
        for study_id in publication.studyId:
            edge_set.update_edges(
                {
                    ":START_ID": study_id,
                    ":END_ID": publication.pmid,
                    ":TYPE": "published",
                    "source:string[]": "publications",
                }
            )
    if write_set:
        write_graph(
            node_set=node_set, 
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name='publications',
            resource_path=os.path.join(RESOURCE_PATH, 'artifacts')
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
                'iri' : iri,
                "source:string[]": "tools",
            },
        )
        ## update name mapping with primary name and synonyms
        name_to_rid[row.resourceName] = rrid
        for synonym in row.synonyms:
            name_to_rid[synonym] = rrid

    return node_set, name_to_rid

def get_tool_edges(project_ids: list, name_to_rid: dict, edge_set:EdgeSet):
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

def get_tools(node_set:NodeSet, edge_set:EdgeSet, project_ids : list, write_set : bool = False ):
    logger.info("Getting nodes for NF Data Portal tools")
    node_set, name_to_rid = get_tool_nodes(node_set=node_set)
    logger.info("Searching project metadata for NF Data Portal tools")
    edge_set = get_tool_edges(project_ids=project_ids, edge_set=edge_set, name_to_rid=name_to_rid)
    if write_set:
        write_graph(
            node_set=node_set, 
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name='tools',
            resource_path=os.path.join(RESOURCE_PATH, 'artifacts')
        )
    return node_set, edge_set