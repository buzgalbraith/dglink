"""
Goal is to evaluate a benchmarking dataset generated from `scripts/assemble_benchmark.py`
"""

import polars as pl
import pandas as pd
from dglink.core.constants import REPORT_PATH
from dglink.core.tabular_data import (
    load_file,
    quality_check_groundings,
    apply_ground,
    get_llm_schema_matching_prompt,
    call_llm_for_schema_matching,
)
import os
from pathlib import Path
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)

benchmark_path = os.path.join(REPORT_PATH, "benchmarking_columns.tsv")


## run schema matching on one col and return true or false TODO: clean up maybe make a class ##
def heuristic_check(
    df: pd.DataFrame,
    target_col: str,
    table_path: str,
) -> bool:
    base_cols = df.columns.to_list()
    raw_groundings = df.apply(apply_ground, axis=1)
    _, entity_cols = quality_check_groundings(
        qc_method="heuristic",
        grounded_dataset=raw_groundings,
        original_dataset_cols=base_cols,
        dataset_path=table_path,
        max_schema_matching_samples=4,
        schema_matching_confidence_threshold=0.5,
        model="",
    )
    return target_col in entity_cols


def llm_check(df: pd.DataFrame, target_col: str, table_path: str, model_name: str):
    confidence_threshold = 0.5
    raw_groundings = df.apply(apply_ground, axis=1)
    all_original_cols = df.columns.to_list()
    llm_prompt = get_llm_schema_matching_prompt(
        entity_df=raw_groundings,
        col=target_col,
        file_name=Path(table_path).name,  ## pass just the name
        max_samples=5,
        table_cols=all_original_cols,
    )
    llm_resp = call_llm_for_schema_matching(llm_prompt=llm_prompt, model=model_name)
    most_likely_entity_type: str = max(llm_resp, key=lambda k: llm_resp[k])
    if (
        llm_resp.get(most_likely_entity_type, 0) < confidence_threshold
        or most_likely_entity_type == "no_schema_match"
    ):
        return False
    else:
        return True


def run_benchmark(
    benchmark: pl.DataFrame,
    heuristic: bool = True,
    llm_models: list[str] = [],
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
        if heuristic:
            record["heuristic_vote"] = heuristic_check(
                df=df, target_col=column, table_path=fp
            )
        for llm_model in tqdm(
            llm_models,
            total=len(llm_models),
            desc="checking schema matching with different models",
            unit="model",
        ):
            record[f"{llm_model}_vote"] = llm_check(
                df=df, target_col=column, table_path=fp, model_name=llm_model
            )
        record["label"] = benchmark_row.get("label")
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
    correct_pred = evaluated_df.filter(pl.col(col_name).eq(pl.col("label")))
    return len(correct_pred) / len(evaluated_df)


def precision(col_name: str, evaluated_df: pl.DataFrame) -> float:
    """Checks precision for a col in the write data frame"""
    tp = len(evaluated_df.filter(pl.col(col_name) & pl.col("label")))
    fp = len(evaluated_df.filter(pl.col(col_name) & ~pl.col("label")))
    return tp / (tp + fp)


def recall(col_name: str, evaluated_df: pl.DataFrame) -> float:
    """Checks recall for a col in the write data frame"""
    tp = len(evaluated_df.filter(pl.col(col_name) & pl.col("label")))
    fn = len(evaluated_df.filter(~pl.col(col_name) & pl.col("label")))
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
    benchmark = pl.read_csv(benchmark_path, separator="\t")
    logger.info("Running benchmark....")
    benchmarked_df = run_benchmark(
        benchmark=benchmark,
        heuristic=True,
        llm_models=llm_models,
        overwrite=False,
        load=True,
    )
    logger.info("Evaluating benchmark....")
    summary_df = get_benchmark_summary(
        evaluated_benchmark_df=benchmarked_df, union=False, intersection=False
    )
    logger.info(f"Summary results\n {summary_df}")
