import polars as pl
import os
from dglink.core.constants import REPORT_PATH
from dglink.portals.nf_data_portal import get_tabular_iterator, get_all_nf_studies
from dglink.core.tabular_data import load_file
from collections import deque
from numpy.random import default_rng
import tqdm

import logging

logger = logging.getLogger(__name__)

TARGET_LENGTH = 250
SEED = 102


if __name__ == "__main__":
    rng = default_rng(seed=SEED)
    result_path = os.path.join(
        os.path.join(REPORT_PATH), "benchmarking_columns_diverse.tsv"
    )
    ## get a list of tabular files and download if need be
    project_ids = get_all_nf_studies()
    tabular_files_queue: deque[tuple[str, deque]] = deque()
    tabular_iterator = get_tabular_iterator(project_list=project_ids)
    ## build the queue
    for group_identifier, file_paths, file_ids in tabular_iterator:
        records: deque = deque()
        for fp in file_paths:
            records.append(fp)
        tabular_files_queue.append((group_identifier, records))
    ## construct the benchmark
    benchmark = []
    pbar = tqdm.tqdm(total=TARGET_LENGTH)
    print(len(tabular_files_queue))
    while len(benchmark) < TARGET_LENGTH and len(tabular_files_queue) > 0:
        pbar.update(1)
        group_id, fps = tabular_files_queue.popleft()
        pbar.set_description(
            f"Processing {group_id}, there are {len(tabular_files_queue) + 1 } groups left..."
        )  # Add this line
        appended = False
        while not appended and len(fps) > 0:
            fp = fps.popleft()
            dfs, read_states = load_file(group_identifier=group_id, fp=fp)
            for df, read_state in zip(dfs, read_states):
                if df is not None:
                    if len(df.columns) < 1:
                        continue
                    else:
                        ## sample just one col ##
                        col_idx = rng.integers(low=0, high=len(df.columns))
                        col = df.columns[col_idx]
                        benchmark.append(
                            {
                                "fp": fp,
                                "sheet": read_state.get("sheet"),
                                "column": col,
                                "group_identifier": group_id,
                                "is_entity_col": "unchecked",
                            }
                        )
                        appended = True
                        break
        if len(fps) > 0:
            tabular_files_queue.append((group_id, fps))
            ## incrementally write the report
            write_df = pl.from_dicts(benchmark)
            write_df.write_csv(
                result_path,
                separator="\t",
            )
    logger.info(f"Benchmark created, written to {result_path}")
