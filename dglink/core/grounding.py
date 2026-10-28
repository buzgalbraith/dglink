"""Ground free-text biomedical terms (e.g. a primary diagnosis) to ontology identifiers.

Shared by every portal's diagnosis parser so grounded disease concepts merge across
portals. Uses `gilda.annotate` (not `ground`) so messy multi-part strings still resolve —
`ground` needs the whole string to match, so e.g. "Papillary transitional cell carcinoma,
non-invasive" fails, whereas `annotate` finds the grounded span within it. Among the
grounded spans we keep the one covering the *longest* substring (the most specific
concept, not a generic sub-token like "carcinoma") above a score threshold; otherwise the
caller falls back to a portal-local id.
"""

import re

import gilda
from bioregistry import normalize_curie, get_bioregistry_iri
from indra.ontology.bio import bio_ontology

from dglink.core.constants import map_biolink_category

GROUNDING_SCORE_THRESHOLD = 0.5
DEFAULT_BIOLINK_CATEGORY = "biolink:NamedThing"


def slugify(name: str) -> str:
    """Lower-case, punctuation-collapsed slug of a name, for keying ungrounded nodes by
    name so duplicates that share a name (e.g. "Not Reported") collapse to one id."""
    return (
        re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_") or "unknown"
    )


def _best_match(text: str, score_threshold: float, min_span_fraction: float):
    """Best gilda match for `text`, or None.

    First tries to ground the whole string with `gilda.ground` (the most specific match);
    if that fails, falls back to `gilda.annotate` and keeps the match on the longest span
    within the string, provided that span covers at least `min_span_fraction` of the text
    (so "xyzzy unknown disease" does not ground to "disease"). Either way only matches
    at/above `score_threshold` are accepted.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    ## 1) prefer a grounding of the entire string
    full = gilda.ground(text)
    if full and full[0].score >= score_threshold:
        return full[0]

    ## 2) fall back to the longest grounded span within the string
    best_match, best_span = None, -1
    for annotation in gilda.annotate(text):
        if not annotation.matches:
            continue
        top = annotation.matches[0]  # gilda returns matches best-score-first
        span = len(annotation.text)
        if top.score >= score_threshold and span > best_span:
            best_span, best_match = span, top
    if best_match is None or best_span < min_span_fraction * len(text.strip()):
        return None
    return best_match


def ground_term(text: str, score_threshold: float = GROUNDING_SCORE_THRESHOLD) -> tuple:
    """Return a (normalized_name, curie, iri) triple for `text`.

    curie/iri are None when `text` is empty or nothing grounds, so callers can detect
    failure and fall back to a portal-local id. See `_best_match` for the matching rules.
    """
    match = _best_match(text, score_threshold, min_span_fraction=0.0)
    if match is None:
        return text, None, None
    term = match.term
    return (
        term.entry_name,
        normalize_curie(f"{term.db}:{term.id}"),
        get_bioregistry_iri(term.db, term.id),
    )


def ground_entity(
    text: str,
    score_threshold: float = GROUNDING_SCORE_THRESHOLD,
    min_span_fraction: float = 0.0,
) -> tuple:
    """Return a (normalized_name, curie, iri, biolink_category) tuple for `text`.

    Like `ground_term`, but also types the grounding (INDRA type mapped to a Biolink
    category) and can reject partial matches covering less than `min_span_fraction` of
    the text. curie/iri/category are None when nothing grounds.
    """
    match = _best_match(text, score_threshold, min_span_fraction)
    if match is None:
        return text, None, None, None
    term = match.term
    curie = normalize_curie(f"{term.db}:{term.id}")
    category = map_biolink_category(bio_ontology.get_type(term.db, term.id), curie)
    ## INDRA has no type for some terms, and unknown types come back unmapped
    if not category or not category.startswith("biolink:"):
        category = DEFAULT_BIOLINK_CATEGORY
    return term.entry_name, curie, get_bioregistry_iri(term.db, term.id), category
