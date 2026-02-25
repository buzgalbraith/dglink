import csv
import os
from subprocess import run
import logging
from ipdb import set_trace
from pathlib import Path

from dglink.core.tabular_data import load_file

logger = logging.getLogger(__name__)

ORIGINAL_BENCHMARK_PATH = "dglink/resources/reports/benchmarking_columns_diverse.tsv"
WRITE_BENCHMARK_PATH = (
    "dglink/resources/reports/benchmarking_columns_diverse_annotated.tsv"
)


def get_benchmark_records() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    with open(ORIGINAL_BENCHMARK_PATH, mode="r") as f:
        resp = csv.DictReader(f, delimiter="\t")
        for record in resp:
            records.append(record)
    return records


def check_existing_annotated_benchmark(records: list[dict[str, str]]) -> set:
    already_labeled = set()
    if not os.path.exists(WRITE_BENCHMARK_PATH):
        logger.info(
            f"No annotated benchmark exists yet, writing results incrementally to {WRITE_BENCHMARK_PATH}"
        )
        with open(WRITE_BENCHMARK_PATH, mode="w") as f:
            csv.DictWriter(
                f, fieldnames=records[0].keys(), delimiter="\t"
            ).writeheader()
    else:
        logger.info(
            f"Annotated benchmark exists loading previous progress from {WRITE_BENCHMARK_PATH}"
        )
        with open(WRITE_BENCHMARK_PATH, mode="r") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                already_labeled.add((r["fp"], r["column"], r["sheet"]))
    return already_labeled


if __name__ == "__main__":
    ## extract original benchmark ##
    benchmark_records = get_benchmark_records()
    # write header to new output path if needed and otherwise get already labeled rows.##
    checked_rows = check_existing_annotated_benchmark(records=benchmark_records)
    # update file ##
    total_records = len(benchmark_records)
    current_record = 0
    with open(WRITE_BENCHMARK_PATH, mode="a") as f:
        csv_write = csv.DictWriter(
            f, fieldnames=benchmark_records[0].keys(), delimiter="\t"
        )
        for row in benchmark_records:
            ## extract fields ##
            dataset_path = row.get("fp", "missing")
            group_id = row.get("group_identifier", "missing")
            target_sheet = row.get("sheet", "missing")
            target_col = row.get("column", "missing")
            key = (dataset_path, target_col, target_sheet)
            current_record += 1
            if key in checked_rows:
                logging.info(
                    f"Already labeled {dataset_path}, {target_sheet}, {target_col}. Skipping..."
                )
                continue
            ## get the proper dataset ##
            dfs, read_states = load_file(group_identifier=group_id, fp=dataset_path)
            sheet_idx = 0
            while read_states[sheet_idx]["sheet"] != target_sheet:
                sheet_idx += 1
            df = dfs[sheet_idx]
            col_view = df[target_col]
            ## open in file viewer ##
            cmd = ["open", dataset_path]
            run(cmd)
            ## Give user information ##
            logger.info(
                f"Looking at record {current_record} out of {total_records}, {total_records-current_record} remain to be labeled."
            )
            logger.info(f"File name: {Path(dataset_path).name}")
            logger.info(f"Sheet name: {target_sheet}")
            logger.info(f"Column name: {target_col}")
            logger.info(f"Group ID: {group_id}")
            ## trace so can look at the DF in memory ##
            set_trace()
            ## get and parse input from user ##
            user_resp = input('Is this a valid "biological entity" column?...\t')
            while user_resp not in ["0", "1"]:
                user_resp = input("Enter the label as either 0 or 1 please...\t")
            parsed_resp = f"{bool(int(user_resp))}"  ## kind of cursed but what ever
            row["is_entity_col"] = parsed_resp
            csv_write.writerow(row)
            f.flush() ## avoids buffer issues ## 
            ## report back and continue ##
            logger.info(f"You have labeled this column as {parsed_resp}")
            logger.info("-" * 50)
