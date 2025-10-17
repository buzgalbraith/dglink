import os
from pathlib import Path
import synapseclient

syn = synapseclient.login()
DGLINK_CACHE = Path.joinpath(Path(os.getenv("HOME")), ".dglink")

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
    "source", 
    "study_url",
]
EDGE_ATTRIBUTES = [
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "source",
]
