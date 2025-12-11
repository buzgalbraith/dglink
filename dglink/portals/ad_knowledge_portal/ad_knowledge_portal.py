from dglink.core.constants import DGLINK_CACHE, syn, RESOURCE_PATH
from .constants import (
    AD_BASE_PROJECT_URL,
    AD_BASE_PROGRAM_URL,
    AD_BASE_STUDY_URL,
    GROUND_FIELDS,
    UNGROUNDED_FIELDS,
)
from dglink.core.meta import get_entities_from_meta
from pathlib import Path
import os
import logging
import pandas
from dglink.core.utils import write_graph
from dglink.core.nodes import NodeSet
from dglink.core.edges import EdgeSet
import polars as pl
import tqdm

logger = logging.getLogger(__name__)


def download_all_ad_studies():
    """
    Download and cache the complete list of studies from the AD Knowledge Portal.

    Queries the AD Knowledge Portal's Synapse table (syn17083367) containing study
    metadata and saves it as a tab-separated file in the DGLink cache directory.


    """
    os.makedirs(Path(DGLINK_CACHE), exist_ok=True)
    query = syn.tableQuery("SELECT * FROM syn17083367")
    df = query.asDataFrame()
    df.to_csv(f"{DGLINK_CACHE}/all_ad_studies.tsv", sep="\t", index=False)


def get_all_ad_studies() -> list:
    """
    Retrieve list of all study identifiers from the AD Knowledge Portal.

    Returns a list of study IDs from the Alzheimer's Disease Knowledge Portal. Uses
    cached data when available, otherwise queries Synapse table syn17083367 and
    caches the result for future use.

    Returns:
        list: Study identifiers from the AD Knowledge Portal
    """
    ad_studies_path = f"{DGLINK_CACHE}/all_ad_studies.tsv"
    if not os.path.exists(ad_studies_path):
        logger.info("AD Knowledge Portal studies list not found.")
        logger.info("Pulling AD Knowledge Portal studies list")
        download_all_ad_studies()
        logger.info(f"AD Knowledge Portal studies list saved to {ad_studies_path}")
    return pandas.read_csv(ad_studies_path, sep="\t")["Study"].to_list()


def get_program_project_study_hierarchy(
    node_set: NodeSet, edge_set: EdgeSet, write_set: bool = False
) -> tuple[NodeSet, EdgeSet]:
    """
    Build knowledge graph representation of AD Knowledge Portal's organizational hierarchy.

    Constructs a three-level hierarchy (Program → Project → Study) by querying AD
    Knowledge Portal metadata tables and adding nodes and edges to the provided graph
    structures. Programs contain Projects (identified by grant numbers), which in turn
    contain Studies.

    The hierarchy structure:
    - Program nodes: Top-level organizational units (e.g., program names)
    - Project nodes: Grant-funded projects identified by grant numbers
    - Study nodes: Individual research studies with Synapse IDs
    - Edges: Program →has_project→ Project →has_study→ Study

    Args:
        node_set: NodeSet instance to add Program, Project, and Study nodes to
        edge_set: EdgeSet instance to add hierarchical relationship edges to
        write_set: If True, writes the graph to disk after construction. Writes to
            {RESOURCE_PATH}/artifacts/ with source filter and strict validation enabled.
            Defaults to False.

    Returns:
        tuple[NodeSet, EdgeSet]: The updated node_set and edge_set with hierarchy added
    """
    project_table_id = "syn17024229"
    studies_table_id = "syn17083367"
    query = syn.tableQuery(f"SELECT * FROM {project_table_id}")
    df = query.asDataFrame()
    df = pl.from_dataframe(df)
    for row in df.iter_rows(named=True):
        ## add the project as a node
        grant_number = row.get("Grant Number", "Missing grant number")
        program_id = row.get("Program", "Missing program")
        node_set.update_nodes(
            {
                "curie:ID": grant_number,
                ":LABEL": "Project",
                "name": row["Name"].strip(),
                "study_url": f"{AD_BASE_PROJECT_URL}={grant_number}",
                "source:string[]": "projects",
            }
        )
        ## Add the program as a node
        node_set.update_nodes(
            {
                "curie:ID": program_id,
                ":LABEL": "Program",
                "name": program_id,
                "study_url": f"{AD_BASE_PROGRAM_URL}={program_id}",
                "source:string[]": "projects",
            }
        )
        ## add an edge from the project to the program
        edge_set.update_edges(
            {
                ":START_ID": program_id,
                ":END_ID": grant_number,
                ":TYPE": "has_project",
                "source:string[]": "projects",
            }
        )
    query = syn.tableQuery(f"SELECT * FROM {studies_table_id}")
    df = query.asDataFrame()
    df = pl.from_dataframe(df)
    for row in df.iter_rows(named=True):
        ## add study nodes
        study_id = row.get("Study", "Missing study id")
        node_set.update_nodes(
            {
                "curie:ID": study_id,
                ":LABEL": "Study",
                "name": row.get("Study_Name", "name missing").strip(),
                "study_url": f"{AD_BASE_STUDY_URL}={study_id}",
                "source:string[]": "studies",
            }
        )
        ## add edges from each project
        for grant_number in row.get("Grant Number"):
            edge_set.update_edges(
                {
                    ":START_ID": grant_number,
                    ":END_ID": study_id,
                    ":TYPE": "has_study",
                    "source:string[]": "studies",
                }
            )
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="programs",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )

    return node_set, edge_set


def get_publications(node_set: NodeSet, edge_set: EdgeSet, write_set: bool = False):
    """
    Add publication nodes and their relationships to studies from AD Knowledge Portal.

    Queries the AD Knowledge Portal publications table (syn20448807) and creates:
    - Publication nodes with PubMed IDs, titles, and DOIs
    - Edges linking publications to their associated grant projects

    Args:
        node_set: NodeSet instance to add publication nodes to
        edge_set: EdgeSet instance to add publication-project edges to
        write_set: If True, writes the graph to disk. Defaults to False.

    Returns:
        tuple[NodeSet, EdgeSet]: Updated node and edge sets with publications added

    """
    query = syn.tableQuery("SELECT * FROM syn20448807")
    df = pl.from_dataframe(query.asDataFrame())

    # Filter out rows with missing critical data upfront
    df = df.filter(pl.col("pubmed_id").is_not_null() & pl.col("grant").is_not_null())

    # Handle missing/null values with fill_null and coalesce
    df = df.with_columns(
        [
            pl.col("DOI").fill_null("doi missing").str.strip_chars().alias("DOI"),
            pl.col("name").fill_null("name missing").str.strip_chars().alias("name"),
            pl.col("pubmed_id").cast(pl.Int64).alias("pubmed_id"),
        ]
    )

    # Iterate over cleaned data
    for pub in tqdm.tqdm(df.iter_rows(named=True)):
        # Add publication node
        node_set.update_nodes(
            {
                "curie:ID": str(pub["pubmed_id"]),
                ":LABEL": "publication",
                "name": pub["name"],
                "DOI": pub["DOI"],
                "source:string[]": "publications",
            }
        )

        # Add edges to all associated projects
        for project_id in pub["grant"]:
            edge_set.update_edges(
                {
                    ":START_ID": str(project_id),
                    ":END_ID": pub["pubmed_id"],
                    ":TYPE": "published",
                    "source:string[]": "publications",
                }
            )

    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="publications",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )

    return node_set, edge_set


def get_metadata_ad_knowledge_portal(
    node_set: NodeSet, edge_set: EdgeSet, write_set: bool = False
) -> tuple[NodeSet, EdgeSet]:
    """method for loading metadata from the AD Knowledge portal, because they are not storing meta data directly on synapse"""
    studies_table_id = "syn17083367"
    query = syn.tableQuery(f"SELECT * FROM {studies_table_id}")
    df = query.asDataFrame()
    df = pl.from_dataframe(df)
    for study_metadata in tqdm.tqdm(df.iter_rows(named=True)):
        node_set, edge_set = get_entities_from_meta(
            study_metadata=study_metadata,
            ground_fields=GROUND_FIELDS,
            unground_fields=UNGROUNDED_FIELDS,
            node_set=node_set,
            edge_set=edge_set,
            id_field="Study",
        )
    return node_set, edge_set
