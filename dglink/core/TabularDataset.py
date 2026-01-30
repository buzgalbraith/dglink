"""
Class for holding a tabular dataset and meta information during processing
"""
from pathlib import Path
import pandas

class TabularDataset():
    entity_columns:list[str] = NotImplemented

    def __init__(self, dataset_path:Path, sheet_name:str, table:pandas.DataFrame) -> None:
        self.dataset_path = dataset_path
        self.sheet_name = sheet_name
        self.table = table
        self.original_columns = table.columns.to_list()
