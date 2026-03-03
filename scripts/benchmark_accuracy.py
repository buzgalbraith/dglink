"""
Goal is to evaluate a benchmarking dataset generated from `scripts/assemble_benchmark.py`
"""

import polars as pl
from dglink.core.constants import REPORT_PATH
from dglink.core.tabular_data import (
    load_file,
    apply_ground,
)
from dglink.core.columnSelectors import LLMSelector, heuristicSelector
from dglink.core.tabularDataset import tabularDataset
import os
from pathlib import Path
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)

benchmark_path = os.path.join(REPORT_PATH, "benchmarking_columns.tsv")


def run_benchmark(
    benchmark: pl.DataFrame,
    overwrite: bool = False,
    load: bool = True,
) -> pl.DataFrame:
    """Run the actual benchmark"""
    write_path = os.path.join(
        REPORT_PATH,
        "evaluated_benchmark.tsv",
    )
    if os.path.exists(write_path):
        if load and overwrite:
            raise ValueError(
                f"Trying to overwrite existing evaluated benchmark, set overwrite = True and load = False if you are sure"
            )
        elif load or (not overwrite and not load):
            return pl.read_csv(write_path, separator="\t")
        else:
            logger.warning(
                f"Overwriting the evaluated benchmark saved at {write_path}!!"
            )
    records = []
    for benchmark_row in tqdm(
        benchmark.iter_rows(named=True),
        total=len(benchmark),
        desc="running benchmark evaluation",
        unit="benchmark column ",
    ):
        record = {}
        group_id = benchmark_row.get("group_identifier", "")
        fp = benchmark_row.get("fp", "")
        target_sheet = benchmark_row.get("sheet", "")
        dfs, read_states = load_file(group_identifier=group_id, fp=fp)
        sheet_idx = 0
        column = benchmark_row.get("column", "")
        while read_states[sheet_idx]["sheet"] != target_sheet:
            sheet_idx += 1
        df = dfs[sheet_idx]
        record["column"] = column
        table = tabularDataset(dataset_path=Path(fp), sheet_name=target_sheet, table=df)
        ## try to ground everything in the dataframe
        table.table = table.table.apply(apply_ground, axis=1)
        selector = heuristicSelector()
        record["heuristic_vote"] = selector.check_column(table=table, col=column, verbose=True)
        selector = LLMSelector()
        record["llm_vote"] = selector.check_column(table=table, col=column, verbose=True)
        if record["heuristic_vote"]:
            record["hiercahal_vote"] = record["llm_vote"]
        else:
            record["hiercahal_vote"] = False
        record["is_entity_col"] = benchmark_row.get("is_entity_col")
        record["sheet"] = target_sheet
        record["group_identifier"] = group_id
        record["file_path"] = fp
        records.append(record)
    write_df = pl.from_dicts(records)
    write_df.write_csv(
        write_path,
        separator="\t",
    )
    return write_df


## metrics for benchmarking
def accuracy(col_name: str, evaluated_df: pl.DataFrame) -> float:
    """Checks number of correct predictions for a col in the write data frame"""
    correct_pred = evaluated_df.filter(pl.col(col_name).eq(pl.col("is_entity_col")))
    return len(correct_pred) / len(evaluated_df)


def precision(col_name: str, evaluated_df: pl.DataFrame) -> float:
    """Checks precision for a col in the write data frame"""
    tp = len(evaluated_df.filter(pl.col(col_name) & pl.col("is_entity_col")))
    fp = len(evaluated_df.filter(pl.col(col_name) & ~pl.col("is_entity_col")))
    return tp / (tp + fp)


def recall(col_name: str, evaluated_df: pl.DataFrame) -> float:
    """Checks recall for a col in the write data frame"""
    tp = len(evaluated_df.filter(pl.col(col_name) & pl.col("is_entity_col")))
    fn = len(evaluated_df.filter(~pl.col(col_name) & pl.col("is_entity_col")))
    return tp / (tp + fn)


def f1_score(col_name: str, evaluated_df: pl.DataFrame) -> float:
    """Checks f1 score for a col in the write data frame"""
    col_precision = precision(col_name=col_name, evaluated_df=evaluated_df)
    col_recall = recall(col_name=col_name, evaluated_df=evaluated_df)
    return 2 * ((col_precision * col_recall) / (col_precision + col_recall))


## methods for evaluating results
def evaluate_col(col_name: str, evaluated_df: pl.DataFrame) -> dict[str, float | str]:
    return {
        "method_name": col_name,
        "accuracy": accuracy(col_name=col_name, evaluated_df=evaluated_df),
        "precision": precision(col_name=col_name, evaluated_df=evaluated_df),
        "recall": recall(col_name=col_name, evaluated_df=evaluated_df),
        "f1_score": f1_score(col_name=col_name, evaluated_df=evaluated_df),
    }


def evaluate_col_heuristic_union(
    col_name: str, evaluated_df: pl.DataFrame
) -> dict[str, float | str]:
    internal_df = evaluated_df.with_columns(
        (pl.col(col_name) | pl.col("heuristic_vote")).alias(f"{col_name}_union")
    )
    return evaluate_col(col_name=f"{col_name}_union", evaluated_df=internal_df)


def evaluate_col_heuristic_intersection(
    col_name: str, evaluated_df: pl.DataFrame
) -> dict[str, float | str]:
    internal_df = evaluated_df.with_columns(
        (pl.col(col_name) & pl.col("heuristic_vote")).alias(f"{col_name}_intersection")
    )
    return evaluate_col(col_name=f"{col_name}_intersection", evaluated_df=internal_df)


def get_benchmark_summary(
    evaluated_benchmark_df: pl.DataFrame, union: bool = True, intersection: bool = False
):
    """Gets summary stats on evaluated benchmark df"""
    method_cols = evaluated_benchmark_df.select(r"^.*(_vote)$").columns
    methods_summary = []
    evaluated_benchmark_df = evaluated_benchmark_df.cast({pl.Int64: pl.Boolean})
    for method in method_cols:
        methods_summary.append(
            evaluate_col(col_name=method, evaluated_df=evaluated_benchmark_df)
        )
        ## check the intersection/union of other methods with heuristic method if desired ##
        if "heuristic_vote" in method_cols and method != "heuristic_vote":
            if union:
                methods_summary.append(
                    evaluate_col_heuristic_union(
                        col_name=method, evaluated_df=evaluated_benchmark_df
                    )
                )
            if intersection:
                methods_summary.append(
                    evaluate_col_heuristic_intersection(
                        col_name=method, evaluated_df=evaluated_benchmark_df
                    )
                )
    benchmark_summary = pl.from_dicts(methods_summary)
    benchmark_summary.write_csv(
        os.path.join(REPORT_PATH, "evaluated_benchmark_summary.tsv"), separator="\t"
    )
    return benchmark_summary


if __name__ == "__main__":
    llm_models = ["gpt-4o", "gpt-4o-mini", "gpt-5", "gpt-5-mini"]
    llm_models = []
    benchmark = pl.read_csv(benchmark_path, separator="\t")
    logger.info("Running benchmark....")
    benchmarked_df = run_benchmark(
        benchmark=benchmark,
        overwrite=True,
        load=False,
    )
    logger.info("Evaluating benchmark....")
    summary_df = get_benchmark_summary(
        evaluated_benchmark_df=benchmarked_df, union=False, intersection=False
    )
    logger.info(f"Summary results\n {summary_df}")
