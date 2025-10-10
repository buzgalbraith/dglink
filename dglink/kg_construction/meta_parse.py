"""
The goal of this script is to load the meta data and wiki information from each project into the KG.
"""

import synapseclient
from nodes import Node, NodeSet, ENTITY_ATTRIBUTES, PROJECT_ATTRIBUTES
import gilda
from bioregistry import normalize_curie, get_bioregistry_iri
from indra.ontology.bio import bio_ontology
from utils import write_edges, load_existing_edges, DGLINK_CACHE
import pandas
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
all_project_ids = pandas.read_csv(f'{DGLINK_CACHE}/all_studies.tsv', sep='\t')['studyId'].to_list()
ground_fields = [
    "manifestation",
    "diseaseFocus",
]


unground_fields = [
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


def get_entities_from_meta(study_metadata, ground_fields, unground_fields, nodes:NodeSet):
    """parse entities from project metadata.
    Args:
        study_metadata : meta data of the project run syn.get(study_id)
        ground_fields: fields to ground with gilda
        unground_fields: fields to not ground with gilda.
    """
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
                    ## add the nodes with their corresponding meta data fields
                entry = str(entry)
                node_attributes = {
                        'curie:ID':entry,
                        ":LABEL": field,
                        'columns:string[]' : 'metadata',
                        "raw_texts:string[]": entry,
                    }
                if field in ground_fields:
                    ans = gilda.annotate(entry)
                    ## if the node should be grounded and can be grounded save the node as that entity type as well.
                    if ans:
                        nsid = ans[0].matches[0].term
                        curie = normalize_curie(f"{nsid.db}:{nsid.id}")
                        node_attributes = {
                            'curie:ID':curie,
                            ":LABEL": bio_ontology.get_type(nsid.db, nsid.id),
                            "grounded_entity_name": nsid.entry_name,
                            "iri": get_bioregistry_iri(nsid.db, nsid.id),
                            "raw_texts:string[]": entry,
                            'columns:string[]' : 'metadata',
                        }
                        meta_relations.add((study_metadata.id, curie, f"has_{field}"))
                meta_relations.add((study_metadata.id, entry, f"has_{field}"))
                working_node = Node(
                        attribute_names=ENTITY_ATTRIBUTES, 
                        attributes = node_attributes
                )
                nodes.update_nodes(new_node= working_node, new_node_id = entry)
    return nodes, meta_relations


def get_entities_from_wiki(study_wiki, wiki_fields, entity_nodes:NodeSet, project_nodes:NodeSet):
    """pull entities from a projects wiki, and add links to them to the graph."""
    wiki_relations = set()
    ## add a node for that wiki, and a link between the project and this wiki node.
    wiki_id = f"{study_wiki.ownerId}:Wiki"
    project_node = Node(attribute_names=PROJECT_ATTRIBUTES, attributes={
        'curie:ID': wiki_id,
        ':LABEL':'Wiki'
    })
    project_nodes.update_nodes(project_node, wiki_id)
    wiki_relations.add((study_wiki.ownerId, wiki_id, f"hasWiki"))
    for field in wiki_fields:
        if field in study_wiki.keys():
            field_val = study_wiki[field]
            ans = gilda.annotate(field_val)
            for annotation in ans:
                nsid = annotation.matches[0].term
                entry = normalize_curie(f"{nsid.db}:{nsid.id}")
                working_node = Node(
                    ENTITY_ATTRIBUTES,
                    attributes={
                    'curie:ID':entry,
                    ":LABEL":  bio_ontology.get_type(nsid.db, nsid.id)  or 'unknown',
                    "grounded_entity_name": nsid.entry_name or 'no_name_found',
                    "raw_texts:string[]": annotation.text,
                    'columns:string[]' : 'wiki',
                    "iri": get_bioregistry_iri(nsid.db, nsid.id),
                }
                )
                entity_nodes.update_nodes(new_node=working_node, new_node_id=entry)
                wiki_relations.add((wiki_id, entry, "mentions"))
    return project_nodes, entity_nodes, wiki_relations


if __name__ == "__main__":
    relations = set()
    entity_nodes = NodeSet(attributes=ENTITY_ATTRIBUTES)
    project_nodes = NodeSet(attributes=PROJECT_ATTRIBUTES)
    entity_nodes.load_node_set('dglink/resources/entity_nodes.tsv')
    project_nodes.load_node_set('dglink/resources/project_nodes.tsv')
    for project_id in all_project_ids:
        study_metadata = syn.get(project_id)
        study_wiki = syn.getWiki(project_id)
        entity_nodes, meta_relations = get_entities_from_meta(
            study_metadata=study_metadata,
            ground_fields=ground_fields,
            unground_fields=unground_fields,
            nodes=entity_nodes
        )
        project_nodes, entity_nodes, wiki_relations = get_entities_from_wiki(
            study_wiki=study_wiki, wiki_fields=wiki_fields, entity_nodes=entity_nodes, project_nodes=project_nodes
        )
        relations = relations | meta_relations | wiki_relations
    entity_nodes.write_node_set('dglink/resources/entity_nodes.tsv')
    project_nodes.write_node_set('dglink/resources/project_nodes.tsv')
    relations = relations | load_existing_edges("dglink/resources/edges.tsv")
    write_edges(edges=relations)