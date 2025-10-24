"""
Reads in existing graph from `dglink/resources/graph` then saves one tsv with only the related project edges and another with out them (for training the model)
"""

import pandas
import os
import json
from dglink.core.constants import RESOURCE_PATH
save_dir = "dglink/applications/project_similarity/resources"


if __name__ == "__main__":
    ## make a directory to store the results and copy all existing edges
    os.makedirs(save_dir, exist_ok=True)
    ## read in the edges
    edges_df = pandas.read_csv(f'{RESOURCE_PATH}/edges.tsv', sep="\t")
    nodes_df = pandas.read_csv(f'{RESOURCE_PATH}/nodes.tsv', sep="\t")
    ## now get a mapping for all names

    names_mapping = {}
    for _, row in nodes_df.iterrows():
        curie = row["curie:ID"]
        names_mapping[curie] = curie
        names_mapping[row["name"]] = curie

    ## make to tsv files one with all edges that are not on related projects another with only related project edges
    related_edges = edges_df[edges_df[":TYPE"] == "has_relatedStudies"]
    non_related_edges = edges_df[edges_df[":TYPE"] != "has_relatedStudies"]
    related_edges.to_csv(f"{save_dir}/related_project_edges.tsv", sep="\t", index=False)
    non_related_edges.to_csv(
        f"{save_dir}/non_related_projects_edges.tsv", sep="\t", index=False
    )
    with open(f"{save_dir}/entity_names.json", mode="w") as f:
        json.dump(names_mapping, f, indent=4)  