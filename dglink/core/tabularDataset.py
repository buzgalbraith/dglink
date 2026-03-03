"""
Class for holding a tabular dataset and meta information during processing
"""
from pathlib import Path
import pandas
from numpy.random import default_rng
from typing import Any

class tabularDataset():
    entity_columns:list[str] = NotImplemented
    def __init__(self, dataset_path:Path, sheet_name:str, table:pandas.DataFrame, seed:int = 101) -> None:
        self.dataset_path = dataset_path
        self.sheet_name = sheet_name
        self.table = table
        self.original_columns = table.columns.to_list()
        self.seed = seed
        self._rng = default_rng(seed=self.seed)
        self._priority_weights : dict[Any, float] | None = None
        self._table_frequencies : dict[Any, float] | None = None
        self._precomputed_sample : list[tuple[Any, float]] | None = None
    def _build_table_frequencies(self):
        """Pre-compute frequency of each value across entire table - upfront"""
        self._table_frequencies = {}
        for col in self.table.columns:
            for val, count in self.table[col].value_counts().items():
                self._table_frequencies[val] = self._table_frequencies.get(val, 0) + count
    def _build_priority_weights(self):
        """Assign random weights to each unique value"""
        if self._table_frequencies is None:
            self._build_table_frequencies()
        assert isinstance(self._table_frequencies, dict)
        self._priority_weights = {}
        self._precomputed_sample = []
        for val in self._table_frequencies.keys():
            self._priority_weights[val] = self._rng.uniform()
            table_freq = self._table_frequencies.get(val, 1) ## assign frequency of one for missing values
            score = table_freq / self._priority_weights[val]
            self._precomputed_sample.append((val, score))
        self._precomputed_sample.sort(key=lambda x: x[1], reverse=True)

    def get_priority_sample(self, col: str, target_size: int)->list[Any]:
        """Returns a priority sample of a columns records weighted by frequency across the table.
        Adapted form Magneto by Liu et al https://arxiv.org/pdf/2412.08194
        Pre-computes sample across entire table for efficiency


        Parameters
        ----------
        col :str
            column name in the table
        target_size: int
            goal size of sample, Note: Will return the minimum of the target size and the number of unique column entries.
        
        Returns
        --------
        col_sample: list
            List of entity names to use for sample rows. 
        """
        if self._precomputed_sample is None:
            self._build_priority_weights()
        assert isinstance(self._precomputed_sample, list)   
        col_sample:list = []
        unique_entries = set(self.table[f"{col}_name"].unique())
        sample_size = min(target_size, len(unique_entries))
        for key, _ in self._precomputed_sample: 
            if key in unique_entries:
                col_sample.append(key)
                if len(col_sample) >= sample_size:
                    break  
        return col_sample
