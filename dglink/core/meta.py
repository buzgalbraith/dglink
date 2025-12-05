from dglink.core.constants import syn, RESOURCE_PATH
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


def get_entities_from_meta(
    study_metadata,
    ground_fields,
    unground_fields,
    node_set: NodeSet,
    edge_set: EdgeSet,
):
    """parse entities from project metadata."""
    for field in ground_fields + unground_fields:
        if field in study_metadata.keys():
            field_val = (
                study_metadata[field]
                if type(study_metadata[field]) == list
                else [study_metadata[field]]
            )
            ## loop through in case list
            for entry in field_val:
                ## ground the node if it is in a grounded field
                ## add the nodes with their corresponding meta data fields
                entry = str(entry)
                node_attributes = {
                    "curie:ID": entry,
                    ":LABEL": field,
                    "name": entry,
                    "columns:string[]": "metadata",
                    "raw_texts:string[]": entry,
                    "source:string[]": "metadata",
                }
                if field in ground_fields:
                    ans = gilda.annotate(entry)
                    ## if the node should be grounded and can be grounded save the node as that entity type as well.
                    if ans:
                        nsid = ans[0].matches[0].term
                        curie = normalize_curie(f"{nsid.db}:{nsid.id}")
                        node_attributes = {
                            "curie:ID": curie,
                            ":LABEL": bio_ontology.get_type(nsid.db, nsid.id),
                            "name": nsid.entry_name,
                            "iri": get_bioregistry_iri(nsid.db, nsid.id),
                            "raw_texts:string[]": entry,
                            "columns:string[]": "metadata",
                            "source:string[]": "metadata",
                        }
                        # edge_set.add((study_metadata.id, curie, f"has_{field}"))
                        edge_set.update_edges(
                            {
                                ":START_ID": study_metadata.id,
                                ":END_ID": curie,
                                ":TYPE": f"has_{field}",
                                "source:string[]": "metadata",
                            }
                        )
                # edge_set.add((study_metadata.id, entry, f"has_{field}"))
                edge_set.update_edges(
                    {
                        ":START_ID": study_metadata.id,
                        ":END_ID": entry,
                        ":TYPE": f"has_{field}",
                        "source:string[]": "metadata",
                    }
                )
                node_set.update_nodes(new_node=node_attributes)
    return node_set, edge_set


def get_meta(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    ground_field: list,
    ungrounded_field: list,
    write_set: bool = False,
):
    """pull all fields from a series of project meta data."""
    logger.info("starting meta data pull")
    for project_id in tqdm.tqdm(project_ids):
        study_metadata = syn.get(project_id)
        node_set, edge_set = get_entities_from_meta(
            study_metadata=study_metadata,
            ground_fields=ground_field,
            unground_fields=ungrounded_field,
            node_set=node_set,
            edge_set=edge_set,
        )
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
