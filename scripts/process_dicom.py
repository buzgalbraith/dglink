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


def process_dicom(file_id: str, node_set: NodeSet, edge_set: EdgeSet, project_ids: set):
    """
    read in dicom file, and extract information
    """
    annotations = syn.get_annotations(file_id)
    project_id = annotations.get("studyId", ["project_id_missing"])[0]
    ## remove after testing for now just add project node
    node_set.update_nodes(
        {
            "curie:ID": project_id,
            ":LABEL": "Project",
            "name": project_id,
            "source:string[]": "dicom",
        }
    )

    if project_id in project_ids:
        return node_set, edge_set, 0, project_ids

    else:
        project_ids.add(project_id)
        try:
            obj = syn.get(file_id)
        except:
            return node_set, edge_set, 0, project_ids
        if obj.path is None:
            return node_set, edge_set, 0, project_ids
        header = pydicom.dcmread(obj.path)
        for dcm_field in structured_dicom_fields:
            res = header.get(str(dcm_field), f"{dcm_field}_missing")
            node_set.update_nodes(
                {
                    "curie:ID": res,
                    ":LABEL": dcm_field,
                    "name": res,
                    "file_id:string[]": file_id,
                    "source:string[]": "dicom",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": project_id,
                    ":END_ID": res,
                    ":TYPE": f"has_dicom_{dcm_field}",
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
        ## process image type
        image_types = header.get("ImageType", [])
        i = 0
        while i < len(image_types):
            node_set.update_nodes(
                {
                    "curie:ID": header.ImageType[i],
                    ":LABEL": image_type_index_map[i],
                    "name": header.ImageType[i],
                    "file_id:string[]": file_id,
                    "source:string[]": "dicom",
                }
            )
            edge_set.update_edges(
                {
                    ":START_ID": project_id,
                    ":END_ID": header.ImageType[i],
                    ":TYPE": f"has_dicom_{image_type_index_map[i]}",
                    "source:string[]": "dicom",
                }
            )
            i = i + 1
    return node_set, edge_set, 1, project_ids


if __name__ == "__main__":
    # node_set = NodeSet()
    # edge_set = EdgeSet()
    node_set, edge_set = load_graph()
    project_ids = set()
    processed = 0
    files_df = pl.read_csv(
        os.path.join(REPORT_PATH, "file_type_report.tsv"), separator="\t"
    ).filter(pl.col("extension").eq(".dcm"))
    i = 0
    for file_id in tqdm.tqdm(files_df["syn_id"]):
        node_set, edge_set, could_process, project_ids = process_dicom(
            file_id=file_id,
            node_set=node_set,
            edge_set=edge_set,
            project_ids=project_ids,
        )
        if i % 100 == 0:
            write_graph(node_set=node_set, edge_set=edge_set)
        i = i + 1
        processed += could_process
    ## run the extract process
    write_graph(node_set=node_set, edge_set=edge_set)
