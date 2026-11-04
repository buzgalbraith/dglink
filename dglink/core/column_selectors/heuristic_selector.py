"""
Select entity columns using heuristics
"""
from .column_selector import ColumnSelector, TabularDataset

import logging

logger = logging.getLogger(__name__)


class HeuristicSelector(ColumnSelector):
    name = "heuristic_selector"

    def __init__(self, nan_percentage: float = 0.1, max_entity_types: int = 8) -> None:
        """
        nan_percentage: a column is rejected if at most this proportion of its rows were grounded (default: 0.1)
        max_entity_types: a column is rejected if it has more than this many distinct entity types (default: 8)
        """
        super().__init__()
        self.nan_percentage = nan_percentage
        self.max_entity_types = max_entity_types

    def execute(self, table: TabularDataset, verbose: bool = False, columns: list | None = None) -> None:
        """Remove low-quality or overly heterogeneous grounded columns, mutating `table` in place.

        A column is rejected if:
        1. at most `nan_percentage` of rows were successfully grounded, or
        2. it contains more than `max_entity_types` distinct entity types.
        """
        starting_cols = self._resolve_columns(table, columns)
        keep, drop = [], []
        for col in starting_cols:
            (keep if self.check_column(table, col) else drop).append(col)
        self._apply_selection(table, keep=keep, drop=drop)
        if verbose:
            self._log_selection(starting_cols, table)

    def check_column(self, table: TabularDataset, col: str, verbose: bool = False) -> bool:
        """Check if a single column contains entities"""
        n_rows = len(table.table)
        if n_rows == 0:
            is_entity = False
        else:
            too_many_types = table.table[f"{col}_type"].nunique() > self.max_entity_types
            too_few_grounded = table.table[f"{col}_name"].count() / n_rows <= self.nan_percentage
            is_entity = not (too_many_types or too_few_grounded)
        if verbose:
            logger.info(f"{col} is_entity = {is_entity}")
        return is_entity
