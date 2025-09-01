from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.client.auth.oauth import FileTokenStorage
from openai import AsyncOpenAI, OpenAI
from fastmcp.client.auth import OAuth
from dotenv import load_dotenv
from typing import Optional
from fastmcp import Client
import nest_asyncio
import logging
import asyncio
import os

logging.basicConfig(
    level=logging.INFO,                      
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

load_dotenv()

nest_asyncio.apply()

class MCPOpenAIClient:
    """
    Client for interacting with OpenAI models using MCP tools.
    """

    def __init__(self, model: str = "gpt-5", protocol: str = "streamable-http"):
        """Initialize the OpenAI MCP client.

        Args:
            model: The OpenAI model to use.
        """
        # Initialize session and client objects
        self.client: Optional[Client] = None
        self.openai_client:OpenAI|AsyncOpenAI = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model:str = model
        self.transport_protocol:str =  protocol
        self.server_host:str = None


    async def connect_to_server(
        self,
        url:str=os.getenv('SERVER_URL'),
        ):
        """Client connection to an MCP server.

        Args:
            server_script_path: Path to the server script.
        """
        storage = FileTokenStorage(server_url="http://localhost:8080")
        storage.clear()  

        oauth = OAuth(mcp_url="http://localhost:8080")

        transport = StreamableHttpTransport(url=url,auth=oauth)
        self.server_host = url
        self.client = Client(transport=transport)


    async def process_query(
        self,
        query: str,
        server_label: str,
        server_url: str,
        oauth_token:str,
        require_approval: str="never"
        ) -> str:
        """Process a query using OpenAI and available MCP tools.

        Args:
            query: The user query.

        Returns:
            The response from OpenAI.
        """
        # Tool call doesn't work with workos authkit !!!
        resp = await self.openai_client.responses.create(
            model="gpt-4o",
            tools=[{
                "type": "mcp",
                "server_label": server_label,
                "server_url": server_url,
                "require_approval": require_approval,
                "headers":{"Authorization": f"Bearer {oauth_token}"}
            }],
            input=(query)
        )

        return resp

    def summarize_response(self, resp):
        """Extract the most important parts of the OpenAI Response into a dict."""

        summary = {
            "id": resp,
            "model": resp.model,
            "status": resp.status,
            "tool_choice": resp.tool_choice,
            "tools_declared": [t.server_label for t in resp.tools],
            "tool_calls": [],
            "assistant_output": [],
            "errors": []
        }

        for item in resp.output:
            if item.type == "mcp_list_tools":
                summary["tools_declared"] = [tool.name for tool in item.tools]

            elif item.type == "mcp_call":
                summary["tool_calls"].append({
                    "name": item.name,
                    "arguments": item.arguments,
                    "error": getattr(item, "error", None),
                    "output": getattr(item, "output", None)
                })
                if getattr(item, "error", None):
                    summary["errors"].append(item.error)

            elif item.type == "message":
                text = " ".join(
                    [c.text for c in item.content if getattr(c, "text", None)]
                )
                summary["assistant_output"].append({
                    "role": item.role,
                    "status": item.status,
                    "text": text
                })

        return summary
    

async def main(protocol, openai_model, server_label, server_url):
    """
    Example client that calls the `edgar-api-latest-filings` tool to fetch
    an SEC filing in chunks until the full filing is retrieved.

    Workflow:
        - Starts with cursor = 0.
        - Calls the MCP tool with the ticker, form type, and cursor.
        - Increments the cursor until `max_cursor` is reached.

    This pattern prevents exceeding model token limits by streaming
    large SEC filings in safe segments.
    """
    client = MCPOpenAIClient()

    await client.connect_to_server()

    session = client.client
    async with session as s:
        oauth_token = '...' # Make the request curl -i -X POST \
        # https://cultured-flower-34-staging.authkit.app/oauth2/token \
        # -H "Content-Type: application/x-www-form-urlencoded" \
        # -d "grant_type=client_credentials" \
        # -d "client_id=xxx" \
        # -d "client_secret=xxx" \
        # -d "scope=kevingarrison90@mail.com"
        
        tools_result = await s.list_tools()
        logger.info(f"\nConnected to server at {client.server_host} with tools:")
        for number, tool in enumerate(tools_result):
            logger.info(f"{number}.{tool}")
        answer = await client.process_query(
        query='Find the latest 10-k filing of Microsoft and summarize it. user agent is kevingarrison90@gmail.com',
        server_label=os.getenv('SERVER_LABEL'),
        server_url=os.getenv('SERVER_URL'),
        oauth_token=oauth_token
        )
        logger.info(client.summarize_response(answer))

if __name__ == "__main__":
    asyncio.run(
        main=main(
            protocol='streamable-http',
            openai_model='gpt-4o',
            server_label='sec_edgar_mcp',
            server_url=os.getenv('SERVER_URL'),
            ))

