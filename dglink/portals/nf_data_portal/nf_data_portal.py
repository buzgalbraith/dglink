from dglink.core.constants import (
    DGLINK_CACHE,
    RESOURCE_PATH,
    TABULAR_FILE_TYPES,
    REPORT_PATH,
)
from dglink.core.tabular_data import (
    check_df_readable,
    get_frictionless_package,
    filter_df,
    apply_ground,
    extract_df_graph,
)
from dglink.core.utils import get_project_files
from .constants import syn
from pathlib import Path
import os
import logging
import pandas
from dglink.core.utils import write_graph
from dglink.core.nodes import NodeSet
from dglink.core.edges import EdgeSet
from bioregistry import get_bioregistry_iri
import tqdm

logger = logging.getLogger(__name__)


def frictionless_file_reader(obj, max_size_bytes=100 * 1024 * 1024):
    """Read tabular files from Synapse file objects using Frictionless framework.

    Downloads and parses various tabular formats (CSV, TSV, Excel) into a dictionary
    of pandas DataFrames, with one DataFrame per sheet for multi-sheet files.

    Args:
        obj: Synapse file object with path attribute
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
    if obj is None:
        return {"all": "locked"}
    if obj.path is None:
        return {"all": "locked"}
    ## check file size
    pth = Path(obj.path)
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


def load_file(syn_file_id, project_id):
    """Load a tabular file from Synapse and validate readability of all sheets.

    Downloads file from Synapse, parses with frictionless framework, and validates
    each sheet (for multi-sheet files like Excel) for entity grounding.

    Args:
        syn_file_id: Synapse file ID (e.g., 'syn12345678')
        project_id: Synapse project ID for tracking

    Returns:
        Tuple of (list of DataFrames, list of read status dicts)
        - DataFrames: One per sheet, or None if sheet unreadable
        - Status dicts contain: project_id, file_id, file_path, can_read, reason, sheet

    Note:
        Handles locked files and parsing failures gracefully by returning empty lists
        and status dicts indicating the failure reason.
    """
    try:
        obj = syn.get(syn_file_id)
    except:
        return [None], [
            {
                "project_id": project_id,
                "file_id": "_",
                "file_path": str(syn_file_id),
                "can_read": False,
                "reason": "Locked",
                "sheet": "all",
            }
        ]
    df_dict = frictionless_file_reader(obj)
    # if len(df_dict) < 1:
    #     return [], {
    #         "project_id": project_id,
    #         "file_id": "_",
    #         "file_path": syn_file_id,
    #         "can_read": False,
    #         "reason": "Locked",
    #         "sheet": "all",
    #     }

    dfs = []
    read_states = []
    for sheet in df_dict:
        df = df_dict[sheet]
        ## determine if the file was read in correctly
        reason, df = check_df_readable(df)
        ## adding to a list of what files can actually be read
        read_states.append(
            {
                "project_id": project_id,
                "file_id": obj.id,
                "file_path": str(obj.path),
                "can_read": reason == "good",
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
) -> tuple[NodeSet, EdgeSet, list, list]:
    """Process all tabular files in a project and extract entities into knowledge graph.

    Main processing loop for a single project that:
    1. Loads each file and validates sheets
    2. Grounds text in all string columns to biomedical entities
    3. Filters columns by grounding quality
    4. Extracts entities and relationships into the knowledge graph
    5. Tracks processing status for reporting

    Args:
        project_files: List of Synapse file IDs to process
        project_id: Synapse project ID
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update
        cols_read: Running list of successfully processed column metadata (modified in place)
        files_read: Running list of file processing status (modified in place)

    Returns:
        Tuple of (updated node_set, updated edge_set, files_read, cols_read)

    Note:
        Uses Gilda for entity grounding with caching to improve performance.
        Processing status is tracked at both file and column granularity for debugging.
    """
    for syn_file_id in tqdm.tqdm(project_files):
        dfs, read_states = load_file(syn_file_id=syn_file_id, project_id=project_id)
        # if len(dfs) < 1:
        #     files_read.append(read_states)
        # else:
        for df, read_state in zip(dfs, read_states):
            files_read.append(read_state)
            if df is not None:
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


def download_all_nf_studies():
    """
    Saves a list of all studies on the NF Data Portal
    """
    os.makedirs(Path(DGLINK_CACHE), exist_ok=True)
    query = syn.tableQuery("SELECT * FROM syn52694652")
    df = query.asDataFrame()
    df.to_csv(f"{DGLINK_CACHE}/all_nf_studies.tsv", sep="\t", index=False)


def get_all_nf_studies():
    """
    Checks the list of all studies on the NF Data Portal exists and makes it if not. Returns all nf study ids as a list.
    """
    nf_studies_path = f"{DGLINK_CACHE}/all_nf_studies.tsv"
    if not os.path.exists(nf_studies_path):
        logger.info("NF Data Portal studies list not found.")
        logger.info("Pulling NF Data Portal studies list")
        download_all_nf_studies()
        logger.info(f"NF Data Portal studies list saved to {nf_studies_path}")
    return pandas.read_csv(nf_studies_path, sep="\t")["studyId"].to_list()


def get_publications(node_set: NodeSet, edge_set: EdgeSet, write_set: bool = False):
    """pulls nodes for publications and adds edges from them to related studies from NF Data Portal"""
    query = syn.tableQuery("SELECT * FROM syn16857542")
    df = query.asDataFrame()
    ## make publication nodes and edges
    for publication in tqdm.tqdm(df.itertuples()):
        node_set.update_nodes(
            {
                "curie:ID": publication.pmid,
                ":LABEL": "publication",
                "name": publication.title,
                "DOI": (
                    publication.doi if not pandas.isnull(publication.doi) else "No DOI"
                ),
                "source:string[]": "publications",
            },
        )
        for study_id in publication.studyId:
            edge_set.update_edges(
                {
                    ":START_ID": study_id,
                    ":END_ID": publication.pmid,
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


def get_tool_nodes(node_set: NodeSet):
    """returns a set with all tool nodes and a mapping from any name (or synonym) to its curie"""
    ## this table has all NF data portal tool meta data, it was generated from the programmatic export on the nf data portal website.
    query = syn.tableQuery("SELECT * FROM syn51730943")
    df = query.asDataFrame()
    ## make set to hold nodes, and mapping from names back to identifiers
    name_to_rid = dict()
    for row in tqdm.tqdm(df.itertuples()):
        ## some tools do not have a curie, in this case we just use the plane text name as an identifier
        rrid = row.rrid if not pandas.isnull(row.rrid) else row.resourceName
        iri = ""
        if type(row.rrid) == str:
            tmp = row.rrid.split(":", maxsplit=1)
            iri = get_bioregistry_iri(tmp[0], tmp[1])

        ## saving curie as id for node and tool as type but also keeping plane text name and type of tools as node attributes
        node_set.update_nodes(
            {
                "curie:ID": rrid,
                ":LABEL": "tool",
                "name": row.resourceName,
                "tool_type": row.resourceType,
                "iri": iri,
                "source:string[]": "tools",
            },
        )
        ## update name mapping with primary name and synonyms
        name_to_rid[row.resourceName] = rrid
        for synonym in row.synonyms:
            name_to_rid[synonym] = rrid

    return node_set, name_to_rid


def get_tool_edges(project_ids: list, name_to_rid: dict, edge_set: EdgeSet):
    """parse file meta data for each project in a list of projects, to extract links between tools and projects.
    Simply checks if the name or (or synonym) of each tool is in the file individualID or any specimenID.
    """
    for project_id in tqdm.tqdm(project_ids):
        query = syn.tableQuery(
            f"SELECT * FROM syn52702673 WHERE ( ( \"studyId\" LIKE '%{project_id.strip('syn')}%' ) ) AND ( resourceType IN ( 'analysis', 'experimentalData', 'results' ) )"
        )
        df = query.asDataFrame()
        for row in df.itertuples():
            for specimen in row.specimenID:
                if specimen in name_to_rid.keys():
                    edge_set.update_edges(
                        {
                            ":START_ID": project_id,
                            ":END_ID": name_to_rid[specimen],
                            ":TYPE": "usesTool",
                            "source:string[]": "tools",
                        }
                    )
            if row.individualID in name_to_rid.keys():
                edge_set.update_edges(
                    {
                        ":START_ID": project_id,
                        ":END_ID": row.individualID,
                        ":TYPE": "usesTool",
                        "source:string[]": "tools",
                    }
                )
    return edge_set


def get_tools(
    node_set: NodeSet, edge_set: EdgeSet, project_ids: list, write_set: bool = False
):
    logger.info("Getting nodes for NF Data Portal tools")
    node_set, name_to_rid = get_tool_nodes(node_set=node_set)
    logger.info("Searching project metadata for NF Data Portal tools")
    edge_set = get_tool_edges(
        project_ids=project_ids, edge_set=edge_set, name_to_rid=name_to_rid
    )
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="tools",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set


def get_tabular_data(
    project_ids: list,
    node_set: NodeSet,
    edge_set: EdgeSet,
    write_set: bool = False,
    write_reports: bool = True,
    write_intermediate: bool = True,
) -> tuple[NodeSet, EdgeSet, list[pandas.DataFrame]]:
    """Process tabular data files from multiple Synapse projects and build knowledge graph.

    Main orchestration function that discovers tabular files (CSV, TSV, Excel) in specified
    projects, extracts biomedical entities through text grounding with Gilda, and constructs
    a knowledge graph. Supports multi-sheet Excel files and various CSV/TSV dialects.

    Args:
        project_ids: List of Synapse project IDs to process
        node_set: Existing set of nodes to update
        edge_set: Existing set of edges to update
        write_set: If True, write final knowledge graph to disk
        write_reports: If True, generate TSV reports of file and column processing status
        write_intermediate: If True, write graph after each project

    Returns:
        Tuple of (updated node_set, updated edge_set, list of report DataFrames)
        Report DataFrames: [files_df (processing status), cols_df (grounded columns)]

    Note:
        Uses Gilda for entity grounding and INDRA for ontology typing. Applies quality
        filters to remove columns with low grounding rates or excessive entity type diversity.
        Intermediate graphs and reports are written to RESOURCE_PATH/artifacts and REPORT_PATH.

    Processing pipeline per file:
        1. Load file with frictionless (handles multiple formats/sheets)
        2. Validate sheet readability
        3. Ground all string columns to biomedical entities
        4. Filter columns by grounding quality (≥10% success, ≤5 entity types)
        5. Extract entities and project relationships into graph

    Examples:
        >>> # Process tabular files from multiple projects
        >>> nodes, edges, reports = get_tabular_data(
        ...     project_ids=['syn12345', 'syn67890'],
        ...     node_set=NodeSet(),
        ...     edge_set=EdgeSet(),
        ...     write_intermediate=True
        ... )
        >>> files_report, cols_report = reports
    """
    logger.info(f"Adding tabular experimental data for {len(project_ids)} projects")
    files_read = []
    cols_read = []
    i = 1
    for project_id in tqdm.tqdm(project_ids):
        project_files = get_project_files(
            project_syn_id=project_id, file_types=TABULAR_FILE_TYPES, as_list=True
        )
        logger.info(
            f"adding experimental data project {project_id}\n\
                    This is project {i} out of {len(project_ids)+1} \n\
                    There are {len(project_files)} total files to parse."
        )
        i = i + 1
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
                source_name=["tabular_data", "experimental_data"],
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
            source_name=["tabular_data", "experimental_data"],
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )

    if write_reports:
        os.makedirs(REPORT_PATH, exist_ok=True)
        files_df.to_csv(
            os.path.join(REPORT_PATH, "file_report.tsv"), sep="\t", index=False
        )
        cols_df.to_csv(
            os.path.join(REPORT_PATH, "col_report.tsv"), sep="\t", index=False
        )

    return node_set, edge_set, [files_df, cols_df]
