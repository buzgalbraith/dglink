# DGLink

DGLink introduces semantic interoperability within data portals through automated metadata extraction and knowledge graph construction. DGLink connects data semantically within a data portal and maps data to external knowledge to enable knowledge-driven data interpretation and discovery.

## Applications

1. MCP: A chat interface that connects to a Neo4j database using the Model Context Protocol (MCP). It supports both OpenAI (GPT) and Anthropic (Claude) models with real-time streaming responses and markdown rendering.

1. Semantic search: Run semantic queries on the knowledge graph via a simple to use web-UI.

1. Genomic search index: Query for transcripts within the portal's FastQ files using a [Mantis](https://github.com/splatlab/mantis) sequence-search index, with hits linked back to the knowledge graph.

## Bringing up the applications
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

## Genomic Search Index

Build a [Mantis](https://github.com/splatlab/mantis) sequence-search index over the FastQ files in the NF Data Portal, then query it for transcripts of interest. Hits are linked back to the knowledge graph served from Neo4j.

### Building the index

The index is built in a Docker container that pulls the FastQ files, builds the Squeakr count structures, and assembles the Mantis index:

```
bash scripts/genomic_index/build_index.sh
```

This writes the index to `dglink/applications/genomic_index/mantis_index`.

### Querying the index via the command line

Pass a FASTA file of query transcripts (defaults to `input_txns.fa`):

```
bash scripts/genomic_index/query_index.sh [query_file.fa]
```

### Bringing up the query service
The index can also be queried via a web-UI which can be brought up by running 
1. Go into the genomic index directory with `cd dglink/applications/genomic_index`
2. Bring up the service (building images if required) with `docker compose up --build`
3. Connect to the services.

### Accessing the genomic index service
- **Frontend UI**: http://localhost:5001
- **Backend API**: http://localhost:8001
- **Neo4j Browser**: http://localhost:7474
