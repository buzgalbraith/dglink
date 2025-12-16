"""
Extract knowledge graph information from DICOM files.

This module processes DICOM (Digital Imaging and Communications in Medicine) files
from Synapse projects to extract medical imaging metadata and extract biomedical
entities from unstructured text fields into a knowledge graph structure.
"""

from .constants import syn, RESOURCE_PATH, REPORT_PATH, UNSTRUCTURED_DICOM_FIELDS
from .nodes import NodeSet
from .edges import EdgeSet
from .utils import get_project_files, write_graph
import pydicom
import os
from bioregistry import normalize_curie
from indra.ontology.bio import bio_ontology
import logging
import tqdm
from gilda import annotate

import polars as pl

logger = logging.getLogger(__name__)


def process_dicom(
    file_id: str,
    node_set: NodeSet,
    edge_set: EdgeSet,
    dicom_identifiers: set,
    project_granularity: bool = False,
) -> tuple[NodeSet, EdgeSet, set, dict]:
    """Process a single DICOM file and extract metadata into the knowledge graph.

    Reads DICOM headers to extract structured metadata (patient info, series details,
    modality, etc.) and uses Gilda to ground unstructured text fields to biomedical
    ontology terms. Supports processing at either series-level or project-level granularity.

    Args:
        file_id: Synapse file ID for the DICOM file (e.g., 'syn12345678')
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update
        dicom_identifiers: Set of already-processed series/project identifiers to avoid duplicates
        project_granularity: If True, process one DICOM per project; if False, process all
            unique series (identified by studyId, assay, specimenID, individualID, timepoint)

    Returns:
        Tuple of (updated node_set, updated edge_set, updated dicom_identifiers, status dict)
        Status dict contains: project_id, file_id, and able_to_process flag

    Note:
        Creates DICOM_series nodes with structured metadata fields and uses entity grounding
        via Gilda to extract biomedical concepts from unstructured DICOM header fields.
    """
    source = set(["dicom_data", "experimental_data"])
    able_to_process = True
    annotations = syn.get_annotations(file_id)
    project_id = annotations.get("studyId", ["project_id_missing"])[0]
    ## try to process all DICOM series
    if not project_granularity:
        ## annotations do not have series identifier so using all this info as a proxy ##
        assay = annotations.get("assay", ["assay_missing"])[0]
        specimenID = annotations.get("specimenID", ["specimenID_missing"])[0]
        individualID = annotations.get("individualID", ["individualID_missing"])[0]
        experimentalTimepoint = annotations.get(
            "experimentalTimepoint", ["experimentalTimepoint_missing"]
        )[0]
        series_identifier = (
            project_id,
            assay,
            specimenID,
            individualID,
            experimentalTimepoint,
        )
    ## try to process one series per study
    else:
        series_identifier = project_id
    if series_identifier in dicom_identifiers:
        able_to_process = False
        # return node_set, edge_set, 0, dicom_identifiers
    else:
        dicom_identifiers.add(series_identifier)
        try:
            obj = syn.get(file_id)
            obj_path = obj.path
        except:
            able_to_process = False
            obj_path = None
        if obj_path is not None:
            header = pydicom.dcmread(obj_path)
            node_set.update_nodes(
                {
                    "curie:ID": header.get(
                        "SeriesInstanceUID", "SeriesInstanceUID_Missing"
                    ),
                    ":LABEL": "DICOM_series",
                    "name": header.get(
                        "SeriesInstanceUID", "SeriesInstanceUID_Missing"
                    ),
                    "file_id:string[]": file_id,
                    "source:string[]": source,
                    "PatientID": header.get("PatientID", ""),
                    "AccessionNumber": header.get("AccessionNumber", ""),
                    "Modality": header.get("Modality", ""),
                    "PatientSex": header.get("PatientSex", ""),
                    "PatientAge": header.get("PatientAge", ""),
                    "SOPClassUID": header.get("SOPClassUID", ""),
                    "Manufacturer": header.get("Manufacturer", ""),
                    "SeriesInstanceUID": header.get("SeriesInstanceUID", ""),
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": project_id,
                    ":END_ID": header.get(
                        "SeriesInstanceUID", "SeriesInstanceUID_Missing"
                    ),
                    ":TYPE": f"has_dicom",
                    "source:string[]": source,
                }
            )
            for dcm_field in UNSTRUCTURED_DICOM_FIELDS:
                res = header.get(str(dcm_field), None)
                ans = annotate(res)
                if ans:
                    nsid = ans[0].matches[0].term
                    node_set.update_nodes(
                        {
                            "curie:ID": normalize_curie(f"{nsid.db}:{nsid.id}"),
                            ":LABEL": bio_ontology.get_type(nsid.db, nsid.id),
                            "name": nsid.entry_name,
                            "file_id:string[]": file_id,
                            "source:string[]": source,
                            "raw_texts:string[]": res,
                        }
                    )
                    edge_set.update_edges(
                        {
                            ":START_ID": project_id,
                            ":END_ID": normalize_curie(f"{nsid.db}:{nsid.id}"),
                            "source:string[]": source,
                        }
                    )
    return (
        node_set,
        edge_set,
        dicom_identifiers,
        {
            "project_id": project_id,
            "file_id": file_id,
            "able_to_process": able_to_process,
        },
    )


def get_dicom_data(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    write_set: bool = False,
    project_granularity: bool = False,
    write_intermediate: bool = True,
    write_reports: bool = True,
) -> tuple[NodeSet, EdgeSet, list[pl.DataFrame]]:
    """Process DICOM files from multiple Synapse projects and build knowledge graph.

    Main orchestration function that discovers DICOM files (.dcm) in specified projects,
    extracts medical imaging metadata and grounded biomedical entities, and constructs
    a knowledge graph. Supports both series-level and project-level processing granularity.

    Args:
        project_ids: List of Synapse project IDs to process
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update
        write_set: If True, write final knowledge graph to disk
        project_granularity: If True, process one DICOM per project; if False, process
            all unique series per project
        write_intermediate: If True, write graph after each project
        write_reports: If True, generate TSV reports of processing status

    Returns:
        Tuple of (updated node_set, updated edge_set, list of processing report DataFrames)

    Note:
        Uses Gilda for entity grounding of unstructured DICOM text fields to biomedical
        ontology terms. Intermediate graphs and reports are written to RESOURCE_PATH/artifacts
        and REPORT_PATH respectively.

    Examples:
        >>> # Process all series from projects
        >>> nodes, edges, reports = get_dicom_data(
        ...     project_ids=['syn12345', 'syn67890'],
        ...     node_set=NodeSet(),
        ...     edge_set=EdgeSet(),
        ...     project_granularity=False
        ... )
        >>>
        >>> # Process one DICOM per project for quick overview
        >>> nodes, edges, reports = get_dicom_data(
        ...     project_ids=['syn12345'],
        ...     node_set=NodeSet(),
        ...     edge_set=EdgeSet(),
        ...     project_granularity=True
        ... )
    """
    logger.info(f"Adding tabular experimental data for {len(project_ids)} projects")
    process_files = []
    dicom_identifiers = set()
    i = 0
    for project_id in tqdm.tqdm(project_ids):
        i = i + 1
        project_files = get_project_files(
            project_syn_id=project_id, file_types=[".dcm"], as_list=True
        )

        logger.info(
            f"adding DCM experimental data project {project_id}\n\
                    This is project {i} out of {len(project_ids)+1} \n\
                    There are {len(project_files)} total files to parse."
        )
        i = i + 1
        for file_id in tqdm.tqdm(project_files):
            node_set, edge_set, dicom_identifiers, able_to_process = process_dicom(
                file_id=file_id,
                node_set=node_set,
                edge_set=edge_set,
                dicom_identifiers=dicom_identifiers,
                project_granularity=project_granularity,
            )
            process_files.append(able_to_process)
        if write_intermediate:
            write_graph(
                node_set=node_set,
                edge_set=edge_set,
                source_filter=True,
                strict=True,
                source_name=["dicom_data", "experimental_data"],
                resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
            )

    ## write a sub-graph with just dicom experimental data
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name=["dicom_data", "experimental_data"],
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    processed_df = pl.from_dicts(process_files)
    if write_reports:
        os.makedirs(REPORT_PATH, exist_ok=True)
        processed_df.write_csv(
            os.path.join(REPORT_PATH, "dicom_file_report.tsv"), separator="\t"
        )

    return node_set, edge_set, [processed_df]
