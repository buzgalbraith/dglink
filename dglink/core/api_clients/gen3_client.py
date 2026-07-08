"""
Helper client for interfacing with Gen3 APIs
"""

from gen3.auth import Gen3Auth
from gen3.file import Gen3File
from gen3.tools.download.drs_download import DownloadManager, Downloadable
import os


class Gen3Client:
    def __init__(self, endpoint: str, credential_file: str = None):
        self.endpoint = endpoint
        self.hostname = endpoint.removeprefix("https://")
        self.auth = Gen3Auth(endpoint=self.endpoint, refresh_file=credential_file)
        self.file_client = Gen3File(self.auth)

    def download_files(
        self,
        file_ids: list[str],
        save_directory="./Downloads",
        show_progress: bool = True,
    ):
        """Download a list of files from Gen3"""
        download_list = [Downloadable(object_id=f) for f in file_ids]
        manager = DownloadManager(
            hostname=self.hostname,
            auth=self.auth,
            download_list=download_list,
            show_progress=show_progress,
        )
        os.makedirs(save_directory, exist_ok=True)
        existing_files = os.listdir(save_directory)
        manager.download_list = list(
            filter(lambda x: x.file_name not in existing_files, manager.download_list)
        )
        return manager.download(
            manager.download_list,
            save_directory=save_directory,
            show_progress=show_progress,
        )
