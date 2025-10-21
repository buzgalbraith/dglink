"""
Methods for reading in project nodes.
"""

import tqdm
import logging
from dglink import NodeSet, write_graph, EdgeSet
from dglink.core.constants import RESOURCE_PATH
import os

logger = logging.getLogger(__name__)


def get_projects(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    studies_base_url: str,
    write_set: bool = False,
):
    logger.info("loading in project nodes")
    to_url = lambda x: (
        f"{studies_base_url}/{x}" if studies_base_url is not None else ""
    )
    for project_id in tqdm.tqdm(project_ids):
        node_set.update_nodes(
            {
                "curie:ID": project_id,
                ":LABEL": "Project",
                "study_url": to_url(project_id),
                "source:string[]": "projects",
            }
        )
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="projects",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set
