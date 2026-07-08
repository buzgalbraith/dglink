"""
Schemas to match columns against
"""

from pydantic import BaseModel


## current schema target based ish of of BioLink
class BiologicalEntity(BaseModel):
    GeneOrGeneProduct: float
    MolecularEntity: float
    Disease: float
    BiologicalProcess: float
    AnatomicalEntity: float
    OrganismTaxon: float
    CellLine: float
    Other: float


## older schema target
class EvaluationResponse(BaseModel):
    human_rna: float
    small_molecule: float
    anatomical_region: float
    cellular_location: float
    human_gene_protein: float
    experimental_factor: float
    biological_process: float
    organism: float
    nonhuman_gene_protein: float
    disease: float
    protein_family_complex: float
    human_gene_other: float
    no_schema_match: float
