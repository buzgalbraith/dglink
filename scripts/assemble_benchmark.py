"""
randomly sample columns for a schema matching benchmark dataset
"""

import polars as pl
from dglink.core.tabular_data import load_file, quality_check_groundings
from dglink.core.tabular_dataset import TabularDataset
import tqdm
from numpy.random import default_rng
from dglink.core.constants import REPORT_PATH
import os
from pathlib import Path


benchmark_tables = 250
seed = 102
rng = default_rng(seed=seed)

if __name__ == "__main__":
    ## get all unique file paths that can be read in.
    fps = (
        pl.read_csv(os.path.join(REPORT_PATH, "file_report.tsv"), separator="\t")
        .filter(pl.col("can_read"))
        .group_by(["file_path"], maintain_order=True)
        .first()
        .select(["file_path", "project_id"])
    )
    ## take one hundred random file paths from this.
    selected_fps = fps.sample(
        n=benchmark_tables, seed=seed, with_replacement=False, shuffle=False
    )
    records = []
    for fp, group_id in tqdm.tqdm(selected_fps.iter_rows(), total=benchmark_tables):
        dfs, read_states = load_file(group_identifier=group_id, fp=fp)
        ## sample just one sheet ##
        sheet_number = rng.integers(low=0, high=len(dfs), size=1)[0]
        df = dfs[sheet_number]
        read_state = read_states[sheet_number]
        ## continue if read data frame is empty ##
        if len(df.columns) < 1:
            continue
        ## sample just one col ##
        col_idx = rng.integers(low=0, high=len(df.columns), size=1)[0]
        col = df.columns[col_idx]
        ## check how heuristic grounding would deal ##
        small_df = df[[col]]
        table = TabularDataset(
            dataset_path=Path(fp),
            sheet_name=read_state.get("sheet"),
            table=small_df,
        )
        ## try to ground everything in the dataframe
        table.ground_table()
        ## heuristic quality check populates table.entity_columns ##
        quality_check_groundings(qc_method="heuristic", table=table)
        ## add records to df ##
        records.append(
            {
                "fp": fp,
                "sheet": read_state.get("sheet"),
                "column": col,
                "group_identifier": group_id,
                "heuristic_vote": col in table.entity_columns,
                "is_entity_col": "unchecked",
            }
        )
    ## write the results ##
    write_df = pl.from_dicts(records)
    write_df.write_csv(
        os.path.join(os.path.join(REPORT_PATH), "benchmarking_columns.tsv"),
        separator="\t",
    )
