import synapseclient
import os 
token = os.getenv("SYNAPSE_AUTHTOKEN")
if token:
    syn = synapseclient.login(authToken=token)
else:
    try:
        syn = synapseclient.login()
    except:
        raise ValueError("Can not authenticate to synapse, either set credentials in ~/.synapseConfig or set $SYNAPSE_AUTHTOKEN in your environment")

NF_STUDIES_BASE_URL = (
    "https://nf.synapse.org/Explore/Studies/{study_id}/Details"
)
NODE_ATTRIBUTES = [
    ## core fields - all nodes should have ths other fields are optional
    "curie:ID",
    ":LABEL",
    "name",
    "iri",
    "source:string[]",
    ## Synapse project field
    "study_url",
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
    'assay',
    'nf1Genotype',
    'nf2Genotype',
    'diagnosis',
    'tumorType'
]
EDGE_ATTRIBUTES = [
    ## core fields - all edges should have ths other fields are optional
    ":START_ID",
    ":END_ID",
    ":TYPE",
    "source:string[]",
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

UNGROUNDED_FIELDS = [
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

WIKI_FIELDS = ["markdown", "title"]
NF_DATA_PORTAL_CACHE_DIR = os.path.join(
    os.getenv("HOME"),
    ".data",
    "nf_data_portal",
)

SPECIMEN_FIELDS = {
    'age': "PatientAge",
    'sex' : "PatientSex"
}

EXPERIMENT_FIELDS = [
'assay',
'nf1Genotype',
'nf2Genotype',
'diagnosis',
'tumorType'
]