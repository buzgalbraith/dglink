import os
from pathlib import Path

DGLINK_CACHE = Path.joinpath(Path(os.getenv("HOME")), ".dglink")
RESOURCE_PATH = "dglink/resources/graph/"
REPORT_PATH = "dglink/resources/reports/"
SEMANTIC_SEARCH_RESOURCE_PATH = "dglink/applications/semantic_search/neo4j/graph"

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
    ["vcf_data", "experimental_data"],
    ["tabular_data", "experimental_data"],
    ["dicom_data", "experimental_data"],
]
UNSTRUCTURED_DICOM_FIELDS = [
    "ImageComments",
]
