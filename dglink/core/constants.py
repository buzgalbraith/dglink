import os
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel

open_ai_client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)

DGLINK_CACHE = Path.joinpath(Path(os.getenv("HOME") or '.'), ".dglink")
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
    "experimental_factor", ## general should not be in experimental data ## 
    "biological_process",
    "organism",
    "nonhuman_gene_protein",
    "disease",
    "protein_family_complex",
    "human_gene_other",
]
INDRA_BIOLINK_EXPERIMENTAL_DATA_TYPE_MAP = {
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
    "protein_family_complex": "biolink:MacromolecularComplexOrProteinFamily",  ## this is just generalizing
}