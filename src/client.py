import asyncio
from fastmcp import Client
import os
from pprint import pprint
from dotenv import load_dotenv

load_dotenv()

client = Client("src/server.py")
ticker = 'AAPL'


async def read_resource():
    async with client:
        result = await client.call_tool("edgar-api-latest-filings", {"company_ticker": ticker, "form":"10-K", "user_agent": os.getenv("USER_AGENT_SEC")})
        pprint(result.content[0])

asyncio.run(read_resource())