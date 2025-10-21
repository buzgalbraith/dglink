import os
from pathlib import Path
import synapseclient

syn = synapseclient.login()
DGLINK_CACHE = Path.joinpath(Path(os.getenv("HOME")), ".dglink")
RESOURCE_PATH = "dglink/resources/graph/"


NODE_ATTRIBUTES = [
    "curie:ID",
    ":LABEL",
    "name",
    "raw_texts:string[]",
    "columns:string[]",
    "iri",
    "file_id:string[]",
    "tool_type",
    "project_url",
    "DOI",
    "source:string[]",
    "study_url",
]
EDGE_ATTRIBUTES = [
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "source:string[]",
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
