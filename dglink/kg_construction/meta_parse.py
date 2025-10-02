"""
The goal of this script is to load the meta data and wiki information from each project into the KG.
"""

import synapseclient
import gilda
from bioregistry import get_iri
from indra.ontology.bio import bio_ontology
from utils import load_existing_edges, load_existing_nodes, write_nodes, write_edges

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


def get_entities_from_meta(study_metadata, ground_fields, unground_fields):
    """parse entities from project metadata.
    Args:
        study_metadata : meta data of the project run syn.get(study_id)
        ground_fields: fields to ground with gilda
        unground_fields: fields to not ground with gilda.
    """
    meta_nodes = dict()
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
                        meta_nodes[entry] = {
                            ":LABEL": bio_ontology.get_type(nsid.db, nsid.id),
                            "grounded_entity_name": nsid.entry_name,
                            "raw_texts:string[]": '""',
                            "columns:string[]": '""',
                            "iri": get_iri(nsid.db, nsid.id),
                        }
                        meta_relations.add((study_metadata.id, entry, f"has_{field}"))
                    else:
                        ## add the nodes with their corresponding meta data fields
                        meta_nodes[entry] = {
                            ":LABEL": field,
                            "grounded_entity_name": "",
                            "raw_texts:string[]": '""',
                            "columns:string[]": '""',
                            "iri": "",
                        }
                        meta_relations.add((study_metadata.id, entry, f"has_{field}"))
                else:
                    ## add the nodes with their corresponding meta data fields
                    meta_nodes[entry] = {
                        ":LABEL": field,
                        "grounded_entity_name": "",
                        "raw_texts:string[]": '""',
                        "columns:string[]": '""',
                        "iri": "",
                    }
                    meta_relations.add((study_metadata.id, entry, f"has_{field}"))

    return meta_nodes, meta_relations


def get_entities_from_wiki(study_wiki, wiki_fields):
    """pull entities from a projects wiki, and add links to them to the graph."""
    wiki_nodes = dict()
    wiki_entities = dict()
    wiki_relations = set()
    ## add a node for that wiki, and a link between the project and this wiki node.
    wiki_id = f"{study_wiki.ownerId}:Wiki"
    wiki_nodes[wiki_id] = {":LABEL": "Wiki"}
    wiki_relations.add((study_wiki.ownerId, wiki_id, f"hasWiki"))
    for field in wiki_fields:
        if field in study_wiki.keys():
            field_val = study_wiki[field]
            ans = gilda.annotate(field_val)
            for annotation in ans:
                nsid = annotation.matches[0].term
                entry = f"{nsid.db}:{nsid.id}"
                wiki_entities[entry] = {
                    ":LABEL": bio_ontology.get_type(nsid.db, nsid.id),
                    "grounded_entity_name": nsid.entry_name,
                    "raw_texts:string[]": '""',
                    "columns:string[]": '""',
                    "iri": get_iri(nsid.db, nsid.id),
                }
                wiki_relations.add((wiki_id, entry, "mentions"))
    return wiki_nodes, wiki_entities, wiki_relations


if __name__ == "__main__":
    ## all projects have an accessible list of funding agencies as well as a markdown from the wiki
    nodes = {"entities": dict(), "project": dict()}
    relations = set()
    for project_id in all_project_ids:
        study_metadata = syn.get(project_id)
        study_wiki = syn.getWiki(project_id)
        meta_nodes, meta_relations = get_entities_from_meta(
            study_metadata=study_metadata,
            ground_fields=ground_fields,
            unground_fields=unground_fields,
        )
        wiki_nodes, wiki_entities, wiki_relations = get_entities_from_wiki(
            study_wiki=study_wiki, wiki_fields=wiki_fields
        )
        nodes["project"][project_id] = {":LABEL": "Project"} | wiki_nodes
        nodes["project"] = nodes["project"] | wiki_nodes
        nodes["entities"] = nodes["entities"] | wiki_entities | meta_nodes
        relations = relations | meta_relations | wiki_relations

    ## read in existing nodes and edges to avoid duplicates
    nodes["entities"] = nodes["entities"] | load_existing_nodes(
        "dglink/resources/entity_nodes.tsv"
    )
    nodes["project"] = nodes["project"] | load_existing_nodes(
        "dglink/resources/project_nodes.tsv"
    )
    relations = relations | load_existing_edges("dglink/resources/edges.tsv")
    ## write edges
    write_edges(edges=relations)
    ## write nodes
    write_nodes(nodes=nodes["project"], node_path="dglink/resources/project_nodes.tsv")
    write_nodes(nodes=nodes["entities"], node_path="dglink/resources/entity_nodes.tsv")
