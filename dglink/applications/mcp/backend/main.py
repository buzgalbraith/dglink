from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import os
from typing import Optional
from contextlib import AsyncExitStack
import textwrap
# OpenAI imports
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

# Anthropic imports
from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://neo-4j:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')
NEO4J_DATABASE = os.getenv('NEO4J_DATABASE', 'neo4j')


# config variable 
PORTAL_NAME= os.getenv('PORTAL_NAME', 'NF Data Portal')
MAX_TURNS = int(os.getenv('MAX_TURNS', '50'))
ABBREVIATED_RESPONSE = os.getenv('ABBREVIATED_RESPONSE', '0')
abbreviated = bool(int(ABBREVIATED_RESPONSE))
# Global variables
openai_mcp = None
openai_agent = None
anthropic_client = None
anthropic_session = None
anthropic_exit_stack = None

class ChatRequest(BaseModel):
    message: str
    provider: str = "openai"

def get_base_prompt():
    base_prompt = textwrap.dedent(f"""
        You are a helpful scientist with access to a Neo4j database of content containing biomedical entities, studies, and datasets from the {PORTAL_NAME}.
        Use the Neo4j database and your scientific knowledge to answer the users questions. 
        Try to answer the user query directly with out going to far off track
            """
        ).strip()
    if abbreviated:
        base_prompt+= textwrap.dedent(f"""
                    Rules:
                    - Answer the user's question directly and concisely.  
                    - Do not explain what you are about to do before doing it.
                    - Do not summarize or restate the question.
                    - Do not add closing remarks like "I hope this helps" or "Let me know if you need more."
                    - If the answer requires data from the graph, query it and report only the relevant results.
                    - If you cannot answer from the graph, say so briefly.

                """).strip()
    print(f'USING abbreviated={abbreviated} for responses!!!!!!')
    print(f"BASE prompt:\n{base_prompt}")
    return base_prompt

async def initialize_openai():
    """Initialize OpenAI agent with MCP"""
    global openai_mcp, openai_agent

    if not OPENAI_API_KEY:
        print("Warning: OPENAI_API_KEY not set, OpenAI agent disabled")
        return

    try:
        # Create the MCP server for OpenAI
        openai_mcp = MCPServerStdio(
            params={
                "command": "uvx",
                "args": ["--with", "fastmcp<2.3.0" ,"mcp-neo4j-cypher@latest"],
                "env": {
                    "NEO4J_URI": NEO4J_URI,
                    "NEO4J_USERNAME": NEO4J_USER,
                    "NEO4J_PASSWORD": NEO4J_PASSWORD,
                    "NEO4J_DATABASE": NEO4J_DATABASE
                }
            }
        )

        # Connect to the server
        await openai_mcp.connect()
        print("OpenAI MCP server connected!")

        # Wait for initialization
        await asyncio.sleep(2)
        base_prompt = get_base_prompt()
        # Create OpenAI agent
        openai_agent = Agent(
            name="Assistant",
            model='gpt-5',
            instructions=base_prompt,
            mcp_servers=[openai_mcp],
        )
        print("OpenAI Agent (gpt-5-chat-latest) Ready!")
    except Exception as e:
        print(f"Error initializing OpenAI agent: {e}")

async def initialize_anthropic():
    """Initialize Anthropic client with MCP"""
    global anthropic_client, anthropic_session, anthropic_exit_stack

    if not ANTHROPIC_API_KEY:
        print("Warning: ANTHROPIC_API_KEY not set, Anthropic client disabled")
        return

    try:
        anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
        anthropic_exit_stack = AsyncExitStack()

        # Set up MCP connection for Anthropic
        server_params = StdioServerParameters(
            command="uvx",
            args=['--with' ,'fastmcp<2.3.0', "mcp-neo4j-cypher@latest"],
            env={
                "NEO4J_URI": NEO4J_URI,
                "NEO4J_USERNAME": NEO4J_USER,
                "NEO4J_PASSWORD": NEO4J_PASSWORD,
                "NEO4J_DATABASE": NEO4J_DATABASE,
            },
        )

        stdio_transport = await anthropic_exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        stdio, write = stdio_transport
        anthropic_session = await anthropic_exit_stack.enter_async_context(
            ClientSession(stdio, write)
        )

        await anthropic_session.initialize()

        # List available tools
        response = await anthropic_session.list_tools()
        tools = response.tools
        print(f"Anthropic MCP connected with tools: {[tool.name for tool in tools]}")
        print("Anthropic Client (Claude Sonnet 4) Ready!")
    except Exception as e:
        print(f"Error initializing Anthropic client: {e}")

async def initialize():
    """Initialize both OpenAI and Anthropic integrations"""
    print("=" * 60)
    print("Initializing MCP integrations...")
    print("=" * 60)

    # Initialize both in parallel
    await asyncio.gather(
        initialize_openai(),
        initialize_anthropic(),
        return_exceptions=True
    )

    print("=" * 60)
    print("Neo4j Query Assistant Ready!")
    print("=" * 60)

async def stream_anthropic_query(query: str):
    """Process and stream a query using Anthropic Claude with MCP tools"""
    if not anthropic_client or not anthropic_session:
        raise HTTPException(
            status_code=503,
            detail="Anthropic client not available. Check ANTHROPIC_API_KEY."
        )

    print("Starting check")
    ## General response format ## 
    messages = [
        {
            "role": "assistant",
            "content": get_base_prompt()
        },      
        {
            "role": "user",
            "content": query
        }
    ]

    # Get available tools
    response = await anthropic_session.list_tools()
    available_tools = [{
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.inputSchema
    } for tool in response.tools]

    # Tool calling loop
    while True:
        tool_used = False

        # Stream the response
        with anthropic_client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=messages,
            tools=available_tools
        ) as stream:
            assistant_content = []

            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        # Text block started, ready to stream
                        pass

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        # Stream text as it arrives
                        yield event.delta.text

                elif event.type == "content_block_stop":
                    # Block finished
                    pass

            # Get the final message after streaming
            final_message = stream.get_final_message()

            # Check for tool use
            for content in final_message.content:
                assistant_content.append(content)

                if content.type == "tool_use":
                    tool_used = True

                    # Log Cypher queries to stdout
                    # if "cypher" in content.name.lower():
                    print(f"\n{'='*60}")
                    print(f"[CYPHER QUERY] Tool: {content.name}")
                    if "query" in content.input:
                        print(f"Query:\n{content.input['query']}")
                    if "params" in content.input and content.input["params"]:
                        print(f"Parameters: {content.input['params']}")
                    print(f"{'='*60}\n")

                    # Call the MCP tool
                    result = await anthropic_session.call_tool(
                        content.name,
                        content.input
                    )

                    # Append assistant message with tool_use
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content
                    })

                    # Append tool_result as user message
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": content.id,
                            "content": result.content
                        }]
                    })

                    break  # Exit the for loop to make another API call

        if not tool_used:
            break  # No more tools needed, exit while loop
    print("EXITING POST")

async def cleanup():
    """Cleanup on shutdown"""
    global openai_mcp, anthropic_exit_stack

    # Cleanup OpenAI MCP
    try:
        if openai_mcp:
            if hasattr(openai_mcp, 'cleanup'):
                await openai_mcp.cleanup()
            elif hasattr(openai_mcp, 'disconnect'):
                await openai_mcp.disconnect()
    except Exception as e:
        print(f"Error cleaning up OpenAI MCP: {e}")

    # Cleanup Anthropic MCP
    try:
        if anthropic_exit_stack:
            await anthropic_exit_stack.aclose()
    except Exception as e:
        print(f"Error cleaning up Anthropic MCP: {e}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await initialize()

@app.on_event("shutdown")
async def shutdown_event():
    await cleanup()

@app.post("/chat")
async def chat(request: ChatRequest):
    """Handle chat requests - routes to appropriate provider"""
    try:
        user_query = request.message.strip()

        if not user_query:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        # Route based on provider
        if request.provider == "anthropic":
            print(f"\nProcessing with Claude: {user_query}")

            # Stream the response back
            async def generate_anthropic():
                async for chunk in stream_anthropic_query(user_query):
                    yield chunk

            return StreamingResponse(generate_anthropic(), media_type="text/plain")

        else:  # OpenAI
            if not openai_agent:
                raise HTTPException(
                    status_code=503,
                    detail="OpenAI agent not available. Check OPENAI_API_KEY."
                )

            print(f"\nProcessing with GPT: {user_query}")

            # Stream the response back
            async def generate_openai():
                result = await Runner.run(openai_agent, user_query, max_turns=MAX_TURNS)
                # Simulate streaming by yielding in chunks
                text = result.final_output
                chunk_size = 50
                for i in range(0, len(text), chunk_size):
                    yield text[i:i+chunk_size]
                    await asyncio.sleep(0.01)  # Small delay for streaming effect

            return StreamingResponse(generate_openai(), media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "openai_agent_ready": openai_agent is not None,
        "anthropic_client_ready": anthropic_client is not None and anthropic_session is not None,
        "openai_mcp_connected": openai_mcp is not None,
        "anthropic_mcp_connected": anthropic_session is not None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

