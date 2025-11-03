import os
from pathlib import Path
import synapseclient

syn = synapseclient.login()
DGLINK_CACHE = Path.joinpath(Path(os.getenv("HOME")), ".dglink")
RESOURCE_PATH = "dglink/resources/graph/"
REPORT_PATH = "dglink/resources/reports/"
SEMANTIC_SEARCH_RESOURCE_PATH = "dglink/applications/semantic_search/neo4j/graph"
NODE_ATTRIBUTES = [
    "curie:ID",
    ":LABEL",
    "name",
    "raw_texts:string[]",
    "columns:string[]",
    "iri",
    "file_id:string[]",
    "tool_type",
    "DOI",
    "source:string[]",
    "study_url",
]
EDGE_ATTRIBUTES = [
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "source:string[]",
    "jacquard_score",
    "score_cutoff",
    "intersection_score",
    "union_score",
    "shared_edges:string[]",
    "head_only_edges:string[]",
    "tail_only_edges:string[]",
    "edge_weights:string[]",
]

FILE_TYPES = [
    ".tsv",
    ".xls",
    ".xlsx",
    ".csv",
]


RESOURCE_TYPES = [
    "metadata",
    "projects",
    "publications",
    "wiki",
    "tools",
    "experimental_data",
]
