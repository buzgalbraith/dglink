"""
Select entity columns using LLMs
"""

from dglink.core.tabular_dataset import TabularDataset
from .column_selector import ColumnSelector, pandas
from ...core.constants import TABULAR_ENTITY_TYPES_LLM, open_ai_client
from .schemas import EvaluationResponse

import json
from openai import BadRequestError
from numpy import array
import logging

logger = logging.getLogger(__name__)


class LLMSelector(ColumnSelector):
    name = "LLM_selector"

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
        self, table: TabularDataset, col: str, verbose: bool = False
    ) -> bool:
        llm_prompt = self.get_llm_prompt(col=col, table=table)
        llm_resp = self.call_llm(llm_prompt=llm_prompt)
        most_likely_entity_type: str = max(llm_resp, key=lambda k: llm_resp[k])
        if (
            llm_resp.get(most_likely_entity_type, 0) < self.confidence_threshold
            or most_likely_entity_type == "no_schema_match"
        ):
            is_entity = False
        else:
            is_entity = True
        if verbose:
            logger.info(f"{col} is_entity = {is_entity}")
        return is_entity

    def execute(self, table: TabularDataset, verbose: bool = False):
        score_map = {}
        matching_cols = []
        for col in table.original_columns:
            llm_prompt = self.get_llm_prompt(col=col, table=table)
            llm_resp = self.call_llm(llm_prompt=llm_prompt)
            ## check cases where it is confident that the col represents nothing or unconfined in everything
            most_likely_entity_type: str = max(llm_resp, key=lambda k: llm_resp[k])
            ## TODO: Decide how want to do cut off for llm schema matching ##
            # if llm_resp.get('no_schema_match', 0) > confidence_threshold or max(llm_resp.values()) < confidence_threshold:
            #     score_map[col] = None
            if (
                llm_resp.get(most_likely_entity_type, 0) < self.confidence_threshold
                or most_likely_entity_type == "no_schema_match"
            ):
                score_map[col] = None
            else:
                score_map[col] = [
                    key
                    for key in TABULAR_ENTITY_TYPES_LLM
                    if llm_resp.get(key, 0) > self.confidence_threshold
                ]
                matching_cols.append(col)
        self.process_response(matching_cols=score_map, table=table)
        if verbose:
            logger.info(
                f"Has {len(table.original_columns)} which are {table.original_columns}"
            )
            logger.info(
                f"Selected {len(table.entity_columns)} which are {table.entity_columns}"
            )
            logger.info("-" * 50)

    def process_response(self, matching_cols: dict, table: TabularDataset):
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

    def call_llm(self, llm_prompt: tuple[str, str]) -> dict[str, float]:
        call_context, call_prompt = llm_prompt
        if call_prompt == "":
            return {
                entity_type: 0
                for entity_type in TABULAR_ENTITY_TYPES_LLM + ["no_schema_match"]
            }
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
                text_format=EvaluationResponse,
            )
        except BadRequestError:
            raise ValueError(
                f"Model {self.open_AI_model} invalid perhaps try gpt-4o, gpt-4o-mini, gpt-5 or gpt-5-mini"
            )

        raw_probs = response.output_parsed
        if raw_probs:
            raw_probs = raw_probs.model_dump()
        else:
            raw_probs = dict()
        values = array(list(raw_probs.values()))
        normalized_probs = values / values.sum()
        out = dict(zip(raw_probs.keys(), normalized_probs))
        return out

    def get_llm_prompt(self, table: TabularDataset, col) -> tuple[str, str]:
        table_len = len(table.table)
        grounded_count = table.table[f"{col}_name"].count()
        rows_with_values = max(table.table[f"{col}_raw_text"].count(), 1)
        ## skip cols where less than 10% of rows that had entities were grounded.
        if (grounded_count / max(rows_with_values, 1)) < self.min_ground_percentage:
            return "", ""
        ungrounded_count = table_len - table.table[f"{col}_name"].count()
        records = []
        identified_entities = (
            table.table[f"{col}_type"].dropna().value_counts().sort_index().to_dict()
        )
        unique_identified_entities = (
            table.table.dropna(subset=f"{col}_type")
            .groupby(f"{col}_type")[f"{col}_raw_text"]
            .nunique()
            .sort_index()
            .to_dict()
        )
        for key in TABULAR_ENTITY_TYPES_LLM:
            if key not in identified_entities:
                identified_entities[key] = 0
                unique_identified_entities[key] = 0
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
        model_prompt = f"""
        Table information:
        - File name: {table.dataset_path.name}
        - Table columns: {table.original_columns}
        - Total rows: {table_len}

        Column information:
        - Column Name: {col}
        - Number of missing rows in column: {table_len - rows_with_values}
        - Number of rows that were unable to be grounded in column: {ungrounded_count}
        - Column Distribution of rows by predicted entity type: {json.dumps(identified_entities, indent=6)}
        - Column Distribution of unique rows by predicted entity type: {json.dumps(unique_identified_entities, indent=6)}
        - Column Sample record: {json.dumps(records, indent=2)}
        """

        # model_context = f"Given the following table and column information, predict the Probability (so that all values some to 1) that the column represents entities of each of the following types {TABULAR_ENTITY_TYPES_LLM} as well as no entity type in the schema"
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
