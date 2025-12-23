# DGLink
DGLink introduces semantic interoperability within data portals through automated metadata extraction and knowledge graph construction. DGLink connects data semantically within a data portal and maps data to external knowledge to enable knowledge-driven data interpretation and discovery.

## Structure 
1. `scripts` - Scripts for recreating KG and artifacts
1. `examples` - Example code, so far just the original proof of concept not using the package.
1. `dglink/core` - Core DGLink code, applicable for all portals. 
1. `dglink/portals` - Portal specific code. 
1. `dglink/applications` - Applications of KGs constructed with DGLink.
    1. `dglink/applications/semantic_search` - bring up web UI for semantic searching on the KG (see instructions bellow)
    1. `dglink/applications/project_similarity` - Leverage KG embedding methods for accessing project similarity (need to install additional dependencies with) `uv pip install ".[graph_embedding]"`
1. `dglink/resources` - data and container for brining up the Neo4j instance. 

## Steps for running semantic search UI
1. Go into the semantic search directory with `cd dglink/applications/semantic_search`
2. Bring up the service (and build images if required with) `docker-compose up --build`
3. Connect to the services. 
    - semantic search UI [http://localhost:5000/](http://localhost:5000/)
    - neo4j browser [http://localhost:7474/browser/](http://localhost:7474/browser/)
