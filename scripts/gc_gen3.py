"""
This script will have a basic example of pulling code from the NCI General Commons (GC) with Gen3
"""
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from gen3.auth import Gen3Auth
from gen3.file import Gen3File
from gen3.tools.download.drs_download import DownloadManager, Downloadable

import logging
logger = logging.getLogger(__name__)

NCI_GQL_ENDPOINT = "https://general.datacommons.cancer.gov/v1/graphql/"
NCI_GEN3_ENDPOINT = 'https://nci-crdc.datacommons.io'


class gqlClient:
    def __init__(self, endpoint,):
        self.endpoint = endpoint
        self.transport = RequestsHTTPTransport(
            url=endpoint,
            verify=True,
        )
        self.client = Client(
            transport=self.transport,
            execute_timeout=30,
            fetch_schema_from_transport=True, 
        )
    def execute(self, query, variable_values, max_retries:int = 3):
        for attempt in range(max_retries):
            try:
                return self.client.execute(query, variable_values=variable_values)
            except Exception as e:
                logger.warning(f"Query attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
class gen3Client():
    def __init__(self, endpoint : str, credential_file:str=None):
        self.endpoint = endpoint
        self.hostname = endpoint.removeprefix("https://")
        self.auth = Gen3Auth(
            endpoint=self.endpoint, 
            refresh_file=credential_file 
        )
        self.file_client = Gen3File(self.auth)
    def download_files(self, file_ids:list[dict], save_directory = "./Downloads", show_progress:bool = True):       
       download_list = [ Downloadable(object_id=f["file_id"].strip()) for f in file_ids]
       manager = DownloadManager(
            hostname=self.hostname,
            auth=self.auth,
            download_list=download_list,
            show_progress=show_progress)
       manager.download(download_list, save_directory=save_directory, show_progress = show_progress)
class nciGeneralCommonsClient():
    def __init__(self, gen3_credential_file:str = None):
        self.gql_client = gqlClient(NCI_GQL_ENDPOINT)
        self.gen3_client = gen3Client(NCI_GEN3_ENDPOINT, gen3_credential_file)
    def get_studies(self, first:int =72, offset:int = 0) -> list[dict]:
        """get studies in a range"""
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
        return self.gql_client.execute(
            base_call, 
            {
                'first' : first,
                'offset' : offset
            }
        ).get('studies', [])
    def get_all_studies(self) -> list[dict]:
        """get all studies"""
        all_studies, offset, page_size = [], 0, 100
        while True:
            batch = self.get_studies(first=page_size, offset=offset)
            if not batch:
                break
            all_studies.extend(batch)
            offset += page_size
        return all_studies
    def get_study_files(self, phs_accession:str, page_size:int = 500):
        """get a list of all files associated with a given study"""
        base_call = gql("""
                        query GetFiles($phs: String!, $first: Int, $offset: Int) {
                            files(
                                phs_accession: $phs,
                                first: $first,
                                offset: $offset
                            ) {
                                file_id
                                file_name
                                file_type
                                file_url_in_cds
                                # participant_ids
                            }
                        }
                    """)
        all_study_files, offset= [], 0
        while True:
            batch = self.gql_client.execute(base_call, {
                'phs' : phs_accession,
                'first' : page_size,
                'offset' : offset
                }
            ).get('files', [])
            if not batch:
                break
            all_study_files.extend(batch)
            offset += page_size
            print(len(all_study_files))
        return all_study_files
    def download_files(self, file_ids:list[dict], save_directory = "./downloads", show_progress:bool = True):
        self.gen3_client.download_files(file_ids=file_ids, save_directory=save_directory, show_progress=show_progress)
        
if __name__ == "__main__":
    client = nciGeneralCommonsClient(gen3_credential_file='nci_general_commons_credentials')
    print("Getting Studies")
    studies = client.get_all_studies()
    test_accession = studies[0].get('phs_accession')
    print("Getting files")
    study_files = client.get_study_files(test_accession)
    print(len(study_files))
    print("Downloading files")
    client.download_files(file_ids=study_files)