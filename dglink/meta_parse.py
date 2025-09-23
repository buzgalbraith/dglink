"""
The goal of this script is to load the meta data and wiki information from each project into the KG.
"""

import synapseclient
import gilda
from indra.ontology.bio import bio_ontology

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

ground_fields = [
    "manifestation",
    "diseaseFocus",
]


unground_fields = [
    "manifestation",
    "diseaseFocus",
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


wiki_fields = ["markdown", "title"]


def load_existing_graph(modifier=""):
    """read in the files already in nodes and edges as sets"""
    existing_nodes = set()
    existing_relations = set()
    with open(f"dglink/resources/{modifier}nodes.tsv", "r") as f:
        for row in f.readlines()[1:]:
            existing_nodes.add(tuple(row.strip().split("\t")))
    with open("dglink/resources/edges.tsv", "r") as f:
        for row in f.readlines()[1:]:
            existing_relations.add(tuple(row.strip().split("\t")))
    return existing_nodes, existing_relations


def get_entities_from_meta(study_metadata, ground_fields, unground_fields):
    """parse entities from project metadata.
    Args:
        study_metadata : meta data of the project run syn.get(study_id)
        ground_fields: fields to ground with gilda
        unground_fields: fields to not ground with gilda.
    """
    meta_nodes = set()
    meta_relations = set()
    for field in ground_fields + unground_fields:
        if field in study_metadata.keys():
            field_val = (
                study_metadata[field]
                if type(study_metadata[field]) == list
                else [study_metadata[field]]
            )
            ## loop through in case list
            for entry in field_val:
                ## ground the node if it is in a grounded field
                if field in ground_fields:
                    ans = gilda.annotate(entry)
                    ## if the node should be grounded and can be grounded save the node as that entity type as well.
                    if ans:
                        nsid = ans[0].matches[0].term
                        entry = f"{nsid.db}:{nsid.id}"
                        alternate_field = bio_ontology.get_type(nsid.db, nsid.id)
                        meta_nodes.add((entry, alternate_field))
                        meta_relations.add(
                            (study_metadata.id, entry, f"has_{alternate_field}")
                        )
                ## add the nodes with their corresponding meta data fields
                meta_nodes.add((entry, field))
                meta_relations.add((study_metadata.id, entry, f"has_{field}"))
    return meta_nodes, meta_relations


def get_entities_from_wiki(study_wiki, wiki_fields):
    """pull entities from a projects wiki, and add links to them to the graph."""
    wiki_nodes = set()
    wiki_relations = set()
    ## add a node for that wiki, and a link between the project and this wiki node.
    wiki_id = f"{study_wiki.ownerId}:Wiki"
    wiki_nodes.add((wiki_id, "Wiki"))
    wiki_relations.add((study_wiki.ownerId, wiki_id, f"hasWiki"))
    for field in wiki_fields:
        if field in study_wiki.keys():
            field_val = study_wiki[field]
            ans = gilda.annotate(field_val)
            for annotation in ans:
                nsid = annotation.matches[0].term
                entry = f"{nsid.db}:{nsid.id}"
                alternate_field = bio_ontology.get_type(nsid.db, nsid.id)
                wiki_nodes.add((entry, alternate_field))
                wiki_relations.add((wiki_id, entry, "mentions"))
    return wiki_nodes, wiki_relations


if __name__ == "__main__":
    ## all projects have an accessible list of funding agencies as well as a markdown from the wiki
    nodes = set()
    relations = set()
    for project_id in all_project_ids:
        study_metadata = syn.get(project_id)
        study_wiki = syn.getWiki(project_id)
        meta_nodes, meta_relations = get_entities_from_meta(
            study_metadata=study_metadata,
            ground_fields=ground_fields,
            unground_fields=unground_fields,
        )
        wiki_nodes, wiki_relations = get_entities_from_wiki(
            study_wiki=study_wiki, wiki_fields=wiki_fields
        )
        nodes.add((project_id, "Project"))
        nodes = nodes | meta_nodes | wiki_nodes
        relations = relations | meta_relations | wiki_relations

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
