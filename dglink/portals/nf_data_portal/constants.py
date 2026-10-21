import synapseclient
import os

token = os.getenv("SYNAPSE_AUTHTOKEN")
if token:
    syn = synapseclient.login(authToken=token)
else:
    try:
        syn = synapseclient.login()
    except:
        raise ValueError(
            "Can not authenticate to synapse, either set credentials in ~/.synapseConfig or set $SYNAPSE_AUTHTOKEN in your environment"
        )

NF_STUDIES_BASE_URL = "https://nf.synapse.org/Explore/Studies/{study_id}/Details"
NODE_ATTRIBUTES = [
    ## core fields - all nodes should have ths other fields are optional
    "curie:ID",
    ":LABEL",
    "raw_label",  ## NF Data Portal native type (e.g. "initiative") kept alongside the Biolink category
    "name",
    "iri",
    "grounded:boolean",
    "source:string[]",
    ## Synapse project field
    "study_url",
    "studyStatus:string[]",
    "parentId:string[]",
    "dataStatus:string[]",
    "dataType:string[]",
    "grantDOI:string[]",
    "diseaseFocus:string[]",  ## raw portal values; grounded values are also edges
    "manifestation:string[]",
    ## tabular data fields
    "raw_texts:string[]",
    "columns:string[]",
    "file_id:string[]",
    ## DICOM Fields
    "PatientID",
    "AccessionNumber",
    "Modality",
    "PatientSex",
    "PatientAge",
    "SOPClassUID",
    "Manufacturer",
    ## VCF fields
    "chrom",
    "pos",
    "ref",
    "alt",
    "genotype",
    "quality",
    ## publication fields
    "DOI",
    ## nf data portal tool fields (maybe move elsewhere)
    "tool_type",
    ## genomic fields
    "assay",
    "nf1Genotype",
    "nf2Genotype",
    "diagnosis",
    "tumorType",
]

EDGE_ATTRIBUTES = [
    ## core fields - all edges should have ths other fields are optional
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "raw_type:string[]",  ## NF Data Portal native relation preserved alongside the Biolink predicate
    "source:string[]",
    ## tabular provenance — which file / column / raw text a tabular-extracted entity was
    ## found in (extract_df_graph now puts these on the group -> entity edge, not the node;
    ## NF keeps them on nodes too for its non-tabular sources: fastq / meta / wiki / dicom)
    "raw_texts:string[]",
    "columns:string[]",
    "file_id:string[]",
    ## predicted similar project fields
    "jacquard_score",
    "score_cutoff",
    "intersection_score",
    "union_score",
    "shared_edges:string[]",
    "head_only_edges:string[]",
    "tail_only_edges:string[]",
    "edge_weights:string[]",
]

GROUND_FIELDS = [
    "manifestation",
    "diseaseFocus",
]

## Biolink categories a grounding may have per field; anything else is treated as ungrounded
NF_GROUND_FIELD_CATEGORIES = {
    "diseaseFocus": {"biolink:Disease"},
    "manifestation": {
        "biolink:Disease",
        "biolink:PhenotypicFeature",
        "biolink:BiologicalProcess",
        "biolink:NamedThing",
    },
}

## category for values that do not ground
NF_UNGROUNDED_CATEGORY = {
    "diseaseFocus": "biolink:Disease",
    "manifestation": "biolink:DiseaseOrPhenotypicFeature",
}

## partial groundings must cover at least this share of the value
NF_GROUNDING_MIN_SPAN_FRACTION = 0.5

METADATA_NODES = [
    "fundingAgency",
    "initiative",
    "institutions",
]

## placeholder values (compared lower-cased) are kept as Study attributes only, never as
## nodes, so they do not link unrelated studies
NF_PLACEHOLDER_VALUES = {"multiple", "other", "unknown", "not applicable", "not reported"}


PROJECT_ATTRS = [
    "studyStatus",
    "parentId",
    "dataStatus",
    "dataType",
    "grantDOI",
    "diseaseFocus",
    "manifestation",
]

WIKI_FIELDS = ["markdown", "title"]
NF_DATA_PORTAL_CACHE_DIR = os.path.join(
    os.getenv("HOME"),
    ".data",
    "nf_data_portal",
)

SPECIMEN_FIELDS = {"age": "PatientAge", "sex": "PatientSex"}

EXPERIMENT_FIELDS = ["assay", "nf1Genotype", "nf2Genotype", "diagnosis", "tumorType"]


## --- Biolink mapping ------------------------------------------------------
## NF Data Portal native entity type -> concrete Biolink category (the native distinction is
## kept in `raw_label`). 
NF_LABEL_TO_BIOLINK = {
    "Project": "biolink:Study",
    "initiative": "biolink:Study",
    "institutions": "biolink:Agent",
    "fundingAgency": "biolink:Agent",
    "publication": "biolink:Publication",
    "tool": "biolink:NamedThing",  ## refined per row by NF_TOOL_TYPE_TO_BIOLINK
    "Wiki": "biolink:DatasetSummary",
    "specimen": "biolink:MaterialSample",
    "sample": "biolink:MaterialSample",  ## VCF samples
    "sequencing_experiment": "biolink:Dataset",
    "DICOM_series": "biolink:Dataset",
    "genetic_variant": "biolink:SequenceVariant",
    ## VCF header nodes, to be folded into file properties
    "VCF_file_format": "biolink:NamedThing",
    "VCF_reference": "biolink:NamedThing",
    "VCF_command": "biolink:NamedThing",
}

## NF tools table `resourceType` -> Biolink category. Antibody, Genetic Reagent and
## Biobank have no Biolink class and fall back to NF_DEFAULT_BIOLINK_CATEGORY.
NF_TOOL_TYPE_TO_BIOLINK = {
    "Cell Line": "biolink:CellLine",
    "Animal Model": "biolink:IndividualOrganism",
}

NF_DEFAULT_BIOLINK_CATEGORY = "biolink:NamedThing"

## NF Data Portal native edge type -> Biolink predicate. The native relation is kept in
## `raw_type`. Study -> grounded entity edges (has_{INDRA type}) use
## GROUP_ENTITY_BIOLINK_PREDICATE from dglink.core.constants, same as tabular data.
NF_EDGE_TO_BIOLINK = {
    ## study metadata (Study -> X)
    "has_initiative": "biolink:part_of",
    "has_relatedStudies": "biolink:related_to_at_instance_level",
    "predicted_relatedStudies_GL": "biolink:related_to_at_instance_level",
    "has_institutions": "biolink:related_to_at_instance_level",  ## contributor is Agent -> ICE
    "has_fundingAgency": "biolink:related_to_at_instance_level",
    "has_diseaseFocus": "biolink:related_to_at_instance_level",
    "has_manifestation": "biolink:related_to_at_instance_level",
    "has_parentId": "biolink:part_of",  ## to be folded into a Study property
    "hasWiki": "biolink:has_part",
    "published": "biolink:has_part",
    "usesTool": "biolink:related_to_at_instance_level",
    "mentions": "biolink:mentions",  ## Wiki -> entity
    ## samples and experiments
    "has_specimen": "biolink:has_part",  ## Study -> MaterialSample
    "has_sample": "biolink:has_part",  ## Study -> MaterialSample (VCF)
    "has_sequencing_experiment": "biolink:has_part",  ## Procedure -> MaterialSample, needs flipping in fastq.py
    "has_organism": "biolink:related_to_at_instance_level",
    "has_dicom": "biolink:has_part",  ## Study -> Dataset
    "has_genetic_variant": "biolink:related_to_at_instance_level",  ## has_sequence_variant needs a GenomicEntity subject
    ## VCF header edges, to be folded into file properties
    "has_vcf_format": "biolink:related_to_at_instance_level",
    "has_vcf_reference": "biolink:related_to_at_instance_level",
    "has_vcf_command": "biolink:related_to_at_instance_level",
}

NF_CURIE_PREFIX = "nfdataportal"
