from fastapi import FastAPI
from neo4j import GraphDatabase
import os 
app = FastAPI()


driver = GraphDatabase.driver('bolt://neo-4j:7687', auth=(os.environ.get('NEO4J_URI'), os.environ.get('NEO4J_PASSWORD')))

@app.get("/query")
def query_dispatch(agent:str,relation:str=None, other_agent:str = None, query_type:str = 'Subject'):
    if query_type == 'Subject':
        res = subject_search(agent=agent, relation = relation, other_agent=other_agent)
    elif query_type == 'Object':
        res = object_search(agent=agent, relation = relation, other_agent=other_agent)
    else:
        subjects = subject_search(agent=agent, relation = relation, other_agent=other_agent)
        objects = object_search(agent=agent, relation = relation, other_agent=other_agent)
        res = subjects + objects
    return {"message": res}
    
def subject_search(agent: str = "syn52740594" , relation:str = None, other_agent:str = None):
    relation_query = f'r:{relation}' if relation else 'r'
    other_agent_query = f"AND e.curie = '{other_agent}'"  if other_agent else ''
    records, _, _ = driver.execute_query(f"""
        MATCH (p)-[{relation_query}]->(e)
        WHERE p.curie = '{agent}' {other_agent_query}
        RETURN p.curie as subject, r as relation, e.curie as object
        """,
        database_="neo4j",
    )
    res = []
    for record in records:
        res.append((record.data()['subject'],record.data()['relation'][1], record.data()['object'] ))
    return res

def object_search(agent: str = "syn52740594" , relation:str = None, other_agent:str = None):
    relation_query = f'r:{relation}' if relation else 'r'
    other_agent_query = f"AND p.curie = '{other_agent}'"  if other_agent else ''
    records, _, _ = driver.execute_query(f"""
        MATCH (p)-[{relation_query}]->(e)
        WHERE e.curie = '{agent}' {other_agent_query}
        RETURN p.curie as subject, r as relation, e.curie as object
        """,
        database_="neo4j",
    )
    res = []
    for record in records:
        res.append((record.data()['subject'],record.data()['relation'][1], record.data()['object'] ))
    return res