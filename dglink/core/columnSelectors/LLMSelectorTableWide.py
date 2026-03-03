"""
Select entity columns using LLMs
"""

from dglink.core.tabularDataset import tabularDataset
from .columnSelector import columnSelector, pandas
from .LLMSelector import LLMSelector, evaluation_response
from ...core.constants import TABULAR_ENTITY_TYPES_LLM, open_ai_client

import json
from pydantic import BaseModel
from openai import BadRequestError
from numpy import array
import logging

logger = logging.getLogger(__name__)


class LLMSelectorTableWide(columnSelector):
    name = "table_wide_LLM_selector"

    def __init__(
        self,
        open_AI_model: str = "gpt-5-mini",
        target_records_for_call: int = 10,
        confidence_threshold: float = 0.5,
        min_ground_percentage: float = 0.1,
    ) -> None:
        super().__init__()
        self.open_AI_model = open_AI_model
        self.target_records_for_call = target_records_for_call
        self.confidence_threshold = confidence_threshold
        self.min_ground_percentage = min_ground_percentage

    def check_column(
        self, table: tabularDataset, col: str, verbose: bool = False
    ) -> bool:
        """
        Does not really make sense to just do one column so this is run with the column-wise llm selector
        """
        selector = LLMSelector(
            self.open_AI_model,
            self.target_records_for_call,
            self.confidence_threshold,
            self.min_ground_percentage,
        )
        return selector.check_column(table, col, verbose)

    def execute(self, table: tabularDataset, verbose: bool = False):
        llm_prompt = self.get_llm_prompt_batch(table=table)
        llm_resp = self.call_llm_batch(llm_prompt=llm_prompt)
        # Handle columns that were skipped (below min_ground_percentage)
        score_map: dict[str, None | list] = {
            col: None for col in table.original_columns
        }

        for col, probs in llm_resp.items():
            most_likely_entity_type = max(probs, key=lambda k: probs[k])

            if (
                probs.get(most_likely_entity_type, 0) < self.confidence_threshold
                or most_likely_entity_type == "no_schema_match"
            ):
                score_map[col] = None
            else:
                score_map[col] = [
                    key
                    for key in TABULAR_ENTITY_TYPES_LLM
                    if probs.get(key, 0) > self.confidence_threshold
                ]

        self.process_response(matching_cols=score_map, table=table)

        if verbose:
            logger.info(
                f"Has {len(table.original_columns)} columns: {table.original_columns}"
            )
            logger.info(
                f"Selected {len(table.entity_columns)} entity columns: {table.entity_columns}"
            )
            logger.info("-" * 50)

    def process_response(self, matching_cols: dict, table: tabularDataset):
        """
        use the schema match to:
            1. drop cols if not matched
            2. return only values for that col which were grounded to the matched schema type
        """
        entity_cols = []
        cols_to_drop = []
        for col in matching_cols:
            associated_cols = [
                f"{col}_entity",
                f"{col}_type",
                f"{col}_name",
                f"{col}_raw_text",
                f"{col}_column_name",
                f"{col}_iri",
            ]
            ## if not matched to schema drop
            if matching_cols[col] is None:
                cols_to_drop += associated_cols
            ## otherwise set entities found with any other data type to na
            else:
                entity_cols.append(col)
                type_col = f"{col}_type"
                index_mask = ~(
                    table.table[type_col].notna()
                    & (table.table[type_col].isin(matching_cols[col]))
                )
                table.table.loc[index_mask, associated_cols] = pandas.NA
        table.table.drop(columns=cols_to_drop, inplace=True)
        table.entity_columns = entity_cols

    def get_llm_prompt_batch(self, table: tabularDataset) -> tuple[str, str]:
        table_len = len(table.table)
        column_infos = []

        for col in table.original_columns:
            ungrounded_count = table_len - table.table[f"{col}_name"].count()
            grounded_count = table.table[f"{col}_name"].count()
            rows_with_values = max(table.table[f"{col}_raw_text"].count(), 1)

            # Skip if below threshold
            if (grounded_count / rows_with_values) < self.min_ground_percentage:
                continue

            # Build column-specific info (similar to existing logic)
            priority_sample = table.get_priority_sample(
                col=col, target_size=5
            )  # Reduce samples per column
            records = []
            logger.info("Getting priority sample")
            priority_sample = table.get_priority_sample(
                col=col, target_size=self.target_records_for_call
            )
            logger.info(f"Got priority sample of length {len(priority_sample)}")
            for val in priority_sample:
                idx = table.table[table.table[f"{col}_name"] == val].index[0]
                row = table.table.iloc[idx]
                row_type = (
                    "Unable to ground"
                    if pandas.isna(row[f"{col}_type"])
                    else row[f"{col}_type"]
                )
                row_name = (
                    "Unable to ground"
                    if pandas.isna(row[f"{col}_name"])
                    else row[f"{col}_name"]
                )
                records.append(
                    {
                        "raw_text": row[f"{col}_raw_text"],
                        "grounded_entity_type": row_type,
                        "grounded_entity_name": row_name,
                    }
                )
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

        model_prompt = f"""
        Table: {table.dataset_path.name}
        Total rows: {len(table.table)}
        
        For each column below, predict probability distribution over entity types:
        {json.dumps(column_infos, indent=2)}
        """
        content_list = "\n    - ".join(TABULAR_ENTITY_TYPES_LLM + ["no_schema_match"])
        model_context = f"""
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
        """

        return model_context, model_prompt

    def call_llm_batch(
        self, llm_prompt: tuple[str, str]
    ) -> dict[str, dict[str, float]]:
        """
        Call LLM to evaluate multiple columns at once.

        Returns:
            dict mapping column_name -> {entity_type: probability}
        """
        call_context, call_prompt = llm_prompt

        if call_prompt == "":
            return {}

        try:
            response = open_ai_client.responses.parse(
                model=self.open_AI_model,
                input=[
                    {
                        "role": "system",
                        "content": call_context,
                    },
                    {"role": "user", "content": call_prompt},
                ],
                text_format=evaluation_response_batch,
            )
        except BadRequestError:
            raise ValueError(
                f"Model {self.open_AI_model} invalid perhaps try gpt-4o, gpt-4o-mini, gpt-5 or gpt-5-mini"
            )

        raw_response = response.output_parsed
        if not raw_response or not raw_response.columns:
            logger.warning("Empty LLM response for batch evaluation")
            return {}

        # Convert list of ColumnEvaluation objects to dict format
        normalized_result = {}

        for col_eval in raw_response.columns:
            col_name = col_eval.column_name

            # Extract all entity type probabilities (excluding column_name field)
            probs = {
                field: getattr(col_eval, field)
                for field in col_eval.model_fields
                if field != "column_name"
            }

            values = array(list(probs.values()))

            # Normalize to sum to 1
            if values.sum() > 0:
                normalized_probs = values / values.sum()
                normalized_result[col_name] = dict(zip(probs.keys(), normalized_probs))
            else:
                # Fallback: uniform distribution if all zeros
                logger.warning(
                    f"All zero probabilities for column {col_name}, using uniform distribution"
                )
                uniform_prob = 1.0 / len(probs)
                normalized_result[col_name] = {k: uniform_prob for k in probs.keys()}

        return normalized_result


class ColumnEvaluation(evaluation_response):
    """slight override with added column name attribute"""

    column_name: str


class evaluation_response_batch(BaseModel):
    """Response model for batch column evaluation"""

    columns: list[ColumnEvaluation]
