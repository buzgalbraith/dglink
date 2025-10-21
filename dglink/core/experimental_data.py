from dglink import NodeSet, EdgeSet, write_graph
from dglink.core.constants import syn, FILE_TYPES, RESOURCE_PATH
from synapseutils import walk
import os
from frictionless import Schema, Resource, formats, Package
import pandas
from pathlib import Path
from functools import lru_cache
from indra.ontology.bio import bio_ontology
from bioregistry import normalize_curie, get_bioregistry_iri
import tqdm
import gilda
import logging

logger = logging.getLogger(__name__)


def get_project_files(project_syn_id, syn=syn, file_types=FILE_TYPES):
    """
    returns a set of all files associated with a given synapse project id.
    """
    project_files = set()
    for _, _, filenames in walk(
        syn=syn,
        synId=project_syn_id,
        includeTypes=[
            "file",
        ],
    ):
        if len(filenames) > 0:
            for filename in filenames:
                if os.path.splitext(filename[0])[1] in file_types:
                    project_files.add(filename)
    return project_files


def filter_df(df, base_cols, nan_percentage=0.1, max_types=5):
    """filter the raw entity df removing columns with less than some percentage of entites found or more than some number of types"""
    ## filter out cols with less than 10% rows successfully grounded
    res = df.loc[:, df.count() / len(df) >= nan_percentage]
    base_cols = [x for x in base_cols if f"{x}_type" in res.columns]
    ## filter out columns with more than some set number of max entity types
    cols_to_drop = []
    for base in base_cols:
        if res[f"{base}_type"].nunique() > max_types:
            cols_to_drop.extend(
                [
                    f"{base}_type",
                    f"{base}_entity",
                    f"{base}_name",
                    f"{base}_raw_text",
                    f"{base}_column_name",
                    f"{base}_iri",
                ]
            )
    final = res.drop(columns=cols_to_drop)
    base_cols = [x for x in base_cols if f"{x}_type" in final.columns]
    return final, base_cols


def get_frictionless_package(pth):
    pac = Package()
    format = pth.suffix
    control_func = lambda x: None
    if pth.suffix in [".xlsx", ".xls"]:
        ## try to directly load as a package
        try:
            pac = Package(pth)
            control_func = lambda x: formats.ExcelControl(
                sheet=x.dialect.controls[0].sheet
            )
        ## this fails for some excel sheets with weird formatting
        except:
            ## try to add each sheet of the file to the package as a resource
            try:
                if format == ".xlsx":
                    from openpyxl import load_workbook

                    col_names = load_workbook(pth, read_only=True)
                else:
                    col_names = pandas.ExcelFile(pth).sheet_names
                for sheet in col_names:
                    pac.add_resource(
                        Resource(pth, control=formats.ExcelControl(sheet=sheet))
                    )
                control_func = lambda x: formats.ExcelControl(
                    sheet=x.dialect.controls[0].sheet
                )
            ## if this fails, as a last ditch effort try loading the file as an excel file.
            except:
                pac.add_resource(Resource(pth, format="tsv"))
                format = ".tsv"
    else:
        pac.add_resource(Resource(pth))
    for res in pac.resources:
        raw_schema = Schema.describe(res.path, control=control_func(res), format=format)
        to_drop = [field.name for field in raw_schema.fields if field.type != "string"]
        for x in to_drop:
            raw_schema.remove_field(x)
        res.schema = raw_schema
    return pac


def frictionless_file_reader(obj, max_size_bytes=100 * 1024 * 1024):
    """
    reads in files from a synapse file object with frictionless. Returns files as a dictionary for working with sheets
    """
    ## issues with pull
    if obj is None:
        return {}
    if obj.path is None:
        return {}
    ## check file size
    pth = Path(obj.path)
    file_size = os.path.getsize(pth)
    if file_size > max_size_bytes:
        logger.info("file to large to read")
        return {}
    ## load file contents into frictionless package
    pack = get_frictionless_package(pth=pth)
    ## load frictionless package into dictionary of pandas data frames
    df_dict = {}
    for res in pack.resources:
        df_dict[res.name] = pandas.DataFrame(res.read_rows())  # stream rows directly
    return df_dict


@lru_cache(maxsize=None)
def cached_annotate(val, col):
    """cached inner function for grounding with gilda"""
    if pandas.notna(val):
        ans = gilda.annotate(str(val))
        if ans:
            nsid = ans[0].matches[0].term

            return (
                normalize_curie(f"{nsid.db}:{nsid.id}"),
                bio_ontology.get_type(nsid.db, nsid.id),
                nsid.entry_name,
                val,
                col,
                get_bioregistry_iri(nsid.db, nsid.id),
            )
    return pandas.NA, pandas.NA, pandas.NA, pandas.NA, pandas.NA, pandas.NA


def apply_ground(row):
    """method for applying grounding to data frame"""
    result = {}
    for col in row.index:
        (
            result[f"{col}_entity"],
            result[f"{col}_type"],
            result[f"{col}_name"],
            result[f"{col}_raw_text"],
            result[f"{col}_column_name"],
            result[f"{col}_iri"],
        ) = cached_annotate(row[col], col)
    return pandas.Series(result)


def extract_df_graph(
    df, cols, project_id, file_id, node_set: NodeSet, edge_set: EdgeSet
):
    """extract nodes and edges form df"""
    for _, row in df.iterrows():
        for col in cols:
            entity = row[f"{col}_entity"]
            entity_type = row[f"{col}_type"]
            if (not pandas.isna(entity)) & (not pandas.isna(entity_type)):
                entity = str(row[f"{col}_entity"]).replace('"', "").replace("'", "")
                entity_type = str(row[f"{col}_type"]).replace('"', "").replace("'", "")
                entity_name = str(row[f"{col}_name"]).replace('"', "").replace("'", "")
                raw_text = str(row[f"{col}_raw_text"]).replace('"', "").replace("'", "")
                column_name = (
                    str(row[f"{col}_column_name"]).replace('"', "").replace("'", "")
                )
                iri = str(row[f"{col}_iri"]).replace('"', "").replace("'", "")
                attributes = {
                    "curie:ID": entity,
                    ":LABEL": entity_type,
                    "name": entity_name,
                    "raw_texts:string[]": raw_text,
                    "columns:string[]": column_name,
                    "iri": iri,
                    "file_id:string[]": file_id,
                    "source:string[]": "experimental_data",
                }
                node_set.update_nodes(new_node=attributes)
                edge_set.update_edges(
                    {
                        ":START_ID": project_id,
                        ":END_ID": entity,
                        ":TYPE": f"has_{entity_type}",
                        "source:string[]": "experimental_data",
                    }
                )

    return node_set, edge_set


def check_df_readable(df, max_unnamed=2):
    """determine if a given data frame was correctly read in"""
    if len(df.columns) < 1:
        return False, df
    unnamed_count = sum(df.columns.str.contains("Unnamed", case=False))
    can_read = False
    if unnamed_count > max_unnamed:
        df = None
    else:
        df = df.select_dtypes(include=["object", "string"])
        can_read = True
    return can_read, df


def load_file(syn_file_id, project_id):
    """
    Reads in the content of the file as a list of data frames to accommodate multiple sheets
    """
    try:
        obj = syn.get(syn_file_id)
    except:
        return [], {
            "project_id": project_id,
            "file_id": "_",
            "file_path": str(syn_file_id),
            "can_read": False,
            "reason": "Locked",
            "sheet": "all",
        }
    df_dict = frictionless_file_reader(obj)
    if len(df_dict) < 1:
        return [], {
            "project_id": project_id,
            "file_id": "_",
            "file_path": syn_file_id,
            "can_read": False,
            "reason": "Locked",
            "sheet": "all",
        }

    dfs = []
    read_states = []
    for sheet in df_dict:
        df = df_dict[sheet]
        ## determine if the file was read in correctly
        df_read, df = check_df_readable(df)
        reason = "good" if df_read else "look_into"
        ## adding to a list of what files can actually be read
        read_states.append(
            {
                "project_id": project_id,
                "file_id": obj.id,
                "file_path": str(obj.path),
                "can_read": df_read,
                "reason": reason,
                "sheet": sheet,
            }
        )
        dfs.append(df)
    return dfs, read_states


def process_project(
    project_files,
    project_id,
    node_set: NodeSet,
    edge_set: EdgeSet,
    cols_read: list = [],
    files_read: list = [],
):
    for _, sny_file_id in tqdm.tqdm(project_files):
        dfs, read_states = load_file(syn_file_id=sny_file_id, project_id=project_id)
        if len(dfs) < 1:
            files_read.append(read_states)
        else:
            for df, read_state in zip(dfs, read_states):
                if df is not None:
                    files_read.append(read_state)
                    base_cols = df.columns
                    ## ground data frame
                    entity_df = df.apply(apply_ground, axis=1)
                    entity_df, base_cols = filter_df(entity_df, base_cols)
                    node_set, edge_set = extract_df_graph(
                        entity_df,
                        base_cols,
                        project_id,
                        read_state["file_id"],
                        node_set=node_set,
                        edge_set=edge_set,
                    )
                    for col in base_cols:
                        cols_read.append(
                            {
                                "project_id": project_id,
                                "file_id": read_state["file_id"],
                                "file_path": read_state["file_path"],
                                "sheet": read_state["sheet"],
                                "col": col,
                            }
                        )
    return node_set, edge_set, files_read, cols_read


def get_experimental_data(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    write_set: bool = False,
    write_reports: bool = True,
    write_intermediate: bool = True,
):
    """main loop for adding experimental data to KG"""
    logger.info(f"Adding experimental data for {len(project_ids)} projects")
    files_read = []
    cols_read = []
    i = 1
    for project_id in tqdm.tqdm(project_ids):

        logger.info(
            f"adding experimental data project {project_id}\n\
                    This is project {i} out of {len(project_ids)+1} \n\
                    There are {len(project_files)} total files to parse."
        )
        i = i + 1
        project_files = get_project_files(project_syn_id=project_id)
        node_set, edge_set, files_read, cols_read = process_project(
            project_files=project_files,
            project_id=project_id,
            node_set=node_set,
            edge_set=edge_set,
            files_read=files_read,
            cols_read=cols_read,
        )
        if write_intermediate:
            write_graph(
                node_set=node_set,
                edge_set=edge_set,
                source_filter=True,
                strict=True,
                source_name="experimental_data",
                resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
            )
    files_df = pandas.DataFrame(data=files_read)
    cols_df = pandas.DataFrame(data=cols_read)
    ## write a sub-graph with just experimental data
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="experimental_data",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    if write_reports:
        files_df.to_csv("file_report.tsv", sep="\t", index=False)
        cols_df.to_csv("col_report.tsv", sep="\t", index=False)

    return node_set, edge_set, [files_df, cols_df]
