# MCP Application - LLM Chat Interface with Neo4j

This application provides a chat interface that connects to a Neo4j database using the Model Context Protocol (MCP). It supports both OpenAI (GPT) and Anthropic (Claude) models with real-time streaming responses and markdown rendering.

## Features

- **Real-time Streaming**: Responses stream in real-time as they're generated
- **Markdown Rendering**: Full markdown support including:
  - Bold (**text**) and italic (*text*)
  - Bullet points and numbered lists
  - Code blocks with syntax highlighting
  - Headers and blockquotes
- **Dual Model Support**: Switch between Anthropic Claude and OpenAI GPT models
- **MCP Integration**: Direct access to Neo4j database through Model Context Protocol
- **Clean UI**: Modern, responsive chat interface

## Architecture

The application consists of three Docker services:

1. **neo-4j**: Neo4j graph database with pre-loaded data
2. **backend**: FastAPI server with MCP integration for Neo4j queries
3. **frontend**: Flask web interface for chat interactions

## Prerequisites

- Docker and Docker Compose installed
- API keys for OpenAI and/or Anthropic

## Environment Setup

Create a `.env` file in the `dglink/applications/mcp/` directory with your API keys:

```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

You need at least one API key for the application to work. Both can be provided to enable switching between models.

## Starting the Application

From the `dglink/applications/mcp/` directory, run:

```bash
docker compose up --build
```

This will:
1. Build and start the Neo4j database with pre-loaded graph data
2. Build and start the FastAPI backend server
3. Build and start the Flask frontend server

## Accessing the Application

Once all services are running:

- **Frontend UI**: http://localhost:5000
- **Backend API**: http://localhost:8000
- **Neo4j Browser**: http://localhost:7474

Default Neo4j credentials:
- Username: `neo4j`
- Password: `password`

## Using the Chat Interface

1. Open http://localhost:5000 in your browser
2. Select your preferred model provider (Anthropic/Claude or OpenAI/GPT) from the dropdown
3. Type your question about the Neo4j database
4. The assistant will use MCP tools to query the database and provide answers

## Backend API Endpoints

### POST /chat
Send a chat message to the assistant.

Request body:
```json
{
  "message": "What nodes are in the database?",
  "provider": "openai"  // or "anthropic"
}
```

### GET /health
Check the health and readiness of the backend service.

Response:
```json
{
  "status": "healthy",
  "openai_agent_ready": true,
  "anthropic_agent_ready": true,
  "mcp_connected": true
}
```

## Architecture Details

### Backend (FastAPI)
- Located in `backend/main.py`
- **Anthropic Integration**: Uses native Anthropic SDK with direct MCP client session
  - Implements streaming API with real-time token delivery
  - Manual tool calling loop for MCP integration
  - Model: Claude Sonnet 4 (claude-sonnet-4-20250514)
- **OpenAI Integration**: Uses `openai-agents` library with MCP server integration
  - Agent-based architecture with MCP server connection
  - Model: GPT-4o
- Both integrations connect to the same Neo4j MCP server
- Streams responses back to the frontend via FastAPI StreamingResponse

### Frontend (Flask)
- Located in `frontend/app.py` and `templates/index.html`
- Clean, modern chat interface with model selector
- Real-time streaming using fetch API with ReadableStream
- Markdown rendering with marked.js library
- Auto-scrolling and responsive design

### Neo4j Database
- Pre-loaded with graph data from `neo4j/graph/`
- Accessible via MCP tools in the backend
- Uses the `mcp-neo4j-cypher` MCP server

## Troubleshooting

### Backend fails to start
- Check that your API keys are set in the `.env` file
- Verify Neo4j is running: `docker compose logs neo-4j`
- Check backend logs: `docker compose logs backend`

### Frontend can't connect to backend
- Verify backend is running: `curl http://localhost:8000/health`
- Check frontend logs: `docker compose logs frontend`

### MCP connection issues
- The backend needs `uvx` to run the MCP server
- Check that the Neo4j service is accessible from the backend container
- Verify Neo4j credentials match in all services

## Stopping the Application

```bash
docker compose down
```

To remove volumes and start fresh:

```bash
docker compose down -v
```

## Development

### Local Development Without Docker

If you want to run services locally for development:

1. Start Neo4j locally on port 7687
2. Update environment variables to point to `localhost`
3. Run backend: `cd backend && uvicorn main:app --reload`
4. Run frontend: `cd frontend && python app.py`

### Customizing the Agents

Edit the agent instructions in `backend/main.py`:

```python
openai_agent = Agent(
    name="Assistant",
    model='gpt-4o',
    instructions="Your custom instructions here",
    mcp_servers=[mcp],
)
```

## Scripts Reference

The backend implementation is based on:
- `scripts/anthropic_mcd.py` - Anthropic agent setup with MCP
- `scripts/openai_mdc.py` - OpenAI agent setup with MCP

These scripts demonstrate the core MCP integration pattern used in the application.
