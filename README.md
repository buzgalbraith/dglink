# DGLink
DGLink introducies semantic interoperability within data portals through automated metadata extraction and knowledge graph construction. DGLink connects data semantically within a data portal and maps data to external knowledge to enable knowledge-driven data interpretation and discovery.

## Structure 
1. `dglink/kg_construction` - for programmatically building the knowledge graph from Synapse data. 
1. `dglink/example` - reconstruct the basic example, we started with. 
1. `dglink/semantic_search` - bring up web UI for semantic searching on the KG (see instructions bellow)
1. `dglink/applications/project_similarity` - Leverage KG embedding methods for accessing project similarity (need to install additional dependencies with) `uv pip install ".[graph_embedding]"`
1. `dglink/resources` - data and code for brining up the Neo4j instance. 

## Steps for running semantic search UI
1. Go into the semantic search directory with `cd dglink/semantic_search`
2. Bring up the service (and build images if required with) `docker-compose up --build`
3. Connect to the services. 
    - semantic search UI [http://localhost:5000/](http://localhost:5000/)
    - neo4j browser [http://localhost:7474/browser/](http://localhost:7474/browser/)
