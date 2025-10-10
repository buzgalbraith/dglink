import synapseclient
import os
from pathlib import Path
from utils import get_project_df
DGLINK_CACHE =  Path.joinpath(Path(os.getenv("HOME")), '.dglink')
syn = synapseclient.login()


if __name__ == "__main__":
    os.makedirs(Path(DGLINK_CACHE), exist_ok=True)
    query = syn.tableQuery("SELECT * FROM syn52694652")
    df = query.asDataFrame()
    df.to_csv(f"{DGLINK_CACHE}/all_studies.tsv", sep='\t', index=False)


