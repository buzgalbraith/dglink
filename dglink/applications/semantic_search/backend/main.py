from fastapi import FastAPI
from neo4j import GraphDatabase
import os
import pygtrie
import pandas
from indra.databases import bioregistry_client
from urllib.parse import quote

app = FastAPI()


driver = GraphDatabase.driver(
    "bolt://neo-4j:7687",
    auth=(os.environ.get("NEO4J_URI"), os.environ.get("NEO4J_PASSWORD")),
)



def load_prefix_sets(nodes_df, edges_df):
    """load the prefix sets of nodes and edges for auto-complete"""
    ## load node prefix set 
    node_prefix_set = pygtrie.PrefixSet()
    ## add curie and name to node prefix set 
    node_prefix_set = node_prefix_set | pygtrie.PrefixSet(nodes_df["curie:ID"].astype(str))
    node_prefix_set = node_prefix_set | pygtrie.PrefixSet(
                    nodes_df["name"].dropna()
    )
    # load edge prefix set 
    edge_prefix_set = pygtrie.PrefixSet()
    edges_df = pandas.read_csv(f"/app/resources/edges.tsv", sep="\t")
    edge_prefix_set = edge_prefix_set | pygtrie.PrefixSet(edges_df[":TYPE"])
    return node_prefix_set, edge_prefix_set

def load_mappings(nodes_df, edges_df):
    """get mapping from entity name to curie (and inverse) as well as a list of projects to their disease focus"""
    ## get name mappings
    names_mapping = {}
    for _, row in nodes_df.iterrows():
        curie = row["curie:ID"]
        names_mapping[curie] = curie
        names_mapping[row["name"]] = curie
    inverse_names_mapping = {names_mapping[key]: key for key in names_mapping}
    ## get project to disease focus
    project_to_disease_focus = {}
    disease_focus_df = edges_df[edges_df[":TYPE"] == "has_diseaseFocus"].drop_duplicates()
    for _, row in disease_focus_df.iterrows():
        if row.iloc[0] not in project_to_disease_focus:
            project_to_disease_focus[row.iloc[0]] = ["", ""]
        if row.iloc[1].startswith("mesh"):
            project_to_disease_focus[row.iloc[0]][0] = row.iloc[1]
        else:
            project_to_disease_focus[row.iloc[0]][1] = row.iloc[1]
    return names_mapping, inverse_names_mapping, project_to_disease_focus

def get_no_context_indra_url(curie):
    get_indra_url = (
        lambda db, id: f"https://discovery.indra.bio/search/?agent_tuple=[%22{db}%22,%22{db}:{id}%22]"
    )
    split_curie = curie.split(":", maxsplit=1)
    if len(split_curie) < 2:
        return None
    db, id = bioregistry_client.get_ns_id_from_bioregistry_curie(curie)
    if id is None:
        return None
    id = id.split(":")[-1]
    return get_indra_url(db, id)


def get_url_with_context_indra_url(curie, project_curie):
    get_indra_url = (
        lambda db, id, mesh_id: f"https://discovery.indra.bio/search/?agent_tuple=[%22{db}%22,%22{db}:{id}%22]&mesh_tuple=[%22MESH%22,%22{mesh_id}%22]"
    )
    split_curie = curie.split(":", maxsplit=1)
    if len(split_curie) < 2:
        return None
    db, id = bioregistry_client.get_ns_id_from_bioregistry_curie(curie)
    if id is None:
        return None
    id = id.split(":")[-1]
    project_curie = project_curie.removesuffix(":Wiki")
    project_disease_focus = project_to_disease_focus.get(project_curie, "")

    if project_disease_focus == "":
        return None
    mesh_id = project_disease_focus[0].split(":", maxsplit=1)
    if len(mesh_id) < 2:
        return None
    return (
        get_indra_url(db, id, mesh_id=mesh_id[1]),
        project_to_disease_focus[project_curie][1],
    )


def add_indra_url_no_context(record, object_whole, subject_whole):
    subject_curie = record.data()["subject"]
    subject_indra_url = get_no_context_indra_url(curie=subject_curie)
    if subject_indra_url is not None:
        subject_whole["Subject literature evidence"] = subject_indra_url
    object_curie = record.data()["object"]
    object_indra_url = get_no_context_indra_url(curie=object_curie)
    if object_indra_url is not None:
        object_whole["Object literature evidence"] = object_indra_url
    return subject_whole, object_whole


def add_indra_url_with_context(record, object_whole, subject_whole):
    subject_curie = record.data()["subject"]
    object_curie = record.data()["object"]
    if subject_curie.startswith("syn"):
        context_url = get_url_with_context_indra_url(
            curie=object_curie, project_curie=subject_curie
        )
        if context_url is not None:
            object_whole[f"Object {context_url[1]} context literature evidence"] = (
                context_url[0]
            )
    elif object_curie.startswith("syn"):
        context_url = get_url_with_context_indra_url(
            curie=subject_curie, project_curie=object_curie
        )
        if context_url is not None:
            subject_whole[f"Subject {context_url[1]} context literature evidence"] = (
                context_url[0]
            )
    return subject_whole, object_whole


# driver = GraphDatabase.driver('bolt://localhost:7687', )
@app.get("/query")
def query_dispatch(
    agent: str,
    relation: str = None,
    other_agent: str = None,
    query_type: str = "Subject",
):
    agent = agent.split(", ", maxsplit=1)[-1]
    other_agent = other_agent.split(", ", maxsplit=1)[-1]
    if agent in names_mapping:
        agent = names_mapping[agent]
    if other_agent in names_mapping:
        other_agent = names_mapping[other_agent]
    if agent == "" and relation != "":
        res = relation_search(relation=relation)
    elif query_type == "Subject":
        res = subject_search(agent=agent, relation=relation, other_agent=other_agent)
    elif query_type == "Object":
        res = object_search(agent=agent, relation=relation, other_agent=other_agent)
    else:
        subjects = subject_search(
            agent=agent, relation=relation, other_agent=other_agent
        )
        objects = object_search(agent=agent, relation=relation, other_agent=other_agent)
        res = subjects + objects
    return {"message": res}


def relation_search(relation: str = None):
    records, _, _ = driver.execute_query(
        f"""
        MATCH (p)-[r:{relation}]->(e)
        RETURN p.curie as subject, p as subject_whole, r as relation, properties(r) as whole_relation, e.curie as object, e as object_whole
        """,
        database_="neo4j",
    )
    res = []
    for record in records:
        object_whole = {
            f"Object {key}": record.data()["object_whole"][key]
            for key in record.data()["object_whole"]
        }
        subject_whole = {
            f"Subject {key}": record.data()["subject_whole"][key]
            for key in record.data()["subject_whole"]
        }
        relation_whole = {
            f"Relation {key}": record.data()["whole_relation"][key]
            for key in record.data()["whole_relation"]
        }
        subject_whole, object_whole = add_indra_url_no_context(
            record=record, object_whole=object_whole, subject_whole=subject_whole
        )
        subject_whole, object_whole = add_indra_url_with_context(
            record=record, object_whole=object_whole, subject_whole=subject_whole
        )
        del subject_whole["Subject curie"]
        del object_whole["Object curie"]
        res.append(
            (
                f"Subject identifier : {record.data()['subject']}",
                f"subject attributes : {subject_whole}",
                f"Relation : {record.data()['relation'][1]}",
                f"Relation attributes : {relation_whole}",
                f"Object identifier : {record.data()['object']}",
                f"object attributes : {object_whole}",
            )
        )
    return res


def subject_search(
    agent: str = "syn52740594", relation: str = None, other_agent: str = None
):
    relation_query = f"r:{relation}" if relation else "r"
    other_agent_query = f"AND e.curie = '{other_agent}'" if other_agent else ""
    records, _, _ = driver.execute_query(
        f"""
        MATCH (p)-[{relation_query}]->(e)
        WHERE p.curie = '{agent}' {other_agent_query}
        RETURN p.curie as subject, p as subject_whole, r as relation, properties(r) as whole_relation, e.curie as object, e as object_whole
        """,
        database_="neo4j",
    )
    res = []
    for record in records:
        object_whole = {
            f"Object {key}": record.data()["object_whole"][key]
            for key in record.data()["object_whole"]
        }
        subject_whole = {
            f"Subject {key}": record.data()["subject_whole"][key]
            for key in record.data()["subject_whole"]
        }
        relation_whole = {
            f"Relation {key}": record.data()["whole_relation"][key]
            for key in record.data()["whole_relation"]
        }

        del subject_whole["Subject curie"]
        del object_whole["Object curie"]
        subject_whole, object_whole = add_indra_url_no_context(
            record=record, object_whole=object_whole, subject_whole=subject_whole
        )
        subject_whole, object_whole = add_indra_url_with_context(
            record=record, object_whole=object_whole, subject_whole=subject_whole
        )
        res.append(
            (
                f"Subject identifier : {record.data()['subject']}",
                f"subject attributes : {subject_whole}",
                f"Relation : {record.data()['relation'][1]}",
                f"Relation attributes : {relation_whole}",
                f"Object identifier : {record.data()['object']}",
                f"object attributes : {object_whole}",
            )
        )
    return res


def object_search(
    agent: str = "syn52740594", relation: str = None, other_agent: str = None
):
    relation_query = f"r:{relation}" if relation else "r"
    other_agent_query = f"AND p.curie = '{other_agent}'" if other_agent else ""
    records, _, _ = driver.execute_query(
        f"""
        MATCH (p)-[{relation_query}]->(e)
        WHERE e.curie = '{agent}' {other_agent_query}
        RETURN p.curie as subject, p as subject_whole, r as relation, properties(r) as whole_relation, e.curie as object, e as object_whole
        """,
        database_="neo4j",
    )
    res = []
    for record in records:
        object_whole = {
            f"Object {key}": record.data()["object_whole"][key]
            for key in record.data()["object_whole"]
        }
        subject_whole = {
            f"Subject {key}": record.data()["subject_whole"][key]
            for key in record.data()["subject_whole"]
        }
        relation_whole = {
            f"Relation {key}": record.data()["whole_relation"][key]
            for key in record.data()["whole_relation"]
        }
        subject_whole, object_whole = add_indra_url_no_context(
            record=record, object_whole=object_whole, subject_whole=subject_whole
        )
        subject_whole, object_whole = add_indra_url_with_context(
            record=record, object_whole=object_whole, subject_whole=subject_whole
        )
        del subject_whole["Subject curie"]
        del object_whole["Object curie"]
        res.append(
            (
                f"Subject identifier : {record.data()['subject']}",
                f"subject attributes : {subject_whole}",
                f"Relation : {record.data()['relation'][1]}",
                f"Object identifier : {record.data()['object']}",
                f"Relation attributes : {relation_whole}",
                f"object attributes : {object_whole}",
            )
        )
    return res


@app.get("/autoComplete")
def Autocomplete(query: str, completion_type: str, k: int = 100):
    if completion_type != "relation":
        res = ["".join(x) for x in node_prefix_set.iter(prefix=query)][:k]
        if len(res) > 0:
            ret = []
            for x in res:
                if x != names_mapping[x]:
                    ret.append(f"{x}, {names_mapping[x]}")
                elif x != inverse_names_mapping[x]:
                    ret.append(f"{x}, {inverse_names_mapping[x]}")
                else:
                    ret.append(x)
            res = ret
    else:
        res = ["".join(x) for x in edge_prefix_set.iter(prefix=query)][:k]
    return {"suggestions": res}



## read in the graph as data frame.
nodes_df = pandas.read_csv(f"/app/resources/nodes.tsv", sep="\t")
edges_df = pandas.read_csv(f"/app/resources/edges.tsv", sep="\t")
node_prefix_set, edge_prefix_set = load_prefix_sets(nodes_df, edges_df)
names_mapping, inverse_names_mapping, project_to_disease_focus = load_mappings(nodes_df, edges_df)