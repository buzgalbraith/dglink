from .column_selector import ColumnSelector
from .schemas import BiologicalEntity
from dglink.core.tabular_dataset import TabularDataset
from dglink.core.llm_clients import OllamaClient, OpenAIClient, LLMClient
from pydantic import BaseModel
from typing import Type
from pandas import DataFrame
import textwrap
import json
import logging

logger = logging.getLogger(__name__)


class LLMSelector(ColumnSelector):
    def __init__(
        self,
        provider:str ="openai",
        model: str = "gpt-5-mini",
        target_records_for_call: int = 10,
        confidence_threshold: float = 0.5,
        min_ground_percentage: float = 0.1,
        schema: Type[BaseModel] = BiologicalEntity,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float = 0.0,
        use_gilda_info: bool = False,
        priority_sample: bool = False,
    ) -> None:
        super().__init__()
        self.model = model
        self.provider = provider.lower()
        self.name = model
        self.target_records_for_call = target_records_for_call
        self.confidence_threshold = confidence_threshold
        self.schema = schema
        self.use_gilda_info = use_gilda_info
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.temperature = temperature
        self.priority_sample = priority_sample
        self.min_ground_percentage = min_ground_percentage
        self.llm_client: LLMClient = self.initialize_llm_client()

    def execute(
        self, table: TabularDataset, verbose: bool = False, table_wide: bool = False
    ):
        col_map = []
        for col in table.original_columns:
            sample = self._get_samples(table, col)
            system_prompt, user_prompt = self._get_prompts(col, sample)
            llm_resp_bm = self.llm_client.structured_call(
                context=system_prompt,
                user_prompt=user_prompt,
                schema=self.schema,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
                temperature=self.temperature,
            )
            llm_resp: dict = llm_resp_bm.model_dump()
            if verbose:
                logger.info(f"Provider: {self.provider} , Model : {self.model}")
                logger.info(llm_resp)
            most_likely_entity_type: str = max(llm_resp, key=lambda k: llm_resp[k])
            if (
                llm_resp.get(most_likely_entity_type, 0) < self.confidence_threshold
                or most_likely_entity_type == "Other"
            ):
                col_map.append((col, None))
            else:
                col_map.append((col, most_likely_entity_type))
        self.process_response(col_map=col_map, table=table)
        if verbose:
            logger.info(
                f"Has {len(table.original_columns)} which are {table.original_columns}"
            )
            logger.info(
                f"Selected {len(table.entity_columns)} which are {table.entity_columns}"
            )
            logger.info("-" * 50)

    def check_column(
        self, table: TabularDataset, col: str, verbose: bool = False
    ) -> bool:
        sample = self._get_samples(table, col)
        system_prompt, user_prompt = self._get_prompts(col, sample)
        llm_resp = self.llm_client.structured_call(
            context=system_prompt,
            user_prompt=user_prompt,
            schema=self.schema,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            temperature=self.temperature,
        )
        llm_resp = llm_resp.model_dump()
        if verbose:
            logger.info(f"Provider: {self.provider} , Model : {self.model}")
            logger.info(llm_resp)
        most_likely_entity_type: str = max(llm_resp, key=lambda k: llm_resp[k])
        if (
            llm_resp.get(most_likely_entity_type, 0) < self.confidence_threshold
            or most_likely_entity_type == "Other"
        ):
            is_entity = False
        else:
            is_entity = True
        if verbose:
            logger.info(f"{col} is_entity = {is_entity}")
        return is_entity

    def initialize_llm_client(self) -> LLMClient:
        """load the client for the correct model provider."""
        if self.provider == "openai":
            return OpenAIClient()
        elif self.provider == "ollama":
            return OllamaClient()
        else:
            raise ValueError(f"{self.provider} is not a recognized model provider.")

    def process_response(self, col_map: list, table: TabularDataset):
        """
        use the schema match to:
            1. drop cols if not matched
            2. return only values for that col which were grounded to the matched schema type
        """
        entity_cols = []
        cols_to_drop = []
        for col, e_type in col_map:
            associated_cols = [
                f"{col}_entity",
                f"{col}_type",
                f"{col}_name",
                f"{col}_raw_text",
                f"{col}_column_name",
                f"{col}_iri",
            ]
            ## if not matched to schema drop
            if e_type is None:
                cols_to_drop += associated_cols
            else:
                ## TODO: use the type labels for some type of value selection
                entity_cols.append(col)
                print(f"{col}->{e_type}")
        table.table.drop(columns=cols_to_drop, inplace=True)
        table.entity_columns = entity_cols

    def _get_prompts(self, col: str, sample: DataFrame):
        """
        helper function for defining the prompt
        """
        system_prompt = textwrap.dedent(f"""
            You are a scientist looking at columns from experimental datasets.
            Predict the likelihood that this column represents one of the classes in the schema below,
            where most classes come from BioLink:

            {self.schema.model_json_schema()}

            Each value in your response should be between 0 and 1, and all values must sum to 1.
        """).strip()
        user_prompt = textwrap.dedent(f"""
            Column name: {col}
            Example values:
            {json.dumps([str(v) for v in sample.values[:, 0].tolist()], indent=2)}
        """).strip()
        if self.use_gilda_info:
            gilda_groundings = json.dumps(sample.values[:, 1].tolist(), indent=2)
            entity_types = json.dumps(sample.values[:, 2].tolist(), indent=2)
            user_prompt += textwrap.dedent(f"""

            Example Gilda groundings:
            {gilda_groundings}

            Example INDRA entity type annotations:
            {entity_types}
            """).strip()
        return system_prompt, user_prompt

    def _get_samples(self, table: TabularDataset, col: str) -> DataFrame:
        df = table.table
        cols = (
            [f"{col}_raw_text"]
            if not self.use_gilda_info
            else [f"{col}_raw_text", f"{col}_name", f"{col}_type"]
        )
        view: DataFrame = df[cols]
        max_samples = max(table.table[f"{col}_raw_text"].count(), 1)
        if not self.priority_sample:
            return (
                view.dropna(subset=[f"{col}_raw_text"])
                .sample(min(self.target_records_for_call, max_samples))
                .fillna(value="not found", axis=1)
            )
        priority_sample = table.get_priority_sample(
            col=col, target_size=self.target_records_for_call
        )
        idxs = []
        for val in priority_sample:
            idxs.append(table.table[table.table[f"{col}_raw_text"] == val].index[0])
        return view.loc[idxs].fillna(value="not found", axis=1)
