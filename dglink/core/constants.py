import os
from pathlib import Path
import synapseclient

syn = synapseclient.login()
DGLINK_CACHE = Path.joinpath(Path(os.getenv("HOME")), ".dglink")
RESOURCE_PATH = "dglink/resources/graph/"
REPORT_PATH = "dglink/resources/reports/"
SEMANTIC_SEARCH_RESOURCE_PATH = "dglink/applications/semantic_search/neo4j/graph"
NODE_ATTRIBUTES = [
    ## core fields - all nodes should have ths other fields are optional
    "curie:ID",
    ":LABEL",
    "name",
    "iri",
    "source:string[]",
    ## Synapse project field
    "study_url",
    ## tabular data fields
    "raw_texts:string[]",
    "columns:string[]",
    "file_id:string[]",
    ## DICOM Fields
    "PatientID",
    "AccessionNumber",
    "Modality",
    "PatientSex",
    "PatientAge",
    "SOPClassUID",
    "Manufacturer",
    ## VCF fields
    "chrom",
    "pos",
    "ref",
    "alt",
    "genotype",
    "quality",
    ## publication fields
    "DOI",
    ## nf data portal tool fields (maybe move elsewhere)
    "tool_type",
]
EDGE_ATTRIBUTES = [
    ## core fields - all edges should have ths other fields are optional
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "source:string[]",
    ## predicted similar project fields
    "jacquard_score",
    "score_cutoff",
    "intersection_score",
    "union_score",
    "shared_edges:string[]",
    "head_only_edges:string[]",
    "tail_only_edges:string[]",
    "edge_weights:string[]",
]

TABULAR_FILE_TYPES = [
    ".tsv",
    ".xls",
    ".xlsx",
    ".csv",
]

VCF_FILE_TYPES = [
    ".vcf",
    ".gvcf",
    ".vcf.gz",
    ".gvcf.gz",
]

RESOURCE_TYPES = [
    "metadata",
    "projects",
    "publications",
    "wiki",
    "tools",
    "tabular_data",
]
UNSTRUCTURED_DICOM_FIELDS = [
    "ImageComments",
]
