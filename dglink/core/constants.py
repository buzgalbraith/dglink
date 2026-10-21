import os
from pathlib import Path

DGLINK_CACHE = Path.joinpath(Path(os.getenv("HOME") or "."), ".dglink")
RESOURCE_PATH = "dglink/resources/graph/"
REPORT_PATH = "dglink/resources/reports/"
SEMANTIC_SEARCH_RESOURCE_PATH = "dglink/applications/semantic_search/neo4j/graph"

TABULAR_FILE_TYPES = [
    ".tsv",
    ".xls",
    ".xlsx",
    ".csv",
]

VCF_FILE_TYPES = [
    ".vcf",
    ".gvcf",
    ".vcf.gz",
    ".gvcf.gz",
]

RESOURCE_TYPES = [
    "metadata",
    "projects",
    "publications",
    "wiki",
    "tools",
    ["vcf_data", "experimental_data"],
    ["tabular_data", "experimental_data"],
    ["dicom_data", "experimental_data"],
]
UNSTRUCTURED_DICOM_FIELDS = [
    "ImageComments",
]

## List of entity types found in experimental data + a null class that are passed as classes to the LLM for schema matching
TABULAR_ENTITY_TYPES_LLM = [
    "human_rna",
    "small_molecule",
    "anatomical_region",
    "cellular_location",
    "human_gene_protein",
    "experimental_factor",  ## general should not be in experimental data ##
    "biological_process",
    "organism",
    "nonhuman_gene_protein",
    "disease",
    "protein_family_complex",
    "human_gene_other",
]
INDRA_BIOLINK_EXPERIMENTAL_DATA_TYPE_MAP = {
    "human_gene_protein": "biolink:Gene",  ## set taxon to human
    "human_gene_other": "biolink:Gene",  ## this one is always a gene but we do not anything else about it
    "nonhuman_gene_protein": "biolink:Gene",  ## want to try to set taxon with uniprot, set as either human mouse rat or other
    "small_molecule": "biolink:SmallMolecule",
    "disease": "biolink:Disease",
    "cellular_location": "biolink:CellularComponent",
    "anatomical_region": "biolink:GrossAnatomicalStructure",
    "organism": "biolink:OrganismTaxon",
    "biological_process": "biolink:BiologicalProcess",
    "small_molecule": "biolink:SmallMolecule",
    "human_rna": "biolink:RNAProduct",
    "protein_family_complex": "biolink:MacromolecularComplex",  ## this is just generalizing (MacromolecularComplexOrProteinFamily does not exist in Biolink 4.x)
    ## these two do not map cleanly onto biolink so we are just linking them to named thing
    "other": "biolink:NamedThing",
    "experimental_factor": "biolink:NamedThing",
}


GENE_OR_PROTEIN_INDRA_TYPES = {"human_gene_protein", "nonhuman_gene_protein"}
GENE_CURIE_PREFIXES = {"hgnc", "hgnc.symbol", "ncbigene", "ensembl", "ensemblgene"}
PROTEIN_CURIE_PREFIXES = {"uniprot", "uniprotkb", "pr"}
## INDRA types HPO terms as "disease"; Biolink models them as phenotypic features
PHENOTYPE_CURIE_PREFIXES = {"hp"}


def map_biolink_category(indra_type, curie=None):
    """Map an INDRA/Gilda entity type to a concrete Biolink category.

    Gene/protein-ambiguous types are disambiguated using the grounded CURIE's
    namespace (e.g. hgnc -> biolink:Gene, uniprot -> biolink:Protein). Falls back
    to biolink:Gene when the namespace is unknown. HPO terms are biolink:PhenotypicFeature
    whatever their INDRA type. Any non-ambiguous type is looked up in
    INDRA_BIOLINK_EXPERIMENTAL_DATA_TYPE_MAP; unknown types are returned as-is.
    """
    prefix = str(curie).split(":")[0].lower() if curie else ""
    if prefix in PHENOTYPE_CURIE_PREFIXES:
        return "biolink:PhenotypicFeature"
    if indra_type in GENE_OR_PROTEIN_INDRA_TYPES:
        if prefix in PROTEIN_CURIE_PREFIXES:
            return "biolink:Protein"
        return "biolink:Gene"
    return INDRA_BIOLINK_EXPERIMENTAL_DATA_TYPE_MAP.get(indra_type, indra_type)


## base edge type for biolink
GROUP_ENTITY_BIOLINK_PREDICATE = "biolink:related_to"
