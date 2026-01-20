from dglink import NodeSet, EdgeSet, write_graph
from dglink.core.constants import RESOURCE_PATH
from .constants import syn
import tqdm
import pandas 
import os
def get_publications(node_set: NodeSet, edge_set: EdgeSet, write_set: bool = False):
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
            source_name="publications",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set