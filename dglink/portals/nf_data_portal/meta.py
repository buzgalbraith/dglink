from dglink.core.constants import RESOURCE_PATH 
from dglink.portals.nf_data_portal.constants import (
    PROJECT_ATTRS,
    METADATA_NODES,
    GROUND_FIELDS,
    NF_LABEL_TO_BIOLINK,
    NF_EDGE_TO_BIOLINK,
    NF_STUDIES_BASE_URL,
    NF_GROUND_FIELD_CATEGORIES,
    NF_UNGROUNDED_CATEGORY,
    NF_GROUNDING_MIN_SPAN_FRACTION,
    NF_PLACEHOLDER_VALUES,
)
from .utils import nf_curie
from .constants import syn
from dglink.core.nodes import NodeSet, _is_empty
from dglink.core.edges import EdgeSet
from dglink import write_graph
from dglink.core.grounding import ground_entity, slugify
from bioregistry import normalize_curie, get_bioregistry_iri
from indra.ontology.bio import bio_ontology
import tqdm
import logging
import os
import re

logger = logging.getLogger(__name__)

SYNAPSE_ID = re.compile(r"syn\d+")

def _meta_values(project_metadata: dict, field: str) -> list:
    """Non-empty values of a metadata field as strings, dropping leaked boolean annotations."""
    values = project_metadata.get(field, "")
    values = values if type(values) == list else [values]
    return [
        str(v)
        for v in values
        if not _is_empty(v) and str(v).lower() not in ("true", "false")
    ]


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() in NF_PLACEHOLDER_VALUES


def parse_project_attrs(project_id:str, project_metadata:dict, node_set:NodeSet)->NodeSet:
    """Extract study node attributes from metadata"""
    project_attrs = {}
    for attr in PROJECT_ATTRS:
        project_attrs[f'{attr}:string[]'] = _meta_values(project_metadata, attr)
    node_set.update_nodes(project_attrs, new_node_id=project_id)
    return node_set

def meta_node_curie(category: str, entry: str) -> str:
    """CURIE for an ungrounded metadata value, keyed by Biolink category so the same name
    under two fields of one category (e.g. a funder that is also an institution) is one node."""
    return nf_curie(f"{category.split(':')[-1].lower()}_{slugify(entry)}")

def parse_related_studies(project_metadata:dict, project_id:str, node_set:NodeSet, edge_set:EdgeSet):

    to_url = lambda x: NF_STUDIES_BASE_URL.replace("{study_id}", x)
    for entry in _meta_values(project_metadata, "relatedStudies"):
        curie = entry if SYNAPSE_ID.fullmatch(entry) else None
        if curie is None:
            logger.debug(f"Project {project_id}: skipping 'relatedStudies' value {entry!r}")
            continue
        ## add the related study as a project only if not present in other nodes ##
        if not curie in node_set.nodes:
            node_set.update_nodes(
                {
                    "curie:ID": curie,
                    ":LABEL": "biolink:Study",
                    "raw_label": "Project",
                    "study_url": to_url(curie),
                    "source:string[]": "metadata",
                }
            )
        edge_set.update_edges(
            {
                ":START_ID": project_id,
                ":END_ID": curie,
                ":TYPE": NF_EDGE_TO_BIOLINK["has_relatedStudies"],
                "raw_type:string[]": "has_relatedStudies",
                "source:string[]": "metadata",
            }
        )
    return node_set, edge_set
def parse_nodes_from_meta(project_id:str, project_metadata:dict,node_set:NodeSet, edge_set:EdgeSet):
    """Extract node values from metadata includes ungrounded fields like """
    nodes = []
    ## Extract simple ungrounded nodes ##
    for node_type in METADATA_NODES:
        for entry in _meta_values(project_metadata, node_type):
            if _is_placeholder(entry):
                continue
            category = NF_LABEL_TO_BIOLINK[node_type]
            nodes.append(
                {
                    "curie:ID": meta_node_curie(category, entry),
                    ":LABEL": category,
                    "name": entry,
                    "raw_texts:string[]": entry,
                    "raw_label" : node_type,
                    "source:string[]": "metadata",
                }
            )
    ## get grounded node types ##
    for node_type in GROUND_FIELDS:
        for raw_name in _meta_values(project_metadata, node_type):
            if _is_placeholder(raw_name):
                continue
            name, curie, iri, category = ground_entity(
                raw_name, min_span_fraction=NF_GROUNDING_MIN_SPAN_FRACTION
            )
            if curie is not None and category not in NF_GROUND_FIELD_CATEGORIES[node_type]:
                logger.debug(
                    f"Project {project_id}: {node_type} {raw_name!r} grounded to {curie} ({category}), treating as ungrounded"
                )
                curie = None
            grounded = curie is not None
            if not grounded:
                category = NF_UNGROUNDED_CATEGORY[node_type]
                name, iri = raw_name, None
                curie = meta_node_curie(category, raw_name)
            nodes.append(
                {
                    "curie:ID": curie,
                    ":LABEL": category,
                    "raw_label": node_type,
                    "name": name,
                    "iri": iri,
                    "grounded:boolean": "true" if grounded else "false",
                    "raw_texts:string[]": raw_name,
                    "source:string[]": "metadata",
                }
            )
    for node in nodes:
        ## fill_empty so a value seen again (e.g. a shared funder) never overwrites the existing node
        node_set.update_nodes(node, fill_empty=True)
        edge_set.update_edges(
            {
                ":START_ID": project_id,
                ":END_ID": node['curie:ID'],
                ":TYPE": NF_EDGE_TO_BIOLINK[f"has_{node['raw_label']}"],
                "raw_type:string[]": f"has_{node['raw_label']}",
                "source:string[]": "metadata",
            }
        )
    return node_set, edge_set
def parse_project_meta(project_id:str, project_metadata:dict, node_set: NodeSet, edge_set: EdgeSet)->NodeSet:
    node_set = parse_project_attrs(project_id = project_id, project_metadata=project_metadata,node_set=node_set)
    node_set, edge_set = parse_nodes_from_meta(project_id=project_id, project_metadata=project_metadata, node_set=node_set, edge_set=edge_set)
    node_set, edge_set = parse_related_studies(project_metadata, project_id, node_set, edge_set)
    return node_set, edge_set


def get_meta(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    write_set: bool = False,
):
    """pull all fields from a series of project meta data."""
    logger.info("starting meta data pull")
    for project_id in tqdm.tqdm(project_ids):
        try:
            project_metadata = syn.get(project_id)
            node_set, edge_set = parse_project_meta(
                project_id=project_id, 
                project_metadata=project_metadata, 
                node_set=node_set,
                edge_set=edge_set
            )
        except Exception as e:
            logger.warning(f"Project: {project_id} metadata could not be loaded, {e}")
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            strict=True,
            source_filter=True,
            source_name="metadata",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set
