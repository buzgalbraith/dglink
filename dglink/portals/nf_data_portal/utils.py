from .constants import syn, NF_DATA_PORTAL_CACHE_DIR
from dglink.core.constants import TABULAR_FILE_TYPES, DGLINK_CACHE, REPORT_PATH
import polars as pl
import pandas
from synapseutils import walk
from synapseclient.models import File

import os
import re
from pathlib import Path
import asyncio
from typing import Iterator, Union
import tqdm
import logging 

logger = logging.getLogger(__name__)



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


def safe_download(syn_id:str)->str|None:
    """safe method to download from nf data portal"""
    try:
        entity = syn.get(syn_id, ifcollision="keep.local") ## keep local file if already downloaded ie do not re-download.
        return entity.path
    except Exception:
        logger.warning(f"Could not download file {syn_id}", exc_info=True)
        return None

def fetch_nf_tabular_files()->pl.DataFrame:
    """
    Pulls all tabular files from the NF data portal and saves them as a list
    
    :return: Description
    :rtype: DataFrame
    """
    output_path:str = os.path.join(
            NF_DATA_PORTAL_CACHE_DIR, 
            'tabular_file_paths.tsv'
        )
    if os.path.exists(output_path):
        logger.info("Loading tabular file paths from cache...")
        tabular_project_files = pl.read_csv(output_path, separator='\t')
    else:
        logger.info("fetching tabular files from the NF data portal...")    
        ## get a full list of studies
        project_ids = get_all_nf_studies()
        ## crawl all projects
        project_files = get_projects_files(project_ids=project_ids, )
        ## filter for tabular projects
        file_types_pattern = f"({'|'.join(re.escape(s) for s in TABULAR_FILE_TYPES)})$"
        tabular_project_files = project_files.filter(
            pl.col("file_name").str.contains(file_types_pattern)
        )
        tabular_project_files = tabular_project_files.with_columns(
            file_path=pl.col('file_syn_id').map_elements(
                safe_download,
                return_dtype=pl.String
            )
        )
        os.makedirs(
            NF_DATA_PORTAL_CACHE_DIR, 
            exist_ok=True
        )
        tabular_project_files.write_csv(
            output_path, 
            separator='\t'
        )
    return tabular_project_files

def get_tabular_iterator(project_list: list) -> Iterator:
    """
    returns a 2d iterator of project_id and associated file_paths
    """
    ## get a list of tabular files and download if need be 
    tabular_files = fetch_nf_tabular_files()
    ## filter for files that could be downloaded and format the col names
    tabular_files = tabular_files.filter(pl.col("file_path").is_not_null()).select(
        ['project_syn_id','file_path', 'file_syn_id', ]
    ).rename(
        {'file_syn_id':'file_id', 'file_path':'file_paths'}
    )
    ## group by project id.
    project_files = tabular_files.group_by("project_syn_id", maintain_order=True).agg(
    [pl.col("file_paths"), pl.col("file_id")]
    )
    ## filter for only desired project id.
    project_files = project_files.filter(pl.col('project_syn_id').is_in(project_list))
    return project_files.iter_rows()

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

def load_known_files_df() -> pl.DataFrame:
    """Load the cached registry of files from previously crawled projects.

    Returns:
        DataFrame with columns: project_syn_id, file_syn_id, file_name.
        Returns empty DataFrame with schema if cache file doesn't exist.
    """
    os.makedirs(REPORT_PATH, exist_ok=True)
    df_path = os.path.join(REPORT_PATH, "project_files.tsv")
    file_df_schema = pl.Schema(
        [("project_syn_id", pl.String), ("file_syn_id", pl.String), ("file_name", pl.String)]
    )
    if os.path.exists(df_path):
        return pl.read_csv(df_path, schema=file_df_schema, separator="\t")
    return pl.DataFrame(schema=file_df_schema)


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
    except Exception:
        logger.warning(
            f"Could not read files for project with id {project_syn_id}", exc_info=True
        )
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


def get_file_annotations(file_ids:list)->dict[str, dict]:
    """Use the Synapse file object to pull file annotations for a list of synapse ids 
    Args:
        file_ids: a list of file syn ids. 
        
    Returns:
        dict[str, dict] a dictionary mapping syn ids to a dictionary of their annotations

    
    """
    logger.info("pulling annotations...")
    async def _safe_get(fid):
        try:
            return fid, await File(id=fid, download_file=False).get_async()
        except Exception as e:
            logger.warning(f"Skipping {fid}: {e}")
            return fid, None

    async def fetch_open_annotations(file_ids, batch_size=50):
        results = {}
        for i in tqdm.tqdm(range(0, len(file_ids), batch_size)):
            batch = file_ids[i:i+batch_size]
            tasks = [_safe_get(fid) for fid in batch]
            outcomes = await asyncio.gather(*tasks)
            
            for fid, entity in outcomes:
                if entity is not None:
                    results[fid] = entity.annotations
        return results
    return asyncio.run(fetch_open_annotations(file_ids))