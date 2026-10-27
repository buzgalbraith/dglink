from dglink.core.constants import RESOURCE_PATH 
from dglink.portals.nf_data_portal.constants import syn, NF_EDGE_TO_BIOLINK, NF_STUDIES_BASE_URL, GROUND_FIELDS, NF_GROUNDING_MIN_SPAN_FRACTION, NF_UNGROUNDED_CATEGORY, NF_GROUND_FIELD_CATEGORIES
from dglink.portals.nf_data_portal.meta import _is_placeholder, _meta_values, meta_node_curie
from dglink.core.grounding import ground_entity
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
    'doi' : re.compile(r"^(https?:\/\/(www\.|dx)?doi\.org\/|doi:\s*)?(10\.\d{4,9}\/\S+$)", re.IGNORECASE),
    'syn' : re.compile(r"syn\d+", re.IGNORECASE),
}

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
    """Extract nodes that are linked to publications. Author, journal funding agencies. 
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
                    "source:string[]": "publications",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": curie,
                    ":END_ID": meta_node_curie(category, entry),
                    ":TYPE": NF_EDGE_TO_BIOLINK[f"has_{node_type}"],
                    "raw_type:string[]": f"has_{node_type}",
                    "source:string[]": "publications",
                }
            )
    return node_set, edge_set

## the two bellow functions can be moved in utils since they have shared functionality with meta.py ## 
def parse_diseaseFocus_and_manifestation(pub:dict, pub_curie:str, node_set: NodeSet, edge_set: EdgeSet):
    for node_type in GROUND_FIELDS:
        for raw_name in _meta_values(pub, node_type):
            if _is_placeholder(raw_name):
                continue
            name, curie, iri, category = ground_entity(
                raw_name, min_span_fraction=NF_GROUNDING_MIN_SPAN_FRACTION
            )
            if curie is not None and category not in NF_GROUND_FIELD_CATEGORIES[node_type]:
                logger.debug(
                    f"Project {pub_curie}: {node_type} {raw_name!r} grounded to {curie} ({category}), treating as ungrounded"
                )
                curie = None
            grounded = curie is not None
            if not grounded:
                category = NF_UNGROUNDED_CATEGORY[node_type]
                name, iri = raw_name, None
                curie = meta_node_curie(category, raw_name)
            node_set.update_nodes(
                {
                    "curie:ID": curie,
                    ":LABEL": category,
                    "raw_label": node_type,
                    "name": name,
                    "iri": iri,
                    "grounded:boolean": "true" if grounded else "false",
                    "raw_texts:string[]": raw_name,
                    "source:string[]": "publications",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": pub_curie,
                    ":END_ID": curie,
                    ":TYPE": NF_EDGE_TO_BIOLINK[f"has_{node_type}"],
                    "raw_type:string[]": f"has_{node_type}",
                    "source:string[]": "publications",
                }
            )
    return node_set, edge_set


def parse_publication_studies(pub:dict, pub_curie:str, node_set:NodeSet, edge_set:EdgeSet):
    to_url = lambda x: NF_STUDIES_BASE_URL.replace("{study_id}", x)
    for entry in _meta_values(pub, "studyId"):
        curie = entry if NS_PATTERNS["syn"].fullmatch(entry) else None
        if curie is None:
            logger.debug(f"Pub {pub_curie}: skipping 'studyId' value {entry!r}")
            continue
        ## add the related study as a project only if not present in other nodes ##
        if not curie in node_set.nodes:
            node_set.update_nodes(
                {
                    "curie:ID": curie,
                    ":LABEL": "biolink:Study",
                    "raw_label": "Project",
                    "study_url": to_url(curie),
                    "source:string[]": "publications",
                }
            )
        edge_set.update_edges(
            {
                ":START_ID": pub_curie,
                ":END_ID": curie,
                ":TYPE": "biolink:has_part",
                "raw_type:string[]": "has_publication",
                "source:string[]": "publications",
            }
        )
    return node_set, edge_set


def get_publications(node_set: NodeSet, edge_set: EdgeSet, write_set:bool = True):
    """Extracts publication nodes and associated edges (also adds nodes if does not exist).
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
        node_set, curie = parse_publication_nodes(pub, node_set)
        if curie is None:
            continue
        node_set, edge_set = parse_related_nodes(pub, curie, node_set, edge_set)
        node_set, edge_set = parse_publication_studies(pub, curie, node_set, edge_set)
        node_set, edge_set = parse_diseaseFocus_and_manifestation(pub, curie, node_set, edge_set)
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