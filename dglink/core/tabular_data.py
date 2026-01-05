"""
Extract knowledge graph information from tabular data files.

This module processes structured tabular files (CSV, TSV, Excel) from Synapse projects
to extract biomedical entities through text grounding and construct a knowledge graph.
Uses Gilda for entity recognition and INDRA for ontology typing.
"""

from .constants import RESOURCE_PATH, REPORT_PATH, TABULAR_FILE_TYPES
from dglink.portals.nf_data_portal import syn
from .utils import get_project_files, write_graph
from .nodes import NodeSet
from .edges import EdgeSet
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
from typing import Iterator


logger = logging.getLogger(__name__)


def filter_df(df, base_cols, nan_percentage=0.1, max_types=8):
    """Filter grounded entity DataFrame to remove low-quality or overly heterogeneous columns.

    Applies two quality filters:
    1. Removes columns where fewer than nan_percentage of rows were successfully grounded
    2. Removes columns containing more than max_types distinct entity types (too heterogeneous)

    Args:
        df: DataFrame with grounded entity columns (entity, type, name, raw_text, column_name, iri)
        base_cols: List of original column names before grounding suffixes were added
        nan_percentage: Minimum proportion of non-null values required to keep column (default: 0.1)
        max_types: Maximum number of distinct entity types allowed per column (default: 5)

    Returns:
        Tuple of (filtered DataFrame, filtered list of base column names)

    Example:
        >>> # Keep only columns with ≥10% grounded and ≤5 entity types
        >>> filtered_df, filtered_cols = filter_df(entity_df, ['gene', 'disease'], 0.1, 5)
    """
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
    """Load a tabular file into a Frictionless Package for robust multi-format parsing.

    Handles various file formats (CSV, TSV, Excel) with fallback strategies for
    problematic Excel files. Creates a Package with Resources that have schemas
    containing only string-type fields for text analysis.

    Args:
        pth: Path object pointing to the tabular file

    Returns:
        Frictionless Package containing one or more Resources (one per sheet for Excel)

    Note:
        For Excel files, attempts three strategies in order:
        1. Direct Package loading
        2. Loading each sheet as separate Resource
        3. Fallback to TSV format if Excel parsing fails

        Non-string columns are removed from schemas since entity grounding only
        operates on text data.
    """
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


def frictionless_file_reader(pth: str, max_size_bytes=100 * 1024 * 1024):
    """Read tabular files from Synapse file objects using Frictionless framework.

    Downloads and parses various tabular formats (CSV, TSV, Excel) into a dictionary
    of pandas DataFrames, with one DataFrame per sheet for multi-sheet files.

    Args:
        pth: path to tabular file to read.
        max_size_bytes: Maximum file size to process in bytes (default: 100MB)

    Returns:
        Dictionary mapping sheet names to pandas DataFrames. Returns empty dict if:
        - File object is None or has no path
        - File exceeds size limit
        - Parsing fails

    Note:
        Uses frictionless for robust parsing with fallback strategies for problematic
        Excel files. All sheets from multi-sheet files are returned separately.
    """
    ## issues with pull
    pth = Path(pth)
    file_size = os.path.getsize(pth)
    if file_size > max_size_bytes:
        logger.info("file to large to read")
        return {"all": "to_large"}
    ## load file contents into frictionless package
    pack = get_frictionless_package(pth=pth)
    ## load frictionless package into dictionary of pandas data frames
    df_dict = {}
    for res in pack.resources:
        try:
            df_dict[res.name] = pandas.DataFrame(
                res.read_rows()
            )  # stream rows directly
        except:
            return {"all": "unable_to_read"}
    return df_dict


@lru_cache(maxsize=None)
def cached_annotate(val, col):
    """Ground a cell value to biomedical ontology terms using Gilda (cached).

    Uses Gilda to identify biomedical entities in text and normalizes them to
    standard ontology terms. Results are cached to avoid redundant API calls.

    Args:
        val: Cell value to ground (will be converted to string)
        col: Column name for tracking provenance

    Returns:
        Tuple of (curie, entity_type, name, raw_text, column_name, iri)
        Returns tuple of pandas.NA values if grounding fails or value is null

    Note:
        Uses INDRA bio_ontology for entity typing and bioregistry for IRI generation.
        Only the top-ranked Gilda match is used.
    """
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
    """Apply entity grounding to all columns in a DataFrame row.

    Transforms a row of raw text values into grounded entity information by calling
    cached_annotate on each cell. Creates new columns with suffixes: _entity, _type,
    _name, _raw_text, _column_name, _iri.

    Args:
        row: pandas Series representing one row of the DataFrame

    Returns:
        pandas Series with grounded entity information for all columns

    Note:
        This function is designed to be used with DataFrame.apply(axis=1)
    """
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
    df, cols, group_identifier, file_id, node_set: NodeSet, edge_set: EdgeSet
) -> tuple[NodeSet, EdgeSet]:
    """Extract nodes and edges from grounded entity DataFrame into knowledge graph.

    Iterates through grounded entities and creates:
    - Nodes for each unique entity with ontology metadata (CURIE, type, name, IRI)
    - Edges connecting the project to each entity type (e.g., "has_gene", "has_disease")

    Args:
        df: DataFrame with grounded entity columns (entity, type, name, raw_text, etc.)
        cols: List of base column names to extract entities from
        group_identifier: group ID for edge creation
        file_id: Synapse file ID for provenance tracking
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update

    Returns:
        Tuple of (updated node_set, updated edge_set)

    Note:
        Tracks provenance by storing raw text, column names, and file IDs in node attributes.
        Edge types are dynamically created based on entity type (e.g., "has_protein").
    """
    source = set(["tabular_data", "experimental_data"])
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
                    "source:string[]": source,
                }
                node_set.update_nodes(new_node=attributes)
                edge_set.update_edges(
                    {
                        ":START_ID": group_identifier,
                        ":END_ID": entity,
                        ":TYPE": f"has_{entity_type}",
                        "source:string[]": source,
                    }
                )

    return node_set, edge_set


def check_df_readable(df, max_unnamed=2):
    """Validate that a DataFrame was correctly parsed and is suitable for processing.

    Checks for parsing issues like excessive unnamed columns and filters to only
    string/object columns suitable for entity grounding.

    Args:
        df: pandas DataFrame to validate
        max_unnamed: Maximum number of "Unnamed" columns allowed (default: 2)

    Returns:
        Tuple of (can_read: bool, filtered_df or None)
        - can_read is True if DataFrame is valid for processing
        - filtered_df contains only string/object columns, or None if validation fails

    Note:
        DataFrames with no columns or too many unnamed columns are considered unreadable,
        indicating parsing errors or improperly formatted source files.
    """
    ## check for error in reading
    if type(df) == str:
        return df, None
    if len(df.columns) < 1:
        return "look_into", df
    unnamed_count = sum(df.columns.str.contains("Unnamed", case=False))
    can_read = False
    if unnamed_count > max_unnamed:
        df = None
    else:
        df = df.select_dtypes(include=["object", "string"])
        can_read = True
    return "good" if can_read else "look_into", df


def load_file(group_identifier: str, fp: str):
    """Load a tabular file and validate readability of all sheets.

    Parses with frictionless framework, and validates
    each sheet (for multi-sheet files like Excel) for entity grounding.

    Args:
        group_identifier: identifier for group of files (project_id in NF data portal and case_id in gdc)
        fp: local path to the file

    Returns:
        Tuple of (list of DataFrames, list of read status dicts)
        - DataFrames: One per sheet, or None if sheet unreadable
        - Status dicts contain: project_id, file_id, file_path, can_read, reason, sheet

    Note:
        Handles locked files and parsing failures gracefully by returning empty lists
        and status dicts indicating the failure reason.
    """
    df_dict = frictionless_file_reader(fp)
    dfs = []
    read_states = []
    for sheet in df_dict:
        df = df_dict[sheet]
        ## determine if the file was read in correctly
        reason, df = check_df_readable(df)
        ## adding to a list of what files can actually be read
        read_states.append(
            {
                "group_identifier": group_identifier,
                "fp": fp,
                "can_read": reason == "good",
                "reason": reason,
                "sheet": sheet,
            }
        )
        dfs.append(df)
    return dfs, read_states


def get_tabular_data(
    group_identifiers: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    tabular_iterator: Iterator,
    write_reports: bool = True,
) -> list[pandas.DataFrame]:
    """Process tabular data files from multiple groups and build knowledge graph.

    Main orchestration function that discovers tabular files (CSV, TSV, Excel) in specified
    projects, extracts biomedical entities through text grounding with Gilda, and constructs
    a knowledge graph. Supports multi-sheet Excel files and various CSV/TSV dialects.
    """
    logger.info(f"Adding tabular experimental data for {len(group_identifiers)} groups")
    files_read = []
    cols_read = []
    for group_identifier, file_paths, file_ids in tqdm.tqdm(
        tabular_iterator, total=len(group_identifiers)
    ):
        for fp, file_id in zip(file_paths, file_ids):
            dfs, read_states = load_file(group_identifier=group_identifier, fp=fp)
            for df, read_state in zip(dfs, read_states):
                files_read.append(read_state)
                if df is not None:
                    base_cols = df.columns
                    ## ground data frame
                    entity_df = df.apply(apply_ground, axis=1)
                    filtered_df, base_cols = filter_df(entity_df, base_cols)
                    node_set, edge_set = extract_df_graph(
                        filtered_df,
                        base_cols,
                        group_identifier,
                        file_id,
                        node_set=node_set,
                        edge_set=edge_set,
                    )
                    for col in base_cols:
                        cols_read.append(
                            {
                                "group_identifier": group_identifier,
                                "file_id": file_id,
                                "file_path": fp,
                                "sheet": read_state["sheet"],
                                "col": col,
                            }
                        )
        write_graph(node_set=node_set, edge_set=edge_set)
    files_df = pandas.DataFrame(data=files_read)
    cols_df = pandas.DataFrame(data=cols_read)
    if write_reports:
        os.makedirs(REPORT_PATH, exist_ok=True)
        files_df.to_csv(
            os.path.join(REPORT_PATH, "file_report.tsv"), sep="\t", index=False
        )
        cols_df.to_csv(
            os.path.join(REPORT_PATH, "col_report.tsv"), sep="\t", index=False
        )

    return [files_df, cols_df]
