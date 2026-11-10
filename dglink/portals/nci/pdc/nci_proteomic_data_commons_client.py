"""
Client for querying and downloading data from the NCI Proteomic Data Commons (PDC).
"""

from dglink.core.api_clients import GqlClient
from .constants import NCI_PDC_CACHE_DIR, PDC_GQL_ENDPOINT

import polars as pl
from dglink.core.optional_deps import import_optional
from urllib3.util.retry import Retry

import hashlib
import os
import requests
from requests.adapters import HTTPAdapter

gql = import_optional("gql", "nci").gql


class NciProteomicCommonsClient:
    def __init__(
        self,
        retry_total: int = 5,
        retry_backoff: float = 1.5,
        retry_status_list=(429, 500, 502, 503, 504),
        timeout_sec=60,
        chunk_size=1024 * 256,
    ):
        """
        Args:
        """
        self.gql_client = GqlClient(PDC_GQL_ENDPOINT, fetch_schema_from_transport=False)
        self.swagger_session = self._initialize_swagger_session(
            retry_total=retry_total,
            retry_backoff=retry_backoff,
            retry_status_list=retry_status_list,
        )
        self.chunk_size = chunk_size
        self.timeout_sec = timeout_sec

    def get_program_hierarchy(self) -> list[dict]:
        """Get all programs and their program -> project -> study hierarchy"""
        base_call = gql("""
        {
            allPrograms{
                program_id  
                program_submitter_id  
                name 
                projects  
                {
                    project_id  
                    project_submitter_id  
                    name  
                    studies  
                    {
                        pdc_study_id 
                        study_id 
                        study_submitter_id 
                        submitter_id_name 
                        analytical_fraction 
                        study_name 
                        disease_types 
                        primary_sites  
                        experiment_type 
                        acquisition_type
                    } 
                }
            }
        }
        """)
        program_hierarchy = self.gql_client.batch_execute(
            query=base_call, variable_values={}, key="allPrograms"
        )
        return program_hierarchy

    def get_study_biospecimen(self, study_id: str, page_size: int = 1000) -> list[dict]:
        """Get the case -> sample -> aliquot biospecimen hierarchy for a study.

        Each row ties one aliquot to its parent sample and case, and carries the
        disease/site/sample-type metadata PDC exposes per biospecimen. This is the
        structural backbone used to build the graph (analogous to GDC's expanded
        `samples` on the cases endpoint).

        Args:
            study_id: study identifier (the UUID `study_id`, not `pdc_study_id`)
            page_size: amount of biospecimen records to fetch at once
        """
        base_call = gql("""
            query biospecimenPerStudy($study_id: String!) {
                biospecimenPerStudy(study_id: $study_id) {
                    aliquot_id
                    sample_id
                    case_id
                    aliquot_submitter_id
                    sample_submitter_id
                    case_submitter_id
                    aliquot_status
                    sample_status
                    case_status
                    project_name
                    sample_type
                    disease_type
                    primary_site
                    pool
                    taxon
                }
            }
        """)
        return self.gql_client.batch_execute(
            base_call,
            {"study_id": study_id},
            page_size=page_size,
            key="biospecimenPerStudy",
        )

    def get_study_files(self, study_id: str, page_size: int = 500) -> list[dict[str]]:
        """Get a list of all files associated with a given study and cache them

        Note: will store results in `NCI_PDC_CACHE_DIR.joinpath("study_to_files.tsv")`
        Args:
            study_id: study identifier
            page_size: amount of files to check at once
        """
        files_df_path = NCI_PDC_CACHE_DIR.joinpath("study_to_files.tsv")
        study_files_df = self._read_manifest()
        if study_files_df is not None:
            hit = study_files_df.filter(pl.col("study_id").eq(study_id))
            if hit.height > 0:
                return hit.to_dicts()
        base_call = gql("""
            query filesPerStudy($study_id: String!) {
                filesPerStudy(study_id: $study_id)
                {
                    study_id
                    pdc_study_id
                    study_submitter_id
                    study_name file_id
                    file_name
                    file_submitter_id 
                    file_type 
                    md5sum 
                    file_location 
                    file_size 
                    data_category 
                    file_format 
                    signedUrl 
                    {
                        url
                    }
                } 
            }
        """)
        all_study_files = self.gql_client.batch_execute(
            base_call, {"study_id": study_id}, page_size=page_size, key="filesPerStudy"
        )
        for x in all_study_files:
            x["signedUrl"] = x["signedUrl"]["url"]
        if study_files_df is not None:
            ## coerce new rows to the existing manifest's schema (incl. the null
            ## `path` column) so vstack aligns
            df_rep = pl.from_dicts(all_study_files, schema=study_files_df.schema)
            study_files_df.vstack(df_rep).unique().write_csv(
                files_df_path, separator="\t"
            )
        else:
            ## first run: no manifest yet, infer the schema from the fetched rows and
            ## seed an empty `path` column (filled in once a file is downloaded)
            df_rep = pl.from_dicts(all_study_files).with_columns(
                path=pl.lit(None, dtype=pl.String)
            )
            df_rep.write_csv(
                files_df_path,
                separator="\t",
            )
        return all_study_files

    def download_files(
        self,
        file_ids: list[str],
    ):
        """Download the requested PDC files into the cache, skipping any already present.

        Mirrors the GDC portal's `download_tabular_files`: the manifest is filtered
        to the requested files, files already in the cache (on disk) are skipped, and
        the rest are streamed to `<cache>/files/<study_id>/<file_name>`. The on-disk
        location is deterministic from (study_id, file_name), so caching keys off disk
        existence; the manifest `path` column is updated to that location whenever a
        file is downloaded (or back-filled for a file already on disk but unrecorded).

        Note: PDC `signedUrl`s are short-lived. If a cached url has expired the
        download 404/403s; re-fetch the study with `get_study_files` (bypassing the
        cache) to mint fresh urls before retrying.
        """
        files_df = self._read_manifest()
        if files_df is None:
            return
        ## filter the manifest down to the requested files
        to_load = files_df.filter(pl.col("file_id").is_in(file_ids))
        downloaded_paths: dict[str, str] = {}
        for file in to_load.iter_rows(named=True):
            file_id = file.get("file_id")
            f_name: str = file.get("file_name") or "missing_file_name"
            f_name = f_name.strip().replace(" ", "_")
            study_id = file.get("study_id")
            save_path = (
                NCI_PDC_CACHE_DIR.joinpath("files").joinpath(study_id).joinpath(f_name)
            )
            ## already in the cache: back-fill the manifest path if it is not recorded
            if save_path.exists():
                if not file.get("path"):
                    downloaded_paths[file_id] = str(save_path)
                continue
            os.makedirs(save_path.parent, exist_ok=True)
            success = self._safe_download(
                url=file.get("signedUrl", "missing"),
                dst_path=save_path,
                expected_md5=file.get("md5sum"),
            )
            if success:
                downloaded_paths[file_id] = str(save_path)
        if downloaded_paths:
            self._record_downloaded_paths(files_df, downloaded_paths)

    def _read_manifest(self):
        """Read the study -> file manifest, or None if it does not exist yet.

        Guarantees a String `path` column (null where a file has not been downloaded)
        so callers can rely on it regardless of how the on-disk manifest was written.
        """
        files_df_path = NCI_PDC_CACHE_DIR.joinpath("study_to_files.tsv")
        if not os.path.exists(files_df_path):
            return None
        files_df = pl.read_csv(files_df_path, separator="\t").cast(
            {"study_id": pl.String}
        )
        if "path" in files_df.columns:
            files_df = files_df.with_columns(pl.col("path").cast(pl.String))
        else:
            files_df = files_df.with_columns(path=pl.lit(None, dtype=pl.String))
        return files_df

    def _record_downloaded_paths(self, files_df, downloaded_paths: dict[str, str]):
        """Write local paths for freshly-downloaded files back into the manifest `path`.

        Args:
            files_df: the full manifest frame (as read by `_read_manifest`).
            downloaded_paths: mapping of file_id -> local path to record.
        """
        updates = pl.DataFrame(
            {
                "file_id": list(downloaded_paths.keys()),
                "_downloaded_path": list(downloaded_paths.values()),
            }
        )
        files_df = (
            files_df.join(updates, on="file_id", how="left")
            .with_columns(path=pl.coalesce(pl.col("_downloaded_path"), pl.col("path")))
            .drop("_downloaded_path")
        )
        files_df.write_csv(
            NCI_PDC_CACHE_DIR.joinpath("study_to_files.tsv"), separator="\t"
        )

    def _verify_md5(self, path, expected_md5) -> bool:
        """Return True if `path`'s md5 matches `expected_md5` (or if no md5 is known)."""
        if not expected_md5:
            ## nothing to check against; trust the file
            return True
        digest = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(self.chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected_md5

    def _initialize_swagger_session(
        self, retry_total, retry_backoff, retry_status_list
    ):
        """
        Create a requests.Session with basic retry behavior.
        """
        session = requests.Session()
        retries = Retry(
            total=retry_total,
            backoff_factor=retry_backoff,
            status_forcelist=retry_status_list,
            allowed_methods=frozenset(["GET", "HEAD"]),
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        # Simple User-Agent so server logs can distinguish this client
        session.headers.update({"User-Agent": "pdc-download-script/1.0"})
        return session

    def _safe_download(self, url, dst_path, expected_md5=None):
        """
        Download a single file to dst_path using streaming.

        Streams to a `.part` sidecar and only renames into place once the transfer
        completes (and the md5 checks out, when known), so an interrupted download
        never leaves a truncated file that later looks cached.

        Returns True on success, False if the file was not downloaded.
        """
        filename = os.path.basename(dst_path)
        part_path = dst_path.with_name(dst_path.name + ".part")
        try:
            resp = self.swagger_session.get(url, stream=True, timeout=self.timeout_sec)
            if resp.status_code != 200:
                print(
                    f"[SKIP] {filename} -> HTTP {resp.status_code} (no file downloaded)"
                )
                return False

            # Avoid writing empty responses
            clen = resp.headers.get("Content-Length")
            if clen is not None and clen.isdigit() and int(clen) == 0:
                print(f"[SKIP] {filename} -> empty Content-Length")
                return False

            with open(part_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)

            ## reject a corrupt transfer instead of caching a bad file
            if not self._verify_md5(part_path, expected_md5):
                print(f"[ERR ] {filename} -> md5 mismatch (discarded)")
                os.remove(part_path)
                return False

            os.replace(part_path, dst_path)
            return True
        except requests.RequestException as e:
            print(f"[ERR ] {filename} -> {e}")
            if os.path.exists(part_path):
                os.remove(part_path)
            return False
