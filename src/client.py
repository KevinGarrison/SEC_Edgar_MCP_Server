import asyncio
from fastmcp import Client
import os
import json
from pprint import pprint
from dotenv import load_dotenv

load_dotenv()

client = Client("src/server.py")
ticker = 'MSFT'


async def read_resource():
    async with client:
        cursor = 0
        while True:    
            result = await client.call_tool("edgar-api-latest-filings", {"company_ticker": ticker, "form":"10-K", "user_agent": os.getenv("USER_AGENT_SEC"), "cursor":cursor})
            payload = json.loads(result.content[0].text)
            pprint(payload[f'filing_chunk_{cursor}'][:100])
            cursor+=1
            max_cursor = payload.get('max_cursor')
            if cursor > max_cursor:
                break
        


if __name__ == "__main__":
    asyncio.run(read_resource())