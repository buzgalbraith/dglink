"""
NF research tools (cell lines, animal models, antibodies, genetic reagents, ...) from the NF
tools db, as Biolink nodes linked to their diseases, species, genes, investigators, and to
the studies and publications that use them.
"""

from dglink import NodeSet, EdgeSet, write_graph
from dglink.core import _is_empty
from dglink.core.constants import RESOURCE_PATH, map_biolink_category
from .constants import syn, NF_KG_SCHEMA, NF_CURIE_PREFIX, NF_DEFAULT_BIOLINK_CATEGORY, \
    NF_TOOLS_TABLE, NF_FILES_VIEW, TOOLS_PUBLICATIONS_TABLE, TOOL_PUBLICATION_TABLES, \
    NF_TOOL_PROPERTIES, NF_TOOL_ID_COLUMNS, NF_TOOL_EDGE_COLUMNS, NF_TOOL_DROPPED_COLUMNS, \
    NF_TOOL_TYPE_TO_BIOLINK, NF_TOOL_DISEASE_FIELDS, NF_TOOL_MODEL_TYPES, \
    NF_SPECIES_TO_TAXON, NF_TOOL_SPECIES_HEAD, NF_TOOL_GENE_FIELDS, NF_GENE_CATEGORIES, \
    NF_UNGROUNDED_GENE_CATEGORY, NF_TOOL_AGENT_FIELDS, NF_TOOL_STUDY_FIELDS
from .publications import publication_curie
from .utils import nf_curie, parse_dict_fields, _unpack_dict_list, meta_node_curie

from bioregistry import get_bioregistry_iri, normalize_curie
from indra.ontology.bio import bio_ontology
import gilda

from functools import lru_cache
import re
import tqdm
import os
import logging

logger = logging.getLogger(__name__)

## gene grounding: gene / protein namespaces only, so "NF1" never grounds to the disease
GENE_NAMESPACES = ["HGNC", "UP", "MGI", "RGD"]
GENE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*")
HUMAN_TAXON = "9606"


def get_tools(
    node_set: NodeSet, edge_set: EdgeSet, project_ids: list, write_set: bool = False
):
    """add every NF tool and its edges (see get_tool_nodes, get_tool_edges and
    get_tool_publication_edges). Run after get_projects and get_publications, whose study
    and publication nodes the tool edges point at."""
    logger.info("Getting nodes for NF Data Portal tools")
    node_set, edge_set, name_to_curie, resource_to_curie = get_tool_nodes(node_set=node_set, edge_set=edge_set)
    logger.info("Linking studies to the tools named in their file annotations")
    edge_set = get_tool_edges(
        project_ids=project_ids, edge_set=edge_set, name_to_curie=name_to_curie
    )
    logger.info("Linking NF Data Portal tools to publications")
    edge_set = get_tool_publication_edges(
        node_set=node_set, edge_set=edge_set, resource_to_curie=resource_to_curie
    )
    if write_set:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name="tools",
            resource_path=os.path.join(RESOURCE_PATH, "artifacts"),
        )
    return node_set, edge_set


## --- tool nodes -------------------------------------------------------------------

def tool_curie(row: dict) -> str:
    """the id a tool node gets: its normalized RRID (e.g. rrid:CVCL_1150), else its tools db
    resourceId under the nfdataportal prefix."""
    rrid = row.get("rrid")
    if not _is_empty(rrid):
        curie = normalize_curie(str(rrid).strip())
        if curie:
            return curie
        logger.warning(f"tool {row.get('resourceId')} has an unparseable RRID {rrid!r}")
    return nf_curie(f"tool_{row['resourceId']}")


def _tool_property(value, attribute: str):
    """a tools view value as a node attribute value: a set for string[] columns, and whole
    numbers (e.g. an age of 56.0) without the trailing .0."""
    if attribute.endswith(":string[]"):
        values = value if isinstance(value, list) else [value]
        return {str(v) for v in values if not _is_empty(v)}
    if _is_empty(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return value


def get_tool_nodes(node_set: NodeSet, edge_set: EdgeSet):
    """returns the node and edge sets with all tools added, a mapping from any name (or
    synonym) to its curie, and a mapping from the tools db `resourceId` to its curie.
    Each tool is a node with
        - curie: normalized RRID, else nfdataportal:tool_<resourceId>
        - category: from its resourceType (NF_TOOL_TYPE_TO_BIOLINK), NamedThing otherwise
        - tool_type: the raw resourceType
        - the NF_TOOL_PROPERTIES columns as attributes
    and the edges from its own fields (see parse_tool_fields).
    """
    ## this table has all NF data portal tool meta data, it was generated from the programmatic export on the nf data portal website.
    query = syn.tableQuery(f"SELECT * FROM {NF_TOOLS_TABLE}")
    df = query.asDataFrame()
    ## flag view columns we do not know how to handle, so upstream schema changes are noticed
    known = set(NF_TOOL_PROPERTIES) | NF_TOOL_ID_COLUMNS | NF_TOOL_EDGE_COLUMNS | NF_TOOL_DROPPED_COLUMNS
    unknown = sorted(set(df.columns) - known)
    if unknown:
        logger.warning(f"tools view has columns that are not handled, skipping them: {unknown}")
    ## mapping from names (and synonyms) and resourceIds back to identifiers
    name_to_curies = dict()
    resource_to_curie = dict()
    for row in tqdm.tqdm(df.to_dict("records")):
        curie = tool_curie(row)
        category = NF_TOOL_TYPE_TO_BIOLINK.get(row["resourceType"], NF_DEFAULT_BIOLINK_CATEGORY)
        node_set.update_nodes(
            {
                "curie:ID": curie,
                ":LABEL": category,
                "raw_label": "tool",
                "name": row["resourceName"],
                "tool_type": row["resourceType"],
                "iri": None if curie.startswith(f"{NF_CURIE_PREFIX}:") else get_bioregistry_iri(*curie.split(":", 1)),
                "source:string[]": "tools",
                **{
                    attribute: _tool_property(row.get(column), attribute)
                    for column, attribute in NF_TOOL_PROPERTIES.items()
                },
            },
        )
        node_set, edge_set = parse_tool_fields(curie, category, row, node_set, edge_set)
        for name in {str(row["resourceName"]).strip()} | _tool_property(row.get("synonyms"), "synonyms:string[]"):
            name_to_curies.setdefault(name, set()).add(curie)
        resource_to_curie[row["resourceId"]] = curie
    ## a name shared by several tools (e.g. "NF1" is a synonym of many antibodies) says
    ## nothing about which one was used, so only names of a single tool are matched
    name_to_curie = {name: next(iter(c)) for name, c in name_to_curies.items() if len(c) == 1}
    logger.info(f"{len(name_to_curies) - len(name_to_curie)} tool names are shared by several tools and not matched")
    return node_set, edge_set, name_to_curie, resource_to_curie


## --- edges from a tool's own fields ---------------------------------------------------

def parse_tool_fields(tool: str, category: str, row: dict, node_set: NodeSet, edge_set: EdgeSet):
    """add the edges (and target nodes) from one tools view row:
        - model (biolink:CellLine, biolink:OrganismTaxon ...) - (biolink:model_of) -> disease
          (biolink:Disease ...) for geneticDisorder, manifestation and tumorType; other tools
          are related_to_at_instance_level their diseases
        - cell line - (biolink:in_taxon) -> species (biolink:OrganismTaxon)
        - animal model (biolink:OrganismTaxon) - (biolink:subclass_of) -> species
        - antibody / genetic reagent - (biolink:related_to_at_instance_level) -> gene
          (biolink:Gene, or biolink:Protein for non-human genes)
        - tool - (biolink:related_to_at_instance_level) -> investigator / institution
          (biolink:Agent); investigators get their ORCID id, shared with publication authors
    """
    node_set, edge_set = parse_dict_fields(
        meta_curie=tool,
        meta=row,
        node_types=NF_TOOL_DISEASE_FIELDS,
        source="tools",
        node_set=node_set,
        edge_set=edge_set,
        head="tool_model" if row["resourceType"] in NF_TOOL_MODEL_TYPES else "tool",
    )
    node_set, edge_set = parse_tool_species(tool, category, row, node_set, edge_set)
    node_set, edge_set = parse_tool_genes(tool, row, node_set, edge_set)
    node_set, edge_set = parse_dict_fields(
        meta_curie=tool,
        meta=row,
        node_types=NF_TOOL_AGENT_FIELDS,
        source="tools",
        node_set=node_set,
        edge_set=edge_set,
    )
    return node_set, edge_set


def _add_tool_edge(node_set: NodeSet, edge_set: EdgeSet, tool: str, head: str, field: str, raw: str, target: dict):
    """add a grounded node (`target`, without the shared fields) and the tool -> node edge."""
    node_set.update_nodes(
        {**target, "raw_label": field, "raw_texts:string[]": raw, "source:string[]": "tools"},
        fill_empty=True,
    )
    edge_set.update_edges(
        {
            ":START_ID": tool,
            ":END_ID": target["curie:ID"],
            ":TYPE": NF_KG_SCHEMA[(head, field)],
            "raw_type:string[]": field,
            "raw_texts:string[]": raw,
            "source:string[]": "tools",
        }
    )


def parse_tool_species(tool: str, category: str, row: dict, node_set: NodeSet, edge_set: EdgeSet):
    """link a tool to its species (NCBI taxon): cell lines with in_taxon, animal model strains
    with subclass_of, anything else with related_to_at_instance_level."""
    head = NF_TOOL_SPECIES_HEAD.get(category, "tool")
    for species in _unpack_dict_list(row, "species"):
        if species not in NF_SPECIES_TO_TAXON:
            logger.warning(f"tool {tool}: species {species!r} is not in NF_SPECIES_TO_TAXON, skipping")
            continue
        taxon, name = NF_SPECIES_TO_TAXON[species]
        target = {
            "curie:ID": taxon,
            ":LABEL": "biolink:OrganismTaxon",
            "name": name,
            "iri": get_bioregistry_iri(*taxon.split(":", 1)),
            "grounded:boolean": "true",
        }
        _add_tool_edge(node_set, edge_set, tool, head, "species", species, target)
    return node_set, edge_set


def _taxon_id(species: str) -> str:
    """NCBI taxon id (e.g. "10090") for a tools view species, human if it is not mapped."""
    taxon = NF_SPECIES_TO_TAXON.get(species)
    return taxon[0].split(":", 1)[1] if taxon else HUMAN_TAXON


@lru_cache(maxsize=None)
def _ground_gene(text: str, taxon: str):
    """(name, curie, iri, category) of the first token of `text` that grounds to a gene or
    gene product of `taxon` (an NCBI taxon id), or None. Token by token, since the values
    wrap a symbol in notes ("NF1 (aa 2760 C-term)", "phospho-NF1", "sh1miR targeting NF1")."""
    for token in GENE_TOKEN.findall(text):
        matches = gilda.ground(token, organisms=[taxon], namespaces=GENE_NAMESPACES)
        if not matches or matches[0].score < 0.5:
            continue
        term = matches[0].term
        curie = normalize_curie(f"{term.db}:{term.id}")
        category = map_biolink_category(bio_ontology.get_type(term.db, term.id), curie)
        if category in NF_GENE_CATEGORIES:
            return term.entry_name, curie, get_bioregistry_iri(term.db, term.id), category
    return None


def parse_tool_genes(tool: str, row: dict, node_set: NodeSet, edge_set: EdgeSet):
    """link a tool to the genes in NF_TOOL_GENE_FIELDS (antibody targets, plasmid inserts),
    grounded for the species the field names (human if none)."""
    for field, species_field in NF_TOOL_GENE_FIELDS.items():
        taxa = [_taxon_id(s) for s in _unpack_dict_list(row, species_field)] if species_field else [HUMAN_TAXON]
        for value in _unpack_dict_list(row, field):
            for taxon in taxa:
                grounding = _ground_gene(value, taxon)
                if grounding is None:
                    logger.debug(f"tool {tool}: {field} {value!r} did not ground to a gene, keeping it as a node")
                    target = {
                        "curie:ID": meta_node_curie("gene", value),
                        ":LABEL": NF_UNGROUNDED_GENE_CATEGORY,
                        "name": value,
                        "iri": None,
                        "grounded:boolean": "false",
                    }
                else:
                    name, curie, iri, category = grounding
                    target = {"curie:ID": curie, ":LABEL": category, "name": name, "iri": iri, "grounded:boolean": "true"}
                _add_tool_edge(node_set, edge_set, tool, "tool", field, value, target)
    return node_set, edge_set


## --- study -> tool edges --------------------------------------------------------------

def _file_values(value) -> list:
    """the values of a file annotation: a list as is, a string split on commas (e.g.
    modelSystemName "90-8TL,S462"), anything else none."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if not _is_empty(v)]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def get_tool_edges(project_ids: list, name_to_curie: dict, edge_set: EdgeSet):
    """link studies to the tools their files come from: a file whose modelSystemName,
    specimenID or individualID is exactly the name (or a synonym) of a single tool. One
    grouped query over the portal file view, keeping only studies in `project_ids`.
    Adds: study (biolink:Study) - (biolink:related_to_at_instance_level) -> tool, with the
    matching annotation field(s) as raw_type.
    """
    fields = ", ".join(NF_TOOL_STUDY_FIELDS)
    query = syn.tableQuery(f"SELECT studyId, {fields} FROM {NF_FILES_VIEW} GROUP BY studyId, {fields}")
    projects = set(project_ids)
    for row in query.asDataFrame().to_dict("records"):
        study = row.get("studyId")
        if study not in projects:
            continue
        for field in NF_TOOL_STUDY_FIELDS:
            for value in _file_values(row.get(field)):
                tool = name_to_curie.get(value)
                if tool is None:
                    continue
                edge_set.update_edges(
                    {
                        ":START_ID": study,
                        ":END_ID": tool,
                        ":TYPE": NF_KG_SCHEMA[("Project", "tool")],
                        "raw_type:string[]": field,
                        "raw_texts:string[]": value,
                        "source:string[]": "tools",
                    }
                )
    return edge_set


## --- publication -> tool edges --------------------------------------------------------

def get_tool_publication_edges(node_set: NodeSet, edge_set: EdgeSet, resource_to_curie: dict):
    """link tools to the publications that used or developed them, from the tools db Usage and
    Development tables. Only publications already in `node_set` are linked, so run
    `get_publications` first (it adds every tools db publication).
    Adds: publication (biolink:Publication) - (biolink:mentions) -> tool
    """
    pubs = syn.tableQuery(f"SELECT publicationId, pmid, doi FROM {TOOLS_PUBLICATIONS_TABLE}").asDataFrame()
    pub_to_curie = {
        row["publicationId"]: publication_curie(row) for row in pubs.to_dict("records")
    }
    for raw_type, table_id in TOOL_PUBLICATION_TABLES.items():
        links = syn.tableQuery(f"SELECT resourceId, publicationId FROM {table_id}").asDataFrame()
        n_linked = 0
        for row in links.itertuples():
            tool = resource_to_curie.get(row.resourceId)
            pub = pub_to_curie.get(row.publicationId)
            if tool is None or pub is None or pub not in node_set.nodes:
                continue
            edge_set.update_edges(
                {
                    ":START_ID": pub,
                    ":END_ID": tool,
                    ":TYPE": NF_KG_SCHEMA[("publication", "tool")],
                    "raw_type:string[]": raw_type,
                    "source:string[]": "tools",
                }
            )
            n_linked += 1
        logger.info(f"linked {n_linked} of {len(links)} tool {raw_type} rows to publications in the graph")
    return edge_set
