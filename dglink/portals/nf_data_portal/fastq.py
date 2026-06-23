from dglink import NodeSet, EdgeSet, write_graph
from dglink.core.constants import RESOURCE_PATH
from .utils import get_projects_files, get_file_annotations
from .constants import SPECIMEN_FIELDS, EXPERIMENT_FIELDS

import polars as pl 
import gilda 
from bioregistry import get_bioregistry_iri, normalize_curie
from indra.ontology.bio import bio_ontology

import os 
from typing import Tuple


SOURCE = "sequencing_experiments"


def _add_edge(edge_set: EdgeSet, start_id: str, end_id: str, edge_type: str) -> None:
    """Add a single edge to the edge set, tagged with the sequencing source."""
    edge_set.update_edges(
        {
            ":START_ID": start_id,
            ":END_ID": end_id,
            ":TYPE": edge_type,
            "source:string[]": SOURCE,
        }
    )


def _ground_and_add_node(raw_text: str, node_set: NodeSet) -> Tuple[str, str] | None:
    """Ground a free-text term with gilda and add the resulting node.

    Returns the grounded ``(curie, label)`` pair, or ``None`` if the text could
    not be grounded to an ontology term.
    """
    ann = gilda.annotate(raw_text)
    if not ann or not ann[0].matches:
        return None
    nsid = ann[0].matches[0].term
    entry = normalize_curie(f"{nsid.db}:{nsid.id}")
    label = bio_ontology.get_type(nsid.db, nsid.id) or "unknown"
    node_set.update_nodes(
        {
            "curie:ID": entry,
            ":LABEL": label,
            "name": nsid.entry_name or "no_name_found",
            "raw_texts:string[]": raw_text,
            "columns:string[]": SOURCE,
            "iri": get_bioregistry_iri(nsid.db, nsid.id),
            "source:string[]": SOURCE,
        }
    )
    return entry, label



def get_fastq_metadata(project_list:list[str], node_set:NodeSet, edge_set:EdgeSet, write_set:bool = False) -> Tuple[NodeSet, EdgeSet]:
    """Extract knowledge-graph nodes and edges from fastq file annotations.

    Crawls the given projects for ``.fastq.gz`` files, pulls each file's Synapse
    annotations, and populates ``node_set``/``edge_set`` in place with the
    sequencing-experiment subgraph. For every annotated file this produces:

    - a ``sequencing_experiment`` node keyed by the file's syn id, carrying the
      :data:`~.constants.EXPERIMENT_FIELDS`;
    - a ``specimen`` node (when ``specimenID`` is present) carrying the
      :data:`~.constants.SPECIMEN_FIELDS`, linked to its file via
      ``has_sequencing_experiment`` and to its project via ``has_specimen``;
    - organism and organ nodes grounded from the free-text ``species`` and
      ``organ`` annotations via gilda, linked back to the specimen/file and
      project (``has_organism`` / ``has_<organ-type>``).

    Edges to the project are only added when the annotation has a ``studyId``.
    Terms that cannot be grounded are skipped.

    Args:
        project_list: Synapse project ids to crawl (e.g. ``['syn12345678']``).
        node_set: NodeSet to accumulate nodes into; mutated in place.
        edge_set: EdgeSet to accumulate edges into; mutated in place.
        write_set: If to write an intermediate result
    Returns:
        Updated NodeSet and EdgeSet.
    """
    pf = get_projects_files(project_ids=project_list)
    genomic_files = pf.filter(pl.col('file_name').str.ends_with('.fastq.gz'))
    ## get file level annotations ## 
    annotations_map = get_file_annotations(file_ids = genomic_files['file_syn_id'].to_list())
    for syn_id, annotation in annotations_map.items():
        project_id = annotation.get("studyId", [None])[0]
        specimen_id = annotation.get('specimenID', [None])[0]
        if specimen_id:
            specimen_rep = {
                    "curie:ID": specimen_id,
                    ":LABEL": "specimen",
                    "source:string[]": SOURCE,
                }
            for query_field, label_field in SPECIMEN_FIELDS.items():
                specimen_rep[label_field] = annotation.get(query_field, [None])[0]
            node_set.update_nodes(specimen_rep)
            _add_edge(edge_set, specimen_id, syn_id, "has_sequencing_experiment")
            _add_edge(edge_set, project_id, specimen_id, "has_specimen")

        species = annotation.get('species', [None])[0]
        if species:
            grounded = _ground_and_add_node(species, node_set)
            if grounded:
                entry, _ = grounded
                ## add edges as possible ## 
                if specimen_id:
                    _add_edge(edge_set, specimen_id, entry, "has_organism")
                if project_id:
                    _add_edge(edge_set, project_id, entry, "has_organism")

        organ = annotation.get('organ', [None])[0]
        if organ:
            grounded = _ground_and_add_node(organ, node_set)
            if grounded:
                entry, label = grounded
                ## add anatomical region to both file and project ##
                _add_edge(edge_set, syn_id, entry, f"has_{label}")
                if project_id:
                    _add_edge(edge_set, project_id, entry, f"has_{label}")

        experiment_rep = {"curie:ID": syn_id,
                    ":LABEL": "sequencing_experiment",
                    "source:string[]": SOURCE,
                }
        for field in EXPERIMENT_FIELDS:
            experiment_rep[field] = annotation.get(field, [None])[0]
        node_set.update_nodes(experiment_rep)
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name=SOURCE,
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set