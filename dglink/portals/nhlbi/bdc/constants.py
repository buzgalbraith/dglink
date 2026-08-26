from pystow import module

## module store info ##
NHLBI_BDC_CACHE_DIR = module("nhlbi_bio_data_catalyst").base

## API END POINTS ##
BDC_GEN3_ENDPOINT = "https://gen3.biodatacatalyst.nhlbi.nih.gov"


## portal specific tabular file CHOICES ##
BDC_TABULAR_FILE_TYPES = ["csv", "xls", "xlsx", "ods", "txt", "tsv"]

NODE_ATTRIBUTES = [
    ## core fields 
    "curie:ID",
    ":LABEL",
    "raw_label",  ## BDC-native type kept alongside the Biolink category
    "name",
    "iri",
    "source:string[]",
    ## program / project fields
    "dbgap_accession_number",
    "code",
    "availability_type",
    "availability_mechanism",
    "state",
    "releasable:boolean",
    "released:boolean",
    "investigator_name",
    "investigator_affiliation",
    ## study fields
    "short_name",
    "study_description",
    "dbgap_phs",
    "dbgap_consent",
    "type_of_data:string[]",
    ## subject fields
    "participant_id",
    "consent_codes:string[]",
    ## publication fields
    "doi",
    "pmid",
    ## core_metadata_collection fields 
    "title",
    "description",
    "data_type",
    "format",
    "creator",
    "contributor",
    "publisher",
    "date",
]
EDGE_ATTRIBUTES = [
    ## core fields
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "raw_type", 
    "source:string[]",
    ## tabular provenance — which file / column / raw text an extracted entity was found in
    "raw_texts:string[]",
    "columns:string[]",
    "file_id:string[]",
]


BDC_CURIE_PREFIX = "nhlbibdc"


def bdc_curie(value: str) -> str:
    """Prefix a raw BDC id (or slugged name) as a CURIE (Biolink requires CURIE ids)."""
    return f"{BDC_CURIE_PREFIX}:{value}"



BDC_LABEL_TO_BIOLINK = {
    "program": "biolink:Study",
    "project": "biolink:Study",
    "study": "biolink:Study",
    "subject": "biolink:Case",
    "publication": "biolink:Publication",
    "core_metadata_collection": "biolink:InformationContentEntity",
}
BDC_DEFAULT_BIOLINK_CATEGORY = "biolink:NamedThing"

BDC_EDGE_TO_BIOLINK = {
    "Has_Project": "biolink:has_part",  ## program -> project
    "Has_Study": "biolink:has_part",  ## project -> study
    "Has_Subject": "biolink:has_part",  ## study -> subject
    "Has_Publication": "biolink:has_part",  ## project -> publication
    "Has_Core_Metadata_Collection": "biolink:has_part",  ## project -> core_metadata_collection
}

## List of file node types to process ##
BDC_FILE_NODE_TYPES = [
            'aligned_reads',
            'imaging_file',
            'imaging_file_reference',
            'reference_file',
            'simple_germline_variation',
            'submitted_aligned_reads',
            'sleep_test_file',
            'submitted_expression_array',
            'submitted_genotyping_array',
            'submitted_methylation',
            'submitted_unaligned_reads',
            'wearable_activity_monitor_file',
        ]