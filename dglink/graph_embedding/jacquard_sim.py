import pandas
import re
from itertools import combinations
import json
import tqdm
from math import comb

RESOURCE_DIR = "dglink/graph_embedding/resources/"

def check_related_study_exists(edges_df, id_1, id_2):
    """checks if a pair of studies has a related edge"""
    df = edges_df[edges_df[":TYPE"] == "has_relatedStudies"]
    forward_df = df[(df[":START_ID"] == id_1) & (df[":END_ID"] == id_2)]
    backward_df = df[(df[":START_ID"] == id_2) & (df[":END_ID"] == id_1)]
    return (len(forward_df) + len(backward_df)) > 0

def get_projects_to_edges(edges_df):
    """get mapping project_id -> entity -> edge_type, which is used for calculating jacquard sim"""
    all_project_ids = set(
        filter(
            lambda x: re.match(r"^syn\d*$", str(x)) is not None,
            edges_df[":START_ID"].unique(),
        )
    ) | set(
        filter(
            lambda x: re.match(r"^syn\d*$", str(x)) is not None,
            edges_df[":END_ID"].unique(),
        )
    )
    ## mapping project_id -> entity -> edge_type
    project_to_edges_map = {project_id: dict() for project_id in all_project_ids}
    for project_id in all_project_ids:
        # get edges where that project (or its wiki ) is the hed node
        head_edges = edges_df.loc[
            edges_df[":START_ID"].isin([project_id, f"{project_id}:Wiki"]),
        ]
        for x, _ in head_edges.groupby(by=[":END_ID", ":TYPE"]).first().itertuples():
            if x[0] not in project_to_edges_map[project_id]:
                project_to_edges_map[project_id][x[0]] = set()
            project_to_edges_map[project_id][x[0]].add(x[1])
        # get edges where that project (or its wiki) is the tail node
        tail_edges = edges_df.loc[
            edges_df[":END_ID"].isin([project_id, f"{project_id}:Wiki"]),
        ]
        for x, _ in tail_edges.groupby(by=[":START_ID", ":TYPE"]).first().itertuples():
            if x[0] not in project_to_edges_map[project_id]:
                project_to_edges_map[project_id][x[0]] = set()
            project_to_edges_map[project_id][x[0]].add(x[1])
    return project_to_edges_map, all_project_ids


def get_entity_names():
    with open(f"{RESOURCE_DIR}/entity_names.json", mode="r") as f:
        name_maps = json.load(f)  # indent for pretty-printing
    return name_maps


def get_edge_weights():
    ## get a dictionary weight mapping for each edge type
    edge_weights = {e_type: 1 for e_type in edges_df[":TYPE"].unique()}
    ## for now just re-weighting a few node-types
    edge_weights["mentions"] = 0.5
    edge_weights["has_fundingAgency"] = 2
    edge_weights["has_institutions"] = 2
    edge_weights["has_diseaseFocus"] = 2
    edge_weights["has_manifestation"] = 2
    edge_weights["has_initiative"] = 3
    edge_weights["usesTool"] = 3
    return edge_weights


def jacquard_sim(pid_1, pid_2):
    intersection_score = 0
    union_score = 0
    all_entities_combined = set(project_to_edges_map[pid_1].keys()) | set(
        project_to_edges_map[pid_2].keys()
    )
    edge_attrs = {
        ":START_ID": pid_1,
        ":END_ID": pid_2,
        "jacquard_score": "",
        "score_cutoff": cutoff,
        "intersection_score": "",
        "union_score": "",
        "shared_edges:string[]": set(),
        "head_only_edges:string[]": set(),
        "tail_only_edges:string[]": set(),
        "edge_weights:string[]": edge_weights,
        ":TYPE": "predicted_relatedStudies_GL",
    }
    for entity in all_entities_combined:
        e_name = name_maps.get(entity, entity)
        types_1 = project_to_edges_map[pid_1].get(entity, set())
        types_2 = project_to_edges_map[pid_2].get(entity, set())

        # Sum weights for intersection
        for edge_type in types_1 & types_2:
            edge_attrs["shared_edges:string[]"].add(f"{edge_type}:{e_name}")
            intersection_score += edge_weights.get(edge_type, 1)

        # Sum weights for union
        for edge_type in types_1 | types_2:
            if edge_type in types_1.difference(types_2):
                edge_attrs["head_only_edges:string[]"].add(f"{edge_type}:{e_name}")
            elif edge_type in types_2.difference(types_1):
                edge_attrs["tail_only_edges:string[]"].add(f"{edge_type}:{e_name}")
            union_score += edge_weights.get(edge_type, 1)
    jacquard_score = intersection_score / union_score if union_score > 0 else 0
    edge_attrs["jacquard_score"] = jacquard_score
    edge_attrs["intersection_score"] = intersection_score
    edge_attrs["union_score"] = union_score
    return jacquard_score, edge_attrs


def write_edges_with_attrs(edges, path):
    attributes = edges[0].keys()
    with open(path, "w") as f:
        f.write("\t".join(attributes) + "\n")
        for edge in edges:
            write_str = f""
            for col in attributes:
                val = edge[col]
                if type(val) == set:
                    # if len(val) > 20:
                    #     val = list(val)[:20]  ## limit max number of elements to 20
                    val = f'"{";".join(val)}"'
                elif type(val) == dict:
                    res = [":".join([x, str(val[x])]) for x in val]
                    val = f'"{";".join(res)}"'
                ## take out any weird line breaks

                val = str(val).replace('"', "").replace("'", "")
                write_str += val.replace("\n", "") + "\t"
            f.write(write_str[:-1] + "\n")


if __name__ == "__main__":
    edges_df = pandas.read_csv(
        f"{RESOURCE_DIR}/non_related_projects_edges.tsv", sep="\t"
    )
    cutoff = 0.20
    project_to_edges_map, all_project_ids = get_projects_to_edges(edges_df=edges_df)
    edge_weights = get_edge_weights()
    name_maps = get_entity_names()
    res = []
    edges = []
    related_project_edges_df = pandas.read_csv(
        f"{RESOURCE_DIR}/related_project_edges.tsv", sep="\t"
    )
    for pid_1, pid_2 in tqdm.tqdm(
        combinations(all_project_ids, 2), total=comb(len(all_project_ids), 2)
    ):
        jacquard_score, edge_attrs = jacquard_sim(pid_1=pid_1, pid_2=pid_2)
        has_related_study = check_related_study_exists(
            related_project_edges_df, pid_1, pid_2
        )
        res.append(
            {
                "id1": pid_1,
                "id2": pid_2,
                "entity_id1": len(project_to_edges_map[pid_1]),
                "entity_id2": len(project_to_edges_map[pid_2]),
                "jacquard_score": jacquard_score,
                "has_related_study": has_related_study,
            }
        )
        if jacquard_score >= cutoff:
            edges.append(edge_attrs)

    df = pandas.DataFrame.from_records(res)
    df.sort_values(by=["jacquard_score"])
    n = 5
    sorted_df = df[(df["entity_id2"] > n) & (df["entity_id1"] > n)].sort_values(
        by=["jacquard_score"]
    )
    # sorted_df.to_csv("jac.csv")

    write_edges_with_attrs(path="related_edges_gl.tsv", edges=edges)

    ## cutoff analysis
    cutoff = 0.15
    count_known_edges = lambda x: sum(x["has_related_study"])
    total = count_known_edges(df)
    after_cutoff = df[df["jacquard_score"] >= cutoff]
    remaining = count_known_edges(after_cutoff)
    print(
        f"Total known {total}, remaining known : {remaining} ({remaining/total}), Total predicted {len(after_cutoff)}"
    )


