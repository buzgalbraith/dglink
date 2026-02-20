"""
This strict is for an initial Biolink integration. It just takes existing neo4j graph and updates node and edge types to biolink.
We want to expand this, so that the graph is just directly created with BioLink.
"""

# """
# This is an example of using biolink entities for dglink
# """

import polars as pl

drop_types = ["biological_process", "experimental_factor", "other", "unknown"]
p_family_or_complex = "protein_family_complex"
experimental_data_type_map = {
    "human_gene_protein": "biolink:GeneOrGeneProduct",  ## set taxon to human
    "human_gene_other": "biolink:Gene",  ## this one is always a gene but we do not anything else about it
    "nonhuman_gene_protein": "biolink:GeneOrGeneProduct",  ## want to try to set taxon with uniprot, set as either human mouse rat or other
    "small_molecule": "biolink:SmallMolecule",
    "disease": "biolink:Disease",
    "cellular_location": "biolink:CellularComponent",
    "anatomical_region": "biolink:GrossAnatomicalStructure",
    "organism": "biolink:OrganismTaxon",
    "biological_process": "biolink:BiologicalProcess",
    "small_molecule": "biolink:SmallMolecule",
    "human_rna": "biolink:RNAProduct",
    "protein_family_complex": "biolink:MolecularEntity",  ## this is just generalizing
}
metadata_type_map = {
    "Project": "biolink:Study",
    "relatedStudies": "biolink:Study",
    "grantDOI": "biolink:Study",
    "parentId": "biolink:Study",
    "initiative": "biolink:Study",
    "institutions": "biolink:Agent",
    "fundingAgency": "biolink:Agent",
    "publication": "biolink:Publication",
}
dealt_with = (
    [x for x in experimental_data_type_map.keys()]
    + [p_family_or_complex]
    + drop_types
    + [x for x in metadata_type_map.keys()]
)

if __name__ == "__main__":
    nodes = pl.read_csv("example_files/example_nodes.tsv", separator="\t")
    keep_types = [x for x in experimental_data_type_map.keys()] + [
        x for x in metadata_type_map.keys()
    ]
    nodes = nodes.filter(pl.col(":LABEL").is_in(keep_types))
    type_map = experimental_data_type_map | metadata_type_map
    nodes = nodes.with_columns(pl.col(":LABEL").replace_strict(type_map))
