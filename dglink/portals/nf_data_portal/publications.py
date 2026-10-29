from dglink.core.constants import RESOURCE_PATH 
from .constants import syn, GROUND_FIELDS, PUBLICATION_METADATA_NODES, NF_LABEL_TO_BIOLINK, \
    PORTAL_PUBLICATIONS_TABLE, TOOLS_PUBLICATIONS_TABLE
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


def publication_curie(pub: dict) -> str | None:
    """the id a publication node gets: its PMID, with its DOI as fallback."""
    pmid_curie, _ = _normalize_publication_id(pub.get("pmid", ''), 'pmid')
    doi_curie, _ = _normalize_publication_id(pub.get("doi", ''), 'doi')
    return pmid_curie or doi_curie


def _tools_publication_to_portal(pub: dict) -> dict:
    """rename a tools db publication row to the portal table's field names."""
    year = pub.get("year")
    date = pub.get("publicationDate")
    ## the tools db year column is almost always empty, the date is usually filled
    if _is_empty(year) and not _is_empty(date):
        year = str(date)[:4]
    return {
        "pmid": pub.get("pmid"),
        "doi": pub.get("doi"),
        "title": pub.get("publicationTitle"),
        "year": year,
        "journal": pub.get("journal"),
    }


def parse_publication_nodes(pub:dict, node_set: NodeSet, source = ("publications",))->Tuple[NodeSet, str|None]:
    """Extract publication node and attributes. `pub` uses the portal table's field names.
    """
    _, doi_iri = _normalize_publication_id(pub.get("doi", ''), 'doi')
    _, pmid_iri = _normalize_publication_id(pub.get("pmid", ''), 'pmid')
    ## get a valid id if possible ##
    curie = publication_curie(pub)
    if not curie:
        logger.warning(f'Publication has neither a valid PMID or DOI. Raw form is \n{pub}')
        return node_set, None
    ## add publication node with metadata, filling fields an earlier table left empty ##
    node_set.update_nodes(
        {
            "curie:ID": curie,
            ":LABEL": NF_LABEL_TO_BIOLINK["publication"],
            "raw_label": "publication",
            "name": pub.get('title'),
            ## going to just put the iri's (i.e. url) for these
            "doi": doi_iri,
            "pmid" : pmid_iri,
            "year" : pub.get('year'),
            ## journal name; Biolink `published in` wants a CURIE (e.g. ISSN), which neither table has
            "journal": next(iter(_unpack_dict_list(pub, "journal")), ""),
            ## take the raw values and add directly as node attributes ##
            "diseaseFocus:string[]" : set(_unpack_dict_list(pub, "diseaseFocus")),
            "manifestation:string[]" : set(_unpack_dict_list(pub, "manifestation")),
            "source:string[]": set(source),
        },
        fill_empty=True,
    )
    return node_set, curie

def get_publications(node_set: NodeSet, edge_set: EdgeSet, project_ids: list | None = None, write_set:bool = True):
    """Extracts publication nodes and associated edges (also adds nodes if does not exist).
    Every publication in the portal publications table and the NF tools db publications table
    is added; a paper in both is one node, with the portal record filling fields first.
    Study links come only from the portal table; if `project_ids` is given, only links to
    those studies are kept (otherwise a stub Study is made for each studyId).
    Tools db papers are tagged with both the `publications` and `tools` source, and add no
    author nodes: their names are abbreviated ("Harada M") so would not merge with portal
    authors, and the authors can be recovered from the PMID.
    For publication node extracts the following features
        - curie: PMID with DOI as fallback
        - name: publication title
        - doi: resolved DOI IRI
        - pmid: resolved PMID IRI
        - year: publication year (from the publication date for tools db papers).
        - journal: journal name.
        - diseaseFocus + manifestation: taken as lists of raw (ungrounded) texts (portal only).
    Adds the following edges (and nodes if the end of the edge does not yet exist)
        - publication (biolink:Publication) - (biolink:has_author) -> author (biolink:Agent) (portal only)
        - publication (biolink:Publication) - (biolink:related_to_at_instance_level) -> funding agency (biolink:Agent)
        - study (biolink:Study) - (biolink:has_part) -> publication (biolink:Publication)
        - publication (biolink:Publication) - (biolink:has_part) -> manifestation/disease focus (biolink:Disease, biolink:BiologicalProcess ...) see grounding logic
    """
    ## portal publications first, so their fields win on papers in both tables ##
    portal_curies = set()
    query = syn.tableQuery(f"SELECT * FROM {PORTAL_PUBLICATIONS_TABLE}")
    for pub in pl.from_pandas(query.asDataFrame()).iter_rows(named=True):
        node_set, curie = parse_publication_nodes(pub, node_set)
        if curie is None:
            continue
        portal_curies.add(curie)
        node_set, edge_set = parse_dict_fields(
                                        meta_curie=curie,
                                        meta= pub,
                                        node_types = PUBLICATION_METADATA_NODES + GROUND_FIELDS,
                                        source='publications',
                                        node_set=node_set,
                                        edge_set=edge_set,
        )
        ## only link the studies we were asked for ##
        studies = _unpack_dict_list(pub, "studyId")
        if project_ids is not None:
            studies = [s for s in studies if s in project_ids]
        node_set, edge_set = parse_related_studies(
                    meta_curie=curie,
                    meta= {"studyId": studies},
                    key = 'studyId',
                    source='publications',
                    node_set=node_set,
                    edge_set=edge_set,
        )
    ## then the tools db publications, filling in what the portal left empty ##
    shared = 0
    query = syn.tableQuery(f"SELECT * FROM {TOOLS_PUBLICATIONS_TABLE}")
    for pub in pl.from_pandas(query.asDataFrame()).iter_rows(named=True):
        pub = _tools_publication_to_portal(pub)
        node_set, curie = parse_publication_nodes(pub, node_set, source=("publications", "tools"))
        if curie is None:
            continue
        shared += curie in portal_curies
    logger.info(f"{len(portal_curies)} portal publications, {shared} of them also in the tools db")
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