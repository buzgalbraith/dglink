"""
Helper client for interfacing with Gen3 APIs
"""

from ..optional_deps import import_optional

import os


class Gen3Client:
    def __init__(self, endpoint: str, credential_file: str|None = None):
        gen3_auth = import_optional("gen3.auth", "gen3")
        gen3_file = import_optional("gen3.file", "gen3")
        gen3_submission = import_optional("gen3.submission", "gen3")
        self.endpoint = endpoint
        self.hostname = endpoint.removeprefix("https://")
        self.auth = gen3_auth.Gen3Auth(endpoint=self.endpoint, refresh_file=credential_file)
        self.file_client = gen3_file.Gen3File(self.auth)
        self.submission_client = gen3_submission.Gen3Submission(self.auth)

    def download_files(
        self,
        file_ids: list[str],
        save_directory="./Downloads",
        show_progress: bool = True,
    ):
        """Download a list of files from Gen3"""
        drs = import_optional("gen3.tools.download.drs_download", "gen3")
        download_list = [drs.Downloadable(object_id=f) for f in file_ids]
        manager = drs.DownloadManager(
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
