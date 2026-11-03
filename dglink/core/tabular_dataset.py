"""
Class for holding a tabular dataset and meta information during processing
"""

from dglink.core.constants import map_biolink_category
from pathlib import Path
import pandas
from numpy.random import default_rng
from typing import Any
from dglink.core.grounding import annotate_text
import logging
import re

logger = logging.getLogger(__name__)

TERM_EXCLUSION_LIST = ["yes", "na", "large", "std", "dead"]
COLUMN_EXCLUSION_LIST = ["Vendor"]

_HEX_ESCAPE_RE = re.compile(r"\\x([0-9a-fA-F]{2})")
_SPACE_SUBSTITUTE_RE = re.compile(r"[_~]+")


def normalize_for_grounding(text: str) -> str:
    """Undo VCF/ClinVar-style space substitution so Gilda can tokenize values  e.g. 'Raine~syndrome' -> 'Raine syndrome'."""
    text = _HEX_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
    text = _SPACE_SUBSTITUTE_RE.sub(" ", text)
    return text.strip()


class TabularDataset:
    entity_columns: list[str] = NotImplemented

    def __init__(
        self,
        dataset_path: Path,
        sheet_name: str,
        table: pandas.DataFrame,
        terms_to_exclude: list[str] = TERM_EXCLUSION_LIST,
        columns_to_exclude: list[str] = COLUMN_EXCLUSION_LIST,
        seed: int = 101,
    ) -> None:
        self.dataset_path = dataset_path
        self.sheet_name = sheet_name
        self.table = table
        self.terms_to_exclude = terms_to_exclude
        self.columns_to_exclude = [x.lower() for x in columns_to_exclude]
        self.original_columns, self.dropped_columns = self._check_column_names()
        self.seed = seed
        self.biolink_entity_types = (
            False  ## initialized as false, but set as true if table grounded with this
        )
        self._rng = default_rng(seed=self.seed)
        self._priority_weights: dict[Any, float] | None = None
        self._table_frequencies: dict[Any, float] | None = None
        self._precomputed_sample: list[tuple[Any, float]] | None = None

    def _check_column_names(self):
        """checks a tables column values and drops any in the self.columns_to_exclude stores the rest in a list"""
        original_cols, dropped_columns = [], []
        for col in self.table.columns:
            if col.lower() in self.columns_to_exclude:
                dropped_columns.append(col)
            else:
                original_cols.append(col)
        if len(dropped_columns) > 0:
            logger.warning(
                f"Removing {dropped_columns} as they are in columns_to_exclude = {self.columns_to_exclude}"
            )
            self.table.drop(columns=dropped_columns, inplace=True)
        return original_cols, dropped_columns

    def _build_table_frequencies(self):
        """Pre-compute frequency of each value across entire table - upfront"""
        self._table_frequencies = {}
        for col in self.table.columns:
            for val, count in self.table[col].value_counts().items():
                self._table_frequencies[val] = (
                    self._table_frequencies.get(val, 0) + count
                )

    def _build_priority_weights(self):
        """Assign random weights to each unique value"""
        if self._table_frequencies is None:
            self._build_table_frequencies()
        assert isinstance(self._table_frequencies, dict)
        self._priority_weights = {}
        self._precomputed_sample = []
        for val in self._table_frequencies.keys():
            self._priority_weights[val] = self._rng.uniform()
            table_freq = self._table_frequencies.get(
                val, 1
            )  ## assign frequency of one for missing values
            score = table_freq / self._priority_weights[val]
            self._precomputed_sample.append((val, score))
        self._precomputed_sample.sort(key=lambda x: x[1], reverse=True)

    def get_priority_sample(self, col: str, target_size: int) -> list[Any]:
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
        col_sample: list = []
        unique_entries = set(self.table[f"{col}_raw_text"].unique())
        sample_size = min(target_size, len(unique_entries))
        for key, _ in self._precomputed_sample:
            if key in unique_entries:
                col_sample.append(key)
                if len(col_sample) >= sample_size:
                    break
        return col_sample

    def ground_table(self, biolink_entity_types: bool = False):
        """Ground the table using gilda.

        Replaces each column `col` with six columns (GROUNDING_SUFFIXES): `col_entity`,
        `col_type`, `col_name`, `col_raw_text`, `col_column_name` and `col_iri`. Each
        distinct value of a column is grounded once (`_ground_value`), and the gilda lookup
        itself is cached across columns and tables (`annotate_text`).
        """
        grounded = {}
        for col in self.table.columns:
            values = self.table[col]
            ## distinct text in this column -> its grounding. Keyed by the text, since
            ## e.g. 1, 1.0 and True compare equal but are different text.
            column_groundings = {}
            cells = []
            for val in values:
                if pandas.isna(val):
                    cells.append(_MISSING_CELL)
                    continue
                text = str(val)
                if text not in column_groundings:
                    column_groundings[text] = self._ground_value(text)
                curie, entity_type, name, iri = column_groundings[text]
                cells.append((curie, entity_type, name, val, col, iri))
            fields = list(zip(*cells)) if cells else [()] * len(GROUNDING_SUFFIXES)
            for suffix, field in zip(GROUNDING_SUFFIXES, fields):
                grounded[f"{col}_{suffix}"] = pandas.Series(field, index=values.index, dtype=object)
        self.table = pandas.DataFrame(grounded, index=self.table.index)
        ## map back to biolink if desired
        if biolink_entity_types:
            self.biolink_entity_types = True
            for col in self.original_columns:
                type_col, entity_col = f"{col}_type", f"{col}_entity"
                self.table[type_col] = [
                    map_biolink_category(t, e)
                    for t, e in zip(self.table[type_col], self.table[entity_col])
                ]

    def _ground_value(self, text: str) -> tuple:
        """Ground a (non-missing) cell's text with Gilda (see `annotate_text`).

        Returns:
            Tuple of (curie, entity_type, name, iri); all pandas.NA if the text does not
            ground or its match is one of this table's `terms_to_exclude`.
        """
        grounding = annotate_text(normalize_for_grounding(text))
        if grounding is None or grounding.norm_text in self.terms_to_exclude:
            return pandas.NA, pandas.NA, pandas.NA, pandas.NA
        return grounding.curie, grounding.entity_type, grounding.name, grounding.iri


## suffixes of the columns ground_table makes from each column, in order
GROUNDING_SUFFIXES = ("entity", "type", "name", "raw_text", "column_name", "iri")
_MISSING_CELL = (pandas.NA,) * len(GROUNDING_SUFFIXES)
