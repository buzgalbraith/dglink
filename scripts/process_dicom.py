"""
Parsing DICOM files, for now only looking at one file
"""

import pydicom
from dglink.core.constants import syn, REPORT_PATH
from dglink import load_graph, NodeSet, EdgeSet, write_graph
import polars as pl
import os
from bioregistry import normalize_curie, get_bioregistry_iri
import tqdm
import gilda
from indra.ontology.bio import bio_ontology

structured_dicom_fields = [
    "PatientID",
    "AccessionNumber",
    "Modality",
    "PatientSex",
    "PatientAge",
    "SOPClassUID",
    "Manufacturer",
    "SeriesInstanceUID",
]
unstructured_dicom_fields = [
    "ImageComments",
]
image_type_index_map = {
    0: "pixel_data_characteristics",
    1: "patient_examination_relationship",
    2: "modality_specific_detail",
    3: "further_sub_class",
}


def process_dicom(
    file_id: str,
    node_set: NodeSet,
    edge_set: EdgeSet,
    dicom_identifiers: set,
    project_granularity: bool = False,
):
    """
    read in dicom file, and extract information
    if project_granularity is true will just load one DICOM per project, otherwise will try to lead all series.
    """
    annotations = syn.get_annotations(file_id)
    project_id = annotations.get("studyId", ["project_id_missing"])[0]
    ## try to process all DICOM series
    if not project_granularity:
        ## annotations do not have series identifier so using all this info as a proxy ##
        assay = annotations.get("assay", ["assay_missing"])[0]
        specimenID = annotations.get("specimenID", ["specimenID_missing"])[0]
        individualID = annotations.get("individualID", ["individualID_missing"])[0]
        experimentalTimepoint = annotations.get(
            "experimentalTimepoint", ["experimentalTimepoint_missing"]
        )[0]
        series_identifier = (
            project_id,
            assay,
            specimenID,
            individualID,
            experimentalTimepoint,
        )
    ## try to process one series per study
    else:
        series_identifier = project_id
    if series_identifier in dicom_identifiers:
        return node_set, edge_set, 0, dicom_identifiers
    else:
        dicom_identifiers.add(series_identifier)
        try:
            obj = syn.get(file_id)
        except:
            return node_set, edge_set, 0, dicom_identifiers
        if obj.path is None:
            return node_set, edge_set, 0, dicom_identifiers
        header = pydicom.dcmread(obj.path)
        node_set.update_nodes(
            {
                "curie:ID": header.get(
                    "SeriesInstanceUID", "SeriesInstanceUID_Missing"
                ),
                ":LABEL": "DICOM_series",
                "name": header.get("SeriesInstanceUID", "SeriesInstanceUID_Missing"),
                "file_id:string[]": file_id,
                "source:string[]": "dicom",
                "PatientID": header.get("PatientID", ""),
                "AccessionNumber": header.get("AccessionNumber", ""),
                "Modality": header.get("Modality", ""),
                "PatientSex": header.get("PatientSex", ""),
                "PatientAge": header.get("PatientAge", ""),
                "SOPClassUID": header.get("SOPClassUID", ""),
                "Manufacturer": header.get("Manufacturer", ""),
                "SeriesInstanceUID": header.get("SeriesInstanceUID", ""),
            }
        )
        edge_set.update_edges(
            {
                ":START_ID": project_id,
                ":END_ID": header.get("SeriesInstanceUID", "SeriesInstanceUID_Missing"),
                ":TYPE": f"has_dicom",
                "source:string[]": "dicom",
            }
        )
        for dcm_field in unstructured_dicom_fields:
            res = header.get(str(dcm_field), None)
            ans = gilda.annotate(res)
            if ans:
                nsid = ans[0].matches[0].term
                node_set.update_nodes(
                    {
                        "curie:ID": normalize_curie(f"{nsid.db}:{nsid.id}"),
                        ":LABEL": bio_ontology.get_type(nsid.db, nsid.id),
                        "name": nsid.entry_name,
                        "file_id:string[]": file_id,
                        "source:string[]": "dicom",
                        "raw_texts:string[]": res,
                    }
                )
                edge_set.update_edges(
                    {
                        ":START_ID": project_id,
                        ":END_ID": normalize_curie(f"{nsid.db}:{nsid.id}"),
                        ":TYPE": f"has_{bio_ontology.get_type(nsid.db, nsid.id)}",
                        "source:string[]": "dicom",
                    }
                )
    return node_set, edge_set, 1, dicom_identifiers


if __name__ == "__main__":
    # node_set = NodeSet()
    # edge_set = EdgeSet()
    node_set, edge_set = load_graph()
    dicom_identifiers = set()
    processed = 0
    files_df = pl.read_csv(
        os.path.join(REPORT_PATH, "file_type_report.tsv"), separator="\t"
    ).filter(pl.col("extension").eq(".dcm"))
    i = 0
    for file_id in tqdm.tqdm(files_df["syn_id"]):
        node_set, edge_set, could_process, dicom_identifiers = process_dicom(
            file_id=file_id,
            node_set=node_set,
            edge_set=edge_set,
            dicom_identifiers=dicom_identifiers,
            project_granularity=True,  ## just processing one file for each study for now
        )
        if i % 100 == 0:
            write_graph(node_set=node_set, edge_set=edge_set)
        i = i + 1
        processed += could_process
    ## run the extract process
    write_graph(node_set=node_set, edge_set=edge_set)
