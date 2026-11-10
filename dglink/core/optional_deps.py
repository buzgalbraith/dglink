"""
Helpers for importing dependencies that live in optional extras (see pyproject.toml).
"""

import importlib
from types import ModuleType


def import_optional(module: str, extra: str) -> ModuleType:
    """Import ``module``, or raise an ImportError naming the dglink extra that provides it.

    Only a missing ``module`` itself is translated; an ImportError raised from inside an
    installed package is re-raised unchanged so real breakage is not masked.
    """
    package = module.split(".")[0]
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name is None or e.name.split(".")[0] != package:
            raise
        raise ImportError(
            f"`{package}` is required for this feature but is not installed. "
            f"Install it with: pip install 'dglink[{extra}]'"
        ) from e
