from .constants import CASES_ENDPNT, FILE_FIELDS, DATA_ENDPNT, GDC_CACHE_DIR
from dglink import NodeSet, EdgeSet, write_graph
from dglink.core.constants import REPORT_PATH

import json
import tqdm
import requests
import polars as pl
import os
import re
from subprocess import run
from typing import Tuple, Iterator
import pandas as pd


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
    ## stack files and ensure uniqueness
    return file_to_cases.vstack(cases_df).unique()


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
    cases_to_files_path = os.path.join(GDC_CACHE_DIR, "cases_to_files.tsv")
    ## load from cache if already exists
    if os.path.exists(cases_to_files_path):
        case_to_files = pl.read_csv(cases_to_files_path, separator="\t")
    else:
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
            write_graph(node_set, edge_set)
    write_graph(node_set, edge_set)
    os.makedirs(GDC_CACHE_DIR, exist_ok=True)
    case_to_files.write_csv(cases_to_files_path, separator="\t")


def download_tabular_files(case_list: list):
    """download tabular files associated with a case list and save in `~/.data/gdc/files`"""
    files_df = pl.read_csv(
        os.path.join(GDC_CACHE_DIR, "cases_to_files.tsv"), separator="\t"
    )
    files_dir = os.path.join(GDC_CACHE_DIR, "files")
    ## filter for available files and also those that are tsv
    to_load = (
        files_df.filter(
            pl.col("file_access").eq("open")
            & pl.col("file_data_format").eq("TSV")
            & pl.col("case_id").is_in(case_list)
        )["file_id"]
        .unique()
        .sort()
        .to_list()
    )
    ## only download files that are not already in the cache
    undownloaded_files = filter(
        lambda x: not os.path.exists(os.path.join(files_dir, x)), to_load
    )
    params = {"ids": list(undownloaded_files)}
    ## if there are no files to download exit
    if len(params["ids"]) < 1:
        return

    response = requests.post(
        DATA_ENDPNT,
        data=json.dumps(params),
        headers={"Content-Type": "application/json"},
    )

    response_head_cd = response.headers["Content-Disposition"]

    file_name = re.findall("filename=(.+)", response_head_cd)[0]

    os.makedirs(files_dir, exist_ok=True)

    archive_path = os.path.join(files_dir, file_name)

    with open(archive_path, "wb") as output_file:
        output_file.write(response.content)
    ## stop all files from going in separate folder
    unzip_cmd = [
        "tar",
        "-xvzf",
        archive_path,
        "-C",
        files_dir,
    ]
    run(unzip_cmd)
    ## quick and dirty stuff to make the downloads nicer to work with
    rm_cmd = ["rm", archive_path, os.path.join(files_dir, "MANIFEST.txt")]
    run(rm_cmd)


def get_tabular_iterator(case_list: list) -> Iterator:
    """
    returns a 2d iterator of case_ids and associated file_paths
    """
    files_df = pl.read_csv(
        os.path.join(GDC_CACHE_DIR, "cases_to_files.tsv"), separator="\t"
    )
    ## get only tabular files
    project_files = files_df.filter(
        pl.col("file_access").eq("open")
        & pl.col("file_data_format").eq("TSV")
        & pl.col("case_id").is_in(case_list)
    ).with_columns(
        file_paths=pl.format(  # Better than string concat
            "{}/files/{}/{}",
            pl.lit(GDC_CACHE_DIR),
            pl.col("file_id"),
            pl.col("file_file_name"),
        )
    )

    ## group by case
    case_files = project_files.group_by("case_id", maintain_order=True).agg(
        [pl.col("file_paths"), pl.col("file_id")]
    )
    return case_files.iter_rows()

    # for case in case_files.iter_rows(named=True):
    #     case_id = case.get('case_id', 'case_id_missing')
    #     dataset_paths = case.get('file_paths', [])
    #     for dataset_path in dataset_paths:
    #         print(dataset_path)
    #         print(
    #             os.path.exists(
    #                 dataset_path
    #             )
    #         )

    # print(
    #     x.get('case_id'),
    #     print(len(x.get('file_id'))),
    #     print(len(x.get('file_file_name'))),
    # )
    # files_read = []
    # cols_read = []
    # for uuid, f_name, case_id in project_files:
    #     dfs, read_states = load_file(uuid, f_name, case_id)
    #     for df, read_state in zip(dfs, read_states):
    #         files_read.append(read_state)
    #         if df is not None:
    #             base_cols = df.columns
    #             ## ground data frame
    #             entity_df = df.apply(apply_ground, axis=1)
    #             filtered_df, base_cols = filter_df(entity_df, base_cols)
    #             node_set, edge_set = extract_df_graph(
    #                 filtered_df,
    #                 base_cols,
    #                 case_id,
    #                 read_state["file_id"],
    #                 node_set=node_set,
    #                 edge_set=edge_set,
    #             )
    #             for col in base_cols:
    #                 cols_read.append(
    #                     {
    #                         "case_id": case_id,
    #                         "file_id": read_state["file_id"],
    #                         "file_path": read_state["file_path"],
    #                         "sheet": read_state["sheet"],
    #                         "col": col,
    #                     }
    #                 )
    # write_graph(node_set, edge_set)
    # return [files_read, cols_read]
