import os

## module store info ## 
home_dir: str = os.getenv("HOME") or "/"
NCI_GC_CACHE_DIR = os.path.join(
    home_dir,
    ".data",
    "nci_general_commons",
)
## API endpoints
NCI_GQL_ENDPOINT = "https://general.datacommons.cancer.gov/v1/graphql/"
NCI_GEN3_ENDPOINT = 'https://nci-crdc.datacommons.io'

## portal specific tabular file detentions ##  
NCI_TABULAR_FILE_TYPES = [
    'CSV',
    'XLS',
    'XLSX',
    'ODS',
    'TXT'
]


NODE_ATTRIBUTES = [
    ## core fields - all nodes should have ths other fields are optional
    "curie:ID",
    ":LABEL",
    "name",
    "iri",
    "source:string[]",
    "raw_label", ## holds original label in case we use pascalify to make node labels look nice ##
    ## Program fields 
    "program_description", 
    "num_participants",
    "num_files", 
    "num_disease_sites",
    "num_samples",
    "program_url",
    ## study fields 
    "study_access",
    "study_version",
    "study_data_types",
    "short_description",
    ## StudyParticipantGroup
    "subject_count",
    ## publication fields ## 
    "publication_type",
    "publication_status",
    "doi",
    ## investigator fields ##
    "email",
    "role_or_affiliation",
    "title",
    ## diagnosis fields ## 
    "disease_type",
    "primary_site",
    "tissue_or_organ_of_origin",
    "site_of_resection_or_biopsy",
    "tumor_grade",
    "tumor_stage_clinical_m",
    "tumor_stage_clinical_n",
    "tumor_stage_clinical_t",
    "morphology",
    "vital_status",
    "age_at_diagnosis",
    "incidence_type",
    "progression_or_recurrence",
    "last_known_disease_status",
    "crdc_id",
    ## tabular data fields ##
    "raw_texts:string[]",
    "columns:string[]",
    "file_id:string[]",
]
EDGE_ATTRIBUTES = [
    ## core fields - all edges should have ths other fields are optional
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "source:string[]",
    "raw_type",
]
