from fastapi import FastAPI
from neo4j import GraphDatabase
import os

app = FastAPI()


driver = GraphDatabase.driver(
    "bolt://neo-4j:7687",
    auth=(os.environ.get("NEO4J_URI"), os.environ.get("NEO4J_PASSWORD")),
)


# driver = GraphDatabase.driver('bolt://localhost:7687', )
@app.get("/query")
def query_dispatch(
    agent: str,
    relation: str = None,
    other_agent: str = None,
    query_type: str = "Subject",
):
    if query_type == "Subject":
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


def subject_search(
    agent: str = "syn52740594", relation: str = None, other_agent: str = None
):
    relation_query = f"r:{relation}" if relation else "r"
    other_agent_query = f"AND e.curie = '{other_agent}'" if other_agent else ""
    records, _, _ = driver.execute_query(
        f"""
        MATCH (p)-[{relation_query}]->(e)
        WHERE p.curie = '{agent}' {other_agent_query}
        RETURN p.curie as subject, p as subject_whole, r as relation, e.curie as object, e as object_whole
        """,
        database_="neo4j",
    )
    res = []
    for record in records:
        object_whole = record.data()["object_whole"]
        subject_whole = record.data()["subject_whole"]
        del object_whole["curie"]
        del subject_whole["curie"]
        res.append(
            (
                f"Subject identifier : {record.data()['subject']}",
                f"subject attributes : {subject_whole}",
                f"Relation : {record.data()['relation'][1]}",
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
        RETURN p.curie as subject, p as subject_whole, r as relation, e.curie as object, e as object_whole
        """,
        database_="neo4j",
    )
    res = []
    for record in records:
        object_whole = record.data()["object_whole"]
        subject_whole = record.data()["subject_whole"]
        del object_whole["curie"]
        del subject_whole["curie"]
        res.append(
            (
                f"Subject identifier : {record.data()['subject']}",
                f"subject attributes : {subject_whole}",
                f"Relation : {record.data()['relation'][1]}",
                f"Object identifier : {record.data()['object']}",
                f"object attributes : {object_whole}",
            )
        )
    return res
