from .constants import (
    syn,
    NF_KG_SCHEMA,
    WIKI_FIELDS,
    NF_GROUNDING_MIN_SPAN_FRACTION,
    NF_WIKI_EXCLUDED_CATEGORIES,
)
from dglink.core import _is_empty
from dglink.core.grounding import ground_entity
from dglink.core.constants import RESOURCE_PATH
from dglink import write_graph, NodeSet, EdgeSet

import gilda

import tqdm
import logging
import os

logger = logging.getLogger(__name__)


def get_entities_from_wiki(
    project_id: str, study_wiki, node_set: NodeSet, edge_set: EdgeSet,
):
    """pull entities from a project's wiki and link them straight to the project (each
    project has a single root wiki, so there is no intermediate wiki node)."""
    for field in WIKI_FIELDS:
        entry = study_wiki.get(field)
        if _is_empty(entry):
            continue
        ## annotate finds the spans, ground_entity re-grounds each span with the shared
        ## score / span / category rules. inefficient but simple.
        for annotation in gilda.annotate(entry):
            name, curie, iri, category = ground_entity(
                annotation.text, min_span_fraction=NF_GROUNDING_MIN_SPAN_FRACTION
            )
            ## skip things that can not be grounded, and generic categories ##
            if curie is None or category in NF_WIKI_EXCLUDED_CATEGORIES:
                continue
            node_set.update_nodes(
                {
                    "curie:ID": curie,
                    ":LABEL": category,
                    "name": name,
                    "raw_texts:string[]": annotation.text,
                    "iri": iri,
                    "source:string[]": "wiki",
                },
                fill_empty=True,
            )
            edge_set.update_edges(
                {
                    ":START_ID": project_id,
                    ":END_ID": curie,
                    ":TYPE": NF_KG_SCHEMA[("Project", "wiki_mention")],
                    "raw_type:string[]": field,
                    "raw_texts:string[]": annotation.text,
                    "source:string[]": "wiki",
                }
            )
    return node_set, edge_set


def get_wikis(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    write_set: bool = False,
):
    logger.info("Getting project Wikis.")
    for project_id in tqdm.tqdm(project_ids):
        try:
            study_wiki = syn.getWiki(project_id)
            node_set, edge_set = get_entities_from_wiki(
                project_id=project_id,
                study_wiki=study_wiki,
                node_set=node_set,
                edge_set=edge_set,
            )
        except Exception as e:
            logger.warning(f"Project: {project_id} wiki could not be loaded, {e}")
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="wiki",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set
