"""
Biolink-model conformance validation for a dglink graph.

Checks that every node ``:LABEL`` is a concrete (instantiable) Biolink category and
that every edge ``:TYPE`` is a valid Biolink predicate, using the Biolink Model
Toolkit (``bmt``).

Run as a script against a graph directory::

    python -m dglink.core.validate_biolink dglink/resources/graph
"""

from collections import Counter
from functools import lru_cache
from importlib.resources import files
import re
import sys

import bmt

## pinned in pyproject.toml; the schema is read from the installed biolink-model
## package rather than bmt's default (an older release fetched from GitHub)
BIOLINK_MODEL_VERSION = "4.4.3"
BIOLINK_PREDICATE_MAP_URL = (
    "https://raw.githubusercontent.com/biolink/biolink-model/"
    f"v{BIOLINK_MODEL_VERSION}/predicate_mapping.yaml"
)


@lru_cache(maxsize=1)
def _toolkit() -> "bmt.Toolkit":
    schema = files("biolink_model.schema").joinpath("biolink_model.yaml")
    toolkit = bmt.Toolkit(schema=str(schema), predicate_map=BIOLINK_PREDICATE_MAP_URL)
    if toolkit.get_model_version() != BIOLINK_MODEL_VERSION:
        raise RuntimeError(
            f"installed biolink-model is {toolkit.get_model_version()}, expected {BIOLINK_MODEL_VERSION}"
        )
    return toolkit


def _candidate_names(label: str):
    """Yield plausible Biolink element names for a raw :LABEL / :TYPE value.

    Handles the ``biolink:`` prefix and both PascalCase (``MaterialSample``) and
    snake_case (``derives_from``) spellings by offering spaced variants that
    ``bmt`` resolves against class/slot names.
    """
    name = label.split(":", 1)[-1] if ":" in label else label
    name = name.strip()
    seen = set()
    for cand in (
        name,
        name.replace("_", " "),
        re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).lower(),  # PascalCase -> spaced
    ):
        cand = cand.strip()
        if cand and cand not in seen:
            seen.add(cand)
            yield cand


@lru_cache(maxsize=4096)
def is_valid_category(label: str) -> bool:
    """True if ``label`` resolves to a concrete, instantiable Biolink category."""
    t = _toolkit()
    for cand in _candidate_names(label):
        el = t.get_element(cand)
        if el is None:
            continue
        # a category must exist, be a class category, and not be a mixin/abstract
        if (
            t.is_category(cand)
            and not getattr(el, "mixin", False)
            and not getattr(el, "abstract", False)
        ):
            return True
    return False


@lru_cache(maxsize=4096)
def is_valid_predicate(type_: str) -> bool:
    """True if ``type_`` resolves to a valid, non-abstract/non-mixin Biolink predicate."""
    t = _toolkit()
    for cand in _candidate_names(type_):
        el = t.get_element(cand)
        if el is None:
            continue
        if (
            t.is_predicate(cand)
            and not getattr(el, "mixin", False)
            and not getattr(el, "abstract", False)
        ):
            return True
    return False


def validate_node_set(node_set) -> dict:
    """Return the set of node ``:LABEL`` values that are not valid Biolink categories."""
    bad = Counter()
    for node in node_set.nodes.values():
        label = node.get(":LABEL", "")
        if not is_valid_category(label):
            bad[label] += 1
    return dict(bad)


def validate_edge_set(edge_set) -> dict:
    """Return the set of edge ``:TYPE`` values that are not valid Biolink predicates."""
    bad = Counter()
    for edge in edge_set.edges.values():
        type_ = edge.get(":TYPE", "")
        if not is_valid_predicate(type_):
            bad[type_] += 1
    return dict(bad)


def validate_graph(node_set, edge_set) -> dict:
    """Validate a NodeSet/EdgeSet pair. Returns a report dict.

    ``conformant`` is True only when no node label and no edge type violates the
    Biolink model.
    """
    bad_labels = validate_node_set(node_set)
    bad_types = validate_edge_set(edge_set)
    return {
        "biolink_version": _toolkit().get_model_version(),
        "n_nodes": len(node_set),
        "n_edges": len(edge_set),
        "invalid_node_labels": bad_labels,
        "invalid_edge_types": bad_types,
        "conformant": not bad_labels and not bad_types,
    }


def _print_report(report: dict) -> None:
    print(f"Biolink model version: {report['biolink_version']}")
    print(f"nodes: {report['n_nodes']:,}   edges: {report['n_edges']:,}")
    if report["invalid_node_labels"]:
        print("\nINVALID node :LABEL values (count):")
        for label, n in sorted(
            report["invalid_node_labels"].items(), key=lambda kv: -kv[1]
        ):
            print(f"  {n:>10,}  {label!r}")
    else:
        print("\nAll node labels are valid Biolink categories. ✓")
    if report["invalid_edge_types"]:
        print("\nINVALID edge :TYPE values (count):")
        for type_, n in sorted(
            report["invalid_edge_types"].items(), key=lambda kv: -kv[1]
        ):
            print(f"  {n:>10,}  {type_!r}")
    else:
        print("All edge types are valid Biolink predicates. ✓")
    print(f"\nCONFORMANT: {report['conformant']}")


def main(argv=None) -> int:
    from dglink.core.utils import load_graph

    argv = argv if argv is not None else sys.argv[1:]
    resource_path = argv[0] if argv else "dglink/resources/graph"
    node_set, edge_set = load_graph(resource_path=resource_path)
    report = validate_graph(node_set, edge_set)
    _print_report(report)
    return 0 if report["conformant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
