"""
Base class and shared helpers for column selectors.

A column selector decides which grounded columns of a TabularDataset contain
biomedical entities. Selectors mutate the table in place: grounding columns of
rejected columns are dropped and `table.entity_columns` is set to the kept columns.
"""
from abc import ABC, abstractmethod
import logging

from ...core.tabular_dataset import GROUNDING_SUFFIXES, TabularDataset

logger = logging.getLogger(__name__)


def grounding_columns(col: str) -> list[str]:
    """All grounding-derived column names for an original column."""
    return [f"{col}_{suffix}" for suffix in GROUNDING_SUFFIXES]


class ColumnSelector(ABC):
    name: str = NotImplemented

    @abstractmethod
    def execute(self, table: TabularDataset, verbose: bool = False, columns: list | None = None) -> None:
        """Select entity columns, mutating `table` in place.

        Parameters:
            table: table to process
            verbose: if to show log info
            columns (optional): list of columns to check. If not given will use original columns
        """

    @abstractmethod
    def check_column(self, table: TabularDataset, col: str, verbose: bool = False) -> bool:
        """Check if a single column contains entities"""

    @staticmethod
    def _resolve_columns(table: TabularDataset, columns: list | None) -> list:
        return list(columns) if columns is not None else list(table.original_columns)

    @staticmethod
    def _apply_selection(table: TabularDataset, keep: list[str], drop: list[str]) -> None:
        """Drop grounding columns of rejected columns and record the kept entity columns."""
        cols_to_drop = [c for col in drop for c in grounding_columns(col)]
        table.table.drop(columns=cols_to_drop, inplace=True)
        table.entity_columns = keep

    @staticmethod
    def _log_selection(starting_cols: list, table: TabularDataset) -> None:
        logger.info(f"Has {len(starting_cols)} which are {starting_cols}")
        logger.info(f"Selected {len(table.entity_columns)} which are {table.entity_columns}")
        logger.info("-" * 50)
