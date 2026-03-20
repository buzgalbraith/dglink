"""
Client for querying and downloading data from the NCI General Commons (GC).
"""

from dglink.core.apiClients import gen3Client, gqlClient
from .constants import NCI_GQL_ENDPOINT, NCI_GEN3_ENDPOINT, NCI_GC_CACHE_DIR
import polars as pl
import os
from gql import gql


class nciGeneralCommonsClient:
    def __init__(self, gen3_credential_file: str = None):
        """
        Args:
            gen3_credential_file: Path to file with NCI Gen3 credential file can be obtained from (https://nci-crdc.datacommons.io/login)
        """
        self.gql_client = gqlClient(NCI_GQL_ENDPOINT)
        self.gen3_client = gen3Client(NCI_GEN3_ENDPOINT, gen3_credential_file)

    def get_all_studies(self, only_open:bool = False) -> list[dict]:
        """Get a list of all studies from the NCI GC, and their metadata"""
        base_call = gql("""
                        query GetStudies($first: Int, $offset: Int) {
                            studies(
                                first: $first,
                                offset: $offset
                            ) {
                                phs_accession
                                study_name
                                study_acronym
                                study_id
                                funding_source_program_name # if this is non-empty has a program
                                study_access # if Open can work with
                            }
                        }
                    """)
        all_studies = self.gql_client.batch_execute(query=base_call, variable_values={}, key='studies')
        if only_open:
            open_studies = []
            for study in all_studies:
                if study.get("study_access") == "Open":
                    open_studies.append(study)
            return open_studies
        return all_studies

    def get_study_files(
        self, phs_accession: str, page_size: int = 500
    ) -> list[dict[str]]:
        """Get a list of all files associated with a given study and cache them

        Note: will store results in `os.path.join(NCI_GC_CACHE_DIR, 'study_to_files.tsv')`
        Args:
            phs_accession: study identifier
            page_size: amount of files to check at once
        """
        files_df_path = os.path.join(NCI_GC_CACHE_DIR, "study_to_files.tsv")
        if os.path.exists(files_df_path):
            study_files_df = pl.read_csv(files_df_path, separator="\t").cast(
                {"phs_accession": pl.String}
            )
            if (
                len(study_files_df.filter(pl.col("phs_accession").eq(phs_accession)))
                > 0
            ):
                return study_files_df.filter(
                    pl.col("phs_accession").eq(phs_accession)
                ).to_dicts()
        base_call = gql("""
                        query GetFiles($phs: String!, $first: Int, $offset: Int) {
                            files(
                                phs_accession: $phs,
                                first: $first,
                                offset: $offset
                            ) {
                                phs_accession
                                file_id
                                file_name
                                file_type
                                file_url_in_cds
                                # participant_ids
                            }
                        }
                    """)
        all_study_files = self.gql_client.batch_execute(base_call, {'phs_accession' : phs_accession}, page_size=page_size, key='files')
        df_rep = pl.from_dicts(all_study_files).with_columns(path=pl.lit(None))
        if os.path.exists(files_df_path):
            study_files_df.vstack(df_rep).unique().write_csv(
                files_df_path, separator="\t"
            )
        else:
            df_rep.write_csv(
                files_df_path,
                separator="\t",
            )
        return all_study_files

    def download_files(
        self,
        file_ids: list[str],
        save_directory="./downloads",
        show_progress: bool = True,
    ):
        """Use Gen3 client to download a list of files, updates `study_to_files.tsv` with path to downloaded files"""
        files_df_path = os.path.join(NCI_GC_CACHE_DIR, "study_to_files.tsv")
        study_files_df = pl.read_csv(files_df_path, separator="\t").cast(
            {"phs_accession": pl.String}
        )
        novel_study_files = study_files_df.filter(
            pl.col("path").is_null() & pl.col("file_id").is_in(file_ids)
        )["file_id"].to_list()
        download_resp = self.gen3_client.download_files(
            file_ids=novel_study_files,
            save_directory=save_directory,
            show_progress=show_progress,
        )
        self._update_study_file_paths(download_resp=download_resp, save_dir=save_directory)
        return download_resp

    def _update_study_file_paths(self, download_resp, save_dir):
        files_df_path = os.path.join(NCI_GC_CACHE_DIR, "study_to_files.tsv")
        study_files_df = pl.read_csv(files_df_path, separator="\t").cast(
            {"phs_accession": pl.String}
        )

        def _apply_update(path, file_id):
            if file_id not in download_resp:
                return path
            return os.path.join(save_dir, download_resp[file_id].filename)

        study_files_df = study_files_df.with_columns(
            path=pl.struct(["file_id", "path"]).map_elements(
                lambda x: _apply_update(x["path"], x["file_id"]), return_dtype=pl.String
            )
        )
        study_files_df.write_csv(files_df_path, separator="\t")

    def get_all_programs(self,) -> list[dict]:
        base_call = gql("""
                        query GetPrograms{
                            programs {
                                program_acronym
                                program_short_description
                                program_full_description
                                program_external_url
                                program_short_name
                                institution
                                crdc_id
                                study_participants
                            }
                        }
                    """)
        return self.gql_client.execute(base_call, {}).get("programs", [])
    def get_program_details(self) -> list[dict]:
        list_call = gql("""
            query GetProgramList {
                programList {
                    acronym
                    name
                    website
                    num_studies
                }
            }
        """)
        programs = self.gql_client.execute(list_call, {}).get("programList", [])

        detail_call = gql("""
            query GetProgramDetail($program_name: String!) {
                programDetail(program_name: $program_name) {
                    program
                    program_name
                    program_url
                    program_short_description
                    num_studies
                    num_participants
                    num_files
                    num_samples
                    num_disease_sites
                    study_participants {
                        group
                        subjects
                    }
                    studies {
                        accession
                        study_name
                        study_access
                        study_version
                        study_data_types
                        study_description
                        short_description
                        num_participants
                        num_samples
                        num_files
                    }
                }
            }
        """)

        return [
            self.gql_client.execute(detail_call, {"program_name": p["name"]}).get("programDetail", {})
            for p in programs
        ]

    def get_publications(self, page_size: int = 100) -> list[dict]:
        studies = self.get_all_studies()

        detail_call = gql("""
            query GetPublications($phs_accession: String!, $first: Int!, $offset: Int!) {
                publications(
                    phs_accession: $phs_accession
                    first: $first
                    offset: $offset
                ) {
                    phs_accession
                    crdc_id
                    Publication_Type
                    Publication_Title
                    Publication_Status
                    DOI_or_Pub_ID
                }
            }
        """)

        all_publications = []

        for study in studies:
            phs = study.get("phs_accession")
            if not phs:
                continue
            all_publications.extend(self.gql_client.batch_execute(
                detail_call,
                {"phs_accession": phs}, 
                page_size=page_size,
                key = 'publications'
            ))

        return all_publications
    def get_investigators(self, page_size: int = 100) -> list[dict]:
        studies = self.get_all_studies()
        query = gql("""
            query GetInvestigators($phs_accession: String!, $first: Int!, $offset: Int!) {
                investigators(
                    phs_accession: $phs_accession
                    first: $first
                    offset: $offset
                ) {
                    investigator_id
                    first_name
                    last_name
                    email
                    role_or_affiliation
                    title
                    primary_investigator_name
                    primary_investigator_email
                    co_investigator_name
                    co_investigator_email
                    phs_accession
                }
            }
        """)

        res = []

        for study in studies:
            phs = study.get("phs_accession")
            if not phs:
                continue
            res.extend(
                self.gql_client.batch_execute(
                    query,
                    {'phs_accession' : phs},
                    page_size=page_size,
                    key = 'investigators'
                )
            )
        return res


    def get_diagnoses(self, page_size: int = 1000, only_open:bool = False) -> list[dict]:
        ## for now
        studies = self.get_all_studies(only_open=only_open)
        query = gql("""
            query GetDiagnoses($phs_accession: String!, $first: Int!, $offset: Int!) {
                diagnoses(
                    phs_accession: $phs_accession
                    first: $first
                    offset: $offset
                ) {
                    diagnosis_id
                    study_diagnosis_id
                    primary_diagnosis
                    disease_type
                    primary_site
                    tissue_or_organ_of_origin
                    site_of_resection_or_biopsy
                    tumor_grade
                    tumor_stage_clinical_m
                    tumor_stage_clinical_n
                    tumor_stage_clinical_t
                    morphology
                    vital_status
                    age_at_diagnosis
                    incidence_type
                    progression_or_recurrence
                    days_to_recurrence
                    days_to_last_followup
                    last_known_disease_status
                    days_to_last_known_disease_status
                    crdc_id
                    phs_accession
                    participant_id
                }
            }
        """)

        all_diagnoses = []

        for study in studies:
            phs = study.get("phs_accession")
            if not phs:
                continue
            all_diagnoses.extend(
                self.gql_client.batch_execute(
                    query,
                    {'phs_accession' : phs},
                    page_size=page_size,
                    key = 'diagnoses'
                )
            )
        return all_diagnoses
