"""
Build the BDC (NHLBI BioData Catalyst) portal's structural/metadata subgraph.
"""


from dglink import NodeSet, EdgeSet
from .constants import BDC_LABEL_TO_BIOLINK, BDC_EDGE_TO_BIOLINK, BDC_CURIE_PREFIX, NHLBI_BDC_CACHE_DIR,  bdc_curie, BDC_TABULAR_FILE_TYPES
from .nhlbi_biodata_catalyst_client import NhlbiBioDataCatalystClient

import polars as pl 

from typing import Iterator
import logging

logger = logging.getLogger(__name__)

lazzy_get = lambda d, x: f"{d.get(x, f'{x}_missing')}"


def get_program_hierarchy(
    client: NhlbiBioDataCatalystClient, node_set: NodeSet, edge_set: EdgeSet
) -> list[str]:
    """Build the program -> project -> study structural subgraph.

    Every node carries a valid Biolink category in :LABEL (with the BDC-native type
    kept in raw_label) and a `nhlbibdc:`-prefixed CURIE id.

    Returns the list of project_ids discovered, so the caller can pull each project's
    subjects/publications/core metadata without re-fetching the program tree.
    """
    project_ids: list[str] = []
    for program in client.get_program_hierarchy():
        program_name = program.get("name")
        if not program_name:
            continue
        program_curie = bdc_curie(program_name)
        node_set.update_nodes(
            {
                "curie:ID": program_curie,
                ":LABEL": BDC_LABEL_TO_BIOLINK["program"],
                "raw_label": "program",
                "name": program_name,
                "dbgap_accession_number": lazzy_get(program, "dbgap_accession_number"),
                "source:string[]": "structural_information",
            }
        )
        for project in program.get("projects") or []:
            project_id = project.get("project_id")
            if not project_id:
                continue
            project_ids.append(project_id)
            project_curie = bdc_curie(project_id)
            node_set.update_nodes(
                {
                    "curie:ID": project_curie,
                    ":LABEL": BDC_LABEL_TO_BIOLINK["project"],
                    "raw_label": "project",
                    "name": lazzy_get(project, "name"),
                    "code": lazzy_get(project, "code"),
                    "dbgap_accession_number": lazzy_get(project, "dbgap_accession_number"),
                    "availability_type": lazzy_get(project, "availability_type"),
                    "availability_mechanism": lazzy_get(project, "availability_mechanism"),
                    "state": lazzy_get(project, "state"),
                    "investigator_name": lazzy_get(project, "investigator_name"),
                    "investigator_affiliation": lazzy_get(project, "investigator_affiliation"),
                    "releasable:boolean": "true" if project.get("releasable") else "false",
                    "released:boolean": "true" if project.get("released") else "false",
                    "source:string[]": "structural_information",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": program_curie,
                    ":END_ID": project_curie,
                    ":TYPE": BDC_EDGE_TO_BIOLINK["Has_Project"],
                    "raw_type": "Has_Project",
                    "source:string[]": "structural_information",
                }
            )
            for study in project.get("studies") or []:
                study_id = study.get("study_id")
                if not study_id:
                    continue
                study_curie = bdc_curie(study_id)
                node_set.update_nodes(
                    {
                        "curie:ID": study_curie,
                        ":LABEL": BDC_LABEL_TO_BIOLINK["study"],
                        "raw_label": "study",
                        "name": lazzy_get(study, "full_name"),
                        "short_name": lazzy_get(study, "short_name"),
                        "study_description": lazzy_get(study, "study_description"),
                        "dbgap_phs": lazzy_get(study, "dbgap_phs"),
                        "dbgap_consent": lazzy_get(study, "dbgap_consent"),
                        "type_of_data:string[]": ";".join(study.get("type_of_data") or []),
                        "source:string[]": "structural_information",
                    }
                )
                edge_set.update_edges(
                    {
                        ":START_ID": project_curie,
                        ":END_ID": study_curie,
                        ":TYPE": BDC_EDGE_TO_BIOLINK["Has_Study"],
                        "raw_type": "Has_Study",
                        "source:string[]": "structural_information",
                    }
                )
    return project_ids


def get_subject_hierarchy(
    client: NhlbiBioDataCatalystClient,
    node_set: NodeSet,
    edge_set: EdgeSet,
    project_ids: list[str],
):
    """Build the study -> subject subgraph for every project.

    Subjects carry `project_id` directly, so they're paged per project; the `studies`
    sub-selection on each subject links it back to its parent study/studies (a subject
    can belong to more than one study).
    """
    for project_id in project_ids:
        for subject in client.get_subjects_for_project(project_id):
            subject_id = subject.get("submitter_id")
            if not subject_id:
                continue
            subject_curie = bdc_curie(subject_id)
            node_set.update_nodes(
                {
                    "curie:ID": subject_curie,
                    ":LABEL": BDC_LABEL_TO_BIOLINK["subject"],
                    "raw_label": "subject",
                    "participant_id": lazzy_get(subject, "participant_id"),
                    "consent_codes:string[]": ";".join(subject.get("consent_codes") or []),
                    "source:string[]": "structural_information",
                }
            )
            for study in subject.get("studies") or []:
                study_id = study.get("study_id")
                if not study_id:
                    continue
                edge_set.update_edges(
                    {
                        ":START_ID": bdc_curie(study_id),
                        ":END_ID": subject_curie,
                        ":TYPE": BDC_EDGE_TO_BIOLINK["Has_Subject"],
                        "raw_type": "Has_Subject",
                        "source:string[]": "structural_information",
                    }
                )


def get_publication_hierarchy(
    client: NhlbiBioDataCatalystClient,
    node_set: NodeSet,
    edge_set: EdgeSet,
    project_ids: list[str],
):
    """Build the project -> publication subgraph for every project."""
    for project_id in project_ids:
        project_curie = bdc_curie(project_id)
        for publication in client.get_publications_for_project(project_id):
            pub_id = publication.get("submitter_id")
            if not pub_id:
                continue
            pub_curie = bdc_curie(pub_id)
            node_set.update_nodes(
                {
                    "curie:ID": pub_curie,
                    ":LABEL": BDC_LABEL_TO_BIOLINK["publication"],
                    "raw_label": "publication",
                    "doi": lazzy_get(publication, "doi"),
                    "pmid": lazzy_get(publication, "pmid"),
                    "source:string[]": "structural_information",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": project_curie,
                    ":END_ID": pub_curie,
                    ":TYPE": BDC_EDGE_TO_BIOLINK["Has_Publication"],
                    "raw_type": "Has_Publication",
                    "source:string[]": "structural_information",
                }
            )


def get_core_metadata_hierarchy(
    client: NhlbiBioDataCatalystClient,
    node_set: NodeSet,
    edge_set: EdgeSet,
    project_ids: list[str],
):
    """Build the project -> core_metadata_collection subgraph for every project.

    core_metadata_collection is BDC's dataset-level descriptive record (Dublin-Core
    style: title/description/creator/publisher/...) - useful as searchable dataset
    metadata distinct from the structural program/project/study nodes.
    """
    for project_id in project_ids:
        project_curie = bdc_curie(project_id)
        for cmc in client.get_core_metadata_for_project(project_id):
            cmc_id = cmc.get("submitter_id")
            if not cmc_id:
                continue
            cmc_curie = bdc_curie(cmc_id)
            node_set.update_nodes(
                {
                    "curie:ID": cmc_curie,
                    ":LABEL": BDC_LABEL_TO_BIOLINK["core_metadata_collection"],
                    "raw_label": "core_metadata_collection",
                    "title": lazzy_get(cmc, "title"),
                    "description": lazzy_get(cmc, "description"),
                    "data_type": lazzy_get(cmc, "data_type"),
                    "format": lazzy_get(cmc, "format"),
                    "creator": lazzy_get(cmc, "creator"),
                    "contributor": lazzy_get(cmc, "contributor"),
                    "publisher": lazzy_get(cmc, "publisher"),
                    "date": lazzy_get(cmc, "date"),
                    "source:string[]": "structural_information",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": project_curie,
                    ":END_ID": cmc_curie,
                    ":TYPE": BDC_EDGE_TO_BIOLINK["Has_Core_Metadata_Collection"],
                    "raw_type": "Has_Core_Metadata_Collection",
                    "source:string[]": "structural_information",
                }
            )


def get_metadata_graph(
    client: NhlbiBioDataCatalystClient,
    node_set: NodeSet,
    edge_set: EdgeSet,
):
    """Build the full BDC structural/metadata subgraph (program -> project -> study,
    plus project -> subject via study, project -> publication, and project ->
    core_metadata_collection) into the node/edge sets. Analogous to PDC's
    get_metadata_graph and GC's get_metadata_graph.
    """
    project_ids = get_program_hierarchy(client, node_set, edge_set)
    get_subject_hierarchy(client, node_set, edge_set, project_ids)
    get_publication_hierarchy(client, node_set, edge_set, project_ids)
    get_core_metadata_hierarchy(client, node_set, edge_set, project_ids)
    return node_set, edge_set


def download_tabular_files(client:NhlbiBioDataCatalystClient, project_list:list, process_zip_files:bool = True):
    all_files = client.get_project_files(project_list)
    download_types = BDC_TABULAR_FILE_TYPES if not process_zip_files else BDC_TABULAR_FILE_TYPES + ['zip']
    download_list = [x.get("object_id") for x in all_files if x.get("data_format").lower() in download_types]
    client.download_files(download_list, show_progress=True, process_zip_files = process_zip_files)



def get_tabular_iterator(project_list: list[str] | None = None, file_list: list[str] | None = None ) -> tuple[list, Iterator]:
    manifest = NHLBI_BDC_CACHE_DIR.joinpath("project_to_files.tsv")
    files_df = pl.read_csv(manifest, separator="\t").cast({"project_id": pl.String})
    files_df = files_df.filter(
        pl.col("data_format").str.to_lowercase().is_in(BDC_TABULAR_FILE_TYPES)
        & pl.col("path").is_not_null()
    )
    if project_list is not None:
        files_df = files_df.filter(pl.col("project_id").is_in(project_list))
    if file_list is not None:
        files_df = files_df.filter(pl.col("object_id").is_in(file_list))
    project_files = (
        files_df.select(["project_id", "path", "object_id"])
        .rename({ "path": "file_paths", "object_id": "object_ids"})
        .group_by("project_id", maintain_order=True)
        .agg([ pl.col("file_paths"), pl.col("object_ids")])
        .with_columns(
            project_curie=pl.format("{}:{}", pl.lit(BDC_CURIE_PREFIX), pl.col("project_id"))
        )
        .select(["project_curie", "file_paths" , "object_ids"])
    )
    group_ids = project_files["project_curie"].to_list()
    return group_ids, project_files.iter_rows()
