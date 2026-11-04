"""
Select entity columns using a single LLM call over the whole table
"""

from dglink.core.tabular_dataset import TabularDataset
from dglink.core.llm_clients import LLMClient
from .column_selector import ColumnSelector, grounding_columns
from .llm_selector import LLMSelector, make_llm_client
from .schemas import EvaluationResponseBatch
from ...core.constants import TABULAR_ENTITY_TYPES_LLM

import json
import textwrap
import logging
import pandas
from numpy import array

logger = logging.getLogger(__name__)

NO_MATCH = "no_schema_match"


class LLMSelectorTableWide(ColumnSelector):
    name = "table_wide_llm_selector"

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-5-mini",
        target_records_for_call: int = 10,
        confidence_threshold: float = 0.5,
        min_ground_percentage: float = 0.1,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float = 0.0,
    ) -> None:
        super().__init__()
        self.provider = provider.lower()
        self.model = model
        self.target_records_for_call = target_records_for_call
        self.confidence_threshold = confidence_threshold
        self.min_ground_percentage = min_ground_percentage
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.temperature = temperature
        self.llm_client: LLMClient = make_llm_client(self.provider, self.model)

    def check_column(self, table: TabularDataset, col: str, verbose: bool = False) -> bool:
        """
        Does not really make sense to just do one column so this is run with the column-wise llm selector
        """
        selector = LLMSelector(
            provider=self.provider,
            model=self.model,
            target_records_for_call=self.target_records_for_call,
            confidence_threshold=self.confidence_threshold,
            min_ground_percentage=self.min_ground_percentage,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            temperature=self.temperature,
        )
        ## reuse our client rather than constructing a new one
        selector.llm_client = self.llm_client
        return selector.check_column(table, col, verbose)

    def execute(self, table: TabularDataset, verbose: bool = False, columns: list | None = None) -> None:
        starting_cols = self._resolve_columns(table, columns)
        llm_resp = self.call_llm_batch(self.get_llm_prompt_batch(table=table, columns=starting_cols))
        ## columns skipped by the prompt (below min_ground_percentage) or not returned are dropped
        score_map: dict[str, list[str] | None] = {col: None for col in starting_cols}
        for col, probs in llm_resp.items():
            if col not in score_map:
                logger.warning(f"LLM returned unknown column {col!r}, ignoring")
                continue
            most_likely_entity_type = max(probs, key=lambda k: probs[k])
            if probs[most_likely_entity_type] >= self.confidence_threshold and most_likely_entity_type != NO_MATCH:
                score_map[col] = [
                    key for key in TABULAR_ENTITY_TYPES_LLM if probs.get(key, 0) > self.confidence_threshold
                ]
        self.process_response(matching_cols=score_map, table=table)
        if verbose:
            self._log_selection(starting_cols, table)

    def process_response(self, matching_cols: dict, table: TabularDataset):
        """
        use the schema match to:
            1. drop cols if not matched
            2. set values grounded to any other entity type to NA
        """
        keep, drop = [], []
        for col, matched_types in matching_cols.items():
            if matched_types is None:
                drop.append(col)
                continue
            keep.append(col)
            type_col = f"{col}_type"
            index_mask = ~(table.table[type_col].notna() & table.table[type_col].isin(matched_types))
            table.table.loc[index_mask, grounding_columns(col)] = pandas.NA
        self._apply_selection(table, keep=keep, drop=drop)

    def get_llm_prompt_batch(self, table: TabularDataset, columns: list | None = None) -> tuple[str, str]:
        """Build (context, prompt). The prompt is "" if no column qualifies for evaluation."""
        df = table.table
        table_len = len(df)
        column_infos = []

        for col in self._resolve_columns(table, columns):
            grounded_count = df[f"{col}_name"].count()
            ungrounded_count = table_len - grounded_count
            rows_with_values = max(df[f"{col}_raw_text"].count(), 1)

            # Skip if below threshold
            if (grounded_count / rows_with_values) < self.min_ground_percentage:
                continue

            priority_sample = table.get_priority_sample(col=col, target_size=self.target_records_for_call)
            logger.info(f"Got priority sample of length {len(priority_sample)} for {col}")
            ## first row for each sampled raw value
            sample_rows = df[df[f"{col}_raw_text"].isin(priority_sample)].drop_duplicates(
                subset=[f"{col}_raw_text"]
            )
            records = [
                {
                    "raw_text": row[f"{col}_raw_text"],
                    "grounded_entity_type": "Unable to ground"
                    if pandas.isna(row[f"{col}_type"])
                    else row[f"{col}_type"],
                    "grounded_entity_name": "Unable to ground"
                    if pandas.isna(row[f"{col}_name"])
                    else row[f"{col}_name"],
                }
                for _, row in sample_rows.iterrows()
            ]
            column_infos.append(
                {
                    "column_name": col,
                    "stats": {
                        "missing_rows": f"{table_len - rows_with_values}",
                        "ungrounded_rows": f"{ungrounded_count}",
                    },
                    "sample": records,
                }
            )

        content_list = "\n- ".join(TABULAR_ENTITY_TYPES_LLM + [NO_MATCH])
        model_context = textwrap.dedent("""
            You must output a probability distribution over the following entity types.
            Each probability must be a float between 0 and 1.
            All probabilities must sum to 1.

            Valid entity types (output field names, must match exactly):
            - {content_list}

            The probabilities should reflect the semantic meaning of the column as a whole,
            not individual rows.

            Note: Rows that were unable to be grounded refers to cases where a unique ontology identifier could not be assigned,
            but the raw values may still be valid entities

            Note: Use no_schema_match when the column does not predominantly contain biological entity names
            or when the column semantics are unclear or non-entity (e.g., free text, measurements, IDs).
        """).strip().format(content_list=content_list)

        if not column_infos:
            return model_context, ""

        model_prompt = textwrap.dedent(f"""
            Table: {table.dataset_path.name}
            Total rows: {table_len}

            For each column below, predict probability distribution over entity types:
        """).strip() + "\n" + json.dumps(column_infos, indent=2, default=str)

        return model_context, model_prompt

    def call_llm_batch(self, llm_prompt: tuple[str, str]) -> dict[str, dict[str, float]]:
        """
        Call LLM to evaluate multiple columns at once.

        Returns:
            dict mapping column_name -> {entity_type: probability}, normalized to sum to 1
        """
        call_context, call_prompt = llm_prompt
        if call_prompt == "":
            return {}

        raw_response = self.llm_client.structured_call(
            context=call_context,
            user_prompt=call_prompt,
            schema=EvaluationResponseBatch,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            temperature=self.temperature,
        )
        if not isinstance(raw_response, EvaluationResponseBatch) or not raw_response.columns:
            logger.warning("Empty LLM response for batch evaluation")
            return {}

        normalized_result = {}
        for col_eval in raw_response.columns:
            probs = col_eval.model_dump(exclude={"column_name"})
            values = array(list(probs.values()), dtype=float)
            if values.sum() > 0:
                normalized_result[col_eval.column_name] = dict(zip(probs.keys(), values / values.sum()))
            else:
                logger.warning(
                    f"All zero probabilities for column {col_eval.column_name}, using uniform distribution"
                )
                normalized_result[col_eval.column_name] = {k: 1.0 / len(probs) for k in probs}
        return normalized_result
