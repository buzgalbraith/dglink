"""
Constants specific to the NCI General Data Commons portal
"""

import os

DATA_ENDPNT = "https://api.gdc.cancer.gov/data"
CASES_ENDPNT = "https://api.gdc.cancer.gov/cases/"
NODE_ATTRIBUTES = [
    ## core fields - all nodes should have ths other fields are optional
    "curie:ID",
    ":LABEL",
    "name",
    "iri",
    "source:string[]",
    "raw_texts:string[]",
    "columns:string[]",
    "file_id:string[]",
    ## sample_types
    "tumor_descriptor",
    "specimen_type",
    "sample_type",
    "tissue_type",
    "preservation_method",
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

## fields to take from files for csv
FILE_FIELDS = [
    "access",
    "data_category",
    "data_format",
    "data_type",
    "experimental_strategy",
    "file_name",
    "file_size",
]
home_dir: str = os.getenv("HOME") or "/"
GDC_CACHE_DIR = os.path.join(
    home_dir,
    ".data",
    "gdc",
)
