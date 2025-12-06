"""
Utility functions for core DGLink functionality
"""

from .nodes import NodeSet
from .edges import EdgeSet
from .constants import RESOURCE_PATH, RESOURCE_TYPES, syn, REPORT_PATH
from synapseclient.models import Table
import os.path
import polars as pl
from typing import Union
from synapseutils import walk
import logging
from polars import Schema, String
from typing import Union
import re
import tqdm

logger = logging.getLogger(__name__)


def load_graph(
    resource_path=RESOURCE_PATH, edge_name="edges.tsv", node_name="nodes.tsv"
):
    """
    read in a knowledge graph as a Node and Edge set.
    """
    node_set = NodeSet()
    edge_set = EdgeSet()

    node_set.load_node_set(os.path.join(resource_path, node_name))
    edge_set.load_edge_set(os.path.join(resource_path, edge_name))
    return node_set, edge_set


def write_graph(
    node_set: NodeSet,
    edge_set: EdgeSet,
    resource_path=RESOURCE_PATH,
    edge_name="edges.tsv",
    node_name="nodes.tsv",
    source_filter: bool = False,
    strict: bool = False,
    source_name: str = None,
    mixed: bool = False,
):
    """
    Write a graph represented as a Node and Edge set to Neo4j compatible tsv files.
    """
    os.makedirs(resource_path, exist_ok=True)
    if source_filter:
        ns, es = get_graph_for_source(
            node_set=node_set, edge_set=edge_set, source_name=source_name, strict=strict
        )
        ns.write_node_set(os.path.join(resource_path, f"nodes_{source_name}.tsv"))
        es.write_edge_set(os.path.join(resource_path, f"edges_{source_name}.tsv"))
    elif mixed:
        ns, es = get_graph_for_source(node_set=node_set, edge_set=edge_set, mixed=True)
        ns.write_node_set(os.path.join(resource_path, "nodes_mixed.tsv"))
        es.write_edge_set(os.path.join(resource_path, "edges_mixed.tsv"))

    else:
        node_set.write_node_set(os.path.join(resource_path, node_name))
        edge_set.write_edge_set(os.path.join(resource_path, edge_name))
    ## save all nodes and edges from multiple sources


def filter_edge_set(edge_set: EdgeSet, filter_for: str):
    """filter out edges of a certain type"""
    filtered_edge_set = EdgeSet()
    for edge_id in edge_set.edges:
        edge = edge_set.edges[edge_id]
        if edge[":TYPE"] != filter_for:
            filtered_edge_set.edges[edge_id] = edge
    filtered_edge_set.write_edge_set(os.path.join(RESOURCE_PATH, "edges.tsv"))
    return filtered_edge_set


def get_graph_for_source(
    node_set: NodeSet,
    edge_set: EdgeSet,
    source_name: str = None,
    strict: bool = True,
    mixed: bool = False,
):
    filter_node_set = NodeSet()
    filter_edge_set = EdgeSet()
    ## get resource set for a specific source
    if not mixed:
        for node_id in node_set.nodes:
            add = True
            node = node_set.nodes[node_id]
            if strict and len(node["source:string[]"]) > 1:
                add = False
            elif source_name not in node["source:string[]"]:
                add = False
            if add:
                filter_node_set.nodes[node_id] = node_set.nodes[node_id]
        for edge_id in edge_set.edges:
            add = True
            edge = edge_set.edges[edge_id]
            if strict and len(edge["source:string[]"]) > 1:
                add = False
            elif source_name not in edge["source:string[]"]:
                add = False
            if add:
                filter_edge_set.edges[edge_id] = edge_set.edges[edge_id]
        return filter_node_set, filter_edge_set
    ## get resource sets from mixed sources
    for node_id in node_set.nodes:
        node = node_set.nodes[node_id]
        if len(node["source:string[]"]) > 1:
            filter_node_set.nodes[node_id] = node_set.nodes[node_id]
    for edge_id in edge_set.edges:
        edge = edge_set.edges[edge_id]
        if len(edge["source:string[]"]) > 1:
            filter_edge_set.edges[edge_id] = edge_set.edges[edge_id]
    return filter_node_set, filter_edge_set


def write_artifacts(
    node_set: NodeSet,
    edge_set: EdgeSet,
    resource_types: list = RESOURCE_TYPES,
    resource_path: str = RESOURCE_PATH,
):
    """get artifacts (ie the resource sets for each resource type) from a graph for a given set of resource types"""
    ## get the strict version of each resource type
    for resource_type in resource_types:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name=resource_type,
            resource_path=os.path.join(resource_path, "artifacts"),
        )
    ## write out the mixed types
    write_graph(
        node_set=node_set,
        edge_set=edge_set,
        mixed=True,
        resource_path=os.path.join(resource_path, "artifacts"),
    )


def write_graph_and_artifacts_default(
    node_set: NodeSet,
    edge_set: EdgeSet,
    resource_types: list = RESOURCE_TYPES,
    resource_path: str = RESOURCE_PATH,
    node_name: str = "nodes.tsv",
    edge_name: str = "edges.tsv",
):
    """default way to write graph and and sub-graphs split by source type"""
    write_graph(
        node_set=node_set,
        edge_set=edge_set,
        resource_path=resource_path,
        node_name=node_name,
        edge_name=edge_name,
    )
    write_artifacts(
        node_set=node_set,
        edge_set=edge_set,
        resource_types=resource_types,
        resource_path=resource_path,
    )


def merge_resource_sets(
    artifacts_path: str = os.path.join(RESOURCE_PATH, "artifacts"),
    write_resource: bool = True,
):
    """merges all resource sets saved at a given path"""
    resource_files = os.listdir(artifacts_path)
    node_sets = filter(lambda x: x.startswith("nodes"), resource_files)
    edge_sets = filter(lambda x: x.startswith("edges"), resource_files)
    full_node_set = NodeSet()
    full_edge_set = EdgeSet()
    for node_path in node_sets:
        node_set = NodeSet()
        node_set.load_node_set(os.path.join(artifacts_path, node_path))
        for node_id in node_set.nodes:
            if node_id not in full_node_set.nodes:
                full_node_set.update_nodes(node_set.nodes[node_id])
    for edge_path in edge_sets:
        edge_set = EdgeSet()
        edge_set.load_edge_set(os.path.join(artifacts_path, edge_path))
        for edge_id in edge_set.edges:
            if edge_id not in full_edge_set.edges:
                full_edge_set.update_edges(edge_set.edges[edge_id])
    if write_resource:
        write_graph(node_set=full_node_set, edge_set=full_edge_set)
    return full_node_set, full_edge_set


def load_known_files_df() -> pl.DataFrame:
    """Load the cached registry of files from previously crawled projects.

    Returns:
        DataFrame with columns: project_syn_id, file_syn_id, file_name.
        Returns empty DataFrame with schema if cache file doesn't exist.
    """
    df_path = os.path.join(REPORT_PATH, "project_files.tsv")
    file_df_schema = Schema(
        [("project_syn_id", String), ("file_syn_id", String), ("file_name", String)]
    )
    if os.path.exists(df_path):
        return pl.read_csv(df_path, schema=file_df_schema, separator="\t")
    return pl.DataFrame(schema=file_df_schema)


def crawl_project_files(
    project_syn_id: str, known_files: pl.DataFrame = None
) -> pl.DataFrame:
    """Crawl a Synapse project to discover all files and update the cache.

    Args:
        project_syn_id: Synapse project ID (e.g., 'syn12345678')
        known_files: Existing file registry. If None, loads from cache.

    Returns:
        Updated DataFrame containing all known files including newly discovered ones.
        Cache file is automatically updated on disk.

    Note:
        Handles locked projects gracefully by logging a warning and continuing.
    """
    if known_files is None:
        known_files = load_known_files_df()
    found_files = []
    try:
        ## will throw and error if try to lead wiki of locked project
        _ = syn.getWiki(project_syn_id)
        file_name_iter = walk(
            syn=syn,
            synId=project_syn_id,
            includeTypes=[
                "file",
            ],
        )
    except:
        logger.warning(f"Could not read files for project with id {project_syn_id}")
        file_name_iter = [
            [
                "",
                "",
                [("", "")],
            ]
        ]  ## give just empty syn_id and file_name
    for _, _, filenames in file_name_iter:
        for filename, file_syn_id in filenames:
            found_files.append(
                {
                    "project_syn_id": project_syn_id,
                    "file_syn_id": file_syn_id,
                    "file_name": filename,
                }
            )

    found_files = pl.from_dicts(found_files, schema=known_files.schema)
    known_files = known_files.vstack(found_files)
    known_files.write_csv(
        os.path.join(REPORT_PATH, "project_files.tsv"), separator="\t"
    )
    return known_files


def get_project_files(
    project_syn_id: str, file_types: list = None, as_list: bool = False
) -> Union[pl.DataFrame, list]:
    """Get all files for a Synapse project, with optional filtering by file extension.

    Uses cached data if available, otherwise crawls the project and updates cache.

    There is a table that has many of the files already aggregated from the nf data portal, but it seems to be missing a lot of files that can be pulled by just crawling everything.

    Args:
        project_syn_id: Synapse project ID (e.g., 'syn12345678')
        file_types: Optional list of file extensions to filter by (e.g., ['.vcf', '.bam'])
        as_list: If True, returns list of file_syn_ids instead of DataFrame

    Returns:
        DataFrame with columns [project_syn_id, file_syn_id, file_name], or
        list of file_syn_ids if as_list=True

    Examples:
        >>> # Get all files as DataFrame
        >>> files = get_project_files('syn12345678')
        >>>
        >>> # Get only VCF files as list of IDs
        >>> vcf_ids = get_project_files('syn12345678', file_types=['.vcf'], as_list=True)
    """
    known_files = load_known_files_df()
    ## check if we have already crawled the files for this data frame
    if len(known_files.filter(pl.col("project_syn_id").eq(project_syn_id))) > 0:
        logger.info(f"loading files for {project_syn_id} from cache")
    ## if not crawl the files and save the results
    else:
        logger.info(
            f"Files from {project_syn_id} not found in cache, checking synapse..."
        )
        known_files = crawl_project_files(
            project_syn_id=project_syn_id, known_files=known_files
        )

    project_files = known_files.filter(pl.col("project_syn_id").eq(project_syn_id))
    if file_types is not None:
        file_types_pattern = f"({'|'.join(re.escape(s) for s in file_types)})$"
        project_files = project_files.filter(
            pl.col("file_name").str.contains(file_types_pattern)
        )
    if as_list:
        project_files = project_files["file_syn_id"].to_list()
    return project_files


def get_projects_files(project_ids: list) -> pl.DataFrame:
    """Get all files for multiple Synapse projects.

    Efficiently retrieves files for multiple projects by using cached data when
    available and only crawling uncached projects.

    Args:
        project_ids: List of Synapse project IDs (e.g., ['syn12345678', 'syn87654321'])

    Returns:
        DataFrame containing files from all specified projects with columns:
        [project_syn_id, file_syn_id, file_name]

    Note:
        Cache is automatically updated with any newly crawled projects.
    """
    known_files = load_known_files_df()
    for project_syn_id in tqdm.tqdm(project_ids):
        ## check if we have already crawled the files for this data frame
        if len(known_files.filter(pl.col("project_syn_id").eq(project_syn_id))) > 0:
            logger.info(f"loading files for {project_syn_id} from cache")
            continue
        ## if not crawl the files and save the results
        else:
            logger.info(
                f"Files from {project_syn_id} not found in cache, checking synapse..."
            )
            known_files = crawl_project_files(
                project_syn_id=project_syn_id, known_files=known_files
            )

    return known_files.filter(pl.col("project_syn_id").is_in(project_ids))
