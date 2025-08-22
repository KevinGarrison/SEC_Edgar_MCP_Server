import asyncio
from fastmcp import Client
import os
import json
from pprint import pprint
from dotenv import load_dotenv

load_dotenv()

client = Client("src/server.py")
ticker = 'MCD'


async def read_resource():
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
    async with client:
        cursor = 0
        while True:    
            result = await client.call_tool("edgar-api-latest-filings", {"company_ticker": ticker, "form":"10-K", "cursor":cursor})
            payload = json.loads(result.content[0].text)
            pprint(payload[f'filing_chunk_{cursor}'][:100])
            cursor+=1
            max_cursor = payload.get('max_cursor')
            if cursor > max_cursor:
                break
        


if __name__ == "__main__":
    asyncio.run(read_resource())