"""
Extract knowledge graph information from tabular data files.

This module processes structured tabular files (CSV, TSV, Excel) from Synapse projects
to extract biomedical entities through text grounding and construct a knowledge graph.
Uses Gilda for entity recognition and INDRA for ontology typing.
"""

from .constants import (
    REPORT_PATH,
    TABULAR_ENTITY_TYPES_LLM,
    open_ai_client,
    evaluation_response,
)
from .utils import write_graph
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
import json
import numpy as np
from openai import BadRequestError


logger = logging.getLogger(__name__)


def heuristic_quality_check(
    df, base_cols, nan_percentage=0.1, max_types=8
) -> tuple[pandas.DataFrame, list]:
    """Filter grounded entity DataFrame to remove low-quality or overly heterogeneous columns based on heuristics

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
    # res = df.loc[:, df.count() / len(df) >= nan_percentage]
    base_cols = [x for x in base_cols if f"{x}_type" in df.columns]
    ## filter out columns with more than some set number of max entity types
    cols_to_drop = []
    for base in base_cols:
        if (df[f"{base}_type"].nunique() > max_types) or (
            df[f"{base}_name"].count() / len(df) <= nan_percentage
        ):
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
    final = df.drop(columns=cols_to_drop)
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
                ## This check makes it type safe. I do not think should have any effect remove if does ##
                if not isinstance(col_names, list):
                    raise ValueError(f"col_names of type {type(col_names)} unexpected")

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
    elif pth.suffix == ".txt":
        # Check first line
        with open(pth) as tmp:
            first_line = tmp.readline()
        # Check tab-separated first (more specific)
        if len(first_line.split("\t")) > 1:
            pac.add_resource(Resource(pth, format="tsv"))
            format = ".tsv"
        # Then check comma-separated
        elif len(first_line.split(",")) > 1:
            pac.add_resource(Resource(pth, format="csv"))
            format = ".csv"
        # Fallback: let Frictionless auto-detect
        else:
            pac.add_resource(Resource(pth))
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
    fp = Path(pth)
    file_size = os.path.getsize(fp)
    if file_size > max_size_bytes:
        logger.info("file to large to read")
        return {"all": "to_large"}
    ## load file contents into frictionless package

    pack = get_frictionless_package(pth=fp)
    ## load frictionless package into dictionary of pandas data frames
    df_dict = {}
    from frictionless.resources import TableResource

    for res in pack.resources:
        ## type check to make things type safe remove is this cause issue
        if not isinstance(res, TableResource):
            raise ValueError(f"this should be a table not {type(res)}")  ## change this
        try:
            df_dict[res.name] = pandas.DataFrame(res.read_rows())
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
        else:
            return pandas.NA, pandas.NA, pandas.NA, val, col, pandas.NA
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


def get_dtype_counts(df: pandas.DataFrame) -> pandas.DataFrame:
    """get the count of data types in each col of a data frame"""
    records = {}
    for col in df.columns:
        string_count = df[col].apply(lambda x: isinstance(x, str)).sum()
        missing_count = df[col].isna().sum()
        records[col] = {
            "string": string_count,
            "missing": missing_count,
            "other": len(df) - string_count - missing_count,
        }
    return pandas.DataFrame(records).T


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
        type_counts = get_dtype_counts(df)
        ## remove columns that have more columns that are neither string nor missing then columns that are string valued
        good_cols = type_counts[
            (type_counts["string"] > type_counts["other"])
        ].index.tolist()
        df = df[good_cols]
        # Older method returns string column and any mixed data type column, was to permissive #
        # df = df.select_dtypes(include=["object", "string"])
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


def get_llm_schema_matching_prompt(
    entity_df: pandas.DataFrame,
    col: str,
    file_name: str,
    table_cols: list,
    max_samples: int = 5,
) -> tuple[str, str]:
    table_len = len(entity_df)
    grounded_count = entity_df[f"{col}_name"].count()
    rows_with_values = max(
        entity_df[f"{col}_raw_text"].count(), 1
    )  ## account for cases where there are no rows with values.
    ## skip columns with no groundings
    # if grounded_count == 0:
    #     return '', ''
    ## skip cols where less than 10% of rows that had entities were grounded.
    if (grounded_count / max(rows_with_values, 1)) < 0.1:
        return "", ""
    ungrounded_count = table_len - entity_df[f"{col}_name"].count()
    records = []
    identified_entities = (
        entity_df[f"{col}_type"].dropna().value_counts().sort_index().to_dict()
    )
    unique_identified_entities = (
        entity_df.dropna(subset=f"{col}_type")
        .groupby(f"{col}_type")[f"{col}_raw_text"]
        .nunique()
        .sort_index()
        .to_dict()
    )
    for key in TABULAR_ENTITY_TYPES_LLM:
        if key not in identified_entities:
            identified_entities[key] = 0
            unique_identified_entities[key] = 0
    sample_df = entity_df[[f"{col}_raw_text", f"{col}_type", f"{col}_name"]].dropna(
        subset=f"{col}_raw_text"
    )
    sample_size = min(max_samples, len(sample_df))
    for _, row in sample_df.sample(n=sample_size).iterrows():
        row_type = (
            "Unable to ground"
            if pandas.isna(row[f"{col}_type"])
            else row[f"{col}_type"]
        )
        row_name = (
            "Unable to ground"
            if pandas.isna(row[f"{col}_name"])
            else row[f"{col}_name"]
        )
        records.append(
            {
                "raw_text": row[f"{col}_raw_text"],
                "grounded_entity_type": row_type,
                "grounded_entity_name": row_name,
            }
        )
    model_prompt = f"""
    Table information:
    - File name: {file_name}
    - Table columns: {table_cols}
    - Total rows: {table_len}

    Column information:
    - Column Name: {col}
    - Number of missing rows in column: {table_len - rows_with_values}
    - Number of rows that were unable to be grounded in column: {ungrounded_count}
    - Column Distribution of rows by predicted entity type: {json.dumps(identified_entities, indent=6)}
    - Column Distribution of unique rows by predicted entity type: {json.dumps(unique_identified_entities, indent=6)}
    - Column Sample record: {json.dumps(records, indent=2)}
    """

    # model_context = f"Given the following table and column information, predict the Probability (so that all values some to 1) that the column represents entities of each of the following types {TABULAR_ENTITY_TYPES_LLM} as well as no entity type in the schema"
    content_list = "\n    - ".join(TABULAR_ENTITY_TYPES_LLM + ["no_schema_match"])
    model_context = f"""
    You must output a probability distribution over the following entity types.
    Each probability must be a float between 0 and 1.
    All probabilities must sum to 1.

    Valid entity types (output field names, must match exactly):
    - {content_list}

    The probabilities should reflect the semantic meaning of the column as a whole,
    not individual rows.

    Note: Rows that were unable to be grounded refers to cases where a unique ontology identifier could not be assigned,
    but the raw values may still be valid entities
    
    Note: Use no_schema_match when the column does not predominantly contain biological entity names
    or when the column semantics are unclear or non-entity (e.g., free text, measurements, IDs).
    """
    return model_context, model_prompt


def call_llm_for_schema_matching(
    llm_prompt: tuple[str, str], model: str
) -> dict[str, float]:
    call_context, call_prompt = llm_prompt
    if call_prompt == "":
        return {
            entity_type: 0
            for entity_type in TABULAR_ENTITY_TYPES_LLM + ["no_schema_match"]
        }
    try:
        response = open_ai_client.responses.parse(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": call_context,
                },
                {"role": "user", "content": call_prompt},
            ],
            text_format=evaluation_response,
        )
    except BadRequestError:
        raise ValueError(
            f"Model {model} invalid perhaps try gpt-4o, gpt-4o-mini, gpt-5 or gpt-5-mini"
        )

    raw_probs = response.output_parsed
    if raw_probs:
        raw_probs = raw_probs.model_dump()
    else:
        raw_probs = dict()
    values = np.array(list(raw_probs.values()))
    normalized_probs = values / values.sum()
    out = dict(zip(raw_probs.keys(), normalized_probs))
    return out


def process_schema_matching(
    matching_cols: dict, entity_df: pandas.DataFrame, base_cols: list
) -> tuple[pandas.DataFrame, list]:
    """
    use the schema match to:
        1. drop cols if not matched
        2. return only values for that col which were grounded to the matched schema type
    """
    for col in matching_cols:
        entity_cols = [
            f"{col}_entity",
            f"{col}_type",
            f"{col}_name",
            f"{col}_raw_text",
            f"{col}_column_name",
            f"{col}_iri",
        ]
        ## if not matched to schema drop
        if matching_cols[col] is None:
            base_cols.remove(col)
        ## otherwise set entities found with any other data type to na
        else:
            type_col = f"{col}_type"
            index_mask = ~(
                entity_df[type_col].notna()
                & (entity_df[type_col].isin(matching_cols[col]))
            )
            entity_df.loc[index_mask, entity_cols] = pandas.NA
    return entity_df, base_cols


def llm_schema_match(
    unmatched_df: pandas.DataFrame,
    all_original_cols: list,
    table_path: str,
    max_samples: int,
    confidence_threshold: float,
    model: str,
) -> tuple[pandas.DataFrame, list]:
    schema_map = {}
    matching_cols = []
    for col in all_original_cols:
        llm_prompt = get_llm_schema_matching_prompt(
            entity_df=unmatched_df,
            col=col,
            file_name=Path(table_path).name,  ## pass just the name
            max_samples=max_samples,
            table_cols=all_original_cols,
        )
        llm_resp = call_llm_for_schema_matching(llm_prompt=llm_prompt, model=model)
        ## check cases where it is confident that the col represents nothing or unconfined in everything
        most_likely_entity_type: str = max(llm_resp, key=lambda k: llm_resp[k])
        ## TODO: Decide how want to do cut off for llm schema matching ##
        # if llm_resp.get('no_schema_match', 0) > confidence_threshold or max(llm_resp.values()) < confidence_threshold:
        #     schema_map[col] = None

        if (
            llm_resp.get(most_likely_entity_type, 0) < confidence_threshold
            or most_likely_entity_type == "no_schema_match"
        ):
            schema_map[col] = None
        else:
            schema_map[col] = [
                key
                for key in TABULAR_ENTITY_TYPES_LLM
                if llm_resp.get(key, 0) > confidence_threshold
            ]
            matching_cols.append(col)
    validated_dataset, matching_cols = process_schema_matching(
        matching_cols=schema_map, entity_df=unmatched_df, base_cols=all_original_cols
    )
    return validated_dataset, matching_cols


def quality_check_groundings(
    qc_method: str,
    grounded_dataset: pandas.DataFrame,
    original_dataset_cols: list,
    dataset_path: str,
    max_schema_matching_samples: int,
    schema_matching_confidence_threshold: float,
    model: str,
) -> tuple[pandas.DataFrame, list]:
    matched_dataset, retained_columns = (
        grounded_dataset,
        original_dataset_cols,
    )
    if qc_method == "heuristic":
        matched_dataset, retained_columns = heuristic_quality_check(
            grounded_dataset, original_dataset_cols
        )
    elif qc_method == "llm_schema_match":
        matched_dataset, retained_columns = llm_schema_match(
            grounded_dataset,
            original_dataset_cols,
            dataset_path,
            max_samples=max_schema_matching_samples,
            confidence_threshold=schema_matching_confidence_threshold,
            model=model,
        )
    return matched_dataset, retained_columns


def get_tabular_data(
    group_identifiers: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    tabular_iterator: Iterator,
    write_reports: bool = True,
    quality_check_method: str = "heuristic",
    max_quality_check_samples: int = 10,
    quality_check_confidence_threshold: float = 0.5,
    model: str = "gpt-4o",
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
                    base_cols = df.columns.to_list()
                    ## try to ground everything in the dataframe
                    raw_groundings = df.apply(apply_ground, axis=1)
                    ## quality check groundings and only select those that pass ##
                    filtered_df, base_cols = quality_check_groundings(
                        qc_method=quality_check_method,
                        grounded_dataset=raw_groundings,
                        original_dataset_cols=base_cols,
                        dataset_path=fp,
                        max_schema_matching_samples=max_quality_check_samples,
                        schema_matching_confidence_threshold=quality_check_confidence_threshold,
                        model=model,
                    )
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
