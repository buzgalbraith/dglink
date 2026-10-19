"""
Identify heart lung and blood diseases parsed from the NHLBI graph and write them to a TSV.
"""

import pyobo
import polars as pl
from dglink.core.constants import RESOURCE_PATH

## map NHLBI disease focuses to MESH roots ##
DISEASE_TO_ROOT = {"heart": "D002318", "lung": "D008171", "blood": "D006402"}


def get_disease_nodes(disease_focus: str) -> pl.DataFrame:
    disease_root = DISEASE_TO_ROOT[disease_focus]
    disease_nodes = mesh.descendants(disease_root)
    disease_nodes = [f"mesh:{x}" for x in disease_nodes]
    present_diseases = nodes_df.filter(pl.col("curie:ID").is_in(disease_nodes))
    df = present_diseases[["curie:ID", "name"]]
    df.write_csv(f"{disease_focus}_diseases.txt")
    return df


if __name__ == "__main__":
    ## load onto and get cardiovascular descendent ##
    mesh = pyobo.get_ontology("mesh")
    ## load nodes ##
    nodes_df = pl.read_csv(f"{RESOURCE_PATH}/nodes.tsv", separator="\t")
    ## find nodes associated with each disease and write them to a tsv ##
    for disease_focus in DISEASE_TO_ROOT:
        get_disease_nodes(disease_focus=disease_focus)
