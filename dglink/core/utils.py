"""
Utility functions for core DGLink functionality
"""

from dglink import NodeSet, EdgeSet
from dglink.core.constants import RESOURCE_PATH, RESOURCE_TYPES
import os.path


def load_graph(
    resource_path=RESOURCE_PATH, edge_name="edges.tsv", node_name="nodes.tsv"
):
    """
    read in a knowledge graph as a Node and Edge set.
    """
    node_set = NodeSet()
    edge_set = EdgeSet()

    node_set.load_node_set(os.path.join(resource_path, node_name))
    edge_set.load_edge_set(os.path.join(resource_path, edge_name))
    return node_set, edge_set


def write_graph(
    node_set: NodeSet,
    edge_set: EdgeSet,
    resource_path=RESOURCE_PATH,
    edge_name="edges.tsv",
    node_name="nodes.tsv",
    source_filter: bool = False,
    strict: bool = False,
    source_name: str = None,
    mixed: bool = False,
):
    """
    Write a graph represented as a Node and Edge set to Neo4j compatible tsv files.
    """
    os.makedirs(resource_path, exist_ok=True)
    if source_filter:
        ns, es = get_graph_for_source(
            node_set=node_set, edge_set=edge_set, source_name=source_name, strict=strict
        )
        ns.write_node_set(os.path.join(resource_path, f"nodes_{source_name}.tsv"))
        es.write_edge_set(os.path.join(resource_path, f"edges_{source_name}.tsv"))
    elif mixed:
        ns, es = get_graph_for_source(node_set=node_set, edge_set=edge_set, mixed=True)
        ns.write_node_set(os.path.join(resource_path, "nodes_mixed.tsv"))
        es.write_edge_set(os.path.join(resource_path, "edges_mixed.tsv"))

    else:
        node_set.write_node_set(os.path.join(resource_path, node_name))
        edge_set.write_edge_set(os.path.join(resource_path, edge_name))
    ## save all nodes and edges from multiple sources


def filter_edge_set(edge_set: EdgeSet, filter_for: str):
    """filter out edges of a certain type"""
    filtered_edge_set = EdgeSet()
    for edge_id in edge_set.edges:
        edge = edge_set.edges[edge_id]
        if edge[":TYPE"] != filter_for:
            filtered_edge_set.edges[edge_id] = edge
    filtered_edge_set.write_edge_set(os.path.join(RESOURCE_PATH, "edges.tsv"))
    return filtered_edge_set


def get_graph_for_source(
    node_set: NodeSet,
    edge_set: EdgeSet,
    source_name: str = None,
    strict: bool = True,
    mixed: bool = False,
):
    filter_node_set = NodeSet()
    filter_edge_set = EdgeSet()
    ## get resource set for a specific source
    if not mixed:
        for node_id in node_set.nodes:
            add = True
            node = node_set.nodes[node_id]
            if strict and len(node["source:string[]"]) > 1:
                add = False
            elif source_name not in node["source:string[]"]:
                add = False
            if add:
                filter_node_set.nodes[node_id] = node_set.nodes[node_id]
        for edge_id in edge_set.edges:
            add = True
            edge = edge_set.edges[edge_id]
            if strict and len(edge["source:string[]"]) > 1:
                add = False
            elif source_name not in edge["source:string[]"]:
                add = False
            if add:
                filter_edge_set.edges[edge_id] = edge_set.edges[edge_id]
        return filter_node_set, filter_edge_set
    ## get resource sets from mixed sources
    for node_id in node_set.nodes:
        node = node_set.nodes[node_id]
        if len(node["source:string[]"]) > 1:
            filter_node_set.nodes[node_id] = node_set.nodes[node_id]
    for edge_id in edge_set.edges:
        edge = edge_set.edges[edge_id]
        if len(edge["source:string[]"]) > 1:
            filter_edge_set.edges[edge_id] = edge_set.edges[edge_id]
    return filter_node_set, filter_edge_set


def write_artifacts(
    node_set: NodeSet,
    edge_set: EdgeSet,
    resource_types: list = RESOURCE_TYPES,
    resource_path: str = RESOURCE_PATH,
):
    """get artifacts (ie the resource sets for each resource type) from a graph for a given set of resource types"""
    ## get the strict version of each resource type
    for resource_type in resource_types:
        write_graph(
            node_set=node_set,
            edge_set=edge_set,
            source_filter=True,
            strict=True,
            source_name=resource_type,
            resource_path=os.path.join(resource_path, "artifacts"),
        )
    ## write out the mixed types
    write_graph(
        node_set=node_set,
        edge_set=edge_set,
        mixed=True,
        resource_path=os.path.join(resource_path, "artifacts"),
    )


def write_graph_and_artifacts_default(
    node_set: NodeSet,
    edge_set: EdgeSet,
    resource_types: list = RESOURCE_TYPES,
    resource_path: str = RESOURCE_PATH,
    node_name: str = "nodes.tsv",
    edge_name: str = "edges.tsv",
):
    """default way to write graph and and sub-graphs split by source type"""
    write_graph(
        node_set=node_set,
        edge_set=edge_set,
        resource_path=resource_path,
        node_name=node_name,
        edge_name=edge_name,
    )
    write_artifacts(
        node_set=node_set,
        edge_set=edge_set,
        resource_types=resource_types,
        resource_path=resource_path,
    )


def merge_resource_sets(
    artifacts_path: str = os.path.join(RESOURCE_PATH, "artifacts"),
    write_resource: bool = True,
):
    """merges all resource sets saved at a given path"""
    resource_files = os.listdir(artifacts_path)
    node_sets = filter(lambda x: x.startswith("nodes"), resource_files)
    edge_sets = filter(lambda x: x.startswith("edges"), resource_files)
    full_node_set = NodeSet()
    full_edge_set = EdgeSet()
    for node_path in node_sets:
        node_set = NodeSet()
        node_set.load_node_set(os.path.join(artifacts_path, node_path))
        for node_id in node_set.nodes:
            if node_id not in full_node_set.nodes:
                full_node_set.update_nodes(node_set.nodes[node_id])
    for edge_path in edge_sets:
        edge_set = EdgeSet()
        edge_set.load_edge_set(os.path.join(artifacts_path, edge_path))
        for edge_id in edge_set.edges:
            if edge_id not in full_edge_set.edges:
                full_edge_set.update_edges(edge_set.edges[edge_id])
    if write_resource:
        write_graph(node_set=full_node_set, edge_set=full_edge_set)
    return full_node_set, full_edge_set
