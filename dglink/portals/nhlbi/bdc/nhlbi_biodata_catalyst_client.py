"""
Client for querying and downloading data from the NHLBI BioData Catalyst (BDC).
"""

from dglink.core.api_clients import Gen3Client
from .constants import BDC_GEN3_ENDPOINT, BDC_FILE_NODE_TYPES, NHLBI_BDC_CACHE_DIR, BDC_CURIE_PREFIX

import polars as pl

import os 
import logging

logger = logging.getLogger(__name__)

DEFAULT_FIRST = 2000
FILE_FIELD_ORDER = ["project_id", "object_id", "file_name", "file_size", "data_format", "data_type"]


class NhlbiBioDataCatalystClient:
    def __init__(
        self,
        credential_file: str | None = None,
    ):
        """
        Args:
            credential_file: path to a Gen3 API key/credentials.json (see
                https://gen3.biodatacatalyst.nhlbi.nih.gov/identity)
        """
        self.gen3_client = Gen3Client(BDC_GEN3_ENDPOINT, credential_file=credential_file)

    def get_program_hierarchy(self) -> list[dict]:
        """Get every program with its nested project -> study structure."""
        query = """
        {
            program {
                name
                dbgap_accession_number
                projects {
                    project_id
                    code
                    name
                    dbgap_accession_number
                    availability_type
                    availability_mechanism
                    releasable
                    released
                    state
                    investigator_name
                    investigator_affiliation
                    studies {
                        study_id
                        full_name
                        short_name
                        study_description
                        dbgap_phs
                        dbgap_consent
                        type_of_data
                    }
                }
            }
        }
        """
        response = self.gen3_client.submission_client.query(query)
        return response["data"]["program"]

    def get_subjects_for_project(self, project_id: str, first: int = DEFAULT_FIRST) -> list[dict]:
        """Get subjects belonging to a project, with the parent studies each belongs to."""
        query = f"""
        {{
            subject(project_id: "{project_id}", first: {first}) {{
                submitter_id
                participant_id
                consent_codes
                studies {{
                    study_id
                }}
            }}
        }}
        """
        response = self.gen3_client.submission_client.query(query)
        return response["data"]["subject"]

    def get_publications_for_project(self, project_id: str, first: int = DEFAULT_FIRST) -> list[dict]:
        """Get publications associated with a project."""
        query = f"""
        {{
            publication(project_id: "{project_id}", first: {first}) {{
                submitter_id
                doi
                pmid
            }}
        }}
        """
        response = self.gen3_client.submission_client.query(query)
        return response["data"]["publication"]

    def get_core_metadata_for_project(self, project_id: str, first: int = DEFAULT_FIRST) -> list[dict]:
        """Get core_metadata_collection records (Dublin-Core-style dataset descriptions)
        associated with a project."""
        query = f"""
        {{
            core_metadata_collection(project_id: "{project_id}", first: {first}) {{
                submitter_id
                title
                description
                data_type
                format
                creator
                contributor
                publisher
                date
            }}
        }}
        """
        response = self.gen3_client.submission_client.query(query)
        return response["data"]["core_metadata_collection"]

    def _fetch_all_for_node_type(self, node_type, project_id, page_size=DEFAULT_FIRST):
        offset = 0
        results = []
        while True:
            query = f"""
            {{
                {node_type}(project_id: "{project_id}", first: {page_size}, offset: {offset}) {{
                    project_id
                    object_id
                    file_name
                    file_size
                    data_format
                    data_type
                }}
            }}
            """
            response = self.gen3_client.submission_client.query(query)
            batch = response.get('data', {}).get(node_type, [])
            if batch:
                batch = [{k: record[k] for k in FILE_FIELD_ORDER} for record in batch]
                print(f"Found {offset + len(batch)} files in {node_type}")
                for f in batch:
                    f['node_type'] = node_type
                results.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return results
    def _read_manifest(self):
        """Read the study -> file manifest, or None if it does not exist yet.

        Guarantees a String `path` column (null where a file has not been downloaded)
        so callers can rely on it regardless of how the on-disk manifest was written.
        """
        files_df_path = NHLBI_BDC_CACHE_DIR.joinpath("project_to_files.tsv")
                
        if not os.path.exists(files_df_path):
            return None
        files_df = pl.read_csv(files_df_path, separator="\t").cast(
            {"project_id": pl.String}
        )
        if "path" in files_df.columns:
            files_df = files_df.with_columns(pl.col("path").cast(pl.String))
        else:
            files_df = files_df.with_columns(path=pl.lit(None, dtype=pl.String))
        return files_df

    def _get_files_for_a_project(self, project_id:str):
        """pull files for a single project."""
        files_df_path = NHLBI_BDC_CACHE_DIR.joinpath("project_to_files.tsv")
        project_files_df = self._read_manifest()
        if project_files_df is not None:
            hit = project_files_df.filter(pl.col("project_id").eq(project_id))
            if hit.height > 0:
                return hit.to_dicts()
        all_files = []
        for node_type in BDC_FILE_NODE_TYPES:
                files = self._fetch_all_for_node_type(node_type=node_type, project_id=project_id)
                all_files.extend(files)
        if project_files_df is not None:
            df_rep = pl.from_dicts(all_files, schema=project_files_df.schema)
            project_files_df.vstack(df_rep).unique().write_csv(
                files_df_path, separator="\t"
            )
        else:
            df_rep = pl.from_dicts(all_files).with_columns(
                path=pl.lit(None, dtype=pl.String)
            )
            df_rep.write_csv(
                files_df_path,
                separator="\t",
            )
        return all_files
    def get_project_files(self, project_ids:list[str]):
        """get tabular files over a list or projects"""
        all_files = []
        for project_id in project_ids:
            all_files += self._get_files_for_a_project(project_id)
        return all_files
    
    def download_files(
        self,
        file_ids: list[str],
        show_progress: bool = True,
        process_zip_files : bool = True,
    ):
        """Download a list of files (by object_id/GUID) from BDC and record their
        on-disk paths in the manifest so future calls treat them as already downloaded."""
        files_df = self._read_manifest()
        if files_df is None:
            return

        ## filter the manifest down to the requested files
        to_load = files_df.filter(pl.col("object_id").is_in(file_ids))
        ## skip those that are already downloaded ##
        to_load = to_load.filter(pl.col("path").is_null()).unique()

        ## Group by project id ##
        project_files = (
            to_load.select(["project_id", "object_id"])
            .rename({ "object_id": "object_ids"})
            .group_by("project_id", maintain_order=True)
            .agg([ pl.col("object_ids")])
            .with_columns(
                project_curie=pl.format("{}:{}", pl.lit(BDC_CURIE_PREFIX), pl.col("project_id"))
            )
            .select(["project_curie", "object_ids"])
        )

        downloaded_paths: dict[str, str] = {}
        for project_curie, object_ids in project_files.iter_rows():
            logger.info(f"Downloading {len(object_ids)} for {project_curie}")
            project_cache = NHLBI_BDC_CACHE_DIR.joinpath('files').joinpath(project_curie)
            results = self.gen3_client.download_files(
                object_ids, save_directory=project_cache, show_progress=show_progress
            )
            for object_id, status in results.items():
                if status.status == "downloaded":
                    downloaded_paths[object_id] = str(project_cache.joinpath(status.filename))

        if downloaded_paths:
            updates_df = pl.DataFrame(
                {
                    "object_id": list(downloaded_paths.keys()),
                    "new_path": list(downloaded_paths.values()),
                }
            )
            files_df = (
                files_df.join(updates_df, on="object_id", how="left")
                .with_columns(pl.coalesce(["new_path", "path"]).alias("path"))
                .drop("new_path")
            )
            files_df.write_csv(
                NHLBI_BDC_CACHE_DIR.joinpath("project_to_files.tsv"), separator="\t"
            )
        if process_zip_files:
            ## get list of zip files that were downloaded successfully to try and extract ## 
            unprocessed_zip_files = (
                files_df.filter(pl.col("data_format").str.to_lowercase().eq("zip"))
                .filter(pl.col("object_id").is_in(file_ids))
                .filter(pl.col("path").is_not_null())
            )
            self._process_zip_files(unprocessed_zip_files)
    def _process_zip_files(self, unprocessed_zip_files:pl.DataFrame):
        """helper function to extract the contents of zip files and add them to the manifest"""
        import zipfile
        from pathlib import Path
        manifest = self._read_manifest()
        existing_ids = set(manifest["object_id"].to_list()) if manifest is not None else set()
        updates = []
        for zip_file in unprocessed_zip_files.iter_rows(named=True):
            base_object_id = zip_file.get("object_id")
            ## skip zips already extracted in a previous call ## 
            if any(eid.startswith(f"{base_object_id}.") for eid in existing_ids):
                continue
            zip_path = Path(zip_file.get("path"))
            project_id = zip_file.get("project_id")
            file_size = zip_file.get("file_size")
            data_type = zip_file.get("data_type")
            node_type = zip_file.get("node_type")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(zip_path.parent)
                offset = 1
                for f_name in zip_ref.namelist():
                    if f_name.endswith("/"):
                        continue
                    extracted_path = zip_path.parent.joinpath(f_name)
                    updates.append(
                        {
                            'project_id' : project_id,
                            'object_id' : f'{base_object_id}.{offset}',
                            'file_name' : f_name,
                            'file_size' : file_size,
                            'data_format' : extracted_path.suffix[1:].upper(),
                            'data_type' : data_type,
                            'node_type' : node_type,
                            'path' : str(extracted_path)
                        }
                    )
                    offset += 1
        if not updates:
            return
        ## append to manifest path and write ##
        files_df_path = NHLBI_BDC_CACHE_DIR.joinpath("project_to_files.tsv")
        manifest.vstack(pl.from_records(updates)).unique().write_csv(
                files_df_path, separator="\t"
            )
    def get_all_projects(self):
        """helper function to get a list of all projects"""
        res = self.get_program_hierarchy()

        all_projects = []
        for program in res:
            projects = program.get('projects')
            if projects:
                all_projects += [x.get("project_id") for x in projects]

        return all_projects