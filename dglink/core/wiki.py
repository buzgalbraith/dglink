from dglink.core.constants import RESOURCE_PATH, syn
from dglink.core.nodes import NodeSet
from dglink.core.edges import EdgeSet
from dglink import write_graph
import gilda
from bioregistry import normalize_curie, get_bioregistry_iri
from indra.ontology.bio import bio_ontology
import tqdm
import logging
import os

logger = logging.getLogger(__name__)


def get_entities_from_wiki(
    study_wiki, wiki_fields, node_set: NodeSet, edge_set: EdgeSet, studies_base_url: str
):
    """pull entities from a projects wiki, and add links to them to the graph."""
    ## add a node for that wiki, and a link between the project and this wiki node.
    wiki_id = f"{study_wiki.ownerId}:Wiki"
    to_url = lambda x: (
        f"{studies_base_url}={x.ownerId}" if studies_base_url is not None else ""
    )
    node_set.update_nodes(
        {
            "curie:ID": wiki_id,
            ":LABEL": "Wiki",
            "study_url": to_url(study_wiki),
            "source:string[]": "wiki",
        }
    )
    edge_set.update_edges(
        {
            ":START_ID": study_wiki.ownerId,
            ":END_ID": wiki_id,
            ":TYPE": "hasWiki",
            "source:string[]": "wiki",
        }
    )
    for field in wiki_fields:
        if field in study_wiki.keys():
            field_val = study_wiki[field]
            ans = gilda.annotate(field_val)
            for annotation in ans:
                nsid = annotation.matches[0].term
                entry = normalize_curie(f"{nsid.db}:{nsid.id}")
                node_set.update_nodes(
                    {
                        "curie:ID": entry,
                        ":LABEL": bio_ontology.get_type(nsid.db, nsid.id) or "unknown",
                        "name": nsid.entry_name or "no_name_found",
                        "raw_texts:string[]": annotation.text,
                        "columns:string[]": "wiki",
                        "iri": get_bioregistry_iri(nsid.db, nsid.id),
                        "source:string[]": "wiki",
                    }
                )
                edge_set.update_edges(
                    {
                        ":START_ID": wiki_id,
                        ":END_ID": entry,
                        ":TYPE": "mentions",
                        "source:string[]": "wiki",
                    }
                )
    return node_set, edge_set


def get_wikis(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    wiki_fields,
    studies_base_url,
    write_set: bool = False,
):
    logger.info("Getting project Wikis.")
    for project_id in tqdm.tqdm(project_ids):
        study_wiki = syn.getWiki(project_id)
        node_set, edge_set = get_entities_from_wiki(
            study_wiki=study_wiki,
            wiki_fields=wiki_fields,
            node_set=node_set,
            edge_set=edge_set,
            studies_base_url=studies_base_url,
        )
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
