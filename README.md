# DGLink

DGLink introduces semantic interoperability within data portals through automated metadata extraction and knowledge graph construction. DGLink connects data semantically within a data portal and maps data to external knowledge to enable knowledge-driven data interpretation and discovery.

## Applications

1. MCP: Leverage This application provides a chat interface that connects to a Neo4j database using the Model Context Protocol (MCP). It supports both OpenAI (GPT) and Anthropic (Claude) models with real-time streaming responses and markdown rendering.

2. Semantic search: Run semantic queries on the knowledge graph via a simple to use web-UI.

## Brining up both applications 
- `cd dglink/applications`
- `docker compose up --build`
## MCP Application - LLM Chat Interface with Neo4j
### Features
- **MCP Integration**: Direct access to Neo4j database through Model Context Protocol
- **Real-time Streaming**: Responses stream in real-time as they're generated
- **Dual Model Support**: Switch between Anthropic Claude and OpenAI GPT models
### Prerequisites

- Docker and Docker Compose installed
- API keys for OpenAI and/or Anthropic.
	- Anthropic API key should be stored in the `ANTHROPIC_API_KEY` environmental variable
	- OpenAI API key should be stored in the `OPENAI_API_KEY` environmental variable 
### Bringing up the MCP service
- cd `dglink/applications/mcp`
- `docker compose up --build`
### Accessing the MCP service
- **Frontend UI**: http://localhost:5000
- **Backend API**: http://localhost:8000
- **Neo4j Browser**: http://localhost:7474

## Semantic Search Web UI

### Bringing up the MCP service
1. Go into the semantic search directory with `cd dglink/applications/semantic_search`

2. Bring up the service (and build images if required with) `docker-compose up --build`

3. Connect to the services.
### Connecting to the semantic search service
- semantic search UI [http://localhost:5001/](http://localhost:5001/)
