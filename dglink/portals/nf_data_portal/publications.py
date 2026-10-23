from dglink.core.constants import RESOURCE_PATH 
from dglink.portals.nf_data_portal.constants import syn, NF_EDGE_TO_BIOLINK
from dglink.portals.nf_data_portal.meta import _is_placeholder, _meta_values, meta_node_curie
from dglink import NodeSet, EdgeSet, write_graph

from bioregistry import get_bioregistry_iri, normalize_curie

import polars as pl 
import re
import os
from typing import Tuple
import logging 
logger = logging.getLogger(__name__)


NS_PATTERNS = {
    'pmid' : re.compile(r"^(PMID:)?(\d+$)", re.IGNORECASE),
    'doi' : re.compile(r"^(https?:\/\/(www\.|dx)?doi\.org\/|doi:\s*)?(10\.\d{4,9}\/\S+$)", re.IGNORECASE)
}

pub_df_cols = [
 'doi' ## str
 'diseaseFocus',## str
 'journal',## str
 'title',## str
 'year',## int 
 'pmid',## str
 'author', ## list
 'manifestation', ## list
 'fundingAgency', ## list
 'studyId', ## list
 'studyName', ## list
 'publicationType' ## str (this seems to be null in all cases so ignore.)
 ]

other_nodes_to_add = [
    'author', ## this will be a list (add as agents)
    'journal', ## this is a string (add as agents)
    'fundingAgency', ## this will be a list (add as agents)
    'studyId' ## this will almost certainly already exist but add that evince came from publications (add as agents)
]

edges_to_add = [
    'author', ## link to publication with biolink.github.io/biolink-model/author/ (or going other way https://biolink.github.io/biolink-model/has_author/)
    'journal' ## link to publication with https://biolink.github.io/biolink-model/publisher/,
    'fundingAgency', ## link to publication biolink:related_to_at_instance_level
    'studyId' ## link to publication "biolink:has_part",
     ## copy how it is done in meta.py for these two ## 
    'diseaseFocus', 
    'manifestation',
]

def _normalize_publication_id(id, namespace = 'pubmed')->Tuple[str|None, str|None]:
    """normalize a curie for either pubmed or DOI, and return the corresponding IRI if possible ."""
    namespace_pattern = NS_PATTERNS.get(namespace, None)
    if namespace_pattern is None:
        ValueError(f"{namespace} is invalid try {NS_PATTERNS.keys()}")
    if id is None:
        return None, None
    res = namespace_pattern.match(id.replace(' ', ''))
    if not res:
        return None, None
    grp = f'{namespace}:{res.groups()[-1]}'
    curie = normalize_curie(grp)
    iri = get_bioregistry_iri(namespace, curie)
    return curie, iri


def parse_publication_nodes(pub:dict, node_set: NodeSet)->Tuple[NodeSet, str|None]:
    """Extract publication node and attributes.
    """
    doi_curie, doi_iri = _normalize_publication_id(pub.get("doi", ''), 'doi')
    pmid_curie, pmid_iri = _normalize_publication_id(pub.get("pmid", ''), 'pmid')
    ## get a valid id if possible ## 
    curie = pmid_curie or doi_curie
    if not curie:
        logger.warning(f'Publication has neither a valid PMID or DOI. Raw form is \n{pub}')
        return node_set, None
    ## add publication node with metadata ## 
    node_set.update_nodes(
        {
            "curie:ID": curie,
            ":LABEL": "biolink:Publication",
            "name": pub.get('title'), ## always filled, I checked.
            ## going to just put the iri's (i.e. url) for these
            "doi": doi_iri,
            "pmid" : pmid_iri,
            "year" : pub.get('year'), ## confirmed was always filled and greater than 2000
            ## take the raw values and add directly as node attributes ##
            "diseaseFocus:string[]" : set(_meta_values(pub, "diseaseFocus")),
            "manifestation:string[]" : set(_meta_values(pub, "manifestation")), 
            "source:string[]": "publications",
        }
    )
    return node_set, curie

def parse_related_nodes(pub:dict, curie:str, node_set: NodeSet, edge_set : EdgeSet)->Tuple[NodeSet, EdgeSet]:
    """Extract nodes that are linked to publications. Author, journal funding agencies and studies ids . 
    """
    category = 'biolink:Agent'
    for node_type in ['author', 'journal', 'fundingAgency']:
        for entry in _meta_values(pub, node_type):
            if _is_placeholder(entry):
                continue
            node_set.update_nodes(
                {
                    "curie:ID": meta_node_curie(category, entry),
                    ":LABEL": category,
                    "name": entry,
                    "raw_texts:string[]": entry,
                    "raw_label" : node_type,
                    "source:string[]": "metadata",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": curie,
                    ":END_ID": meta_node_curie(category, entry),
                    ":TYPE": NF_EDGE_TO_BIOLINK[f"has_{node_type}"],
                    "raw_type:string[]": f"has_{node_type}",
                    "source:string[]": "metadata",
                }
            )
    return node_set, edge_set
def get_publications(node_set: NodeSet, edge_set: EdgeSet, write_set:bool = True):
    """Extracts publication nodes and associated edges.

    
    
    """
    query = syn.tableQuery("SELECT * FROM syn16857542")
    for pub in pl.from_pandas(query.asDataFrame()).iter_rows(named=True):
        node_set, curie = parse_publication_nodes(pub, node_set)
        if curie is None:
            continue
        node_set, edge_set = parse_related_nodes(pub, curie, node_set, edge_set)
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            strict=True,
            source_filter=True,
            source_name="publications",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set