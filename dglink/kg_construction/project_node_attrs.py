from nodes import NodeSet

study_base_url = (
    "https://nf.synapse.org/Explore/Studies/DetailsPage/StudyDetails?studyId"
)

project_nodes = NodeSet()
project_nodes.load_node_set(path="dglink/resources/project_nodes.tsv")

if "project_url" not in project_nodes.attributes:
    project_nodes.attributes = [x for x in project_nodes.attributes] + ["project_url"]

for node in project_nodes.nodes:
    project_nodes[node].attributes[
        "project_url"
    ] = f'{study_base_url}={node.removesuffix(":Wiki")}'


project_nodes.write_node_set("dglink/semantic_search/neo4j/project_nodes.tsv")
