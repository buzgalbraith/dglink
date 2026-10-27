from dglink.core.constants import RESOURCE_PATH 
from .constants import syn, GROUND_FIELDS, PUBLICATION_METADATA_NODES, NF_LABEL_TO_BIOLINK
from .utils import _unpack_dict_list, parse_dict_fields, parse_related_studies
from dglink import NodeSet, EdgeSet, write_graph
from dglink.core import _is_empty

from bioregistry import get_bioregistry_iri, normalize_curie

import polars as pl 
import re
import os
from typing import Tuple
import logging 
logger = logging.getLogger(__name__)


NS_PATTERNS = {
    'pmid' : re.compile(r"^(PMID:)?(\d+$)", re.IGNORECASE),
    'doi' : re.compile(r"^(https?:\/\/(www\.|dx\.)?doi\.org\/|doi:\s*)?(10\.\d{4,9}\/\S+$)", re.IGNORECASE),
    'syn' : re.compile(r"syn\d+", re.IGNORECASE),
}

def _normalize_publication_id(id, namespace = 'pmid')->Tuple[str|None, str|None]:
    """normalize a curie for either pubmed or DOI, and return the corresponding IRI if possible ."""
    namespace_pattern = NS_PATTERNS.get(namespace, None)
    if namespace_pattern is None:
        raise ValueError(f"{namespace} is invalid try {list(NS_PATTERNS)}")
    if _is_empty(id):
        return None, None
    ## the table may hold PMIDs as numbers
    res = namespace_pattern.match(str(id).replace(' ', ''))
    if not res:
        return None, None
    grp = f'{namespace}:{res.groups()[-1]}'
    curie = normalize_curie(grp)
    iri = get_bioregistry_iri(*curie.split(":", 1))
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
            ":LABEL": NF_LABEL_TO_BIOLINK["publication"],
            "raw_label": "publication",
            "name": pub.get('title'), ## always filled, I checked.
            ## going to just put the iri's (i.e. url) for these
            "doi": doi_iri,
            "pmid" : pmid_iri,
            "year" : pub.get('year'), ## confirmed was always filled and greater than 2000
            ## take the raw values and add directly as node attributes ##
            "diseaseFocus:string[]" : set(_unpack_dict_list(pub, "diseaseFocus")),
            "manifestation:string[]" : set(_unpack_dict_list(pub, "manifestation")), 
            "source:string[]": "publications",
        }
    )
    return node_set, curie

def get_publications(node_set: NodeSet, edge_set: EdgeSet, project_ids: list | None = None, write_set:bool = True):
    """Extracts publication nodes and associated edges (also adds nodes if does not exist).
    If `project_ids` is given, only publications linked to one of those studies are kept
    (otherwise every publication in the portal, and a stub Study for each studyId).
    For publication node extracts the following features 
        - curie: PMID with DOI as fallback
        - name: publication title 
        - doi: resolved DOI IRI
        - pmid: resolved PMID IRI
        - year: publication year. 
        - diseaseFocus + manifestation: taken as lists of raw (ungrounded) texts.
    Adds the following edges (and nodes if the end of the edge does not yet exist)
        - publication (biolink:Publication) - (biolink:has_author) -> author (biolink:Agent)
        - publication (biolink:Publication) - (biolink:has_publisher) -> journal (biolink:Agent)
        - publication (biolink:Publication) - (biolink:related_to_at_instance_level) -> funding agency (biolink:Agent)
        - study (biolink:Study) - (biolink:has_part) -> publication (biolink:Publication)
        - publication (biolink:Publication) - (biolink:has_part) -> manifestation/disease focus (biolink:Disease, biolink:BiologicalProcess ...) see grounding logic
    """
    query = syn.tableQuery("SELECT * FROM syn16857542")
    for pub in pl.from_pandas(query.asDataFrame()).iter_rows(named=True):
        if project_ids is not None and not set(_unpack_dict_list(pub, "studyId")) & set(project_ids):
            continue
        node_set, curie = parse_publication_nodes(pub, node_set)
        if curie is None:
            continue
        # node_set, edge_set = parse_related_nodes(pub, curie, node_set, edge_set)
        node_set, edge_set = parse_dict_fields(
                                        meta_curie=curie,
                                        meta= pub,
                                        node_types = PUBLICATION_METADATA_NODES + GROUND_FIELDS,
                                        source='publications',
                                        node_set=node_set, 
                                        edge_set=edge_set,
        )
    
        node_set, edge_set = parse_related_studies(
                    meta_curie=curie,
                    meta= pub,
                    key = 'studyId',
                    source='publications',
                    node_set=node_set, 
                    edge_set=edge_set,
        )

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