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

benchmark_path = os.path.join(REPORT_PATH, "benchmarking_columns.tsv")


def heuristic_check(df: pd.DataFrame, target_col: str) -> bool:
    base_cols = df.columns.to_list()
    raw_groundings = df.apply(apply_ground, axis=1)
    _, entity_cols = quality_check_groundings(
        qc_method="heuristic",
        grounded_dataset=raw_groundings,
        original_dataset_cols=base_cols,
        dataset_path=fp,
        max_schema_matching_samples=4,
        schema_matching_confidence_threshold=0.5,
    )
    return target_col in entity_cols


def llm_check(df: pd.DataFrame, target_col: str, table_path: str):
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
    llm_resp = call_llm_for_schema_matching(
        llm_prompt=llm_prompt,
    )
    most_likely_entity_type: str = max(llm_resp, key=llm_resp.get)
    if (
        llm_resp.get(most_likely_entity_type, 0) < confidence_threshold
        or most_likely_entity_type == "no_schema_match"
    ):
        return False
    else:
        return True


if __name__ == "__main__":
    records = []
    benchmark = pl.read_csv(benchmark_path, separator="\t")
    for benchmark_row in tqdm(
        benchmark.iter_rows(named=True),
        total=len(benchmark),
        desc="running benchmark evaluation",
        unit="benchmark column ",
    ):
        group_id = benchmark_row.get("group_identifier", "")
        fp = benchmark_row.get("fp", "")
        target_sheet = benchmark_row.get("sheet", "")
        dfs, read_states = load_file(group_identifier=group_id, fp=fp)
        sheet_idx = 0
        column = benchmark_row.get("column", "")
        while read_states[sheet_idx]["sheet"] != target_sheet:
            sheet_idx += 1
        df = dfs[sheet_idx]
        heuristic_vote = heuristic_check(df=df, target_col=column)
        llm_vote = llm_check(df=df, target_col=column, table_path=fp)
        label = benchmark_row.get("is_entity_col")
        # if (label != llm_vote) or (heuristic_vote != llm_vote):
        #     import ipdb; ipdb.set_trace()
        records.append(
            {
                "col": column,
                "heuristic_vote": heuristic_vote,
                "llm_vote": llm_vote,
                "is_entity_col": label,
                "sheet": target_sheet,
                "group_identifier": group_id,
                "file_path": fp,
            }
        )
    write_df = pl.from_dicts(records)
    write_df.write_csv(
        os.path.join(
            REPORT_PATH,
            "evaluated_benchmark.tsv",
        ),
        separator="\t",
    )

    # llm_acc = write_df.filter(pl.col('llm_vote').eq(pl.col('is_entity_col')))
    # huerstic_acc = write_df.filter(pl.col('heuristic_vote').eq(pl.col('is_entity_col')))
    llm_tp = len(write_df.filter(pl.col("llm_vote") & pl.col("is_entity_col")))
    llm_fp = len(write_df.filter(pl.col("llm_vote") & ~pl.col("is_entity_col")))
    llm_fn = len(write_df.filter(~pl.col("llm_vote") & pl.col("is_entity_col")))
    llm_precision = llm_tp / (llm_tp + llm_fp)
    llm_recall = llm_tp / (llm_tp + llm_fn)
    llm_f1 = 2 * ((llm_precision * llm_recall) / (llm_precision + llm_recall))
    h_tp = len(write_df.filter(pl.col("heuristic_vote") & pl.col("is_entity_col")))
    h_fp = len(write_df.filter(pl.col("heuristic_vote") & ~pl.col("is_entity_col")))
    h_fn = len(write_df.filter(~pl.col("heuristic_vote") & pl.col("is_entity_col")))
    h_precision = h_tp / (h_tp + h_fp)
    h_recall = h_tp / (h_tp + h_fn)
    h_f1 = 2 * ((h_precision * h_recall) / (h_precision + h_recall))
    # INTERSECTION (both must agree)
    intersection_acc = len(
        write_df.filter(
            pl.col("heuristic_vote").eq(pl.col("is_entity_col"))
            & pl.col("llm_vote").eq(pl.col("is_entity_col"))
        )
    )
    intersection_tp = len(
        write_df.filter(
            pl.col("heuristic_vote") & pl.col("llm_vote") & pl.col("is_entity_col")
        )
    )
    intersection_fp = len(
        write_df.filter(
            pl.col("heuristic_vote") & pl.col("llm_vote") & ~pl.col("is_entity_col")
        )
    )
    intersection_fn = len(
        write_df.filter(
            ~(pl.col("heuristic_vote") & pl.col("llm_vote")) & pl.col("is_entity_col")
        )
    )
    intersection_precision = intersection_tp / (intersection_tp + intersection_fp)
    intersection_recall = intersection_tp / (intersection_tp + intersection_fn)
    intersection_f1 = 2 * (
        (intersection_precision * intersection_recall)
        / (intersection_precision + intersection_recall)
    )
    # UNION (either votes yes)
    intersection_acc = len(
        write_df.filter(
            (pl.col("heuristic_vote") | pl.col("llm_vote")).eq(pl.col("is_entity_col"))
        )
    )
    union_tp = len(
        write_df.filter(
            (pl.col("heuristic_vote") | pl.col("llm_vote")) & pl.col("is_entity_col")
        )
    )
    union_fp = len(
        write_df.filter(
            (pl.col("heuristic_vote") | pl.col("llm_vote")) & ~pl.col("is_entity_col")
        )
    )
    union_fn = len(
        write_df.filter(
            ~pl.col("heuristic_vote") & ~pl.col("llm_vote") & pl.col("is_entity_col")
        )
    )
    union_precision = union_tp / (union_tp + union_fp)
    union_recall = union_tp / (union_tp + union_fn)
    union_f1 = 2 * ((union_precision * union_recall) / (union_precision + union_recall))
    ## where they differ
    differ = write_df.filter(pl.col("heuristic_vote").eq(~pl.col("llm_vote")))
    ## what were llm methods missing
    write_df.filter(
        pl.col("heuristic_vote") & ~pl.col("llm_vote") & pl.col("is_entity_col")
    ).write_csv("missing_by_llm.tsv", separator="\t")
