"""Make values safe to write into the neo4j-admin import TSVs."""

import math
import re

## tabs / newlines would split a row or a column, other control and invisible characters
## (NUL, zero-width spaces, BOMs, unicode line separators) corrupt or hide text
_UNSAFE_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f ​-‍  ﻿]")
_WHITESPACE = re.compile(r"\s+")


def clean_tsv_text(val, array_item: bool = False) -> str:
    """Return `val` as a single-line string that cannot break a TSV row.

    Unsafe characters become spaces and runs of whitespace collapse to one space. Double
    quotes become single quotes, since neo4j-admin import reads `"` as a quote character.
    For items of a `string[]` column (`array_item`), `;` (the array delimiter) becomes `,`.
    None and NaN become "".
    """
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    text = _UNSAFE_CHARS.sub(" ", str(val)).replace('"', "'")
    if array_item:
        text = text.replace(";", ",")
    return _WHITESPACE.sub(" ", text).strip()
