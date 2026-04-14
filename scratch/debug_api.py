import asyncio
import json
from api import vigloo_api

async def test():
    print("Fetching rankings...")
    rank = await vigloo_api.fetch_rank()
    if rank and rank.get("success"):
        payloads = rank.get("data", {}).get("payloads", [])
        if payloads:
            drama = payloads[0].get("program", {})
            print(f"Found Drama: {drama.get('title')} (ID: {drama.get('id')})")
            
            # Fetch detail to get season ID
            detail = await vigloo_api.get_drama_detail(drama.get('id'))
            if detail and detail.get("success"):
                payload = detail.get("data", {}).get("payload", {})
                seasons = payload.get("seasons", [])
                if seasons:
                    season_id = seasons[0].get("id")
                    print(f"Found Season ID: {season_id}")
                    
                    # Fetch episodes
                    eps = await vigloo_api.get_episodes(drama.get('id'), season_id)
                    if eps and eps.get("success"):
                        episodes = eps.get("data", {}).get("payloads", [])
                        if episodes:
                            print(f"Found {len(episodes)} episodes.")
                            print(f"First Episode ID: {episodes[0].get('id')}")
                        else:
                            print("No episodes found.")
                    else:
                        print("Failed to fetch episodes.")
                else:
                    print("No seasons found.")
            else:
                print("Failed to fetch drama detail.")
        else:
            print("No dramas in ranking.")
    else:
        print(f"Ranking API failed: {rank}")

if __name__ == "__main__":
    asyncio.run(test())
