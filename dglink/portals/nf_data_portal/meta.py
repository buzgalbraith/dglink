from .constants import PROJECT_ATTRS, METADATA_NODES, GROUND_FIELDS, syn
from .utils import _unpack_dict_list, parse_dict_fields, parse_related_studies, get_project_name, get_project_summary
from dglink.core.constants import RESOURCE_PATH 
from dglink import NodeSet, EdgeSet, write_graph


import tqdm
import logging
import os
import re

logger = logging.getLogger(__name__)

SYNAPSE_ID = re.compile(r"syn\d+")

def parse_project_attrs(project_id:str, project_metadata:dict, node_set:NodeSet)->NodeSet:
    """Extract study node attributes from metadata"""
    project_attrs = {}
    for attr in PROJECT_ATTRS:
        project_attrs[f'{attr}:string[]'] = _unpack_dict_list(project_metadata, attr)
    # take the name as the curie when no text name is available #
    project_attrs['name'] = get_project_name(project_id)
    project_attrs['summary'] = get_project_summary(project_id)
    node_set.update_nodes(project_attrs, new_node_id=project_id, fill_empty=True)
    return node_set

def parse_project_meta(project_id:str, project_metadata:dict, node_set: NodeSet, edge_set: EdgeSet)->NodeSet:
    node_set = parse_project_attrs(project_id = project_id, project_metadata=project_metadata,node_set=node_set)
    node_set, edge_set = parse_dict_fields(
                                        meta_curie=project_id,
                                        meta= project_metadata,
                                        node_types = METADATA_NODES + GROUND_FIELDS,
                                        source='metadata',
                                        node_set=node_set, 
                                        edge_set=edge_set,
                        )
    
    node_set, edge_set = parse_related_studies(
                meta_curie=project_id,
                meta= project_metadata,
                key = 'relatedStudies',
                source='metadata',
                node_set=node_set, 
                edge_set=edge_set,
    )
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
