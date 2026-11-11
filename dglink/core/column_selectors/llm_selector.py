"""
Select entity columns by asking an LLM to classify each column against a schema
"""
from .column_selector import ColumnSelector
from .schemas import BiologicalEntity
from dglink.core.tabular_dataset import TabularDataset
from dglink.core.llm_clients import OllamaClient, OpenAIClient, LLMClient, AnthropicClient
from pydantic import BaseModel
from typing import Type
from pandas import DataFrame
import textwrap
import json
import logging

logger = logging.getLogger(__name__)


def make_llm_client(provider: str, model: str) -> LLMClient:
    """Load the client for the given model provider."""
    provider = provider.lower()
    if provider == "openai":
        return OpenAIClient(model=model)
    elif provider == "ollama":
        return OllamaClient(model=model)
    elif provider == "anthropic":
        return AnthropicClient(model = model)
    raise ValueError(f"{provider} is not a recognized model provider.")


class LLMSelector(ColumnSelector):
    name = "llm_selector"

    def __init__(
        self,
        provider: str = "openai",
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
        """
        Note: min_ground_percentage is accepted for interface compatibility but is not
        currently used by the column-wise LLM selector.
        """
        super().__init__()
        self.model = model
        self.provider = provider.lower()
        self.target_records_for_call = target_records_for_call
        self.confidence_threshold = confidence_threshold
        self.schema = schema
        self.use_gilda_info = use_gilda_info
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.temperature = temperature
        self.priority_sample = priority_sample
        self.min_ground_percentage = min_ground_percentage
        self.llm_client: LLMClient = make_llm_client(self.provider, self.model)

    def execute(self, table: TabularDataset, verbose: bool = False, columns: list | None = None) -> None:
        starting_cols = self._resolve_columns(table, columns)
        keep, drop = [], []
        for col in starting_cols:
            e_type = self._classify_column(table, col, verbose)
            if e_type is None:
                drop.append(col)
            else:
                ## TODO: use the type labels for some type of value selection
                keep.append(col)
                logger.info(f"{col}->{e_type}")
        self._apply_selection(table, keep=keep, drop=drop)
        if verbose:
            self._log_selection(starting_cols, table)

    def check_column(self, table: TabularDataset, col: str, verbose: bool = False) -> bool:
        is_entity = self._classify_column(table, col, verbose) is not None
        if verbose:
            logger.info(f"{col} is_entity = {is_entity}")
        return is_entity

    def _classify_column(self, table: TabularDataset, col: str, verbose: bool = False) -> str | None:
        """Return the most likely schema entity type for a column, or None if no confident match."""
        sample = self._get_samples(table, col)
        system_prompt, user_prompt = self._get_prompts(col, sample)
        llm_resp: dict = self.llm_client.structured_call(
            context=system_prompt,
            user_prompt=user_prompt,
            schema=self.schema,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            temperature=self.temperature,
        ).model_dump()
        if verbose:
            logger.info(f"Provider: {self.provider} , Model : {self.model}")
            logger.info(llm_resp)
        most_likely_entity_type: str = max(llm_resp, key=lambda k: llm_resp[k])
        if llm_resp[most_likely_entity_type] < self.confidence_threshold or most_likely_entity_type == "Other":
            return None
        return most_likely_entity_type

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
        raw_col = f"{col}_raw_text"
        cols = [raw_col] if not self.use_gilda_info else [raw_col, f"{col}_name", f"{col}_type"]
        view: DataFrame = table.table[cols]
        ## take a random sample ##
        if not self.priority_sample:
            max_samples = max(view[raw_col].count(), 1)
            return (
                view.dropna(subset=[raw_col])
                ## seeded per table so the same table/column always gets the same sample
                .sample(min(self.target_records_for_call, max_samples), random_state=table.seed)
                .fillna(value="not found", axis=1)
            )
        priority_sample = table.get_priority_sample(col=col, target_size=self.target_records_for_call)
        ## first row for each sampled value
        return (
            view[view[raw_col].isin(priority_sample)]
            .drop_duplicates(subset=[raw_col])
            .fillna(value="not found", axis=1)
        )
