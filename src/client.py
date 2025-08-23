from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.client.transports import StdioTransport
from typing import Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
from fastmcp import Client
from pprint import pprint
import nest_asyncio
import asyncio
import os

load_dotenv()

nest_asyncio.apply()

class MCPOpenAIClient:
    """
    Client for interacting with OpenAI models using MCP tools.
    """

    def __init__(self, model: str = "gpt-4o", protocol: str = "stdio"):
        """Initialize the OpenAI MCP client.

        Args:
            model: The OpenAI model to use.
        """
        # Initialize session and client objects
        self.client: Optional[Client] = None
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.transport_protocol =  protocol


    async def connect_to_server(
        self,
        server_script_path: str = "src/server.py",
        cmd: str="uv",
        args: str=["run", "server.py"]
        ):
        """Client connection to an MCP server.

        Args:
            server_script_path: Path to the server script.
        """
        if self.transport_protocol == 'stdio':
            transport = StdioTransport(command="uv", args=args)
            server = 'local'
        elif self.transport_protocol == 'http':
            transport = StreamableHttpTransport(url=os.getenv('SERVER_URL'),auth=None)
            server = os.getenv('SERVER_URL')

        self.client = Client(transport=transport)

        # List available tools
        tools_result = await self.client.list_tools()
        if server == 'local':
            print("\nConnected to server on local machine with tools:")
        else:
            print(f"\nConnected to server at {server} with tools:")
        for tool in tools_result.tools:
            print(f"  - {tool.name}: {tool.description}")
            
        

    async def process_query(
        self,
        query: str,
        server_label: str,
        server_url: str,
        require_approval: str="never"
        ) -> str:
        """Process a query using OpenAI and available MCP tools.

        Args:
            query: The user query.

        Returns:
            The response from OpenAI.
        """

        resp = self.client.responses.create(
            model="gpt-4o",
            tools=[{
                "type": "mcp",
                "server_label": server_label,
                "server_url": server_url,
                "require_approval": require_approval,
            }],
            input=(query)
        )

        return resp


async def main(protocol, openai_model, server_label, server_url, ):
    """
    Example client that calls the `edgar-api-latest-filings` tool to fetch
    an SEC filing in chunks until the full filing is retrieved.

    Workflow:
        - Starts with cursor = 0.
        - Calls the MCP tool with the ticker, form type, and cursor.
        - Prints the first 100 characters of each filing chunk.
        - Increments the cursor until `max_cursor` is reached.

    This pattern prevents exceeding model token limits by streaming
    large SEC filings in safe segments.
    """
    client = MCPOpenAIClient()
    client.connect_to_server()
    async with client:
        answer = client.process_query()
        print('OpenAI:')
        print()
        pprint(answer)
        

if __name__ == "__main__":
    asyncio.run(
        main=main(
            protocol='http',
            openai_model='gpt-4o',
            server_label=os.getenv('SERVER_LABEL'),
            server_url=os.getenv('SERVER_URL'),
            ))
