import asyncio
import os
import logging
import httpx
from api import vigloo_api
from config import *

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_drama_episodes(query):
    if query.isdigit():
        drama_id = int(query)
        drama_title = f"ID:{drama_id}"
        print(f"Using Direct Drama ID: {drama_id}")
    else:
        print(f"Searching for drama: {query}...")
        search_res = await vigloo_api.search(query)
        payloads = search_res.get("payloads") or search_res.get("data", {}).get("payloads", [])
        
        if not payloads:
            print("Drama not found.")
            return

        # In Search, the drama object is usually at top level of payload items
        first_item = payloads[0]
        drama = first_item.get("program") if first_item.get("program") else first_item
        
        drama_id = drama.get("id")
        drama_title = drama.get("title")
    
    print(f"Testing Drama: {drama_title} (ID: {drama_id})")

    print(f"Fetching Details...")
    detail_res = await vigloo_api.get_drama_detail(drama_id)
    payload = detail_res.get("drama") or detail_res.get("payload") or detail_res.get("data", {}).get("payload", {})
    
    seasons = payload.get("seasons", [])
    if not seasons:
        print("No seasons found.")
        return

    season = seasons[0]
    season_id = season.get("id")
    print(f"Testing Season 1 (ID: {season_id})")

    print(f"Fetching Episode List...")
    eps_res = await vigloo_api.get_episodes(drama_id, season_id)
    episodes = eps_res.get("payloads") or eps_res.get("data", {}).get("payloads", [])
    
    print(f"--- DETEKSI ERROR EPISODE (Total: {len(episodes)}) ---")
    
    async def check_ep(idx, ep):
        ep_num = ep.get("episodeNumber", idx)
        # Try to get stream link
        stream_res = await vigloo_api.get_stream(season_id, ep_num)
        
        info = stream_res.get("payload")
        if not isinstance(info, dict):
            info = stream_res.get("source")
        
        if not isinstance(info, dict) or not info.get("url"):
            status = "[API_LOCKED]"
        else:
            # Try to fetch m3u8 (simulate download start)
            user_agent = "Vigloo/1.1.0 (com.vigloo.android; build:110; Android 13; Model:SM-G998B)"
            cookie_str = "; ".join([f"{k}={v}" for k, v in info.get("cookies", {}).items()])
            headers = {
                "User-Agent": user_agent,
                "Authorization": f"Bearer {API_TOKEN}",
                "Cookie": cookie_str
            }
            try:
                async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
                    r = await client.get(info.get("url"))
                    if r.status_code == 200:
                        status = "[OK]"
                    elif r.status_code == 403:
                        status = "[FORBIDDEN_403]"
                    else:
                        status = f"[HTTP_{r.status_code}]"
            except Exception as e:
                status = f"[ERROR: {str(e)}]"
        
        print(f"Ep {ep_num}: {status}")
        return (ep_num, status)

    # Run checks sequentially or in small batches to avoid spamming
    results = []
    for i, ep in enumerate(episodes):
        res = await check_ep(i, ep)
        results.append(res)
        await asyncio.sleep(0.5)
    
    print("\n--- SUMMARY ---")
    ok_count = len([r for r in results if r[1] == "✅ OK"])
    print(f"Total: {len(results)}")
    print(f"OK: {ok_count}")
    print(f"Failed: {len(results) - ok_count}")

if __name__ == "__main__":
    import sys
    drama_query = "Suami Pengkhianat"
    if len(sys.argv) > 1:
        drama_query = " ".join(sys.argv[1:])
    asyncio.run(test_drama_episodes(drama_query))
