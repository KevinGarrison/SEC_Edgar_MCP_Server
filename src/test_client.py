from fastmcp import Client
from fastmcp.client.auth import OAuth
from fastmcp.client.auth.oauth import FileTokenStorage
import asyncio

async def main():
    # If the token has to be refreshed
    storage = FileTokenStorage(server_url="http://localhost:8080")
    storage.clear()  

    oauth = OAuth(mcp_url="http://localhost:8080")
    async with Client("http://localhost:8080/mcp", auth=oauth) as client:
        assert await client.ping()
        print("ping OK")

if __name__ == "__main__":
    asyncio.run(main())

