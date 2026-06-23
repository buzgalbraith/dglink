import os
from pathlib import Path
from shutil import move

import polars as pl

from dglink.portals.nf_data_portal.constants import syn
from dglink.portals.nf_data_portal.utils import safe_download


## pull a list of public fastq files from these two studies ##
query = syn.tableQuery("SELECT * FROM syn52702673 WHERE ( ( ( \"accessType\" = 'Public Access' ) AND ( \"fileFormat\" = 'fastq' ) AND ( \"studyName\" = 'A 3D Cutaneous Neurofibroma Model for Automated High-Throughput Drug Screenings' OR \"studyName\" = 'Defining the factors that dictate the pattern of glioma formation in NF1' ) ) ) AND ( resourceType IN ( 'analysis', 'experimentalData', 'results' ) )")

## filter for specific ids##
desired_ids = ['syn61692659', 'syn22753073']

df = query.asDataFrame()
df = pl.from_pandas(df)

df = df.filter(pl.col("id").is_in(desired_ids))

## download
genomic_files = df.with_columns(
            file_path=pl.col('id').map_elements(
                        safe_download,
                                return_dtype=pl.String
                                    )
            )
## move results to a conistent location ##
os.makedirs('fastq_files', exist_ok=True)
# for x in genomic_files['file_path']:
for row in genomic_files.iter_rows(named=True):
    syn_id = row.get("id")
    x = row.get("file_path")
    x = Path(x)
    new_path =  os.path.join("fastq_files",f'{syn_id}.fastq.gz')
    move(x, new_path)
