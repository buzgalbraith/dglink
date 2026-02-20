"""
Goal is to evaluate a benchmarking dataset generated from `scripts/assemble_benchmark.py`
"""

import polars as pl
from dglink.core.constants import REPORT_PATH
from dglink.core.tabular_data import (
    load_file,
    apply_ground,
)
from dglink.core.ColumnSelectors import LLMSelector, heuristicSelector
from dglink.core.TabularDataset import TabularDataset
import os
from pathlib import Path
from tqdm import tqdm
import time
import logging

logger = logging.getLogger(__name__)

benchmark_path = os.path.join(REPORT_PATH, "benchmarking_columns.tsv")


def run_benchmark(
    benchmark: pl.DataFrame,
) -> pl.DataFrame:
    """Run the actual benchmark"""
    write_path = os.path.join(
        REPORT_PATH,
        "time_benchmark.tsv",
    )
    records = []

    hueristic_selector = heuristicSelector()
    llm_selector = LLMSelector()
    for benchmark_row in tqdm(
        benchmark.iter_rows(named=True),
        total=len(benchmark),
        desc="running benchmark evaluation",
        unit="Tables to benchmark",
    ):
        group_id = benchmark_row.get("group_identifier", "")
        fp = benchmark_row.get("fp", "")
        dfs, read_states = load_file(group_identifier=group_id, fp=fp)
        for df, read_states in zip(dfs, read_states):
            record = {}
            sheet_name = read_states.get("sheet", None)
            table = TabularDataset(
                dataset_path=Path(fp), sheet_name=sheet_name, table=df
            )
            ## try to ground everything in the dataframe
            table.table = table.table.apply(apply_ground, axis=1)
            llm_times = []
            hierarchal_times = []
            n_cols = max(len(table.original_columns), 1)
            llm_cals_during_hierchal = 0
            for column in tqdm(
                table.original_columns, total=n_cols, desc="columns to check"
            ):
                hierarchal_start = time.perf_counter()
                hueristic_vote = hueristic_selector.check_column(
                    table=table, col=column, verbose=True
                )
                if not hueristic_vote:
                    hierarchal_time = time.perf_counter() - hierarchal_start
                llm_start = time.perf_counter()
                llm_selector.check_column(table=table, col=column, verbose=True)
                llm_time = time.perf_counter() - llm_start
                if hueristic_vote:
                    hierarchal_time = time.perf_counter() - hierarchal_start
                else:
                    llm_cals_during_hierchal += 1
                llm_times.append(llm_time)
                hierarchal_times.append(hierarchal_time)
            record["sheet"] = sheet_name
            record["group_identifier"] = group_id
            record["file_path"] = fp
            record["number_columns"] = n_cols
            record["llm_total_time"] = sum(llm_times)
            record["llm_average_time"] = sum(llm_times) / n_cols
            record["hierchal_total_time"] = sum(hierarchal_times)
            record["hierchal_average_time"] = sum(hierarchal_times) / n_cols
            record["hierchal_llm_calls"] = llm_cals_during_hierchal
            records.append(record)
    write_df = pl.from_dicts(records)
    write_df.write_csv(
        write_path,
        separator="\t",
    )
    return write_df


if __name__ == "__main__":
    llm_models = ["gpt-5-mini"]
    benchmark = pl.read_csv(benchmark_path, separator="\t")
    logger.info("Running benchmark....")
    benchmarked_df = run_benchmark(
        benchmark=benchmark,
    )
    logger.info(f"Benchmark done writing to {benchmark_path}")
