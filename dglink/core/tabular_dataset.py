"""
Class for holding a tabular dataset and meta information during processing
"""
from dglink.core.constants import INDRA_BIOLINK_EXPERIMENTAL_DATA_TYPE_MAP
from pathlib import Path
import pandas
from numpy.random import default_rng
from typing import Any
from functools import lru_cache
from indra.ontology.bio import bio_ontology
from bioregistry import normalize_curie, get_bioregistry_iri
import gilda 
import logging 

logger = logging.getLogger(__name__)

TERM_EXCLUSION_LIST = ["yes", "na", "large", "std", "dead"]
COLUMN_EXCLUSION_LIST = ["Vendor"]

class TabularDataset():
    entity_columns:list[str] = NotImplemented
    def __init__(self, dataset_path:Path, sheet_name:str, table:pandas.DataFrame, terms_to_exclude:list[str]=TERM_EXCLUSION_LIST, columns_to_exclude:list[str] = COLUMN_EXCLUSION_LIST, seed:int = 101, ) -> None:
        self.dataset_path = dataset_path
        self.sheet_name = sheet_name
        self.table = table
        self.terms_to_exclude = terms_to_exclude
        self.columns_to_exclude = [x.lower() for x in columns_to_exclude]
        self.original_columns, self.dropped_columns = self._check_column_names()
        self.seed = seed
        self.biolink_entity_types = False ## initialized as false, but set as true if table grounded with this 
        self._rng = default_rng(seed=self.seed)
        self._priority_weights : dict[Any, float] | None = None
        self._table_frequencies : dict[Any, float] | None = None
        self._precomputed_sample : list[tuple[Any, float]] | None = None

    def _check_column_names(self):
        """checks a tables column values and drops any in the self.columns_to_exclude stores the rest in a list"""
        original_cols, dropped_columns = [], []
        for col in self.table.columns:
            if col.lower() in self.columns_to_exclude:
                dropped_columns.append(col)
            else:
                original_cols.append(col)
        if len(dropped_columns) > 0:
            logger.warning(f"Removing {dropped_columns} as they are in columns_to_exclude = {self.columns_to_exclude}")
            self.table.drop(columns=dropped_columns, inplace=True)
        return original_cols, dropped_columns
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
        unique_entries = set(self.table[f"{col}_raw_text"].unique())
        sample_size = min(target_size, len(unique_entries))
        for key, _ in self._precomputed_sample: 
            if key in unique_entries:
                col_sample.append(key)
                if len(col_sample) >= sample_size:
                    break  
        return col_sample
    def ground_table(self, biolink_entity_types:bool = False):
        """Ground the table using gilda"""
        self.table = self.table.apply(self._apply_ground, axis=1)
        if biolink_entity_types:
            self.biolink_entity_types = True
            type_cols = [f'{x}_type' for x in self.original_columns]
            self.table[type_cols] = self.table[type_cols].map(lambda x: INDRA_BIOLINK_EXPERIMENTAL_DATA_TYPE_MAP.get(x, x))

    def _apply_ground(self, row):
        """Apply entity grounding to all columns in a DataFrame row.

        Transforms a row of raw text values into grounded entity information by calling
        cached_annotate on each cell. Creates new columns with suffixes: _entity, _type,
        _name, _raw_text, _column_name, _iri.

        Args:
            row: pandas Series representing one row of the DataFrame

        Returns:
            pandas Series with grounded entity information for all columns

        Note:
            This function is designed to be used with DataFrame.apply(axis=1)
        """
        result = {}
        for col in row.index:
            (
                result[f"{col}_entity"],
                result[f"{col}_type"],
                result[f"{col}_name"],
                result[f"{col}_raw_text"],
                result[f"{col}_column_name"],
                result[f"{col}_iri"],
            ) = self._cached_annotate(row[col], col)
        return pandas.Series(result)

    @lru_cache(maxsize=None)
    def _cached_annotate(self, val, col):
        """Ground a cell value to biomedical ontology terms using Gilda (cached).

        Uses Gilda to identify biomedical entities in text and normalizes them to
        standard ontology terms. Results are cached to avoid redundant API calls.

        Args:
            val: Cell value to ground (will be converted to string)
            col: Column name for tracking provenance

        Returns:
            Tuple of (curie, entity_type, name, raw_text, column_name, iri)
            Returns tuple of pandas.NA values if grounding fails or value is null

        Note:
            Uses INDRA bio_ontology for entity typing and bioregistry for IRI generation.
            Only the top-ranked Gilda match is used.
        """
        if pandas.notna(val):
            ans = gilda.annotate(str(val))
            if ans:
                nsid = ans[0].matches[0].term
                if nsid.norm_text in self.terms_to_exclude:
                    return pandas.NA, pandas.NA, pandas.NA, val, col, pandas.NA
                else:
                    return (
                        normalize_curie(f"{nsid.db}:{nsid.id}"),
                        bio_ontology.get_type(nsid.db, nsid.id),
                        nsid.entry_name,
                        val,
                        col,
                        get_bioregistry_iri(nsid.db, nsid.id),
                    )
            else:
                return pandas.NA, pandas.NA, pandas.NA, val, col, pandas.NA
        return pandas.NA, pandas.NA, pandas.NA, pandas.NA, pandas.NA, pandas.NA
