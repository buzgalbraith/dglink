from .constants import CASES_ENDPNT, FILE_FIELDS
from dglink import NodeSet, EdgeSet, write_graph
from dglink.core.constants import REPORT_PATH

import json
import tqdm
import requests
import polars as pl
import os


def connect_cases_to_files(hits, file_to_cases: pl.DataFrame = None) -> pl.DataFrame:
    """
    connects all files from a case API call to their associated case id. Updates the data frame.
    """
    records = []
    for hit in hits:
        case_id = hit.get("case_id", "case_id_missing")
        case_files = hit.get("files", [])
        for case_file in case_files:
            file_record = {
                "file_id": case_file.get("file_id", "file_id_missing"),
                "case_id": case_id,
            }
            for field in FILE_FIELDS:
                file_record[f"file_{field}"] = case_file.get(
                    field, f"file_{field}_missing"
                )
            records.append(file_record)
    if len(records) == 0:
        return file_to_cases
    cases_df = pl.from_dicts(records)
    if file_to_cases is None:
        return cases_df
    return file_to_cases.vstack(cases_df)


## TODO: Re-examine
def get_sample_metadata(hits: list, node_set: NodeSet):
    """
    Manually pulls all metadata field for a sample from the cases end point. Could be better done with existing GDC graph.
    """
    for hit in hits:
        for sample in hit.get("samples", [dict()]):
            node_set.update_nodes(
                {
                    "curie:ID": sample.get("sample_id", "sample_id_missing"),
                    ":LABEL": "sample",
                    "tumor_descriptor": sample.get(
                        "tumor_descriptor", "tumor_descriptor_missing"
                    ),
                    "specimen_type": sample.get(
                        "specimen_type", "specimen_type_missing"
                    ),
                    "sample_type": sample.get("sample_type", "sample_type_missing"),
                    "tissue_type": sample.get("tissue_type", "tissue_type_missing"),
                    "preservation_method": sample.get(
                        "preservation_method", "preservation_method_missing"
                    ),
                }
            )


def process_case_hierarchy(hits, node_set, edge_set):
    """extracts hierarchy from case and adds to graph"""
    for hit in hits:
        case_id = hit.get("id", "case_id_missing")
        node_set.update_nodes(
            {
                "curie:ID": case_id,
                ":LABEL": "case",
            }
        )
        ## all connected nodes seem to be prefix with id
        for key in hit.keys():
            ## fields where each case only connected to one node (ex: uploader id)
            if key.endswith("_id"):
                vals = [hit.get(key, f"{key}_missing")]
                label = key.removesuffix("_id")
            ## fields where each case only connected to one node (ex: sample)
            elif key.endswith("_ids"):
                vals = hit.get(key, f"{key}_missing")
                label = key.removesuffix("_ids")
            else:
                vals = []
            ## add identified nodes & edges to graph
            for val in vals:
                node_set.update_nodes(
                    {
                        "curie:ID": val,
                        ":LABEL": label,
                    }
                )
                edge_set.update_edges(
                    {
                        ":START_ID": case_id,
                        ":END_ID": val,
                        ":TYPE": f"has_{label}",
                    }
                )


def max_call_size(end_point):
    """small helper function to get max size for an api call"""
    params = {"format": "JSON", "size": 0}
    response = requests.get(end_point, params=params)
    return response.json()["data"]["pagination"]["total"]


def get_case_hierarchy(
    node_set: NodeSet,
    edge_set: EdgeSet,
    case_list: list = None,
    number_cases: int = None,
    batch_length: int = 500,
):
    """connect cases to all down stream objects. Saves files as a tsv in `dglink/resources/reports/cases_to_files.tsv` , and connects all meta objects (samples, studies, projects, etc.) to case in the graph."""
    ## Filter for a specific list of cases
    if case_list is not None:
        number_cases = len(case_list)
        filters = {
            "op": "and",
            "content": [
                {"op": "in", "content": {"field": "case_id", "value": case_list}}
            ],
        }
    ## if no set of cases specified either process the first `number_cases` cases or process all.
    else:
        number_cases = number_cases or max_call_size(CASES_ENDPNT)
        filters = {}
    params = {
        "filters": json.dumps(filters),
        "format": "JSON",
        "expand": "files,samples",  ## get associated files and expand samples
    }
    case_to_files = None
    for x in tqdm.tqdm(range(0, number_cases, batch_length)):
        params["from"] = x
        params["size"] = min(batch_length, number_cases - x)
        response = requests.get(CASES_ENDPNT, params=params)
        json_resp = json.loads(response.content.decode("utf-8"))
        data = json_resp.get("data", dict())
        hits = data.get("hits", [dict()])
        case_to_files = connect_cases_to_files(hits=hits, file_to_cases=case_to_files)
        get_sample_metadata(hits, node_set=node_set)
        process_case_hierarchy(hits=hits, node_set=node_set, edge_set=edge_set)
        if x % (batch_length * 10) == 0:
            print("writing ", x)
            write_graph(node_set, edge_set)
    write_graph(node_set, edge_set)
    case_to_files.write_csv(
        os.path.join(REPORT_PATH, "cases_to_files.tsv"), separator="\t"
    )
