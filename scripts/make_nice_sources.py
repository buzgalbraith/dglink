"""
small helper script make the source names more clear for the demo
"""

import polars as pl
from dglink.core.constants import SEMANTIC_SEARCH_RESOURCE_PATH

nodes = pl.read_csv(
    "dglink/applications/semantic_search/neo4j/graph/nodes.tsv", separator="\t"
)
edges = pl.read_csv(
    "dglink/applications/semantic_search/neo4j/graph/edges.tsv", separator="\t"
)
resources = ["nodes", "edges"]
col = "source:string[]"
val = "experimental_data"
og_formats = [val, "vcf", "dicom"]
new_formats = [f"tabular_{val}", f"vcf_{val}", f"dicom_{val}"]

for resource in resources:
    df = pl.read_csv(f"{SEMANTIC_SEARCH_RESOURCE_PATH}/{resource}.tsv", separator="\t")
    for og, new in zip(og_formats, new_formats):
        df = df.with_columns(pl.col(col).str.replace_all(og, new))
    df.write_csv(f"{SEMANTIC_SEARCH_RESOURCE_PATH}/{resource}.tsv", separator="\t")
