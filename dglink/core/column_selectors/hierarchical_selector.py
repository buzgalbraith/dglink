"""
Select entity columns in two stages: a cheap heuristic filter, then an LLM check
on only the columns that survive the heuristic.
"""
from typing import Type

from pydantic import BaseModel

from .column_selector import ColumnSelector, TabularDataset
from .heuristic_selector import HeuristicSelector
from .llm_selector import LLMSelector
from .schemas import BiologicalEntity


class HierarchicalSelector(ColumnSelector):
    name = "hierarchical_selector"

    def __init__(
        self,
        nan_percentage: float = 0.1,
        max_entity_types: int = 8,
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
    ):
        super().__init__()
        self.heuristic = HeuristicSelector(
            nan_percentage=nan_percentage, max_entity_types=max_entity_types
        )
        self.llm = LLMSelector(
            provider=provider,
            model=model,
            target_records_for_call=target_records_for_call,
            confidence_threshold=confidence_threshold,
            min_ground_percentage=min_ground_percentage,
            schema=schema,
            max_retries=max_retries,
            retry_delay=retry_delay,
            temperature=temperature,
            use_gilda_info=use_gilda_info,
            priority_sample=priority_sample,
        )

    def execute(self, table: TabularDataset, verbose: bool = False, columns: list | None = None) -> None:
        self.heuristic.execute(table, verbose=verbose, columns=columns)
        ## only spend LLM calls on columns that passed the heuristic
        if len(table.entity_columns) > 0:
            self.llm.execute(table, verbose=verbose, columns=table.entity_columns)

    def check_column(self, table: TabularDataset, col: str, verbose: bool = False) -> bool:
        """Check if a single column contains entities (LLM only consulted if heuristic passes)."""
        return self.heuristic.check_column(table, col, verbose) and self.llm.check_column(
            table, col, verbose
        )
