"""
Select entity columns using heuristics
"""
from .columnSelector import columnSelector, pandas, TabularDataset


import logging
logger = logging.getLogger(__name__)


class heuristicSelector(columnSelector):
    name = 'heuristic_selector'
    
    def __init__(self, nan_percentage:float = 0.1, max_entity_types:int = 8) -> None:
        """
        nan_percentage: Minimum proportion of non-null values required to keep column (default: 0.1)
        max_types: Maximum number of distinct entity types allowed per column (default: 5)
        """
        super().__init__()
        self.nan_percentage = nan_percentage
        self.max_entity_types = max_entity_types
    
    def execute(self, table:TabularDataset, verbose:bool = False):
        """Filter grounded entity table.table to remove low-quality or overly heterogeneous columns based on heuristics

        Applies two quality filters:
        1. Removes columns where fewer than nan_percentage of rows were successfully grounded
        2. Removes columns containing more than max_types distinct entity types (too heterogeneous)

        Args:
            table.table: table.table with grounded entity columns (entity, type, name, raw_text, column_name, iri)
            base_cols: List of original column names before grounding suffixes were added

        Returns:
            Tuple of (filtered table.table, filtered list of base column names)

        """
        ## filter out columns with more than some set number of max entity types
        cols_to_drop = []
        entity_cols = []
        for col in table.original_columns:
            if (table.table[f"{col}_type"].nunique() > self.max_entity_types) or (
                table.table[f"{col}_name"].count() / len(table.table) <= self.nan_percentage
            ):
                cols_to_drop.extend(
                    [
                        f"{col}_type",
                        f"{col}_entity",
                        f"{col}_name",
                        f"{col}_raw_text",
                        f"{col}_column_name",
                        f"{col}_iri",
                    ]
                )
            else:
                entity_cols.append(col)
        if verbose:
            logger.info(f'Has {len(table.original_columns)} which are {table.original_columns}')
            logger.info(f'Selected {len(entity_cols)} which are {entity_cols}')
            logger.info(f'-'*50)
        table.table.drop(columns=cols_to_drop, inplace=True)
        table.entity_columns = entity_cols

    def check_column(self, table:TabularDataset, col:str, verbose:bool = False)->bool:
        """Check if a single column contains entities"""

        not_entity = (table.table[f"{col}_type"].nunique() > self.max_entity_types) or (
                table.table[f"{col}_name"].count() / len(table.table) <= self.nan_percentage
            )
        is_entity = not not_entity
        if verbose:
            logger.info(f"{col} is_entity = {is_entity}")
        return is_entity