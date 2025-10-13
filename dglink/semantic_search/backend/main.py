from fastapi import FastAPI
from neo4j import GraphDatabase
import os
import pygtrie
import pandas

app = FastAPI()


driver = GraphDatabase.driver(
    "bolt://neo-4j:7687",
    auth=(os.environ.get("NEO4J_URI"), os.environ.get("NEO4J_PASSWORD")),
)

## get the prefix sets

entity_types = ["entity", "project", "publication", "tool"]
edge_types = ["edges", "publication", "tool", "related_edges_gl"]
entity_prefix_set = pygtrie.PrefixSet()
edge_prefix_set = pygtrie.PrefixSet()
names_mapping = dict()
for entity_type in entity_types:
    node_path = f"/app/resources/{entity_type}_nodes.tsv"
    if os.path.exists(node_path):
        df = pandas.read_csv(node_path, sep="\t")
        name_check = "name" in df.columns
        grounded_name_check = "grounded_entity_name" in df.columns
        entity_prefix_set = entity_prefix_set | pygtrie.PrefixSet(
            df["curie:ID"].astype(str)
        )
        if grounded_name_check:
            entity_prefix_set = entity_prefix_set | pygtrie.PrefixSet(
                df["grounded_entity_name"].dropna()
            )
        if name_check:
            entity_prefix_set = entity_prefix_set | pygtrie.PrefixSet(
                df["name"].dropna()
            )
        for _, row in df.iterrows():
            curie = row["curie:ID"]
            names_mapping[curie] = curie
            if grounded_name_check:
                names_mapping[row["grounded_entity_name"]] = curie
            if name_check:
                names_mapping[row["name"]] = curie


for edge_type in edge_types:
    edge_path = (
        f"/app/resources/{edge_type}_edges.tsv"
        if edge_type not in ["edges", "related_edges_gl"]
        else f"/app/resources/{edge_type}.tsv"
    )
    if os.path.exists(edge_path):
        df = pandas.read_csv(edge_path, sep="\t")
        edge_prefix_set = edge_prefix_set | pygtrie.PrefixSet(df[":TYPE"])


# driver = GraphDatabase.driver('bolt://localhost:7687', )
@app.get("/query")
def query_dispatch(
    agent: str,
    relation: str = None,
    other_agent: str = None,
    query_type: str = "Subject",
):
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
def Autocomplete(query: str, completion_type: str, k: int = 5):
    if completion_type != "relation":
        res = ["".join(x) for x in entity_prefix_set.iter(prefix=query)][:k]
    else:
        res = ["".join(x) for x in edge_prefix_set.iter(prefix=query)][:k]
    return {"suggestions": res}
