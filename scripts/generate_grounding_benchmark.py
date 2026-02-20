"""
This can be used to generate a random sample of groundings from nodes.tsv
"""

import polars as pl
from dglink.portals.nf_data_portal import syn

df = pl.read_csv("dglink/applications/mcp/neo4j/graph/nodes.tsv", separator="\t")
df = df.sample(shuffle=True, fraction=1.0)
df = (
    df.filter(~pl.col("raw_texts:string[]").eq(""))
    .filter(pl.col("source:string[]").eq("tabular_experimental_data"))
    .with_columns(
        raw_text=pl.col("raw_texts:string[]").str.split(";").list.get(0),
        file_id=pl.col("file_id:string[]").str.split(";").list.get(0),
    )
    .select(["curie:ID", "name", "raw_text", "file_id"])[:100]
)
records = []
for row in df.iter_rows(named=True):
    fid = row.get("file_id")
    res = syn.get(fid)
    records.append(
        {
            "file_id": fid,
            "file_name": res.get("name"),
            "study_id": res.get("studyId")[0],
        }
    )
df_2 = pl.from_dicts(records).unique()
merges = (
    df.join(df_2, left_on="sources", right_on="file_id", how="left")
    .sample(shuffle=True, fraction=1.0)
    .select(["raw_text", "name", "curie:ID", "file_name", "study_id"])
    .write_csv("example_grounding.tsv", separator="\t")
)
