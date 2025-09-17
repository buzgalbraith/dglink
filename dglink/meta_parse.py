"""
The goal of this script is to test out parsing entities from synapse meta data,
"""

import synapseclient
import gilda

syn = synapseclient.login()

all_project_ids = [
    "syn2343195",
    "syn5562324",
    "syn27761862",
    "syn4939874",
    "syn4939876",
    "syn4939906",
    "syn4939916",
    "syn7217928",
    "syn8016635",
    "syn11638893",
    "syn11817821",
    "syn21641813",
    "syn21642027",
    "syn21650493",
    "syn21984813",
    "syn23639889",
    "syn51133914",
    "syn52740594",
]

ground_fields = {
    "manifestation": ["phenotype"],
    "diseaseFocus": ["disease"],
}

direct_fields = [
    "fundingAgency",
    "studyStatus",
    "initiative",
    "relatedStudies",
    "parentId",
    "dataStatus",
    "institutions",
    "dataType",
    "grantDOI",
]

## these are fields that have entities which may not be from a specific type of entity
namespace_ambiguous_fields = ["studyName", "name", "keywords"]


def load_existing_graph():
    """read in the files already in nodes and edges as sets"""
    existing_nodes = set()
    existing_relations = set()
    with open("dglink/resources/nodes.tsv", "r") as f:
        for row in f.readlines()[1:]:
            existing_nodes.add(tuple(row.strip().split("\t")))
    with open("dglink/resources/edges.tsv", "r") as f:
        for row in f.readlines()[1:]:
            existing_relations.add(tuple(row.strip().split("\t")))
    return existing_nodes, existing_relations


def get_annotated_fields(whole_study):
    """parse the set of fields that need to be annotated with Gilda"""
    annotated_nodes = set()
    annotated_relations = set()
    for field in ground_fields:
        if field in whole_study.keys():
            field_val = (
                whole_study[field]
                if type(whole_study[field]) == list
                else [whole_study[field]]
            )
            ## loop through in case list
            for entry in field_val:
                ans = gilda.annotate(entry)
                if ans:
                    entry = f"{ans[0].matches[0].term.db}:{ans[0].matches[0].term.id}"
                    for alternate_field in ground_fields[field]:
                        annotated_nodes.add((entry, alternate_field))
                        annotated_relations.add(
                            (project_id, entry, f"has_{alternate_field}")
                        )
                ### add the primary terms
                annotated_nodes.add((entry, field))
                annotated_relations.add((project_id, entry, f"has_{field}"))
    return annotated_nodes, annotated_relations


def get_direct_fields(whole_study):
    """parse the set of fields that do not need to be annotated with Gilda"""
    direct_nodes = set()
    direct_relations = set()
    for field in direct_fields:
        if field in whole_study.keys():
            field_val = (
                whole_study[field]
                if type(whole_study[field]) == list
                else [whole_study[field]]
            )
            ## loop through in case list
            for entry in field_val:
                direct_nodes.add((entry, field))
                direct_relations.add((project_id, entry, f"has_{field}"))
    return direct_nodes, direct_relations


if __name__ == "__main__":
    ## all projects have an accessible list of funding agencies as well as a markdown from the wiki
    nodes = set()
    relations = set()
    for project_id in all_project_ids:
        whole_study = syn.get(project_id)
        annotated_nodes, annotated_relations = get_annotated_fields(
            whole_study=whole_study
        )
        direct_nodes, direct_relations = get_direct_fields(whole_study=whole_study)
        nodes.add((project_id, "Project"))
        nodes = nodes | annotated_nodes | direct_nodes
        relations = relations | annotated_relations | direct_relations

    ## read in existing nodes and edges to avoid duplicates
    existing_nodes, existing_relations = load_existing_graph()
    ## combine the sets
    nodes = [["curie:ID", ":LABEL"]] + list(nodes | existing_nodes)
    relations = [[":START_ID", ":END_ID", ":TYPE"]] + list(
        relations | existing_relations
    )
    # # # Dump nodes into nodes.tsv and relations into edges.tsv
    with open("dglink/resources/nodes.tsv", "w") as f:
        for row in nodes:
            f.write("\t".join(row) + "\n")
    with open("dglink/resources/edges.tsv", "w") as f:
        for row in relations:
            f.write("\t".join(row) + "\n")
