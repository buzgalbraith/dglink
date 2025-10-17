from dglink.core.constants import DGLINK_CACHE, syn
from pathlib import Path
import os
import logging
import pandas 
from dglink.core.nodes import NodeSet
from dglink.core.edges import EdgeSet

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
        logger.info(
            f"NF Data Portal studies list saved to {nf_studies_path}"
        )
    return pandas.read_csv(nf_studies_path, sep="\t")[
    "studyId"
    ].to_list()


def get_publications(node_set:NodeSet, edge_set:EdgeSet):
    """pulls nodes for publications and adds edges from them to related studies from NF Data Portal"""
    query = syn.tableQuery("SELECT * FROM syn16857542")
    df = query.asDataFrame()
    ## make publication nodes and edges
    for publication in df.itertuples():
        node_set.update_nodes(
            {
                  "curie:ID" : publication.pmid,
                  ":LABEL": 'publication', 
                  "name" : publication.title,
                  "DOI" : publication.doi if not pandas.isnull(publication.doi) else "No DOI",
                  "source" : "publications"
            }, 
            
        )
        for study_id in publication.studyId:
            edge_set.update_edges(
                {
                    ':START_ID':study_id,
                    ':END_ID':publication.pmid,
                    ':TYPE' : "published",
                    "source" : 'publications'
                }
            )
    return node_set, edge_set



if __name__ == "__main__":
    node_set = NodeSet()
    edge_set = EdgeSet()
    node_set.load_node_set("dglink/resources/nodes.tsv")
    edge_set.load_edge_set("dglnk/resources/edges.tsv")
    get_publications(node_set=node_set, edge_set=edge_set)
    node_set.write_node_set("dglink/resources/nodes.tsv")
    edge_set.write_edge_set("dglink/resources/edges.tsv")