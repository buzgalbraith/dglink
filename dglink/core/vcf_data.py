"""
Extract knowledge graph information from VCF (Variant Call Format) files.

This module processes VCF files from Synapse projects to extract genetic variants,
sample information, and metadata into a knowledge graph structure.
"""

from .constants import syn, VCF_FILE_TYPES, RESOURCE_PATH, REPORT_PATH
from .nodes import NodeSet
from .edges import EdgeSet
from .utils import get_project_files, write_graph
import vcf
import re
import os
from bioregistry import normalize_curie, get_iri, parse_curie
import logging
import tqdm
import polars as pl

logger = logging.getLogger(__name__)
data_source = set(["vcf_data", "experimental_data"])


def extract_variants(
    obj, node_set: NodeSet, edge_set: EdgeSet
) -> tuple[NodeSet, EdgeSet]:
    """Extract genetic variants from a VCF file and add them to the knowledge graph.

    Parses VCF files to extract variant identifiers (dbSNP rs IDs) and creates:
    - Nodes for each genetic variant with normalized CURIEs and IRIs
    - Edges connecting samples to their variants

    Args:
        obj: Synapse file object containing the VCF file path and metadata
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update

    Returns:
        Tuple of (updated node_set, updated edge_set)

    Note:
        Attempts to parse using PyVCF3 first, falls back to direct file parsing if that fails.
        Only processes variants with dbSNP rs identifiers.
    """
    file_id = obj.get("id", "")
    ## first try doing this pyvcf3
    compressed = obj.path.endswith(".gz")
    read_cmd = "rb" if compressed else "r"
    try:
        with open(obj.path, mode=read_cmd) as f:
            vcf_reader = vcf.Reader(f, compressed=compressed)
            ## extract variant info
            for record in vcf_reader:
                raw_id = record.ID
                if raw_id is not None:
                    ## ids are from dbSNP (the NCBI Single Nucleotide Polymorphism Database) ##
                    if raw_id.startswith("rs"):
                        curie = normalize_curie(f"dbsnp:{raw_id}")
                        parsed_curie = parse_curie(curie)
                        node_set.update_nodes(
                            {
                                "curie:ID": curie,
                                ":LABEL": "genetic_variant",  ## vcf files are structured so know this will be the only entity type.
                                "iri": get_iri(
                                    prefix=parsed_curie.prefix,
                                    identifier=parsed_curie.identifier,
                                ),
                                "file_id:string[]": file_id,
                                "source:string[]": data_source,
                            }
                        )
                        ## add edges between samples and the variant
                        for sample in vcf_reader.samples:
                            edge_set.update_edges(
                                {
                                    ":START_ID": sample,
                                    ":END_ID": curie,
                                    ":TYPE": "has_genetic_variant",
                                    "source:string[]": data_source,
                                }
                            )
    ## if this fails, try to directly read teh file.
    except:
        with open(obj.path, read_cmd) as f:
            ## skip header lines
            for line in f:
                if line.startswith("#"):
                    continue
                fields = line.strip().split("\t")
                if len(fields) > 2:
                    raw_id = fields[2]  # ID is column 3 (0-indexed: column 2)
                    if raw_id is not None:
                        ## ids are from dbSNP (the NCBI Single Nucleotide Polymorphism Database) ##
                        if raw_id.startswith("rs"):
                            curie = normalize_curie(f"dbsnp:{raw_id}")
                            parsed_curie = parse_curie(curie)
                            node_set.update_nodes(
                                {
                                    "curie:ID": curie,
                                    ":LABEL": "genetic_variant",  ## vcf files are structured so know this will be the only entity type.
                                    "iri": get_iri(
                                        prefix=parsed_curie.prefix,
                                        identifier=parsed_curie.identifier,
                                    ),
                                    "file_id:string[]": file_id,
                                    "source:string[]": data_source,
                                }
                            )
                            ## add edges between samples and the variant
                            for sample in vcf_reader.samples:
                                edge_set.update_edges(
                                    {
                                        ":START_ID": sample,
                                        ":END_ID": curie,
                                        ":TYPE": "has_genetic_variant",
                                        "source:string[]": data_source,
                                    }
                                )
    return node_set, edge_set


def extract_vcf_metadata(
    obj, node_set: NodeSet, edge_set: EdgeSet
) -> tuple[NodeSet, EdgeSet]:
    """Extract metadata and sample information from VCF file headers.

    Parses VCF metadata to create knowledge graph nodes and relationships for:
    - File format specifications
    - Reference genome information
    - Processing commands (source and GATK command lines)
    - Sample information and relationships to study

    Creates edges connecting samples to their study, file format, reference genome,
    and processing commands.

    Args:
        obj: Synapse file object containing the VCF file path and metadata
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update

    Returns:
        Tuple of (updated node_set, updated edge_set)
    """
    file_id = obj.get("id", "")
    study_id = obj.get("studyId", ["study_id_missing"])[0]
    compressed = obj.path.endswith(".gz")
    read_cmd = "rb" if compressed else "r"
    with open(obj.path, mode=read_cmd) as f:
        compressed = obj.path.endswith(".gz")
        vcf_reader = vcf.Reader(f, compressed=compressed)
    meta = vcf_reader.metadata
    vcf_format = meta.get("fileformat", "vcf_format_missing")
    reference = meta.get("reference", "reference_fasta_missing")
    vcf_cmnds = meta.get("source", ["vcf_command_missing"])
    node_set.update_nodes(
        {
            "curie:ID": vcf_format,
            ":LABEL": "VCF_file_format",
            "name": vcf_format,
            "file_id:string[]": file_id,
            "source:string[]": data_source,
        }
    )
    node_set.update_nodes(
        {
            "curie:ID": reference,
            ":LABEL": "VCR_reference",
            "name": reference,
            "file_id:string[]": file_id,
            "source:string[]": data_source,
        }
    )
    ## extract the sources
    for source in vcf_cmnds:
        node_set.update_nodes(
            {
                "curie:ID": source,
                ":LABEL": "VCF_command",
                "name": source,
                "file_id:string[]": file_id,
                "source:string[]": data_source,
            }
        )
    ## source and commands are similar so merge to one node type
    ## extract the commands
    cmnds = meta.get("GATKCommandLine", [])
    for cmnd in cmnds:
        cmnd_id = cmnd.get("ID", "missing_command")
        node_set.update_nodes(
            {
                "curie:ID": cmnd_id,
                ":LABEL": "VCF_command",
                "name": cmnd_id,
                "file_id:string[]": file_id,
                "source:string[]": data_source,
            }
        )
        vcf_cmnds.append(cmnd_id)
    ## go through all possible samples
    for sample in vcf_reader.samples:
        ## add sample as node
        node_set.update_nodes(
            {
                "curie:ID": sample,
                ":LABEL": "sample",
                "name": sample,
                "file_id:string[]": file_id,
                "source:string[]": data_source,
            }
        )
        ## add edge between sample and project
        edge_set.update_edges(
            {
                ":START_ID": study_id,
                ":END_ID": sample,
                ":TYPE": "has_sample",
                "source:string[]": data_source,
            }
        )
        ## add edges from each sample to the file format and reference
        edge_set.update_edges(
            {
                ":START_ID": sample,
                ":END_ID": vcf_format,
                ":TYPE": "has_vcf_format",
                "source:string[]": data_source,
            }
        )
        edge_set.update_edges(
            {
                ":START_ID": sample,
                ":END_ID": reference,
                ":TYPE": "has_vcf_reference",
                "source:string[]": data_source,
            }
        )
        ## add each of the command ids to the sample
        for vcf_cmnd in vcf_cmnds:
            edge_set.update_edges(
                {
                    ":START_ID": sample,
                    ":END_ID": vcf_cmnd,
                    ":TYPE": "has_vcf_command",
                    "source:string[]": data_source,
                }
            )
    return node_set, edge_set


def parse_vcf_file(
    file_id: str,
    node_set: NodeSet,
    edge_set: EdgeSet,
    project_id: str,
    process_variants: bool = True,
) -> tuple[NodeSet, EdgeSet, dict]:
    """Parse a single VCF file and extract all relevant information into the knowledge graph.

    Downloads the VCF file from Synapse and extracts both variants and metadata.

    Args:
        file_id: Synapse file ID (e.g., 'syn12345678')
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update
        project_id: Synapse project ID containing the file
        process_variants: If True, extract variant information; if False, only extract metadata

    Returns:
        Tuple of (updated node_set, updated edge_set, processing status dict)
        Status dict contains: project_id, file_id, and able_to_process flag
    """
    able_to_process = True
    try:
        obj = syn.get(file_id)
        file_path = obj.path
    except:
        file_path = None
    if file_path is None:
        able_to_process = False
    else:
        ## extract the variants
        if process_variants:
            node_set, edge_set = extract_variants(
                obj=obj, node_set=node_set, edge_set=edge_set
            )
        ## extract the meta data
        node_set, edge_set = extract_vcf_metadata(
            obj=obj, node_set=node_set, edge_set=edge_set
        )
    return (
        node_set,
        edge_set,
        {
            "project_id": project_id,
            "file_id": file_id,
            "able_to_process": able_to_process,
        },
    )


def get_vcf_data(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    write_set: bool = False,
    process_compressed_files: bool = True,
    process_variants: bool = True,
    write_intermediate: bool = True,
    write_reports: bool = True,
) -> tuple[NodeSet, EdgeSet, list[pl.DataFrame]]:
    """Process VCF files from multiple Synapse projects and build knowledge graph.

    Main orchestration function that discovers VCF files in specified projects,
    processes them to extract variants and metadata, and constructs a knowledge graph.
    Supports both compressed (.vcf.gz) and uncompressed (.vcf) files.

    Args:
        project_ids: List of Synapse project IDs to process
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update
        write_set: If True, write final knowledge graph to disk
        process_compressed_files: If True, process .vcf.gz files; if False, skip them
        process_variants: If True, extract variant data; if False, only extract metadata
        write_intermediate: If True, write graph after each project
        write_reports: If True, generate TSV reports of processing status

    Returns:
        Tuple of (updated node_set, updated edge_set, list of processing report DataFrames)

    Note:
        Intermediate graphs and reports are written to RESOURCE_PATH/artifacts and REPORT_PATH.
    """
    logger.info(f"Adding tabular experimental data for {len(project_ids)} projects")
    process_files = []
    i = 0
    vcf_formats = (
        VCF_FILE_TYPES
        if process_compressed_files
        else [x for x in VCF_FILE_TYPES if not x.endswith("gz")]
    )
    for project_id in tqdm.tqdm(project_ids):
        i = i + 1
        project_files = get_project_files(
            project_syn_id=project_id, file_types=vcf_formats, as_list=True
        )

        logger.info(
            f"adding VCF experimental data project {project_id}\n\
                    This is project {i} out of {len(project_ids)+1} \n\
                    There are {len(project_files)} total files to parse."
        )
        i = i + 1
        for file_id in tqdm.tqdm(project_files):
            node_set, edge_set, able_to_process = parse_vcf_file(
                file_id=file_id,
                node_set=node_set,
                edge_set=edge_set,
                process_variants=process_variants,
                project_id=project_id,
            )
            process_files.append(able_to_process)
        if write_intermediate:
            write_graph(
                node_set=node_set,
                edge_set=edge_set,
                source_filter=True,
                strict=True,
                source_name="vcf_data",
                resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
            )

    ## write a sub-graph with just vcf experimental data
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="vcf_data",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    processed_df = pl.from_dicts(process_files)
    if write_reports:
        os.makedirs(REPORT_PATH, exist_ok=True)
        processed_df.write_csv(
            os.path.join(REPORT_PATH, "vcf_file_report.tsv"), separator="\t"
        )

    return node_set, edge_set, [processed_df]
