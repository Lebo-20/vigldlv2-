import asyncio
import json
from api import vigloo_api

async def check_search():
    res = await vigloo_api.search("Suami Pengkhianat")
    print(json.dumps(res, indent=4))

if __name__ == "__main__":
    asyncio.run(check_search())
