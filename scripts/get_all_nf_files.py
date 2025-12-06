"""
Gets a list of all files from the NF data portal and their extensions and saves it in a cached location
"""

from dglink.core.utils import get_projects_files
from dglink.portals.nf_data_portal import get_all_nf_studies

if __name__ == "__main__":
    projects_ids = get_all_nf_studies()
    get_projects_files(project_ids=projects_ids)
